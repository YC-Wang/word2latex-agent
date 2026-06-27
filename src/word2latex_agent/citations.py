"""Citation detection and natbib/BibTeX conversion."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import BibliographyEntry, CitationRecord

PARENTHETICAL_PATTERN = re.compile(r"\(([^()]*\d{4}[^()]*)\)")
NARRATIVE_PATTERN = re.compile(
    r"(?P<author>[A-Z][A-Za-z'`\-]+(?: et al\.)?)\s*\((?P<year>\d{4})\)"
)
AUTHOR_YEAR_PATTERN = re.compile(
    r"^\s*(?P<author>[A-Z][A-Za-z'`\-]+(?: et al\.)?)\s*,\s*(?P<year>\d{4})\s*$"
)
REFERENCE_PATTERN = re.compile(
    r"^(?P<authors>.+),\s*(?P<year>\d{4})\s*:\s*(?P<rest>.+)$"
)
PAGE_RANGE_PATTERN = re.compile(r"(?P<start>\d+)\s*-\s*(?P<end>\d+)")
TITLE_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
TITLE_STOPWORDS = {"a", "an", "the"}


def convert_text_citations(
    text: str,
    citation_key_lookup: dict[tuple[str, str], str] | None = None,
) -> tuple[str, list[CitationRecord]]:
    """Convert simple author-year citations to natbib commands."""
    collected: dict[str, CitationRecord] = {}
    lookup = citation_key_lookup or {}
    after_parenthetical = PARENTHETICAL_PATTERN.sub(
        lambda match: _replace_parenthetical(match.group(1), collected, lookup),
        text,
    )
    after_narrative = NARRATIVE_PATTERN.sub(
        lambda match: _replace_narrative(
            match.group("author"),
            match.group("year"),
            collected,
            lookup,
        ),
        after_parenthetical,
    )
    return after_narrative, list(collected.values())


def parse_reference_entries(lines: Iterable[str]) -> list[BibliographyEntry]:
    """Parse bibliography lines into best-effort BibTeX entries."""
    entries: list[BibliographyEntry] = []
    seen_keys: set[str] = set()
    for line in lines:
        entry = parse_reference_line(line)
        if entry is None:
            continue
        key = entry.key
        suffix = 1
        while key in seen_keys:
            suffix += 1
            key = f"{entry.key}{suffix}"
        seen_keys.add(key)
        if key != entry.key:
            entry = BibliographyEntry(
                key=key,
                author=entry.author,
                title=entry.title,
                journal=entry.journal,
                year=entry.year,
                volume=entry.volume,
                pages=entry.pages,
            )
        entries.append(entry)
    return entries


def parse_reference_line(line: str) -> BibliographyEntry | None:
    """Parse a climate-science style reference line into a BibTeX entry."""
    text = " ".join(line.strip().split())
    if not text:
        return None

    match = REFERENCE_PATTERN.fullmatch(text)
    if match is None:
        return None

    authors = _normalize_reference_authors(match.group("authors"))
    year = match.group("year")
    title, journal, volume, pages = _parse_reference_rest(match.group("rest"))
    if title is None or journal is None:
        return None

    key = _build_reference_key(authors, year, title)
    return BibliographyEntry(
        key=key,
        author=authors,
        title=title,
        journal=journal,
        year=year,
        volume=volume,
        pages=pages,
    )


def build_reference_lookup(
    entries: Iterable[BibliographyEntry],
) -> dict[tuple[str, str], str]:
    """Map author-year pairs to parsed bibliography keys."""
    lookup: dict[tuple[str, str], str] = {}
    for entry in entries:
        surname = _extract_primary_surname(entry.author)
        lookup.setdefault((surname, entry.year), entry.key)
    return lookup


def render_bibliography(
    records: Iterable[CitationRecord],
    reference_entries: Iterable[BibliographyEntry] = (),
) -> str:
    """Render parsed bibliography entries and placeholders for unmatched citations."""
    citation_map = {record.key: record for record in records}
    bibliography_map = {entry.key: entry for entry in reference_entries}

    lines: list[str] = []
    for key in sorted(bibliography_map):
        lines.extend(_render_bibliography_entry(bibliography_map[key]))
    for key in sorted(citation_map):
        if key in bibliography_map:
            continue
        lines.extend(_render_placeholder_entry(citation_map[key]))
    return "\n".join(lines).rstrip() + "\n"


def _replace_parenthetical(
    content: str,
    collected: dict[str, CitationRecord],
    lookup: dict[tuple[str, str], str],
) -> str:
    parts = [part.strip() for part in content.split(";")]
    citations: list[CitationRecord] = []
    for part in parts:
        parsed = _parse_author_year(part, lookup)
        if parsed is None:
            return f"({content})"
        citations.append(parsed)
        collected[parsed.key] = parsed
    keys = ",".join(citation.key for citation in citations)
    return rf"\citep{{{keys}}}"


def _replace_narrative(
    author: str,
    year: str,
    collected: dict[str, CitationRecord],
    lookup: dict[tuple[str, str], str],
) -> str:
    citation = _make_citation(author, year, lookup)
    collected[citation.key] = citation
    return rf"\citet{{{citation.key}}}"


def _parse_author_year(
    text: str,
    lookup: dict[tuple[str, str], str],
) -> CitationRecord | None:
    match = AUTHOR_YEAR_PATTERN.fullmatch(text)
    if match is None:
        return None
    return _make_citation(match.group("author"), match.group("year"), lookup)


def _make_citation(
    author: str,
    year: str,
    lookup: dict[tuple[str, str], str],
) -> CitationRecord:
    surname = author.split()[0].lower()
    key = lookup.get((surname, year), f"{surname}{year}")
    return CitationRecord(key=key, author_token=author, year=year)


def _parse_reference_rest(rest: str) -> tuple[str | None, str | None, str | None, str | None]:
    title, separator, remainder = rest.partition(". ")
    if not separator:
        return None, None, None, None

    title = title.strip().rstrip(".")
    remainder = remainder.strip().rstrip(".")
    parts = [part.strip() for part in remainder.split(",") if part.strip()]
    if len(parts) < 3:
        return None, None, None, None

    journal = ", ".join(parts[:-2]).strip()
    volume = parts[-2].strip() or None
    pages = _normalize_pages(parts[-1].strip())
    return title, journal or None, volume, pages


def _normalize_reference_authors(authors_text: str) -> str:
    text = " ".join(authors_text.strip().split())
    text = re.sub(r",?\s+and\s+Coauthors\b", " and others", text, flags=re.IGNORECASE)
    if text.endswith(","):
        text = text[:-1].rstrip()

    has_others = text.endswith(" and others")
    base_text = text[:-11].rstrip() if has_others else text
    name_matches = re.findall(
        r"[A-Z][A-Za-z'`\- ]+,\s*[A-Z](?:[A-Za-z]*\.)?(?:\s*[A-Z]\.)*",
        base_text,
    )
    if name_matches:
        normalized = " and ".join(name.strip().rstrip(",") for name in name_matches)
    else:
        normalized = base_text.replace(", and ", " and ").strip().rstrip(",")
    if has_others:
        normalized = f"{normalized} and others" if normalized else "others"
    return normalized


def _build_reference_key(authors: str, year: str, title: str) -> str:
    surname = _extract_primary_surname(authors)
    title_token = _extract_title_token(title)
    return f"{surname}{year}{title_token}"


def _extract_primary_surname(authors: str) -> str:
    primary_author = authors.split(" and ")[0].strip()
    surname = primary_author.split(",", 1)[0].strip().lower()
    return slug_text(surname) or "reference"


def _extract_title_token(title: str) -> str:
    for token in TITLE_TOKEN_PATTERN.findall(title.lower()):
        if token not in TITLE_STOPWORDS:
            return slug_text(token) or "work"
    return "work"


def _normalize_pages(pages: str) -> str:
    return PAGE_RANGE_PATTERN.sub(r"\g<start>--\g<end>", pages).rstrip(".")


def _render_bibliography_entry(entry: BibliographyEntry) -> list[str]:
    lines = [
        f"@article{{{entry.key},",
        f"  author = {{{entry.author}}},",
        f"  title = {{{entry.title}}},",
        f"  journal = {{{entry.journal}}},",
        f"  year = {{{entry.year}}},",
    ]
    if entry.volume:
        lines.append(f"  volume = {{{entry.volume}}},")
    if entry.pages:
        lines.append(f"  pages = {{{entry.pages}}},")
    lines.extend(["}", ""])
    return lines


def _render_placeholder_entry(record: CitationRecord) -> list[str]:
    return [
        f"@article{{{record.key},",
        f"  author = {{{_placeholder_author(record.author_token)}}},",
        f"  title = {{Placeholder title for {record.key}}},",
        f"  journal = {{Placeholder journal}},",
        f"  year = {{{record.year}}},",
        "}",
        "",
    ]


def _placeholder_author(author_token: str) -> str:
    token = author_token.replace(" et al.", "")
    return f"{token} and Placeholder Coauthor"


def slug_text(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())
