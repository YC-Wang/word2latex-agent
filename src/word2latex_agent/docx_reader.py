"""Read paragraph content from DOCX files without external parsers."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .models import ParagraphBlock, Section

WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def read_docx_paragraphs(path: str | Path) -> list[ParagraphBlock]:
    """Extract visible paragraph text and style names from a DOCX file."""
    source = Path(path)
    with ZipFile(source) as archive:
        document_xml = archive.read("word/document.xml")
        styles_xml = archive.read("word/styles.xml") if "word/styles.xml" in archive.namelist() else None

    style_map = _parse_styles(styles_xml) if styles_xml is not None else {}
    root = ET.fromstring(document_xml)
    paragraphs: list[ParagraphBlock] = []

    for paragraph in root.findall(".//w:body/w:p", WORD_NAMESPACE):
        text_parts = [node.text or "" for node in paragraph.findall(".//w:t", WORD_NAMESPACE)]
        text = "".join(text_parts).strip()
        if not text:
            continue

        style_id = _find_paragraph_style_id(paragraph)
        style_name = style_map.get(style_id, style_id or "Normal")
        paragraphs.append(ParagraphBlock(text=text, style=style_name))

    return paragraphs


def split_into_sections(paragraphs: list[ParagraphBlock]) -> list[Section]:
    """Group paragraphs into sections based on heading styles."""
    sections: list[Section] = []
    current = Section(title="Introduction")

    for block in paragraphs:
        if _is_heading(block.style):
            if current.paragraphs or current.title != "Introduction":
                sections.append(current)
            current = Section(title=block.text)
            continue

        current.paragraphs.append(block.text)

    if current.paragraphs or not sections:
        sections.append(current)

    return sections


def _parse_styles(styles_xml: bytes) -> dict[str, str]:
    root = ET.fromstring(styles_xml)
    style_map: dict[str, str] = {}
    for style in root.findall(".//w:style", WORD_NAMESPACE):
        style_id = style.attrib.get(f"{{{WORD_NAMESPACE['w']}}}styleId")
        name = style.find("w:name", WORD_NAMESPACE)
        if style_id and name is not None:
            style_map[style_id] = name.attrib.get(f"{{{WORD_NAMESPACE['w']}}}val", style_id)
    return style_map


def _find_paragraph_style_id(paragraph: ET.Element) -> str | None:
    style = paragraph.find("./w:pPr/w:pStyle", WORD_NAMESPACE)
    if style is None:
        return None
    return style.attrib.get(f"{{{WORD_NAMESPACE['w']}}}val")


def _is_heading(style_name: str) -> bool:
    lowered = style_name.lower()
    return lowered.startswith("heading")
