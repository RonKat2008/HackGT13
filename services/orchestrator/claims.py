from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import fitz

import repro
from models import ClaimType, Depth, DeskClaim, Verdict

PREFERRED_SECTIONS = (
    "abstract",
    "introduction",
    "related_work",
    "methods",
    "results",
    "discussion",
)
SKIP_SECTIONS = frozenset({"references", "bibliography"})
SEMANTIC_CAP = 10

PAREN_CITATION = re.compile(
    r"\(([A-Z][A-Za-z\-']+)(?: et al\.)?,? (\d{4})\)"
)
NARRATIVE_CITATION = re.compile(
    r"\b([A-Z][A-Za-z\-']+)(?: et al\.)? \((\d{4})\)"
)
BRACKET_CITATION = re.compile(r"\[\d+\]")
DOI_RE = re.compile(r"(?:doi:\s*)?(10\.\d{4,}/[^\s,;]+)", re.I)
HAS_NUMBER = re.compile(r"\d")
DECIMAL_RE = re.compile(r"\d+\.\d+")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
INT_UNIT_RE = re.compile(
    r"\b(\d{2,}|\d{1,3}(?:,\d{3})+)\s*"
    r"(?:%|percent|accuracy|ms|steps?|points?|epochs?|tokens?|layers?|hours?|years?)\b",
    re.I,
)
COMPARE_RE = re.compile(
    r"\bimproves?|\boutperforms?|\bover\b|\bby\s+\d+(?:\.\d+)?\s+(?:percentage\s+)?"
    r"points?\b|\bgain\b|\bhigher\b|\blower\b|\breduces?",
    re.I,
)
ROW_COUNT_RE = re.compile(
    r"\b\d[\d,]*\s+(rows|observations|passengers|samples|records|districts)\b",
    re.I,
)
OF_THE_RE = re.compile(r"\bof the\s+\d", re.I)
SEMANTIC_RE = re.compile(
    r"\bwe show\b|\bwe demonstrate\b|\bsignificantly\b|\brobust\b|\bconverges\b|"
    r"\bimproves\b|\boutperforms\b|\bstays under\b|\blowers\b|\bis (?:more|less)\b",
    re.I,
)
ABBREV_RE = re.compile(r"\b(?:et al|e\.g|i\.e|fig|vs|dr|mr|ms|prof)\.", re.I)
SPLIT_RE = re.compile(r"(?<=[.!?])(?:\s+(?=[A-Z])|\n+)")
STANDALONE_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(?:discussion|related work|conclusion|acknowledgements?|appendix|background)"
    r"\s*:?\s*$",
    re.I,
)
TABLE_GAP_RE = re.compile(r"\s{3,}")


def _is_skipped_line(line: str) -> bool:
    """A heading, a page number, or a padded table row is not part of the next sentence."""
    stripped = line.strip()
    if not stripped:
        return False
    if STANDALONE_HEADING_RE.match(stripped):
        return True
    if TABLE_GAP_RE.search(line):
        return True
    if re.fullmatch(r"\d{1,3}", stripped):
        return True
    if len(stripped.split()) <= 6 and not re.search(r"[.!?0-9]", stripped):
        return True
    return False


def evidence_pieces(text: str) -> list[str]:
    """Prose sentences and table rows in reading order."""
    pieces: list[str] = []
    prose: list[str] = []

    def flush() -> None:
        if prose:
            pieces.extend(split_sentences("\n".join(prose)))
            prose.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            prose.append("")
            continue
        if STANDALONE_HEADING_RE.match(stripped) or re.fullmatch(r"\d{1,3}", stripped):
            flush()
            continue
        if len(stripped.split()) <= 6 and not re.search(r"[.!?0-9]", stripped):
            flush()
            continue
        if TABLE_GAP_RE.search(line):
            flush()
            compact = " ".join(stripped.split())
            if compact:
                pieces.append(compact)
            continue
        prose.append(line)
    flush()
    return pieces


