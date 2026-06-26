"""Helpers for building DOCX fixtures in tests."""

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias
from zipfile import ZipFile

ParagraphFixture: TypeAlias = tuple[str, str]
TableFixture: TypeAlias = dict[str, list[list[str]]]
EquationFixture: TypeAlias = dict[str, object]
ImageFixture: TypeAlias = dict[str, object]
DocxFixtureBlock: TypeAlias = ParagraphFixture | TableFixture | EquationFixture | ImageFixture

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="jpg" ContentType="image/jpeg"/>
  <Default Extension="jpeg" ContentType="image/jpeg"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/></w:style>
</w:styles>
"""


def make_docx(path: Path, blocks: list[DocxFixtureBlock]) -> None:
    document_xml, relationships_xml, media_files = _build_document_xml(blocks)
    path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", RELS_XML)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", STYLES_XML)
        if relationships_xml is not None:
            archive.writestr("word/_rels/document.xml.rels", relationships_xml)
        for media_path, bytes_data in media_files:
            archive.writestr(media_path, bytes_data)


def _build_document_xml(blocks: list[DocxFixtureBlock]) -> tuple[str, str | None, list[tuple[str, bytes]]]:
    body = []
    relationships: list[tuple[str, str]] = []
    media_files: list[tuple[str, bytes]] = []
    image_count = 0
    for block in blocks:
        if isinstance(block, tuple):
            style_id, text = block
            body.append(
                "<w:p>"
                "<w:pPr>"
                f'<w:pStyle w:val="{style_id}"/>'
                "</w:pPr>"
                "<w:r>"
                f"<w:t>{_escape_xml(text)}</w:t>"
                "</w:r>"
                "</w:p>"
            )
            continue

        if "equation" in block:
            body.append(_build_equation_paragraph(block["equation"]))
            continue
        if "image" in block:
            image = block["image"]
            if not isinstance(image, dict):
                raise TypeError("image fixture must be a dictionary")
            image_count += 1
            filename = str(image.get("filename", f"image_{image_count}.png"))
            bytes_data = image.get("bytes", b"")
            if not isinstance(bytes_data, bytes):
                raise TypeError("image bytes must be bytes")
            relationship_id = f"rIdImage{image_count}"
            relationships.append((relationship_id, f"media/{filename}"))
            media_files.append((f"word/media/{filename}", bytes_data))
            body.append(_build_image_paragraph(relationship_id))
            continue

        rows = block.get("rows", [])
        cells_xml: list[str] = []
        for row in rows:
            row_xml = "".join(
                "<w:tc><w:p><w:r><w:t>"
                + _escape_xml(cell)
                + "</w:t></w:r></w:p></w:tc>"
                for cell in row
            )
            cells_xml.append("<w:tr>" + row_xml + "</w:tr>")
        body.append("<w:tbl>" + "".join(cells_xml) + "</w:tbl>")

    joined = "".join(body)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        f"<w:body>{joined}</w:body>"
        "</w:document>"
    )
    relationships_xml = _build_document_relationships_xml(relationships) if relationships else None
    return document_xml, relationships_xml, media_files


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_equation_paragraph(equation: object) -> str:
    if not isinstance(equation, dict):
        raise TypeError("equation fixture must be a dictionary")

    kind = equation.get("kind", "text")
    if kind == "text":
        value = _escape_xml(str(equation.get("value", "")))
        math_xml = (
            '<m:oMath>'
            '<m:r><m:t>' + value + "</m:t></m:r>"
            "</m:oMath>"
        )
    elif kind == "fraction":
        numerator = _escape_xml(str(equation.get("numerator", "")))
        denominator = _escape_xml(str(equation.get("denominator", "")))
        math_xml = (
            '<m:oMath>'
            "<m:f>"
            "<m:num><m:r><m:t>" + numerator + "</m:t></m:r></m:num>"
            "<m:den><m:r><m:t>" + denominator + "</m:t></m:r></m:den>"
            "</m:f>"
            "</m:oMath>"
        )
    elif kind == "superscript":
        base = _escape_xml(str(equation.get("base", "")))
        superscript = _escape_xml(str(equation.get("sup", "")))
        math_xml = (
            '<m:oMath>'
            "<m:sSup>"
            "<m:e><m:r><m:t>" + base + "</m:t></m:r></m:e>"
            "<m:sup><m:r><m:t>" + superscript + "</m:t></m:r></m:sup>"
            "</m:sSup>"
            "</m:oMath>"
        )
    else:
        math_xml = (
            '<m:oMath>'
            "<m:nary><m:e><m:r><m:t>unsupported</m:t></m:r></m:e></m:nary>"
            "</m:oMath>"
        )

    return (
        '<w:p xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        + math_xml
        + "</w:p>"
    )


def _build_image_paragraph(relationship_id: str) -> str:
    return (
        "<w:p>"
        "<w:r>"
        "<w:drawing>"
        "<wp:inline>"
        "<a:graphic>"
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        "<pic:pic>"
        "<pic:blipFill>"
        f'<a:blip r:embed="{relationship_id}"/>'
        "</pic:blipFill>"
        "</pic:pic>"
        "</a:graphicData>"
        "</a:graphic>"
        "</wp:inline>"
        "</w:drawing>"
        "</w:r>"
        "</w:p>"
    )


def _build_document_relationships_xml(relationships: list[tuple[str, str]]) -> str:
    body = "".join(
        '<Relationship Id="'
        + relationship_id
        + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="'
        + target
        + '"/>'
        for relationship_id, target in relationships
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + body
        + "</Relationships>"
    )
