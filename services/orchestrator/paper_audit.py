from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import fitz

import claims as claim_extract
import evidence as evidence_index
import probe
import references as reference_index
import shelf
import tables as table_check
import verify as claim_verify

from models import STAGES

SPECIALISTS = list(STAGES)

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
    typed_claims: list[dict[str, Any]] = []
    claims_error = ""
    hidden = False
    hidden_sentence = ""
    kaggle: dict[str, Any] = {}
    pages = 0

    def emit(specialist: str, state: str, detail: str = "") -> None:
        record(job_id, specialist, state, detail)
        events.append({"specialist": specialist, "state": state, "detail": detail})

    def parse() -> None:
        nonlocal text, pages, sections
        text = load_paper(path)
        pages = _page_count(path)
        sections = split_sections(text)

    def claims_step() -> None:
        nonlocal claims, typed_claims, claims_error
        claims = _extract_claims(sections)
        try:
            typed_claims = claim_extract.extract_claims(path, job_id, sections)
        except Exception as exc:
            typed_claims = []
            claims_error = f" Typed claim extract failed: {exc}"

    def evidence() -> None:
        try:
            evidence_index.attach(path, sections, typed_claims)
        except Exception:
            pass
        issues.extend(
            _support_issues(
                claims,
                sections.get("methods", ""),
                sections.get("results", ""),
            )
        )

    def citations() -> None:
        issues.extend(_citation_issues(claims, sections.get("references", "")))
        reference_index.attach(typed_claims, sections.get("references", ""))

    def numbers() -> None:
        issues.extend(_number_issues(sections.get("abstract", ""), sections.get("results", "")))

    def tables() -> None:
        table_check.annotate(path, typed_claims)

    def dataset() -> None:
        issues.extend(dataset_issues(claims, text))

    def reproduce() -> None:
        nonlocal kaggle
        if results_path is not None:
            kaggle = _kaggle_result(results_path)
        elif repro is not None:
            try:
                produced = repro(claims, sections)
            except Exception:
                produced = None
            if isinstance(produced, dict):
                kaggle = produced
            elif isinstance(produced, list):
                failed = next(
                    (item for item in produced if item.get("status") == "could_not_reproduce"),
                    None,
                )
                kaggle = {
                    "where": "local",
                    "status": "not_run" if not produced else "ran",
                    "log": "" if failed is None else str(failed.get("log") or ""),
                    "kernel_url": None,
                    "detail": (
                        "No public table to rerun."
                        if not produced
                        else str(failed.get("log") or "A dataset claim could not be reproduced.")
                        if failed
                        else "The public table matches the count written in the paper."
                    ),
                    "computations": produced,
                    "claim_text": "" if failed is None else str(failed.get("formula") or ""),
                }
            else:
                kaggle = _kaggle_result(None)
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

    def verify() -> None:
        claim_verify.judge_claims(typed_claims)
        _settle_local(typed_claims, sections, kaggle, path)

    def critic() -> None:
        claim_verify.review_uncertain(typed_claims)

    def stamp() -> None:
        collapsed = unique_issues(issues)
        issues.clear()
        issues.extend(collapsed)
        for issue in issues:
            issue["jev_label"] = "contradicted"
            reason = str(issue.get("reason") or "").strip()
            if not reason or "fraudulent" in reason.lower():
                issue["reason"] = "The claim is contradicted by the paper evidence."
            else:
                issue["reason"] = reason.split("\n")[0].strip()

    steps: dict[str, Callable[[], None]] = {
        "parse": parse,
        "claims": claims_step,
        "evidence": evidence,
        "citations": citations,
        "numbers": numbers,
        "tables": tables,
        "dataset": dataset,
        "reproduce": reproduce,
        "verify": verify,
        "critic": critic,
        "stamp": stamp,
    }
    if auc is not None:
        hidden = probe.should_hide(auc)
        if hidden:
            hidden_sentence = HIDDEN_SENTENCE
    for name in SPECIALISTS:
        emit(name, "started", _STARTED[name])
        steps[name]()
        finished = _finished_detail(
            name,
            pages=pages,
            sections=sections,
            claims=typed_claims if name in {"claims", "verify", "critic", "tables"} else claims,
            issues=issues,
            kaggle=kaggle,
        )
        if name == "claims":
            finished = finished + claims_error
        emit(name, "finished", finished)
    _annotate_pages(path, issues)

    result: dict[str, Any] = {
        "issues": issues,
        "claims": typed_claims,
        "events": events,
        "hidden": hidden,
        "kaggle": kaggle,
        "section_quality": sections.get("section_quality", "ok"),
    }
    if hidden_sentence:
        result["hidden_sentence"] = hidden_sentence
    return result