def split_sentences(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    kept = [line for line in text.splitlines() if not _is_skipped_line(line)]
    prose = "\n".join(kept)
    masked = ABBREV_RE.sub(lambda match: match.group(0)[:-1] + "\uE000", prose)
    out: list[str] = []
    for part in SPLIT_RE.split(masked):
        sentence = part.replace("\uE000", ".").strip()
        if len(sentence) >= 20:
            out.append(sentence)
    return out


def _is_heading(sentence: str) -> bool:
    compact = " ".join(sentence.split())
    if re.match(r"^\d+(?:\.\d+)+\s+\S", compact) and len(compact.split()) <= 10:
        return True
    return False


def _is_arxiv_banner(sentence: str) -> bool:
    compact = " ".join(sentence.split())
    return bool(re.match(r"arXiv:\s*\d{4}\.\d{4,5}", compact, re.I)) and len(compact) < 120


def _is_citation(sentence: str) -> bool:
    return bool(
        PAREN_CITATION.search(sentence)
        or NARRATIVE_CITATION.search(sentence)
        or BRACKET_CITATION.search(sentence)
        or DOI_RE.search(sentence)
        or "doi:" in sentence.lower()
    )


def _is_dataset(sentence: str) -> bool:
    if repro.SLUG_RE.search(sentence):
        return True
    lowered = sentence.lower()
    if any(name in lowered for name in repro.KNOWN_DATASETS):
        return True
    return bool(ROW_COUNT_RE.search(sentence) or OF_THE_RE.search(sentence))


def _is_numerical(sentence: str) -> bool:
    return bool(DECIMAL_RE.search(sentence) or PERCENT_RE.search(sentence) or INT_UNIT_RE.search(sentence))


def classify(sentence: str) -> ClaimType | None:
    if _is_citation(sentence):
        return ClaimType.CITATION
    if HAS_NUMBER.search(sentence) and COMPARE_RE.search(sentence):
        return ClaimType.NUMERICAL_COMPARISON
    if _is_dataset(sentence):
        return ClaimType.DATASET
    if _is_numerical(sentence):
        return ClaimType.NUMERICAL
    if not HAS_NUMBER.search(sentence) and SEMANTIC_RE.search(sentence):
        return ClaimType.SEMANTIC
    return None


def classify_types(sentence: str) -> list[ClaimType]:
    types: list[ClaimType] = []
    if _is_citation(sentence):
        types.append(ClaimType.CITATION)
    if HAS_NUMBER.search(sentence) and COMPARE_RE.search(sentence):
        types.append(ClaimType.NUMERICAL_COMPARISON)
    elif _is_dataset(sentence):
        types.append(ClaimType.DATASET)
    elif _is_numerical(sentence):
        types.append(ClaimType.NUMERICAL)
    if not types and not HAS_NUMBER.search(sentence) and SEMANTIC_RE.search(sentence):
        types.append(ClaimType.SEMANTIC)
    return types


def depth_for(claim_type: ClaimType) -> Depth:
    return {
        ClaimType.CITATION: Depth.EXTERNAL,
        ClaimType.NUMERICAL: Depth.CONSISTENCY,
        ClaimType.NUMERICAL_COMPARISON: Depth.MATHEMATICAL,
        ClaimType.DATASET: Depth.COMPUTATIONAL,
        ClaimType.SEMANTIC: Depth.EVIDENCE,
    }[claim_type]


def claim_id(job_id: str, text: str) -> str:
    return hashlib.sha1((job_id + text).encode()).hexdigest()[:12]


def find_page(doc: fitz.Document, text: str) -> int | None:
    needles = [text[:80], text[:40]]
    for needle in needles:
        cleaned = " ".join(needle.split())
        if len(cleaned) < 4:
            continue
        for index, page in enumerate(doc):
            try:
                if page.search_for(cleaned):
                    return index + 1
            except Exception:
                continue
    return None


def _without_citation(sentence: str) -> str:
    stripped = PAREN_CITATION.sub("", sentence)
    stripped = NARRATIVE_CITATION.sub("", stripped)
    stripped = BRACKET_CITATION.sub("", stripped)
    return re.sub(r"\s+", " ", stripped).strip(" ,.;")


def _sections_to_scan(sections: dict[str, str], path: str | Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for name in PREFERRED_SECTIONS:
        body = str(sections.get(name) or "").strip()
        if body:
            found.append((name, body))
    if found:
        return found
    other = str(sections.get("other") or "").strip()
    if other:
        return [("body", other)]
    doc = fitz.open(path)
    try:
        text = "\n".join(page.get_text() for page in doc).strip()
    finally:
        doc.close()
    return [("body", text)] if text else []


def extract_claims(path: str | Path, job_id: str, sections: dict[str, str]) -> list[dict[str, Any]]:
    ordered = _sections_to_scan(sections, path)
    doc = fitz.open(path)
    try:
        raw: list[dict[str, Any]] = []
        seen: set[str] = set()
        semantic_count = 0
        position = 0
        for section, body in ordered:
            if section in SKIP_SECTIONS:
                continue
            for sentence in split_sentences(body):
                if _is_arxiv_banner(sentence) or _is_heading(sentence):
                    continue
                for claim_type in classify_types(sentence):
                    if claim_type == ClaimType.NUMERICAL and section != "abstract":
                        continue
                    text = sentence
                    if claim_type != ClaimType.CITATION and _is_citation(sentence):
                        stripped = _without_citation(sentence)
                        if len(stripped) >= 20 and stripped != sentence:
                            text = stripped
                    if claim_type == ClaimType.SEMANTIC:
                        if semantic_count >= SEMANTIC_CAP:
                            continue
                        semantic_count += 1
                    identifier = claim_id(job_id, text)
                    if identifier in seen:
                        continue
                    seen.add(identifier)
                    page = find_page(doc, text) or find_page(doc, sentence)
                    step = f"Located claim on page {page}" if page is not None else "Located claim"
                    claim = DeskClaim.model_validate(
                        {
                            "claim_id": identifier,
                            "job_id": job_id,
                            "text": text,
                            "page": page,
                            "section": section,
                            "claim_type": claim_type,
                            "verdict": Verdict.NOT_CHECKED,
                            "confidence": 0.0,
                            "depth": depth_for(claim_type),
                            "rounds": 0,
                            "reason": "",
                            "evidence": [],
                            "steps": [step],
                            "catalog": None,
                            "computation": None,
                        }
                    )
                    raw.append({**claim.model_dump(mode="json"), "_position": position})
                    position += 1
    finally:
        doc.close()
    raw.sort(key=lambda item: (item["page"] if item["page"] is not None else 10**9, item["_position"]))
    for item in raw:
        item.pop("_position", None)
    return raw
