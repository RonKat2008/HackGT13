from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import fitz

import probe
import shelf

SPECIALISTS = [
    "ingest",
    "sections",
    "retrieve",
    "extract",
    "resolve",
    "numbers",
    "support",
    "provenance",
    "kaggle_runner",
    "jev",
]

SECTION_KEYS = (
    "abstract",
    "introduction",
    "methods",
    "results",
    "references",
    "other",
)
HEADING_ALIASES = {
    "abstract": "abstract",
    "introduction": "introduction",
    "method": "methods",
    "methods": "methods",
    "results": "results",
    "references": "references",
    "bibliography": "references",
}
HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?("
    r"abstract|introduction|methods?|results|references|bibliography"
    r")\s*:?\s*$",
    re.I,
)
CITATION_RE = re.compile(r"\(([A-Z][A-Za-z.\-]+),\s*(\d{4})\)")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
NUMBER_RE = re.compile(r"\d+\.\d+")
DATASET_SLUG_RE = re.compile(r"\b([a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]*)\b", re.I)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z]{4,}")
HIDDEN_SENTENCE = "Probe below 0.60 AUC on the holdout. AI-likeness hidden."
TEST_FAIL_STATUSES = {"mismatch", "missing_row"}

Recorder = Callable[[str, str, str, str], None]


def load_paper(path: str | Path) -> str:
    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def split_sections(text: str) -> dict[str, str]:
    sections = {key: "" for key in SECTION_KEYS}
    lines = text.splitlines()
    heading_at: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if match:
            heading_at.append((index, HEADING_ALIASES[match.group(1).lower()]))

    if not heading_at:
        sections["other"] = text
        sections["section_quality"] = "weak"
        return sections

    sections["section_quality"] = "ok"
    first_index = heading_at[0][0]
    preamble = "\n".join(lines[:first_index])
    if preamble:
        sections["other"] = preamble

    for position, (start, name) in enumerate(heading_at):
        end = heading_at[position + 1][0] if position + 1 < len(heading_at) else len(lines)
        body = "\n".join(lines[start + 1 : end]).strip()
        if sections[name]:
            sections[name] = f"{sections[name]}\n{body}".strip()
        else:
            sections[name] = body
    return sections


def dataset_issues(claims: list[dict[str, Any]], paper_text: str) -> list[dict[str, Any]]:
    lowered = paper_text.lower()
    issues: list[dict[str, Any]] = []
    for claim in claims:
        name = claim.get("dataset")
        if not name:
            continue
        if str(name).lower() not in lowered:
            issues.append(
                _issue(
                    "dataset",
                    str(claim.get("text") or name),
                    str(name),
                    "The named dataset does not appear in the paper text.",
                )
            )
    return issues


