"""High-level conversion service."""

from __future__ import annotations

from pathlib import Path

from .citations import parse_reference_entries
from .config import load_config
from .docx_reader import extract_front_matter, extract_reference_section, read_docx_blocks, split_into_sections
from .latex_writer import write_project
from .models import ConversionResult, FigureBlock, ImageBlock, TableBlock


class WordToLatexAgent:
    """Convert DOCX files into an Overleaf-ready LaTeX project."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        template_name: str | None = None,
    ) -> None:
        self.config = load_config(config_path)
        workflow = self.config.get("workflow", {})
        if isinstance(workflow, dict):
            default_template = workflow.get("default_template")
            if default_template and "template" not in self.config:
                self.config["template"] = default_template
        if template_name is not None:
            self.config["template"] = template_name

    def convert(self, input_path: str | Path, output_dir: str | Path) -> ConversionResult:
        source = Path(input_path)
        destination = Path(output_dir)

        blocks = read_docx_blocks(source)
        front_matter, body_blocks = extract_front_matter(blocks)
        sections, reference_lines = extract_reference_section(split_into_sections(body_blocks))
        bibliography_entries = parse_reference_entries(reference_lines)
        (
            main_tex_path,
            section_files,
            table_files,
            figure_files,
            bibliography_path,
            preamble_path,
            citation_count,
        ) = write_project(
            destination,
            sections,
            self.config,
            bibliography_entries,
            front_matter,
        )

        table_count = sum(isinstance(block, TableBlock) for block in blocks)
        figure_count = sum(
            isinstance(block, (FigureBlock, ImageBlock)) for block in blocks
        )

        return ConversionResult(
            input_path=source,
            output_dir=destination,
            main_tex_path=main_tex_path,
            section_files=section_files,
            table_files=table_files,
            figure_files=figure_files,
            bibliography_path=bibliography_path,
            preamble_path=preamble_path,
            template_name=str(self.config.get("template", "generic_article")),
            section_count=sum(1 for section in sections if section.level == 1),
            table_count=table_count,
            figure_count=figure_count,
            citation_count=citation_count,
        )
