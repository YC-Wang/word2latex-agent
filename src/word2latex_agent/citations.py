"""Citation detection and natbib conversion."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import CitationRecord

PARENTHETICAL_PATTERN = re.compile(r"\(([^()]*\d{4}[^()]*)\)")
NARRATIVE_PATTERN = re.compile(
    r"(?P<author>[A-Z][A-Za-z'`\-]+(?: et al\.)?)\s*\((?P<year>\d{4})\)"
)
AUTHOR_YEAR_PATTERN = re.compile(
    r"^\s*(?P<author>[A-Z][A-Za-z'`\-]+(?: et al\.)?)\s*,\s*(?P<year>\d{4})\s*$"
)


def convert_text_citations(text: str) -> tuple[str, list[CitationRecord]]:
    """Convert simple author-year citations to natbib commands."""
    collected: dict[str, CitationRecord] = {}
    after_parenthetical = PARENTHETICAL_PATTERN.sub(
        lambda match: _replace_parenthetical(match.group(1), collected),
        text,
    )
    after_narrative = NARRATIVE_PATTERN.sub(
        lambda match: _replace_narrative(match.group("author"), match.group("year"), collected),
        after_parenthetical,
    )
    return after_narrative, list(collected.values())


def render_bibliography(records: Iterable[CitationRecord]) -> str:
    """Create placeholder BibTeX entries for the detected citations."""
    unique = {record.key: record for record in records}
    lines: list[str] = []
    for key in sorted(unique):
        record = unique[key]
        lines.extend(
            [
                f"@article{{{record.key},",
                f"  author = {{{_placeholder_author(record.author_token)}}},",
                f"  title = {{Placeholder title for {record.key}}},",
                f"  journal = {{Placeholder journal}},",
                f"  year = {{{record.year}}},",
                "}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _replace_parenthetical(content: str, collected: dict[str, CitationRecord]) -> str:
    parts = [part.strip() for part in content.split(";")]
    citations: list[CitationRecord] = []
    for part in parts:
        parsed = _parse_author_year(part)
        if parsed is None:
            return f"({content})"
        citations.append(parsed)
        collected[parsed.key] = parsed
    keys = ",".join(citation.key for citation in citations)
    return rf"\citep{{{keys}}}"


def _replace_narrative(author: str, year: str, collected: dict[str, CitationRecord]) -> str:
    citation = _make_citation(author, year)
    collected[citation.key] = citation
    return rf"\citet{{{citation.key}}}"


def _parse_author_year(text: str) -> CitationRecord | None:
    match = AUTHOR_YEAR_PATTERN.fullmatch(text)
    if match is None:
        return None
    return _make_citation(match.group("author"), match.group("year"))


def _make_citation(author: str, year: str) -> CitationRecord:
    surname = author.split()[0].lower()
    key = f"{surname}{year}"
    return CitationRecord(key=key, author_token=author, year=year)


def _placeholder_author(author_token: str) -> str:
    token = author_token.replace(" et al.", "")
    return f"{token} and Placeholder Coauthor"