_STARTED = {
    "parse": "Opening the PDF and splitting sections.",
    "claims": "Pulling verifiable claims.",
    "evidence": "Retrieving evidence for each claim.",
    "citations": "Checking citations.",
    "numbers": "Checking numbers across sections.",
    "tables": "Reading tables.",
    "dataset": "Looking for named datasets.",
    "reproduce": "Looking for a public table to rerun.",
    "verify": "Asking Jev to judge each claim.",
    "critic": "Reviewing uncertain verdicts.",
    "stamp": "Stamping findings.",
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
    if name == "parse":
        count = pages if pages > 0 else 0
        unit = "page" if count == 1 else "pages"
        return f"Opened {count} {unit}. {_section_sentence(sections)}"
    if name == "claims":
        count = len(claims)
        unit = "claim" if count == 1 else "claims"
        return f"Pulled {count} {unit}."
    if name == "citations":
        count = len(
            {
                " ".join(str(issue.get("evidence_span") or "").split()).lower()
                for issue in issues
                if issue.get("issue_type") == "citation" and str(issue.get("evidence_span") or "").strip()
            }
        )
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
    if name == "evidence":
        count = _count(issues, "support")
        if count == 0:
            return "Claims have support in the methods or results."
        if count == 1:
            return "1 claim has no support in the methods or results."
        return f"{count} claims have no support in the methods or results."
    if name == "tables":
        checked = sum(1 for claim in claims if isinstance(claim, dict) and claim.get("computation"))
        if checked == 0:
            return "No table arithmetic checked yet."
        unit = "comparison" if checked == 1 else "comparisons"
        return f"Checked {checked} table {unit}."
    if name == "dataset":
        count = _count(issues, "dataset")
        if count == 0:
            return "Named datasets appear in the paper."
        if count == 1:
            return "1 named dataset does not appear in the paper."
        return f"{count} named datasets do not appear in the paper."
    if name == "reproduce":
        return _kaggle_sentence(kaggle)
    if name == "verify":
        return claim_verify.finished_sentence(claims)
    if name == "critic":
        return claim_verify.critic_sentence(claims)
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


def unique_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one copy of a finding that names the same span and the same reason."""
    kept: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], int] = {}
    for issue in issues:
        kind = str(issue.get("issue_type") or "")
        span = " ".join(str(issue.get("evidence_span") or "").split()).lower()
        reason = " ".join(str(issue.get("reason") or "").split()).lower()
        key = (kind, span or reason)
        if key in seen:
            prior = kept[seen[key]]
            prior["_repeats"] = int(prior.get("_repeats") or 1) + 1
            continue
        copy = dict(issue)
        copy["_repeats"] = 1
        seen[key] = len(kept)
        kept.append(copy)
    for issue in kept:
        repeats = int(issue.pop("_repeats", 1))
        if repeats > 1 and issue.get("issue_type") == "support":
            issue["reason"] = (
                f"{repeats} claims share no content word of length 4 or more with methods or results."
            )
        span = " ".join(str(issue.get("evidence_span") or "").split())
        claim = " ".join(str(issue.get("claim_text") or "").split())
        if len(span) > 180 and claim:
            issue["evidence_span"] = claim
    return kept


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


def _settle_local(
    claims: list[dict[str, Any]],
    sections: dict[str, str],
    kaggle: dict[str, Any],
    path: str | Path,
) -> None:
    references = str(sections.get("references") or "")
    results = str(sections.get("results") or "")
    pool = _content_words(f"{sections.get('methods', '')} {results}")
    for claim in claims:
        if str(claim.get("verdict") or "not_checked") != "not_checked":
            continue
        kind = str(claim.get("claim_type") or "")
        if kind == "citation":
            _settle_citation(claim, references)
        elif kind in {"numerical", "numerical_comparison"} and claim.get("section") == "abstract":
            _settle_abstract_number(claim, results, path)
        elif kind == "semantic":
            _settle_semantic(claim, pool)
        elif kind == "dataset":
            _settle_dataset(claim, kaggle)


def _settle_citation(claim: dict[str, Any], references: str) -> None:
    if claim.get("catalog"):
        return
    match = CITATION_RE.search(str(claim.get("text") or ""))
    if match is None:
        return
    author, year = match.group(1), match.group(2)
    token = f"{author}, {year}"
    refs_lower = references.lower()
    found = token.lower() in refs_lower or (author.lower() in refs_lower and year in references)
    steps = list(claim.get("steps") or [])
    if found:
        claim["verdict"] = "supported"
        claim["confidence"] = 1.0
        steps.append("Matched the citation to the reference list.")
    else:
        claim["verdict"] = "unresolved"
        claim["confidence"] = 1.0
        claim["reason"] = f"The citation ({token}) does not appear in the references."
        steps.append("The citation is missing from the reference list.")
    claim["steps"] = steps


def _settle_abstract_number(claim: dict[str, Any], results: str, path: str | Path) -> None:
    numbers = NUMBER_RE.findall(str(claim.get("text") or ""))
    if not numbers:
        return
    missing = [token for token in numbers if token not in results]
    steps = list(claim.get("steps") or [])
    steps.append("Compared the abstract number with the results.")
    claim["steps"] = steps
    claim["confidence"] = 1.0
    if missing:
        claim["verdict"] = "contradicted"
        claim["reason"] = f"The number {missing[0]} in the abstract is absent from the results."
    else:
        claim["verdict"] = "supported"
    snippet = next((line.strip() for line in results.splitlines() if line.strip()), "Results")
    evidence = list(claim.get("evidence") or [])
    evidence.append(
        {
            "page": claim.get("page") if isinstance(claim.get("page"), int) else _text_page(path, str(claim.get("text") or "")),
            "section": "abstract",
            "text": str(claim.get("text") or ""),
            "role": "contradicts" if missing else "supports",
            "source": "paper",
        }
    )
    evidence.append(
        {
            "page": _text_page(path, snippet),
            "section": "results",
            "text": snippet,
            "role": "contradicts" if missing else "supports",
            "source": "paper",
        }
    )
    claim["evidence"] = evidence


def _text_page(path: str | Path, text: str) -> int | None:
    if not str(text or "").strip():
        return None
    doc = fitz.open(path)
    try:
        return claim_extract.find_page(doc, str(text))
    finally:
        doc.close()


def _settle_semantic(claim: dict[str, Any], pool: set[str]) -> None:
    words = _content_words(str(claim.get("text") or ""))
    if not words:
        return
    steps = list(claim.get("steps") or [])
    claim["confidence"] = 1.0
    if words.isdisjoint(pool):
        claim["verdict"] = "contradicted"
        claim["reason"] = "The claim shares no content word of length 4 or more with methods or results."
        steps.append("Checked the claim against the methods and results.")
    else:
        claim["verdict"] = "supported"
        steps.append("The claim shares wording with the methods or results.")
    claim["steps"] = steps


def _settle_dataset(claim: dict[str, Any], kaggle: dict[str, Any]) -> None:
    status = str(kaggle.get("status") or "")
    if status not in {"match", *TEST_FAIL_STATUSES}:
        return
    target = str(kaggle.get("claim_text") or "")
    text = str(claim.get("text") or "")
    if not target or (target not in text and text not in target):
        return
    steps = list(claim.get("steps") or [])
    steps.append("Compared the claim with the public table.")
    claim["steps"] = steps
    claim["confidence"] = 1.0
    if status == "match":
        claim["verdict"] = "reproduced"
    else:
        claim["verdict"] = "could_not_reproduce"
        claim["reason"] = str(kaggle.get("detail") or "The stored claim test log disagrees with the paper.")


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
