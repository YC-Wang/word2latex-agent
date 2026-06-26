"""Helpers for building DOCX fixtures in tests."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
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


def make_docx(path: Path, paragraphs: list[tuple[str, str]]) -> None:
    document_xml = _build_document_xml(paragraphs)
    path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", RELS_XML)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", STYLES_XML)


def _build_document_xml(paragraphs: list[tuple[str, str]]) -> str:
    body = []
    for style_id, text in paragraphs:
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
    joined = "".join(body)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{joined}</w:body>"
        "</w:document>"
    )


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
