"""Spoken briefing and chat actions. Neither path changes a stored verdict."""

from __future__ import annotations

import base64
import os
import re
from typing import Any

from models import is_finding

PROMPT = """You answer one conference chair about the papers on their list.
They can name a paper by its title or with @ and an arXiv id.
Use only the paper text, the issue list, and the stored claims you are given.
You can list findings, point at a page, and explain a stored formula.
You cannot change a verdict. If asked, say the desk does not change a verdict from chat.
Talk about unresolved citations, missing numbers, unsupported claims, and failed reruns.
A sentence that needs a person was left unsure. Leave it that way.
Stay with the stored citation, number, formula, and passage.
If a paper has not been read yet, say so. Quote a short span when you point at a problem.
Mention each finding once. Do not repeat the same citation, number, or claim.
Keep the reply to a few sentences the chair can use.
"""

_REFUSE_VERDICT = (
    "change the verdict",
    "set the verdict",
    "mark it supported",
    "mark this supported",
    "override the verdict",
    "clear the finding",
)


def needs_person(claim: dict[str, Any]) -> bool:
    verdict = str(claim.get("verdict") or "")
    if verdict == "insufficient_evidence":
        return True
    return is_finding(claim) and verdict == "not_mentioned"


def formula_of(claim: dict[str, Any]) -> str:
    computation = claim.get("computation")
    if not isinstance(computation, dict):
        return ""
    return str(computation.get("formula") or "").strip()


def claim_lines(paper: dict[str, Any]) -> str:
    lines: list[str] = []
    for claim in paper.get("claims") or []:
        formula = formula_of(claim)
        if not is_finding(claim) and not formula:
            continue
        text = " ".join(str(claim.get("text") or "").split())[:180]
        reason = " ".join(str(claim.get("reason") or "").split())
        page = claim.get("page")
        page_bit = f" p.{page}" if isinstance(page, int) else ""
        extra = f" formula {formula}" if formula else ""
        why = f" — {reason}" if reason else ""
        lines.append(
            f"- {claim.get('claim_type')} {claim.get('verdict')}{page_bit}: {text}{extra}{why}"
        )
        if len(lines) >= 8:
            break
    return "\n".join(lines) or "- none"


def desk_action(question: str, papers: list[dict[str, Any]]) -> dict[str, Any] | None:
    asked = " ".join(question.lower().split())
    if any(phrase in asked for phrase in _REFUSE_VERDICT):
        return {"type": "refuse"}
    if not papers:
        return None
    if "formula" in asked:
        for paper in papers:
            for claim in paper.get("claims") or []:
                formula = formula_of(claim)
                if not formula:
                    continue
                return {
                    "type": "explain",
                    "job_id": paper["job_id"],
                    "arxiv_id": paper["arxiv_id"],
                    "title": paper.get("title") or paper["arxiv_id"],
                    "page": claim.get("page") if isinstance(claim.get("page"), int) else None,
                    "text": str(claim.get("text") or ""),
                    "formula": formula,
                }
        return {"type": "explain", "formula": ""}
    opens = re.search(r"\b(open|show)\b", asked) and any(
        word in asked for word in ("page", "finding", "paper", "pdf", "claim")
    )
    if opens:
        paper = papers[0]
        claim = next((item for item in paper.get("claims") or [] if is_finding(item)), None)
        if claim is None and paper.get("claims"):
            claim = paper["claims"][0]
        text = ""
        page = None
        if claim:
            text = str(claim.get("text") or "")
            page = claim.get("page") if isinstance(claim.get("page"), int) else None
        elif paper.get("issues"):
            issue = paper["issues"][0]
            text = str(issue.get("evidence_span") or issue.get("claim_text") or "")
            page = issue.get("page") if isinstance(issue.get("page"), int) else None
        return {
            "type": "open",
            "job_id": paper["job_id"],
            "arxiv_id": paper["arxiv_id"],
            "title": paper.get("title") or paper["arxiv_id"],
            "page": page,
            "text": text,
        }
    if "finding" in asked:
        return {"type": "list"}
    return None