def audit_paper(
    path: str | Path,
    job_id: str,
    *,
    results_path: str | Path | None = None,
    recorder: Recorder | None = None,
    auc: float | None = None,
    repro: Callable[[list[dict[str, Any]], dict[str, str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    record = recorder if recorder is not None else shelf.record_event
    events: list[dict[str, str]] = []
    issues: list[dict[str, Any]] = []
    text = ""
    sections: dict[str, str] = {key: "" for key in SECTION_KEYS}
    claims: list[dict[str, Any]] = []
    hidden = False
    hidden_sentence = ""
    kaggle: dict[str, Any] = {}
    pages = 0

    def emit(specialist: str, state: str, detail: str = "") -> None:
        record(job_id, specialist, state, detail)
        events.append({"specialist": specialist, "state": state, "detail": detail})

    def ingest() -> None:
        nonlocal text, pages
        text = load_paper(path)
        pages = _page_count(path)

    def sections_step() -> None:
        nonlocal sections
        sections = split_sections(text)

    def retrieve() -> None:
        return

    def extract() -> None:
        nonlocal claims
        claims = _extract_claims(sections)

    def resolve() -> None:
        issues.extend(_citation_issues(claims, sections.get("references", "")))

    def numbers() -> None:
        issues.extend(_number_issues(sections.get("abstract", ""), sections.get("results", "")))

    def support() -> None:
        issues.extend(
            _support_issues(
                claims,
                sections.get("methods", ""),
                sections.get("results", ""),
            )
        )
        issues.extend(dataset_issues(claims, text))

    def provenance() -> None:
        nonlocal hidden, hidden_sentence
        if auc is None:
            return
        hidden = probe.should_hide(auc)
        if hidden:
            hidden_sentence = HIDDEN_SENTENCE

    def kaggle_runner() -> None:
        nonlocal kaggle
        if results_path is not None:
            kaggle = _kaggle_result(results_path)
        elif repro is not None:
            try:
                produced = repro(claims, sections)
            except Exception:
                produced = None
            kaggle = produced if isinstance(produced, dict) else _kaggle_result(None)
        else:
            kaggle = _kaggle_result(None)
        if kaggle.get("status") in TEST_FAIL_STATUSES:
            issues.append(
                _issue(
                    "test",
                    str(kaggle.get("claim_text") or "Stored claim test disagreed with the paper."),
                    str(kaggle.get("log") or kaggle.get("status") or ""),
                    str(kaggle.get("detail") or "The stored claim test log disagrees with the paper."),
                )
            )

    def jev() -> None:
        for issue in issues:
            issue["jev_label"] = "contradicted"
            reason = str(issue.get("reason") or "").strip()
            if not reason or "fraudulent" in reason.lower():
                issue["reason"] = "The claim is contradicted by the paper evidence."
            else:
                issue["reason"] = reason.split("\n")[0].strip()

    steps: dict[str, Callable[[], None]] = {
        "ingest": ingest,
        "sections": sections_step,
        "retrieve": retrieve,
        "extract": extract,
        "resolve": resolve,
        "numbers": numbers,
        "support": support,
        "provenance": provenance,
        "kaggle_runner": kaggle_runner,
        "jev": jev,
    }
    for name in SPECIALISTS:
        emit(name, "started", _STARTED[name])
        steps[name]()
        emit(
            name,
            "finished",
            _finished_detail(
                name,
                pages=pages,
                sections=sections,
                claims=claims,
                issues=issues,
                kaggle=kaggle,
            ),
        )
    _annotate_pages(path, issues)

    result: dict[str, Any] = {
        "issues": issues,
        "events": events,
        "hidden": hidden,
        "kaggle": kaggle,
        "section_quality": sections.get("section_quality", "ok"),
    }
    if hidden_sentence:
        result["hidden_sentence"] = hidden_sentence
    return result


_STARTED = {
    "ingest": "Opening the PDF.",
    "sections": "Splitting sections.",
    "retrieve": "Checking for extra sources.",
    "extract": "Pulling claims.",
    "resolve": "Checking citations.",
    "numbers": "Checking abstract numbers.",
    "support": "Checking claim support.",
    "provenance": "Skipping likeness.",
    "kaggle_runner": "Looking for a public table.",
    "jev": "Stamping problems.",
}


def _finished_detail(
    name: str,
    *,
    pages: int,
    sections: dict[str, str],
    claims: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    kaggle: dict[str, Any],
) -> str:
    if name == "ingest":
        count = pages if pages > 0 else 0
        unit = "page" if count == 1 else "pages"
        return f"Opened {count} {unit}."
    if name == "sections":
        return _section_sentence(sections)
    if name == "retrieve":
        return "No extra sources. The check uses this PDF."
    if name == "extract":
        count = len(claims)
        unit = "claim" if count == 1 else "claims"
        return f"Pulled {count} {unit}."
    if name == "resolve":
        count = _count(issues, "citation")
        if count == 0:
            return "Citations match the reference list."
        if count == 1:
            return "1 citation does not resolve."
        return f"{count} citations do not resolve."
    if name == "numbers":
        count = _count(issues, "number")
        if count == 0:
            return "Abstract numbers appear in the results."
        if count == 1:
            return "1 number in the abstract is missing from the results."
        return f"{count} numbers in the abstract are missing from the results."
    if name == "support":
        count = _count(issues, "support") + _count(issues, "dataset")
        if count == 0:
            return "Claims have support in the methods or results."
        if count == 1:
            return "1 claim has no support in the methods or results."
        return f"{count} claims have no support in the methods or results."
    if name == "provenance":
        return "Likeness is not scored on this desk."
    if name == "kaggle_runner":
        return _kaggle_sentence(kaggle)
    count = len(issues)
    if count == 0:
        return "No problem to stamp."
    if count == 1:
        return "Stamped 1 problem."
    return f"Stamped {count} problems."


def _count(issues: list[dict[str, Any]], kind: str) -> int:
    return sum(1 for issue in issues if issue.get("issue_type") == kind)


def _section_sentence(sections: dict[str, str]) -> str:
    if sections.get("section_quality") == "weak":
        return "Section headings are weak."
    found = [
        label
        for label in ("abstract", "methods", "results")
        if str(sections.get(label) or "").strip()
    ]
    if not found:
        return "Section headings are weak."
    return f"Found {_and(found)}."


def _and(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _kaggle_sentence(kaggle: dict[str, Any]) -> str:
    status = str(kaggle.get("status") or "not_run")
    detail = str(kaggle.get("detail") or "").strip()
    if status == "not_run":
        return "No public table to rerun."
    lowered = detail.lower()
    if detail and "fraudulent" not in lowered and "written by ai" not in lowered:
        return detail if detail.endswith(".") else f"{detail}."
    if status in TEST_FAIL_STATUSES:
        return "The stored claim test disagrees with the paper."
    return "The public table matches the count written in the paper."


def _page_count(path: str | Path) -> int:
    doc = fitz.open(path)
    try:
        return int(doc.page_count)
    finally:
        doc.close()


def _annotate_pages(path: str | Path, issues: list[dict[str, Any]]) -> None:
    if not issues:
        return
    doc = fitz.open(path)
    try:
        for issue in issues:
            needles = _needles(issue)
            page_no = None
            if needles:
                for index, page in enumerate(doc):
                    if _page_has(page, needles):
                        page_no = index + 1
                        break
            issue["page"] = page_no
    finally:
        doc.close()


def _needles(issue: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for raw in (issue.get("evidence_span"), issue.get("claim_text")):
        cleaned = " ".join(str(raw or "").split())
        if len(cleaned) < 4:
            continue
        clipped = cleaned[:80]
        for candidate in (cleaned, clipped):
            if candidate not in seen:
                seen.append(candidate)
    return seen


def _page_has(page: Any, needles: list[str]) -> bool:
    for needle in needles:
        try:
            if page.search_for(needle):
                return True
        except Exception:
            continue
    return False


def _issue(issue_type: str, claim_text: str, evidence_span: str, reason: str) -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "claim_text": claim_text,
        "evidence_span": evidence_span,
        "jev_label": "contradicted",
        "reason": reason,
    }


def _extract_claims(sections: dict[str, str]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for section in ("abstract", "introduction", "methods", "results"):
        for sentence in _sentences(sections.get(section, "")):
            citation = CITATION_RE.search(sentence)
            doi = DOI_RE.search(sentence)
            numbers = NUMBER_RE.findall(sentence)
            dataset = _dataset_name(sentence)
            if not (citation or doi or numbers or dataset):
                continue
            claims.append(
                {
                    "text": sentence,
                    "section": section,
                    "citation": (citation.group(1), citation.group(2)) if citation else None,
                    "doi": doi.group(0) if doi else None,
                    "numbers": numbers,
                    "dataset": dataset,
                }
            )
    return claims


def _sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return [part.strip() for part in SENTENCE_RE.split(stripped) if part.strip()]


def _dataset_name(text: str) -> str | None:
    match = DATASET_SLUG_RE.search(text)
    if match:
        return match.group(1)
    return None


def _citation_issues(claims: list[dict[str, Any]], references: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    refs_lower = references.lower()
    for claim in claims:
        citation = claim.get("citation")
        if citation:
            author, year = citation
            token = f"{author}, {year}"
            if token.lower() not in refs_lower and not (
                author.lower() in refs_lower and year in references
            ):
                issues.append(
                    _issue(
                        "citation",
                        claim["text"],
                        token,
                        f"The citation ({token}) does not appear in the references.",
                    )
                )
        doi = claim.get("doi")
        if doi and str(doi).lower() not in refs_lower:
            issues.append(
                _issue(
                    "citation",
                    claim["text"],
                    str(doi),
                    f"The DOI {doi} does not appear in the references.",
                )
            )
    return issues


def _number_issues(abstract: str, results: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for token in NUMBER_RE.findall(abstract):
        if token in seen:
            continue
        seen.add(token)
        if token not in results:
            claim = next(
                (sentence for sentence in _sentences(abstract) if token in sentence),
                abstract.strip(),
            )
            issues.append(
                _issue(
                    "number",
                    claim,
                    token,
                    f"The number {token} in the abstract is absent from the results.",
                )
            )
    return issues


def _content_words(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(text)}


def _support_issues(
    claims: list[dict[str, Any]],
    methods: str,
    results: str,
) -> list[dict[str, Any]]:
    pool = _content_words(f"{methods} {results}")
    issues: list[dict[str, Any]] = []
    for claim in claims:
        sentence = str(claim.get("text") or "")
        words = _content_words(sentence)
        if words and words.isdisjoint(pool):
            issues.append(
                _issue(
                    "support",
                    sentence,
                    (methods + " " + results).strip(),
                    "The claim shares no content word of length 4 or more with methods or results.",
                )
            )
    return issues


def _kaggle_result(results_path: str | Path | None) -> dict[str, Any]:
    if results_path is not None:
        path = Path(results_path)
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
            return {
                "where": payload.get("where"),
                "status": payload.get("status"),
                "log": payload.get("log"),
                "kernel_url": payload.get("kernel_url"),
            }
    return {
        "where": "not_run",
        "status": "not_run",
        "log": "",
        "kernel_url": None,
        "detail": "There is no results file.",
    }
