"""Parse a reference list and match in-text citations to entries."""

from __future__ import annotations

import os
import re
from typing import Any

import claims as claim_extract

YEAR_RE = re.compile(r"\b((?:19|20|21)\d{2})\b")
QUOTE_RE = re.compile(r"[\"“]([^\"”]{8,})[\"”]")
SPLIT_RE = re.compile(r"(?:^|\n)\s*(?=\[\d+\]|\d+\.\s+[A-Z])")
NUMBER_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)\.)\s*")
SURNAME_RE = re.compile(r"\b([A-Z][A-Za-z\-']{2,})\s*,")


def parse_references(text: str) -> list[dict[str, Any]]:
    body = str(text or "").strip()
    if not body:
        return []
    chunks = [chunk.strip() for chunk in SPLIT_RE.split(body) if chunk.strip()]
    if len(chunks) == 1 and "\n\n" in body:
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", body) if chunk.strip()]
    return [_entry(chunk) for chunk in chunks]


def match_entry(sentence: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    bracket = claim_extract.BRACKET_CITATION.search(sentence)
    if bracket:
        number = bracket.group(0).strip("[]")
        for entry in entries:
            if entry.get("number") == number:
                return entry
    for pattern in (claim_extract.PAREN_CITATION, claim_extract.NARRATIVE_CITATION):
        found = pattern.search(sentence)
        if found is None:
            continue
        author, year = found.group(1), found.group(2)
        for entry in entries:
            if entry.get("year") == year and _has_author(entry, author):
                return entry
    return None


def _entry(chunk: str) -> dict[str, Any]:
    number_match = NUMBER_RE.match(chunk)
    number = ""
    if number_match:
        number = number_match.group(1) or number_match.group(2) or ""
    doi_match = claim_extract.DOI_RE.search(chunk)
    doi = doi_match.group(1).rstrip(").,;") if doi_match else ""
    years = YEAR_RE.findall(chunk)
    year = years[0] if years else ""
    quoted = QUOTE_RE.search(chunk)
    title = quoted.group(1).strip() if quoted else _title_after_year(chunk, year)
    before_year = chunk.split(year, 1)[0] if year else chunk
    authors: list[str] = []
    for surname in SURNAME_RE.findall(before_year):
        if surname.lower() in {"doi", "vol", "pp"}:
            continue
        if surname not in authors:
            authors.append(surname)
    return {
        "raw": " ".join(chunk.split()),
        "number": number,
        "year": year,
        "doi": doi,
        "title": title,
        "authors": authors,
    }


def _title_after_year(chunk: str, year: str) -> str:
    if not year or year not in chunk:
        return ""
    after = chunk.split(year, 1)[1]
    after = re.sub(r"^[\s).,\-:]+", "", after)
    sentence = re.split(r"\.\s+", after, maxsplit=1)[0]
    sentence = claim_extract.DOI_RE.sub("", sentence)
    return " ".join(sentence.replace("doi:", "").split()).strip(" .")


def _has_author(entry: dict[str, Any], author: str) -> bool:
    wanted = author.lower()
    return any(str(name).lower() == wanted for name in entry.get("authors") or [])


def attach(claims: list[dict[str, Any]], references_text: str, transport: Any = None) -> None:
    if transport is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return
    import catalogs

    entries = parse_references(references_text)
    for claim in claims:
        if str(claim.get("claim_type") or "") != "citation":
            continue
        entry = match_entry(str(claim.get("text") or ""), entries)
        query = str(entry["raw"] if entry else claim.get("text") or "")
        catalog = catalogs.lookup(query, entry or {}, transport=transport)
        claim["catalog"] = catalog
        verdict, confidence, reason = catalogs.decide(claim, catalog)
        claim["verdict"] = verdict
        claim["confidence"] = confidence
        if reason:
            claim["reason"] = reason
        steps = list(claim.get("steps") or [])
        steps.append("Queried Crossref, OpenAlex, and Semantic Scholar.")
        claim["steps"] = steps
