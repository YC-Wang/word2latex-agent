"""Shared data models for the conversion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ParagraphBlock:
    """Represents a paragraph extracted from a Word document."""

    text: str
    style: str


@dataclass(slots=True)
class Section:
    """Represents a logical section in the generated LaTeX project."""

    title: str
    paragraphs: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        normalized = "".join(
            character.lower() if character.isalnum() else "_"
            for character in self.title.strip()
        )
        compact = "_".join(part for part in normalized.split("_") if part)
        return compact or "section"


@dataclass(slots=True)
class ConversionResult:
    """Describes the generated project output."""

    input_path: Path
    output_dir: Path
    main_tex_path: Path
    section_files: list[Path]
