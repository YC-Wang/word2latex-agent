"""Write an Overleaf-ready LaTeX project structure."""

from __future__ import annotations

from pathlib import Path

from .citations import convert_text_citations, render_bibliography
from .models import CitationRecord, EquationBlock, FigureBlock, ParagraphBlock, Section, TableBlock, slugify

LARGE_TABLE_ROW_THRESHOLD = 5
LARGE_TABLE_COLUMN_THRESHOLD = 4


def write_project(
    output_dir: str | Path,
    sections: list[Section],
    config: dict[str, object],
) -> tuple[Path, list[Path], list[Path], Path, Path]:
    """Write `main.tex` and section files into the output directory."""
    root = Path(output_dir)
    sections_dir = root / "sections"
    tables_dir = root / "tables"
    sections_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    section_files: list[Path] = []
    table_files: list[Path] = []
    all_citations: list[CitationRecord] = []
    for index, section in enumerate(sections, start=1):
        section_path = sections_dir / f"section_{index:02d}_{section.slug}.tex"
        section_text, created_table_files, citations = _render_section(section, index, tables_dir)
        section_path.write_text(section_text, encoding="utf-8")
        section_files.append(section_path)
        table_files.extend(created_table_files)
        all_citations.extend(citations)

    preamble_path = root / "preamble.tex"
    preamble_path.write_text(_render_preamble(), encoding="utf-8")
    bibliography_path = root / "references.bib"
    bibliography_path.write_text(render_bibliography(all_citations), encoding="utf-8")
    main_tex = root / "main.tex"
    main_tex.write_text(_render_main(config, section_files), encoding="utf-8")
    return main_tex, section_files, table_files, bibliography_path, preamble_path


def _render_main(config: dict[str, object], section_files: list[Path]) -> str:
    project = _get_nested_dict(config, "project")
    latex = _get_nested_dict(config, "latex")
    title = _escape_latex(str(project.get("title", "Converted Word Document")))
    author = _escape_latex(str(project.get("author", "word2latex-agent")))
    document_class = _escape_latex(str(latex.get("document_class", "article")))
    include_toc = bool(latex.get("include_toc", True))

    lines = [
        rf"\documentclass{{{document_class}}}",
        r"\input{preamble}",
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
    lines.extend([r"\bibliographystyle{plainnat}", r"\bibliography{references}", r"\end{document}", ""])
    return "\n".join(lines)


def _render_section(
    section: Section, section_index: int, tables_dir: Path
) -> tuple[str, list[Path], list[CitationRecord]]:
    lines = [r"\section{" + _escape_latex(section.title) + "}"]
    created_table_files: list[Path] = []
    citations: list[CitationRecord] = []
    figure_count = 0
    table_count = 0
    equation_count = 0

    for block in section.blocks:
        if isinstance(block, ParagraphBlock):
            rendered_text, paragraph_citations = _render_text_with_citations(block.text)
            citations.extend(paragraph_citations)
            lines.extend([rendered_text, ""])
            continue

        if isinstance(block, FigureBlock):
            figure_count += 1
            label = f"fig:{section.slug}_{slugify(block.caption, fallback=f'figure_{figure_count}')}"
            lines.extend(
                [
                    r"\begin{figure}[htbp]",
                    r"\centering",
                    r"\fbox{\parbox{0.75\linewidth}{\centering Figure placeholder}}",
                    r"\caption{" + _escape_latex(block.caption) + "}",
                    r"\label{" + label + "}",
                    r"\end{figure}",
                    "",
                ]
            )
            continue

        if isinstance(block, TableBlock):
            table_count += 1
            table_label = _build_table_label(section, block, table_count)
            rendered_table = _render_table(block, table_label)
            if _is_large_table(block):
                table_path = tables_dir / f"table_{section_index:02d}_{table_count:02d}_{slugify(block.caption or block.rows[0][0] if block.rows and block.rows[0] else 'table', fallback='table')}.tex"
                table_path.write_text(rendered_table, encoding="utf-8")
                created_table_files.append(table_path)
                include_path = table_path.relative_to(table_path.parent.parent).with_suffix("")
                lines.extend([r"\input{" + include_path.as_posix() + "}", ""])
            else:
                lines.extend([rendered_table.rstrip(), ""])
            continue

        if isinstance(block, EquationBlock):
            equation_count += 1
            equation_label = _build_equation_label(section, block, equation_count)
            lines.extend(_render_equation(block, equation_label))

    return "\n".join(lines).rstrip() + "\n", created_table_files, citations


def _render_table(block: TableBlock, label: str) -> str:
    column_count = max((len(row) for row in block.rows), default=1)
    column_spec = "|" + "|".join("l" for _ in range(column_count)) + "|"
    caption = block.caption or "Table"

    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{" + _escape_latex(caption) + "}",
        r"\label{" + label + "}",
        r"\begin{tabular}{" + column_spec + "}",
        r"\hline",
    ]

    for row in block.rows:
        padded = row + [""] * (column_count - len(row))
        rendered_cells = " & ".join(_escape_latex(cell) for cell in padded)
        lines.extend([rendered_cells + r" \\", r"\hline"])

    lines.extend([r"\end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


def _is_large_table(block: TableBlock) -> bool:
    column_count = max((len(row) for row in block.rows), default=0)
    return len(block.rows) >= LARGE_TABLE_ROW_THRESHOLD or column_count >= LARGE_TABLE_COLUMN_THRESHOLD


def _build_table_label(section: Section, block: TableBlock, table_count: int) -> str:
    source = block.caption or f"{section.title} table {table_count}"
    return f"tab:{section.slug}_{slugify(source, fallback=f'table_{table_count}')}"


def _build_equation_label(section: Section, block: EquationBlock, equation_count: int) -> str:
    source = block.latex or block.source_text or f"{section.title} equation {equation_count}"
    return f"eq:{section.slug}_{slugify(source, fallback=f'equation_{equation_count}')}"


def _render_equation(block: EquationBlock, label: str) -> list[str]:
    lines = [r"\begin{equation}"]
    if block.latex is None:
        lines.append(r"% TODO: Equation could not be converted")
    else:
        lines.append(block.latex)
    lines.extend([r"\label{" + label + "}", r"\end{equation}", ""])
    return lines


def _render_text_with_citations(text: str) -> tuple[str, list[CitationRecord]]:
    converted, citations = convert_text_citations(text)
    parts = converted.split("\\")
    if not parts:
        return "", citations

    rendered = [_escape_latex(parts[0])]
    for part in parts[1:]:
        rendered.append("\\")
        macro, separator, remainder = part.partition("{")
        if separator:
            command = macro + "{"
            body, body_separator, tail = remainder.partition("}")
            if body_separator:
                rendered.append(command + body + "}")
                rendered.append(_escape_latex(tail))
                continue
        rendered.append(_escape_latex(part))
    return "".join(rendered), citations


def _render_preamble() -> str:
    return "\n".join(
        [
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{natbib}",
            r"\usepackage{amsmath}",
            "",
        ]
    )


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
