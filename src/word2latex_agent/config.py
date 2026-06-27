"""Configuration loading for the converter."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "template": "generic_article",
    "workflow": {
        "default_input_file": "input/report.docx",
        "default_output_folder": "output",
        "default_template": "generic_article",
        "dry_run": False,
    },
    "project": {
        "title": "Converted Word Document",
        "author": "word2latex-agent",
        "date": r"\today",
    },
    "latex": {
        "include_toc": True,
    },
    "overleaf": {
        "enabled": False,
        "project_id": "",
        "git_remote": "",
        "branch": "main",
    },
}


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML and merge it over the defaults."""
    merged = deepcopy(DEFAULT_CONFIG)
    if config_path is None:
        return merged

    path = Path(config_path)
    if not path.exists():
        return merged

    loaded = parse_simple_yaml(path.read_text(encoding="utf-8"))
    _merge_dicts(merged, loaded)
    return merged


def _merge_dicts(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_dicts(base[key], value)
            continue
        base[key] = value


def parse_simple_yaml(raw_text: str) -> dict[str, Any]:
    """Parse the repository's small two-level YAML configuration format."""
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, result)]

    for raw_line in raw_text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue

        key, remainder = line.split(":", 1)
        value = remainder.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        current = stack[-1][1]
        if value == "":
            nested: dict[str, Any] = {}
            current[key] = nested
            stack.append((indent, nested))
            continue

        current[key] = _coerce_scalar(value)

    return result


def _coerce_scalar(value: str) -> Any:
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]

    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value