def briefing(paper: dict[str, Any]) -> str:
    title = str(paper.get("title") or paper.get("arxiv_id") or "This paper")
    summary = paper.get("summary") if isinstance(paper.get("summary"), dict) else {}
    analyzed = int(summary.get("analyzed") or 0)
    supported = int(summary.get("supported") or 0)
    claims = list(paper.get("claims") or [])
    person = [claim for claim in claims if needs_person(claim)]
    findings = [claim for claim in claims if is_finding(claim)]
    parts = [f"{title}."]
    if analyzed:
        parts.append(f"{analyzed} claims analyzed. {supported} supported.")
    if not findings:
        parts.append("Nothing on this paper needs a finding.")
    elif person and len(person) == len(findings):
        parts.append(f"{len(person)} sentences need a person. They were left unsure.")
    else:
        parts.append(f"{len(findings)} findings to review.")
    for claim in person[:2]:
        text = " ".join(str(claim.get("text") or "").split())[:220]
        if text:
            parts.append(f"Needs a person: {text}")
    citation = next(
        (
            claim
            for claim in claims
            if claim.get("claim_type") == "citation"
            and claim.get("verdict") in {"unresolved", "supported"}
        ),
        None,
    )
    if citation:
        label = "Unresolved citation" if citation.get("verdict") == "unresolved" else "Resolved citation"
        text = " ".join(str(citation.get("text") or "").split())[:180]
        if text:
            parts.append(f"{label}: {text}")
    return " ".join(parts)


def why_script(paper: dict[str, Any], question: str, claim_text: str) -> str:
    claims = list(paper.get("claims") or [])
    needle = " ".join(claim_text.split())[:80]
    match = None
    if needle:
        match = next(
            (
                claim
                for claim in claims
                if needle in " ".join(str(claim.get("text") or "").split())
            ),
            None,
        )
    if match is None:
        match = next((claim for claim in claims if needs_person(claim) or is_finding(claim)), None)
    if match is None:
        return "This paper has no stored claim to explain."
    bits = [f"The sentence says: {' '.join(str(match.get('text') or '').split())[:300]}"]
    verdict = str(match.get("verdict") or "not_checked").replace("_", " ")
    bits.append(f"The stored verdict is {verdict}.")
    reason = " ".join(str(match.get("reason") or "").split())
    if reason:
        bits.append(reason)
    formula = formula_of(match)
    if formula:
        bits.append(f"The formula is {formula}.")
    evidence = match.get("evidence") or []
    if evidence and isinstance(evidence[0], dict):
        passage = " ".join(str(evidence[0].get("text") or "").split())
        if passage and not passage.startswith("Neighbor window"):
            bits.append(f"The passage beside it says: {passage[:240]}")
    if "why" in question.lower() and needs_person(match):
        bits.append("A person should compare that sentence with the page. The desk stayed unsure.")
    return " ".join(bits)


def speak(paper: dict[str, Any], question: str = "", claim: str = "") -> dict[str, Any]:
    asked = question.strip()
    script = why_script(paper, asked, claim) if asked else briefing(paper)
    script = " ".join(script.split())
    audio = tts(script)
    return {"script": script, "audio": audio, "voice": "grok" if audio else "browser"}


def bind_speak(load: Any) -> Any:
    def speak_paper(job_id: str, question: str = "", claim: str = "") -> dict[str, Any]:
        return speak(load(job_id), question, claim)

    return speak_paper


def finish(
    question: str,
    papers: list[dict[str, Any]],
    grok: Any,
    local: Any,
    conference: str,
) -> tuple[str, dict[str, Any] | None]:
    action = desk_action(question, papers)
    if action and action.get("type") == "refuse":
        return "The desk does not change a verdict from chat. The stored read stays as it is.", action
    if action and action.get("type") == "explain" and not action.get("formula"):
        return (
            "No stored formula is on these papers. A gain gets a formula only when a nearby table has an Ours row.",
            action,
        )
    answer = grok(conference, question, papers) or local(papers)
    if action and action.get("type") == "explain":
        formula = str(action.get("formula") or "")
        if formula and formula not in answer:
            answer = f"The table gives {formula}. {answer}"
    return answer, action


def tts(text: str) -> str | None:
    spoken = " ".join(text.split())[:4000]
    if not spoken:
        return None
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    try:
        import httpx

        response = httpx.post(
            "https://api.x.ai/v1/tts",
            headers={"Authorization": f"Bearer {key}"},
            json={"text": spoken, "voice_id": "eve", "language": "en"},
            timeout=45,
        )
    except Exception:
        return None
    if response.status_code != 200 or not response.content:
        return None
    if "json" in response.headers.get("content-type", ""):
        return None
    return base64.b64encode(response.content).decode("ascii")
