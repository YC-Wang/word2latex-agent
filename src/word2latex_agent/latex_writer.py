"""Write an Overleaf-ready LaTeX project structure."""

from __future__ import annotations

from pathlib import Path

from .models import Section


def write_project(
    output_dir: str | Path,
    sections: list[Section],
    config: dict[str, object],
) -> tuple[Path, list[Path]]:
    """Write `main.tex` and section files into the output directory."""
    root = Path(output_dir)
    sections_dir = root / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    section_files: list[Path] = []
    for index, section in enumerate(sections, start=1):
        section_path = sections_dir / f"section_{index:02d}_{section.slug}.tex"
        section_path.write_text(_render_section(section), encoding="utf-8")
        section_files.append(section_path)

    main_tex = root / "main.tex"
    main_tex.write_text(_render_main(config, section_files), encoding="utf-8")
    return main_tex, section_files


def _render_main(config: dict[str, object], section_files: list[Path]) -> str:
    project = _get_nested_dict(config, "project")
    latex = _get_nested_dict(config, "latex")
    title = _escape_latex(str(project.get("title", "Converted Word Document")))
    author = _escape_latex(str(project.get("author", "word2latex-agent")))
    document_class = _escape_latex(str(latex.get("document_class", "article")))
    include_toc = bool(latex.get("include_toc", True))

    lines = [
        rf"\documentclass{{{document_class}}}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\title{" + title + "}",
        r"\author{" + author + "}",
        r"\begin{document}",
        r"\maketitle",
    ]
    if include_toc:
        lines.extend([r"\tableofcontents", r"\newpage"])
    for section_file in section_files:
        include_path = section_file.relative_to(section_file.parent.parent).with_suffix("")
        lines.append(r"\input{" + include_path.as_posix() + "}")
    lines.extend([r"\end{document}", ""])
    return "\n".join(lines)


def _render_section(section: Section) -> str:
    lines = [r"\section{" + _escape_latex(section.title) + "}"]
    for paragraph in section.paragraphs:
        lines.extend([_escape_latex(paragraph), ""])
    return "\n".join(lines).rstrip() + "\n"


def _escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in text)


def _get_nested_dict(config: dict[str, object], key: str) -> dict[str, object]:
    value = config.get(key, {})
    if isinstance(value, dict):
        return value
    return {}
