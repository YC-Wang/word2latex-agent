"""Quality-assurance checks for generated LaTeX projects."""

from __future__ import annotations

import re
from pathlib import Path

from .models import QAIssue, QAResult

INPUT_PATTERN = re.compile(r"\\input\{([^}]+)\}")
INCLUDEGRAPHICS_PATTERN = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
LABEL_PATTERN = re.compile(r"\\label\{([^}]+)\}")
REF_PATTERN = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")
CITE_PATTERN = re.compile(r"\\cite(?:p|t)\{([^}]+)\}")
BIB_ENTRY_PATTERN = re.compile(r"@\w+\{([^,]+),")
TODO_PATTERN = re.compile(r"TODO")
SUPPORTED_FIGURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


def check_project(project_dir: str | Path) -> QAResult:
    """Validate a generated LaTeX project and emit a markdown report."""
    root = Path(project_dir)
    report_path = root / "QA_REPORT.md"
    failures: list[QAIssue] = []
    warnings: list[QAIssue] = []

    required_files = {
        "main.tex": root / "main.tex",
        "preamble.tex": root / "preamble.tex",
        "references.bib": root / "references.bib",
    }
    for label, path in required_files.items():
        if not path.exists():
            failures.append(QAIssue("FAIL", f"Required file is missing: {label}", str(path)))

    existing_tex_files = sorted(root.rglob("*.tex")) if root.exists() else []
    tex_contents = {
        path: path.read_text(encoding="utf-8")
        for path in existing_tex_files
        if path.exists()
    }

    labels: dict[str, list[Path]] = {}
    refs: list[tuple[str, Path]] = []
    citations: dict[str, list[Path]] = {}

    for tex_path, content in tex_contents.items():
        for relative_input in INPUT_PATTERN.findall(content):
            resolved = _resolve_input_path(root, relative_input)
            if not resolved.exists():
                failures.append(
                    QAIssue("FAIL", f"Referenced input file is missing: {relative_input}", str(tex_path))
                )
        for graphic_path in INCLUDEGRAPHICS_PATTERN.findall(content):
            resolved = (root / graphic_path).resolve()
            if not resolved.exists():
                failures.append(
                    QAIssue("FAIL", f"Referenced figure file is missing: {graphic_path}", str(tex_path))
                )
        for label in LABEL_PATTERN.findall(content):
            labels.setdefault(label, []).append(tex_path)
        for ref in REF_PATTERN.findall(content):
            refs.append((ref, tex_path))
        for cite_block in CITE_PATTERN.findall(content):
            for key in [part.strip() for part in cite_block.split(",") if part.strip()]:
                citations.setdefault(key, []).append(tex_path)
        if TODO_PATTERN.search(content):
            warnings.append(QAIssue("WARN", "TODO placeholder found in LaTeX source", str(tex_path)))

    for label, locations in labels.items():
        if len(locations) > 1:
            failures.append(
                QAIssue(
                    "FAIL",
                    f"Duplicate label detected: {label}",
                    ", ".join(str(path) for path in locations),
                )
            )

    existing_labels = set(labels)
    for ref, tex_path in refs:
        if ref not in existing_labels:
            failures.append(QAIssue("FAIL", f"Missing label for reference: {ref}", str(tex_path)))

    bibliography_path = required_files["references.bib"]
    bib_keys: set[str] = set()
    if bibliography_path.exists():
        bibliography_content = bibliography_path.read_text(encoding="utf-8")
        bib_keys = set(BIB_ENTRY_PATTERN.findall(bibliography_content))
        if TODO_PATTERN.search(bibliography_content):
            warnings.append(
                QAIssue("WARN", "TODO placeholder found in bibliography", str(bibliography_path))
            )

    for citation_key, locations in citations.items():
        if citation_key not in bib_keys:
            failures.append(
                QAIssue(
                    "FAIL",
                    f"Missing BibTeX entry for citation key: {citation_key}",
                    ", ".join(str(path) for path in locations),
                )
            )

    unused_keys = sorted(bib_keys - set(citations))
    for key in unused_keys:
        warnings.append(
            QAIssue("WARN", f"Unused BibTeX entry: {key}", str(bibliography_path))
        )

    figures_dir = root / "figures"
    if figures_dir.exists():
        for figure_path in sorted(figures_dir.iterdir()):
            if figure_path.is_file() and figure_path.suffix.lower() not in SUPPORTED_FIGURE_EXTENSIONS:
                warnings.append(
                    QAIssue(
                        "WARN",
                        f"Unsupported figure format for Overleaf: {figure_path.name}",
                        str(figure_path),
                    )
                )

    status = _compute_status(failures, warnings)
    report_path.write_text(_render_report(root, status, failures, warnings), encoding="utf-8")
    return QAResult(
        project_dir=root,
        report_path=report_path,
        status=status,
        failures=failures,
        warnings=warnings,
    )


def _resolve_input_path(project_root: Path, relative_input: str) -> Path:
    candidate = project_root / relative_input
    if candidate.suffix == "":
        candidate = candidate.with_suffix(".tex")
    return candidate.resolve()


def _compute_status(failures: list[QAIssue], warnings: list[QAIssue]) -> str:
    if failures:
        return "FAIL"
    if warnings:
        return "WARN"
    return "PASS"


def _render_report(
    project_dir: Path, status: str, failures: list[QAIssue], warnings: list[QAIssue]
) -> str:
    lines = [
        "# QA Report",
        "",
        f"- Project: `{project_dir}`",
        f"- Status: `{status}`",
        f"- Failures: `{len(failures)}`",
        f"- Warnings: `{len(warnings)}`",
        "",
    ]
    lines.extend(_render_issue_section("Failures", failures))
    lines.extend(_render_issue_section("Warnings", warnings))
    return "\n".join(lines).rstrip() + "\n"


def _render_issue_section(title: str, issues: list[QAIssue]) -> list[str]:
    lines = [f"## {title}", ""]
    if not issues:
        lines.append("- None")
        lines.append("")
        return lines
    for issue in issues:
        lines.append(f"- [{issue.severity}] {issue.message} ({issue.source})")
    lines.append("")
    return lines
