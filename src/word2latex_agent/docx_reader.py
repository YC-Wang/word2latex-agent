"""Read ordered paragraph and table content from DOCX files."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .models import FigureBlock, ParagraphBlock, Section, SectionContent, TableBlock

WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def read_docx_blocks(path: str | Path) -> list[SectionContent]:
    """Extract ordered paragraph, figure-caption, and table blocks from a DOCX file."""
    source = Path(path)
    with ZipFile(source) as archive:
        document_xml = archive.read("word/document.xml")
        styles_xml = (
            archive.read("word/styles.xml") if "word/styles.xml" in archive.namelist() else None
        )

    style_map = _parse_styles(styles_xml) if styles_xml is not None else {}
    root = ET.fromstring(document_xml)
    body = root.find(".//w:body", WORD_NAMESPACE)
    if body is None:
        return []

    blocks: list[SectionContent] = []
    pending_table_caption: str | None = None

    for child in list(body):
        local_name = _local_name(child.tag)

        if local_name == "p":
            paragraph = _parse_paragraph(child, style_map)
            if paragraph is None:
                continue

            if _is_heading(paragraph.style):
                if pending_table_caption is not None:
                    blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                    pending_table_caption = None
                blocks.append(paragraph)
                continue

            caption_kind = _detect_caption_kind(paragraph.text)
            if caption_kind == "figure":
                if pending_table_caption is not None:
                    blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                    pending_table_caption = None
                blocks.append(FigureBlock(caption=paragraph.text))
                continue
            if caption_kind == "table":
                if pending_table_caption is not None:
                    blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                pending_table_caption = paragraph.text
                continue

            if pending_table_caption is not None:
                blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                pending_table_caption = None
            blocks.append(paragraph)
            continue

        if local_name == "tbl":
            table = _parse_table(child, pending_table_caption)
            pending_table_caption = None
            blocks.append(table)

    if pending_table_caption is not None:
        blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))

    return blocks


def split_into_sections(blocks: list[SectionContent]) -> list[Section]:
    """Group ordered content into sections based on heading paragraphs."""
    sections: list[Section] = []
    current = Section(title="Introduction")

    for block in blocks:
        if isinstance(block, ParagraphBlock) and _is_heading(block.style):
            if current.blocks or current.title != "Introduction":
                sections.append(current)
            current = Section(title=block.text)
            continue

        current.blocks.append(block)

    if current.blocks or not sections:
        sections.append(current)

    return sections


def read_docx_paragraphs(path: str | Path) -> list[ParagraphBlock]:
    """Backward-compatible paragraph-only view of DOCX content."""
    return [block for block in read_docx_blocks(path) if isinstance(block, ParagraphBlock)]


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


def _parse_paragraph(paragraph: ET.Element, style_map: dict[str, str]) -> ParagraphBlock | None:
    text_parts = [node.text or "" for node in paragraph.findall(".//w:t", WORD_NAMESPACE)]
    text = "".join(text_parts).strip()
    if not text:
        return None

    style_id = _find_paragraph_style_id(paragraph)
    style_name = style_map.get(style_id, style_id or "Normal")
    return ParagraphBlock(text=text, style=style_name)


def _parse_table(table: ET.Element, caption: str | None) -> TableBlock:
    rows: list[list[str]] = []
    for row in table.findall("./w:tr", WORD_NAMESPACE):
        cells: list[str] = []
        for cell in row.findall("./w:tc", WORD_NAMESPACE):
            texts = [node.text or "" for node in cell.findall(".//w:t", WORD_NAMESPACE)]
            cell_text = " ".join(part.strip() for part in texts if part.strip())
            cells.append(cell_text)
        if any(cell for cell in cells):
            rows.append(cells)
    return TableBlock(rows=rows, caption=caption)


def _detect_caption_kind(text: str) -> str | None:
    lowered = text.strip().lower()
    if lowered.startswith("figure") or lowered.startswith("fig."):
        return "figure"
    if lowered.startswith("table"):
        return "table"
    return None


def _is_heading(style_name: str) -> bool:
    lowered = style_name.lower()
    return lowered.startswith("heading")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]
