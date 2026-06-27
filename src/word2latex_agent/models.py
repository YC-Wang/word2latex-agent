"""Shared data models for the conversion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias


@dataclass(slots=True)
class ParagraphBlock:
    """Represents a paragraph extracted from a Word document."""

    text: str
    style: str


@dataclass(slots=True)
class FigureBlock:
    """Represents a detected figure caption placeholder."""

    caption: str


@dataclass(slots=True)
class TableBlock:
    """Represents a table extracted from a Word document."""

    rows: list[list[str]]
    caption: str | None = None


@dataclass(slots=True)
class EquationBlock:
    """Represents a displayed equation extracted from OMML."""

    latex: str | None
    source_text: str


@dataclass(slots=True)
class ImageBlock:
    """Represents an embedded image extracted from the DOCX package."""

    bytes_data: bytes
    extension: str
    source_name: str
    caption: str | None = None


SectionContent: TypeAlias = ParagraphBlock | FigureBlock | TableBlock | EquationBlock | ImageBlock


@dataclass(frozen=True, slots=True)
class CitationRecord:
    """Represents a detected citation and its placeholder bibliography entry."""

    key: str
    author_token: str
    year: str


@dataclass(slots=True)
class Section:
    """Represents a logical section in the generated LaTeX project."""

    title: str
    blocks: list[SectionContent] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return slugify(self.title, fallback="section")


def slugify(text: str, fallback: str) -> str:
    """Convert arbitrary text into a deterministic ASCII-ish slug."""
    normalized = "".join(
        character.lower() if character.isalnum() else "_"
        for character in text.strip()
    )
    compact = "_".join(part for part in normalized.split("_") if part)
    return compact or fallback


@dataclass(slots=True)
class ConversionResult:
    """Describes the generated project output."""

    input_path: Path
    output_dir: Path
    main_tex_path: Path
    section_files: list[Path]
    table_files: list[Path]
    figure_files: list[Path]
    bibliography_path: Path
    preamble_path: Path


@dataclass(frozen=True, slots=True)
class QAIssue:
    """Represents a single QA finding for a generated project."""

    severity: str
    message: str
    source: str


@dataclass(slots=True)
class QAResult:
    """Represents the full QA outcome for a generated project."""

    project_dir: Path
    report_path: Path
    status: str
    failures: list[QAIssue]
    warnings: list[QAIssue]
