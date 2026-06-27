"""Read ordered paragraph, table, equation, and image content from DOCX files."""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .models import EquationBlock, FigureBlock, FrontMatter, ImageBlock, ParagraphBlock, Section, SectionContent, TableBlock

REFERENCE_SECTION_TITLES = {"reference", "references", "bibliography"}
TEXT_HEADING_TITLES = {
    "abstract",
    "acknowledgments",
    "acknowledgements",
    "reference",
    "references",
    "bibliography",
    "tables",
    "figures",
    "supplementary",
}
NUMBERED_HEADING_PATTERN = r"^\d+(?:\.\d+)*\.?\s+\S+"
FIGURE_CAPTION_PATTERN = r"^(?:figure|fig\.)\s+[a-z0-9]+(?:[\s.:].*)?$"
TABLE_CAPTION_PATTERN = r"^table\s+[a-z0-9]+(?:[\s.:].*)?$"
BIBLIOGRAPHY_STYLE_TOKEN = "bibliography"
TITLE_HEADING_TITLES = {"abstract", "acknowledgments", "acknowledgements", "tables", "figures", "supplementary"}
KEYWORDS_PREFIXES = ("keywords:", "keyword:", "key words:")
AFFILIATION_HINTS = (
    "university",
    "institute",
    "department",
    "administration",
    "center",
    "centre",
    "laboratory",
    "academy",
    "academia",
    "school",
)

WORD_NAMESPACE = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def read_docx_blocks(path: str | Path) -> list[SectionContent]:
    """Extract ordered paragraph, figure, table, equation, and image blocks from a DOCX file."""
    source = Path(path)
    with ZipFile(source) as archive:
        document_xml = archive.read("word/document.xml")
        styles_xml = (
            archive.read("word/styles.xml") if "word/styles.xml" in archive.namelist() else None
        )
        relationship_map = _parse_relationships(
            archive.read("word/_rels/document.xml.rels")
        ) if "word/_rels/document.xml.rels" in archive.namelist() else {}
        media_map = _load_related_media(archive, relationship_map)

    style_map = _parse_styles(styles_xml) if styles_xml is not None else {}
    root = ET.fromstring(document_xml)
    body = root.find(".//w:body", WORD_NAMESPACE)
    if body is None:
        return []

    blocks: list[SectionContent] = []
    pending_table_caption: str | None = None
    pending_figure_caption: str | None = None

    for child in list(body):
        local_name = _local_name(child.tag)

        if local_name == "p":
            paragraph_blocks = _parse_paragraph_blocks(child, style_map, media_map)
            if not paragraph_blocks:
                continue

            if len(paragraph_blocks) == 1 and isinstance(paragraph_blocks[0], ParagraphBlock):
                paragraph = paragraph_blocks[0]
            else:
                if pending_table_caption is not None:
                    blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                    pending_table_caption = None
                for block in paragraph_blocks:
                    if isinstance(block, ImageBlock) and pending_figure_caption is not None:
                        block.caption = pending_figure_caption
                        pending_figure_caption = None
                    blocks.append(block)
                _flush_pending_figure_caption(blocks, pending_figure_caption)
                pending_figure_caption = None
                continue

            if _is_heading_paragraph(paragraph):
                if pending_table_caption is not None:
                    blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                    pending_table_caption = None
                _flush_pending_figure_caption(blocks, pending_figure_caption)
                pending_figure_caption = None
                blocks.append(paragraph)
                continue

            caption_kind = _detect_caption_kind(paragraph.text)
            if caption_kind == "figure":
                if pending_table_caption is not None:
                    blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                    pending_table_caption = None
                if _attach_caption_to_previous_image(blocks, paragraph.text):
                    pending_figure_caption = None
                else:
                    pending_figure_caption = paragraph.text
                continue
            if caption_kind == "table":
                if pending_table_caption is not None:
                    blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                _flush_pending_figure_caption(blocks, pending_figure_caption)
                pending_figure_caption = None
                pending_table_caption = paragraph.text
                continue

            if pending_table_caption is not None:
                blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
                pending_table_caption = None
            _flush_pending_figure_caption(blocks, pending_figure_caption)
            pending_figure_caption = None
            blocks.append(paragraph)
            continue

        if local_name == "tbl":
            table = _parse_table(child, pending_table_caption)
            pending_table_caption = None
            _flush_pending_figure_caption(blocks, pending_figure_caption)
            pending_figure_caption = None
            blocks.append(table)

    if pending_table_caption is not None:
        blocks.append(ParagraphBlock(text=pending_table_caption, style="Normal"))
    _flush_pending_figure_caption(blocks, pending_figure_caption)

    return blocks


