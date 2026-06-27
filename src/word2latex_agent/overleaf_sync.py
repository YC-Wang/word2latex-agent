"""Overleaf Git synchronization helpers."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Represents the outcome of an Overleaf sync operation."""

    project_dir: Path
    dry_run: bool
    commands: list[list[str]]
    message: str


class OverleafSyncError(RuntimeError):
    """Raised when Overleaf synchronization cannot proceed safely."""


def sync_to_overleaf(
    project_dir: str | Path,
    config: dict[str, Any],
    dry_run: bool = False,
) -> SyncResult:
    """Push a generated LaTeX project to Overleaf via Git."""
    root = Path(project_dir)
    if not root.exists() or not root.is_dir():
        raise OverleafSyncError(f"Project directory does not exist: {root}")

    main_tex = root / "main.tex"
    if not main_tex.exists():
        raise OverleafSyncError(f"main.tex is missing from project directory: {main_tex}")

    overleaf = config.get("overleaf", {})
    if not isinstance(overleaf, dict):
        overleaf = {}
    git_remote = str(overleaf.get("git_remote", "")).strip()
    branch = str(overleaf.get("branch", "main")).strip() or "main"
    if not git_remote:
        raise OverleafSyncError("Overleaf git_remote is missing in config.yaml")

    commands: list[list[str]] = []
    git_dir = root / ".git"
    repo_exists = git_dir.exists()

    if not repo_exists:
        commands.append(["git", "init"])

    if repo_exists and _git_status(root):
        raise OverleafSyncError(
            "Uncommitted changes exist in the output project. Commit or clean them before syncing."
        )

    remote_state = _get_remote_state(root) if repo_exists else None
    if remote_state is not None and remote_state != git_remote:
        raise OverleafSyncError(
            f"Remote 'overleaf' already exists with a different URL: {remote_state}"
        )
    if remote_state is None:
        commands.append(["git", "remote", "add", "overleaf", git_remote])

    commands.extend(
        [
            ["git", "add", "."],
            ["git", "commit", "-m", "Sync generated Overleaf project"],
            ["git", "push", "overleaf", f"HEAD:{branch}"],
        ]
    )

    if dry_run:
        return SyncResult(
            project_dir=root,
            dry_run=True,
            commands=commands,
            message="Dry run only. No Git commands were executed.",
        )

    executed_commands: list[list[str]] = []
    for command in commands:
        if command[:2] == ["git", "remote"] and repo_exists is False:
            pass
        try:
            _run_git(command, root)
            executed_commands.append(command)
        except subprocess.CalledProcessError as error:
            stderr = (error.stderr or "").strip()
            stdout = (error.stdout or "").strip()
            details = stderr or stdout or str(error)
            if command[:2] == ["git", "push"] and _looks_like_auth_failure(details):
                raise OverleafSyncError(
                    f"Overleaf authentication failed while pushing to {git_remote}: {details}"
                ) from error
            if command[:2] == ["git", "commit"] and "nothing to commit" in details.lower():
                executed_commands.append(command)
                continue
            raise OverleafSyncError(f"Git command failed: {' '.join(command)}\n{details}") from error

    return SyncResult(
        project_dir=root,
        dry_run=False,
        commands=executed_commands,
        message=f"Pushed project to Overleaf remote '{git_remote}' on branch '{branch}'.",
    )


def _git_status(project_dir: Path) -> list[str]:
    result = _run_git(["git", "status", "--porcelain"], project_dir)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines


def _get_remote_state(project_dir: Path) -> str | None:
    try:
        result = _run_git(["git", "remote", "get-url", "overleaf"], project_dir)
    except subprocess.CalledProcessError:
        return None
    return result.stdout.strip() or None


def _run_git(command: list[str], project_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )


def _looks_like_auth_failure(details: str) -> bool:
    lowered = details.lower()
    return "authentication" in lowered or "permission denied" in lowered or "fatal: could not read" in lowered
