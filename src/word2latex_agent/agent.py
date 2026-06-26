"""High-level conversion service."""

from __future__ import annotations

from pathlib import Path

from .config import load_config
from .docx_reader import read_docx_paragraphs, split_into_sections
from .latex_writer import write_project
from .models import ConversionResult


class WordToLatexAgent:
    """Convert DOCX files into an Overleaf-ready LaTeX project."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config = load_config(config_path)

    def convert(self, input_path: str | Path, output_dir: str | Path) -> ConversionResult:
        source = Path(input_path)
        destination = Path(output_dir)

        paragraphs = read_docx_paragraphs(source)
        sections = split_into_sections(paragraphs)
        main_tex_path, section_files = write_project(destination, sections, self.config)

        return ConversionResult(
            input_path=source,
            output_dir=destination,
            main_tex_path=main_tex_path,
            section_files=section_files,
        )