def split_into_sections(blocks: list[SectionContent]) -> list[Section]:
    """Group ordered content into sections based on detected heading levels."""
    sections: list[Section] = []
    current = Section(title="Introduction", level=1)

    for block in blocks:
        if isinstance(block, ParagraphBlock):
            heading_level = _detect_heading_level(block)
        else:
            heading_level = None
        if heading_level is not None:
            if current.blocks or current.title != "Introduction":
                sections.append(current)
            current = Section(title=_clean_heading_title(block.text), level=heading_level)
            continue

        current.blocks.append(block)

    if current.blocks or not sections:
        sections.append(current)

    return sections


def extract_reference_section(sections: list[Section]) -> tuple[list[Section], list[str]]:
    """Split off References/Bibliography content when present."""
    if not sections:
        return [], []

    reference_lines: list[str] = []
    content_sections: list[Section] = []

    for section in sections:
        if _is_reference_section_title(section.title):
            reference_lines.extend(_collect_reference_lines(section.blocks))
            continue

        filtered_blocks: list[SectionContent] = []
        for block in section.blocks:
            if isinstance(block, ParagraphBlock) and _is_bibliography_paragraph(block):
                normalized = _normalize_reference_line(block.text)
                if normalized:
                    reference_lines.append(normalized)
                continue
            filtered_blocks.append(block)
        if filtered_blocks or not content_sections:
            content_sections.append(Section(title=section.title, level=section.level, blocks=filtered_blocks))

    if not content_sections:
        content_sections = [Section(title="Introduction")]
    return content_sections, _deduplicate_preserving_order(reference_lines)


def extract_front_matter(blocks: list[SectionContent]) -> tuple[FrontMatter, list[SectionContent]]:
    """Detect title/authors/affiliations/abstract/keywords ahead of the body."""
    front_matter = FrontMatter()
    body_start = 0
    preamble_blocks: list[ParagraphBlock] = []

    for index, block in enumerate(blocks):
        if not isinstance(block, ParagraphBlock):
            break
        if _is_body_start_paragraph(block):
            body_start = index
            break
        preamble_blocks.append(block)
    else:
        body_start = len(preamble_blocks)

    leading_index = 0
    if preamble_blocks:
        first_text = preamble_blocks[0].text.strip()
        if first_text and first_text.lower() not in TEXT_HEADING_TITLES:
            front_matter.title = first_text
            leading_index = 1

    abstract_index = _find_special_heading_index(preamble_blocks, "abstract")
    keywords_index = _find_keywords_index(preamble_blocks)

    metadata_end = len(preamble_blocks)
    if abstract_index is not None:
        metadata_end = min(metadata_end, abstract_index)
    if keywords_index is not None:
        metadata_end = min(metadata_end, keywords_index)

    metadata_blocks = preamble_blocks[leading_index:metadata_end]
    front_matter.authors, front_matter.affiliations = _split_author_metadata(metadata_blocks)

    if abstract_index is not None:
        abstract_end = len(preamble_blocks)
        if keywords_index is not None and keywords_index > abstract_index:
            abstract_end = keywords_index
        for block in preamble_blocks[abstract_index + 1 : abstract_end]:
            text = block.text.strip()
            if text:
                front_matter.abstract.append(text)

    if keywords_index is not None:
        front_matter.keywords = _extract_keywords(preamble_blocks[keywords_index].text)

    remaining_blocks = blocks[body_start:]
    if abstract_index is not None or keywords_index is not None:
        remove_indexes = set(range(0, body_start))
        remaining_blocks = [block for index, block in enumerate(blocks) if index not in remove_indexes]

    return front_matter, remaining_blocks


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


def _parse_paragraph_blocks(
    paragraph: ET.Element, style_map: dict[str, str], media_map: dict[str, tuple[str, bytes]]
) -> list[SectionContent]:
    style_id = _find_paragraph_style_id(paragraph)
    style_name = style_map.get(style_id, style_id or "Normal")
    blocks: list[SectionContent] = []
    buffered_text: list[str] = []

    for child in list(paragraph):
        local_name = _local_name(child.tag)
        if local_name == "r":
            for run_child in list(child):
                run_local_name = _local_name(run_child.tag)
                if run_local_name == "t":
                    buffered_text.append(run_child.text or "")
                    continue
                if run_local_name == "drawing":
                    _flush_text_block(buffered_text, style_name, blocks)
                    image_block = _parse_image_block(run_child, media_map)
                    if image_block is not None:
                        blocks.append(image_block)
                    continue
                buffered_text.extend(
                    node.text or "" for node in run_child.findall(".//w:t", WORD_NAMESPACE)
                )
            continue
        if local_name in {"oMath", "oMathPara"}:
            _flush_text_block(buffered_text, style_name, blocks)
            blocks.append(_parse_equation_block(child))
            continue

        buffered_text.extend(node.text or "" for node in child.findall(".//w:t", WORD_NAMESPACE))

    _flush_text_block(buffered_text, style_name, blocks)
    return blocks


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
    if lowered in TEXT_HEADING_TITLES:
        return None
    if _matches_text_pattern(lowered, FIGURE_CAPTION_PATTERN):
        return "figure"
    if _matches_text_pattern(lowered, TABLE_CAPTION_PATTERN):
        return "table"
    return None


