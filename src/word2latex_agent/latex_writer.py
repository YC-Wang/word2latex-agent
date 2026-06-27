"""Write an Overleaf-ready LaTeX project structure."""

from __future__ import annotations

from pathlib import Path

from .citations import build_reference_lookup, convert_text_citations, render_bibliography
from .models import BibliographyEntry, CitationRecord, EquationBlock, FigureBlock, FrontMatter, ImageBlock, ParagraphBlock, Section, TableBlock, slugify
from .template_manager import load_template, render_template

LARGE_TABLE_ROW_THRESHOLD = 5
LARGE_TABLE_COLUMN_THRESHOLD = 4
MAX_FILENAME_STEM_LENGTH = 80
SUPPORTED_LATEX_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
HEADING_COMMANDS = {1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph"}
SPLIT_LEVELS = {"section": 1, "subsection": 2, "none": None}


def write_project(
    output_dir: str | Path,
    sections: list[Section],
    config: dict[str, object],
    bibliography_entries: list[BibliographyEntry] | None = None,
    front_matter: FrontMatter | None = None,
) -> tuple[Path, list[Path], list[Path], list[Path], Path, Path, int]:
    """Write the LaTeX project into the output directory."""
    template_name = str(config.get("template", "generic_article"))
    template_definition = load_template(template_name)
    root = Path(output_dir)
    sections_dir = root / "sections"
    tables_dir = root / "tables"
    figures_dir = root / "figures"
    sections_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    body_content, section_files, table_files, figure_files, citations = _write_body_content(
        sections,
        config,
        sections_dir,
        tables_dir,
        figures_dir,
        bibliography_entries or [],
    )

    preamble_path = root / "preamble.tex"
    preamble_path.write_text(_render_preamble(template_definition), encoding="utf-8")
    bibliography_path = root / "references.bib"
    bibliography_path.write_text(
        render_bibliography(citations, bibliography_entries or []),
        encoding="utf-8",
    )
    main_tex = root / "main.tex"
    main_tex.write_text(
        _render_main(config, body_content, template_definition, front_matter or FrontMatter()),
        encoding="utf-8",
    )
    citation_count = len({citation.key for citation in citations})
    return (
        main_tex,
        section_files,
        table_files,
        figure_files,
        bibliography_path,
        preamble_path,
        citation_count,
    )


def _write_body_content(
    sections: list[Section],
    config: dict[str, object],
    sections_dir: Path,
    tables_dir: Path,
    figures_dir: Path,
    bibliography_entries: list[BibliographyEntry],
) -> tuple[str, list[Path], list[Path], list[Path], list[CitationRecord]]:
    split_level = _resolve_split_level(config)
    reference_lookup = build_reference_lookup(bibliography_entries)
    section_files: list[Path] = []
    table_files: list[Path] = []
    figure_files: list[Path] = []
    citations: list[CitationRecord] = []

    if split_level is None:
        body_text, created_tables, created_figures, created_citations = _render_section_group(
            sections,
            tables_dir,
            figures_dir,
            0,
            reference_lookup,
        )
        table_files.extend(created_tables)
        figure_files.extend(created_figures)
        citations.extend(created_citations)
        return body_text.rstrip() + "\n", section_files, table_files, figure_files, citations

    section_groups = _group_sections_for_output(sections, split_level)
    body_lines: list[str] = []
    for index, group in enumerate(section_groups, start=1):
        if not group:
            continue
        section_path = sections_dir / f"{index:02d}_{group[0].slug}.tex"
        section_text, created_tables, created_figures, created_citations = _render_section_group(
            group,
            tables_dir,
            figures_dir,
            len(figure_files),
            reference_lookup,
        )
        section_path.write_text(section_text, encoding="utf-8")
        section_files.append(section_path)
        table_files.extend(created_tables)
        figure_files.extend(created_figures)
        citations.extend(created_citations)
        include_path = section_path.relative_to(section_path.parent.parent).with_suffix("")
        body_lines.append(r"\input{" + include_path.as_posix() + "}")
    return "\n".join(body_lines).rstrip() + "\n", section_files, table_files, figure_files, citations


def _render_main(
    config: dict[str, object],
    body_content: str,
    template_definition: object,
    front_matter: FrontMatter,
) -> str:
    project = _get_nested_dict(config, "project")
    latex = _get_nested_dict(config, "latex")
    template_metadata = getattr(template_definition, "metadata")
    template_defaults = _get_nested_dict(template_metadata, "defaults")

    title = _escape_latex(_resolve_project_title(project, front_matter))
    author = _escape_latex(_resolve_project_author(project, front_matter))
    date = _render_latex_metadata_value(project.get("date", r"\today"))
    document_class = _escape_latex(
        str(latex.get("document_class", template_defaults.get("document_class", "article")))
    )
    include_toc = bool(latex.get("include_toc", True))
    bibliography_style = str(template_defaults.get("bibliography_style", "plainnat"))

    body_parts: list[str] = []
    if include_toc:
        body_parts.extend([r"\tableofcontents", r"\newpage"])
    body_parts.extend(_render_front_matter_blocks(front_matter))
    if body_content.strip():
        body_parts.append(body_content.rstrip())

    values = {
        "document_class": document_class,
        "title": title,
        "author": author,
        "date": date,
        "body_content": "\n".join(part for part in body_parts if part).rstrip(),
        "bibliography_style": bibliography_style,
        "bibliography_file": "references",
    }
    rendered = _normalize_template_whitespace(
        render_template(template_definition.main_template, values)
    )
    return rendered.rstrip() + "\n"


def _render_front_matter_blocks(front_matter: FrontMatter) -> list[str]:
    blocks: list[str] = []
    if front_matter.affiliations:
        blocks.append(
            r"\begin{center}"
            + "\n"
            + r"\\ ".join(_escape_latex(line) for line in front_matter.affiliations)
            + "\n"
            + r"\end{center}"
        )
    if front_matter.abstract:
        blocks.extend(
            [
                r"\begin{abstract}",
                *(_escape_latex(line) for line in front_matter.abstract),
                r"\end{abstract}",
            ]
        )
    if front_matter.keywords:
        blocks.append(r"\noindent\textbf{Keywords:} " + _escape_latex(front_matter.keywords))
    return blocks


def _render_section_group(
    sections: list[Section],
    tables_dir: Path,
    figures_dir: Path,
    figure_offset: int,
    citation_key_lookup: dict[tuple[str, str], str],
) -> tuple[str, list[Path], list[Path], list[CitationRecord]]:
    lines: list[str] = []
    created_table_files: list[Path] = []
    created_figure_files: list[Path] = []
    citations: list[CitationRecord] = []
    figure_count = 0
    table_count = 0
    equation_count = 0

    for section in sections:
        lines.extend(_render_heading(section))
        for block in section.blocks:
            if isinstance(block, ParagraphBlock):
                rendered_text, paragraph_citations = _render_text_with_citations(
                    block.text,
                    citation_key_lookup,
                )
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

            if isinstance(block, ImageBlock):
                figure_count += 1
                global_figure_index = figure_offset + len(created_figure_files) + 1
                figure_path = figures_dir / f"figure_{global_figure_index:03d}.{block.extension}"
                figure_path.write_bytes(block.bytes_data)
                created_figure_files.append(figure_path)
                caption = block.caption or "TODO: Add caption"
                label_source = block.caption or figure_path.stem
                label = f"fig:{section.slug}_{slugify(label_source, fallback=f'figure_{figure_count}')}"
                if block.extension in SUPPORTED_LATEX_IMAGE_EXTENSIONS:
                    include_path = figure_path.relative_to(figure_path.parent.parent).as_posix()
                    lines.extend(
                        [
                            r"\begin{figure}[htbp]",
                            r"\centering",
                            r"\includegraphics[width=\linewidth]{" + include_path + "}",
                            r"\caption{" + _escape_latex(caption) + "}",
                            r"\label{" + label + "}",
                            r"\end{figure}",
                            "",
                        ]
                    )
                else:
                    lines.extend(
                        [
                            r"\begin{figure}[htbp]",
                            r"\centering",
                            r"\fbox{\parbox{0.75\linewidth}{\centering Unsupported figure format: "
                            + _escape_latex(figure_path.name)
                            + "}}",
                            r"% TODO: Convert unsupported figure format for Overleaf",
                            r"\caption{" + _escape_latex(caption) + "}",
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
                    table_slug = _safe_filename_slug(
                        block.caption or block.rows[0][0] if block.rows and block.rows[0] else "table",
                        fallback="table",
                    )
                    table_path = tables_dir / f"table_{table_count:02d}_{table_slug}.tex"
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

    return "\n".join(lines).rstrip() + "\n", created_table_files, created_figure_files, citations


def _render_heading(section: Section) -> list[str]:
    command = HEADING_COMMANDS.get(section.level, "paragraph")
    heading = rf"\{command}" + "{" + _escape_latex(section.title) + "}"
    return [heading]


def _group_sections_for_output(sections: list[Section], split_level: int) -> list[list[Section]]:
    groups: list[list[Section]] = []
    current_group: list[Section] = []
    for section in sections:
        if section.level <= split_level:
            if current_group:
                groups.append(current_group)
            current_group = [section]
            continue
        if not current_group:
            current_group = [section]
        else:
            current_group.append(section)
    if current_group:
        groups.append(current_group)
    return groups


def _resolve_split_level(config: dict[str, object]) -> int | None:
    section_splitting = _get_nested_dict(config, "section_splitting")
    split_level = str(section_splitting.get("split_level", "section")).strip().lower()
    if split_level not in SPLIT_LEVELS:
        raise ValueError(
            "Invalid section_splitting.split_level. Supported values: section, subsection, none"
        )
    return SPLIT_LEVELS[split_level]


def _resolve_project_title(project: dict[str, object], front_matter: FrontMatter) -> str:
    configured = str(project.get("title", "Converted Word Document"))
    if configured != "Converted Word Document" or not front_matter.title:
        return configured
    return front_matter.title


def _resolve_project_author(project: dict[str, object], front_matter: FrontMatter) -> str:
    configured = str(project.get("author", "word2latex-agent"))
    if configured != "word2latex-agent" or not front_matter.authors:
        return configured
    return r" \\ ".join(front_matter.authors)


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


def _render_text_with_citations(
    text: str,
    citation_key_lookup: dict[tuple[str, str], str],
) -> tuple[str, list[CitationRecord]]:
    converted, citations = convert_text_citations(text, citation_key_lookup)
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


def _render_preamble(template_definition: object) -> str:
    return _normalize_template_whitespace(
        render_template(getattr(template_definition, "preamble_template"), {})
    ).rstrip() + "\n"


def _render_latex_metadata_value(value: object) -> str:
    text = str(value)
    if text.startswith("\\"):
        return text
    return _escape_latex(text)


def _normalize_template_whitespace(text: str) -> str:
    return text.replace("{ ", "{").replace(" }", "}")


def _safe_filename_slug(text: str, fallback: str) -> str:
    slug = slugify(text, fallback=fallback)
    return slug[:MAX_FILENAME_STEM_LENGTH].rstrip("_") or fallback


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