def _parse_relationships(relationships_xml: bytes) -> dict[str, str]:
    root = ET.fromstring(relationships_xml)
    relationship_map: dict[str, str] = {}
    for relationship in root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
        relationship_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if relationship_id and target:
            relationship_map[relationship_id] = target
    return relationship_map


def _load_related_media(
    archive: ZipFile, relationship_map: dict[str, str]
) -> dict[str, tuple[str, bytes]]:
    media_map: dict[str, tuple[str, bytes]] = {}
    for relationship_id, target in relationship_map.items():
        normalized = target.replace("\\", "/")
        if not normalized.startswith("media/"):
            continue
        package_path = "word/" + normalized
        if package_path not in archive.namelist():
            continue
        media_map[relationship_id] = (Path(normalized).name, archive.read(package_path))
    return media_map


def _parse_image_block(
    drawing: ET.Element, media_map: dict[str, tuple[str, bytes]]
) -> ImageBlock | None:
    blip = drawing.find(".//a:blip", WORD_NAMESPACE)
    if blip is None:
        return None
    relationship_id = blip.attrib.get(f"{{{WORD_NAMESPACE['r']}}}embed")
    if relationship_id is None or relationship_id not in media_map:
        return None
    source_name, bytes_data = media_map[relationship_id]
    extension = Path(source_name).suffix.lower().lstrip(".")
    if extension not in {"png", "jpg", "jpeg"}:
        extension = extension or "png"
    return ImageBlock(bytes_data=bytes_data, extension=extension, source_name=source_name)


def _parse_equation_block(node: ET.Element) -> EquationBlock:
    math_node = node.find(".//m:oMath", WORD_NAMESPACE) if _local_name(node.tag) == "oMathPara" else node
    if math_node is None:
        source_text = "".join(text or "" for text in node.itertext()).strip()
        return EquationBlock(latex=None, source_text=source_text or "equation")

    latex = _convert_omml_to_latex(math_node)
    source_text = "".join(text or "" for text in math_node.itertext()).strip()
    return EquationBlock(latex=latex, source_text=source_text or "equation")


def _convert_omml_to_latex(node: ET.Element) -> str | None:
    parts: list[str] = []
    for child in list(node):
        converted = _convert_math_element(child)
        if converted is None:
            return None
        parts.append(converted)
    return "".join(parts).strip() or None


def _convert_math_element(node: ET.Element) -> str | None:
    local_name = _local_name(node.tag)
    if local_name == "r":
        return "".join(text_node.text or "" for text_node in node.findall(".//m:t", WORD_NAMESPACE))
    if local_name == "f":
        numerator = node.find("./m:num/*", WORD_NAMESPACE)
        denominator = node.find("./m:den/*", WORD_NAMESPACE)
        if numerator is None or denominator is None:
            return None
        numerator_text = _convert_omml_to_latex(numerator) if _local_name(numerator.tag) == "oMath" else _convert_math_element(numerator)
        denominator_text = _convert_omml_to_latex(denominator) if _local_name(denominator.tag) == "oMath" else _convert_math_element(denominator)
        if numerator_text is None or denominator_text is None:
            return None
        return rf"\frac{{{numerator_text}}}{{{denominator_text}}}"
    if local_name == "sSup":
        base = node.find("./m:e/*", WORD_NAMESPACE)
        superscript = node.find("./m:sup/*", WORD_NAMESPACE)
        if base is None or superscript is None:
            return None
        base_text = _convert_omml_to_latex(base) if _local_name(base.tag) == "oMath" else _convert_math_element(base)
        superscript_text = _convert_omml_to_latex(superscript) if _local_name(superscript.tag) == "oMath" else _convert_math_element(superscript)
        if base_text is None or superscript_text is None:
            return None
        return rf"{base_text}^{{{superscript_text}}}"
    if local_name == "sSub":
        base = node.find("./m:e/*", WORD_NAMESPACE)
        subscript = node.find("./m:sub/*", WORD_NAMESPACE)
        if base is None or subscript is None:
            return None
        base_text = _convert_omml_to_latex(base) if _local_name(base.tag) == "oMath" else _convert_math_element(base)
        subscript_text = _convert_omml_to_latex(subscript) if _local_name(subscript.tag) == "oMath" else _convert_math_element(subscript)
        if base_text is None or subscript_text is None:
            return None
        return rf"{base_text}_{{{subscript_text}}}"
    if local_name == "oMath":
        return _convert_omml_to_latex(node)
    return None


def _flush_text_block(
    buffered_text: list[str], style_name: str, blocks: list[SectionContent]
) -> None:
    text = "".join(buffered_text).strip()
    buffered_text.clear()
    if text:
        blocks.append(ParagraphBlock(text=text, style=style_name))


def _attach_caption_to_previous_image(blocks: list[SectionContent], caption: str) -> bool:
    if not blocks:
        return False
    last_block = blocks[-1]
    if isinstance(last_block, ImageBlock) and last_block.caption is None:
        last_block.caption = caption
        return True
    return False


def _flush_pending_figure_caption(
    blocks: list[SectionContent], pending_figure_caption: str | None
) -> None:
    if pending_figure_caption is not None:
        blocks.append(FigureBlock(caption=pending_figure_caption))


def _is_heading(style_name: str) -> bool:
    lowered = style_name.lower()
    return lowered.startswith("heading")


def _is_heading_paragraph(paragraph: ParagraphBlock) -> bool:
    return _detect_heading_level(paragraph) is not None


def _looks_like_heading_text(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered in TEXT_HEADING_TITLES:
        return True
    return _matches_text_pattern(stripped, NUMBERED_HEADING_PATTERN)


def _detect_heading_level(paragraph: ParagraphBlock) -> int | None:
    style_level = _heading_level_from_style(paragraph.style)
    if style_level is not None:
        return style_level

    stripped = paragraph.text.strip()
    lowered = stripped.lower()
    if lowered in TITLE_HEADING_TITLES or lowered in REFERENCE_SECTION_TITLES:
        return 1
    numbering_level = _heading_level_from_text(stripped)
    if numbering_level is not None:
        return numbering_level
    return None


def _heading_level_from_style(style_name: str) -> int | None:
    lowered = style_name.lower().replace(" ", "")
    match = re.match(r"heading(?P<level>\d+)", lowered)
    if match is None:
        return None
    return int(match.group("level"))


def _heading_level_from_text(text: str) -> int | None:
    match = re.match(r"^(?P<numbering>\d+(?:\.\d+)*)\.?\s+\S+", text)
    if match is None:
        return None
    return match.group("numbering").count(".") + 1


def _clean_heading_title(text: str) -> str:
    stripped = text.strip()
    return re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", stripped)


def _is_reference_section_title(title: str) -> bool:
    return title.strip().lower() in REFERENCE_SECTION_TITLES


def _is_bibliography_paragraph(paragraph: ParagraphBlock) -> bool:
    return BIBLIOGRAPHY_STYLE_TOKEN in paragraph.style.lower()


def _collect_reference_lines(blocks: list[SectionContent]) -> list[str]:
    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, ParagraphBlock):
            continue
        normalized = _normalize_reference_line(block.text)
        if normalized:
            lines.append(normalized)
    return lines


def _normalize_reference_line(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    lowered = stripped.lower()
    if lowered in REFERENCE_SECTION_TITLES:
        return ""
    for prefix in ("bibliography ", "references ", "reference "):
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()
    return stripped


def _is_body_start_paragraph(paragraph: ParagraphBlock) -> bool:
    text = paragraph.text.strip()
    lowered = text.lower()
    if lowered in {"abstract"}:
        return False
    if _is_heading_paragraph(paragraph):
        return True
    if _matches_keywords_prefix(lowered):
        return False
    return False


def _find_special_heading_index(blocks: list[ParagraphBlock], title: str) -> int | None:
    for index, block in enumerate(blocks):
        if block.text.strip().lower() == title:
            return index
    return None


def _find_keywords_index(blocks: list[ParagraphBlock]) -> int | None:
    for index, block in enumerate(blocks):
        if _matches_keywords_prefix(block.text.strip().lower()):
            return index
    return None


def _matches_keywords_prefix(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in KEYWORDS_PREFIXES)


def _extract_keywords(text: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in KEYWORDS_PREFIXES:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()
    return stripped


def _split_author_metadata(blocks: list[ParagraphBlock]) -> tuple[list[str], list[str]]:
    authors: list[str] = []
    affiliations: list[str] = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if _looks_like_affiliation(text):
            affiliations.append(text)
        else:
            authors.append(text)
    return authors, affiliations


def _looks_like_affiliation(text: str) -> bool:
    lowered = text.lower()
    if any(hint in lowered for hint in AFFILIATION_HINTS):
        return True
    if re.match(r"^\d+\s*", text):
        return True
    if lowered.startswith("corresponding author"):
        return True
    return False


def _deduplicate_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _matches_text_pattern(text: str, pattern: str) -> bool:
    return re.match(pattern, text, re.IGNORECASE) is not None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]
