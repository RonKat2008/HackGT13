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


_NAV = (
    "pull up",
    "bring up",
    "show me",
    "switch to",
    "go to",
    "open up",
    "open",
    "show",
    "pull",
    "bring",
)
_FILLER = {"the", "a", "an", "me", "my", "please", "to", "up", "desk", "list"}
_SKIP = _FILLER | {
    "and",
    "with",
    "for",
    "from",
    "this",
    "that",
    "paper",
    "papers",
    "summary",
    "chat",
    "chatbot",
    "about",
    "into",
    "using",
    "their",
    "have",
    "been",
    "when",
    "what",
    "your",
    "just",
}
_CHAT_PHRASES = (
    "with the chatbot",
    "with chatbot",
    "with the chat",
    "with chat",
    "and the chatbot",
    "and chatbot",
    "chat bot",
    "chatbot",
)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9.@-]+", " ", text.lower()).split())


def _strip_phrases(text: str, phrases: tuple[str, ...]) -> str:
    padded = f" {text} "
    for phrase in phrases:
        padded = padded.replace(f" {phrase} ", " ")
    return " ".join(padded.split())


def _only(query: str, words: set[str]) -> bool:
    meaningful = [token for token in query.split() if token not in _FILLER]
    return bool(meaningful) and all(token in words for token in meaningful)


def _tokens(title: str) -> list[str]:
    return [word for word in _norm(title).split() if len(word) >= 4 and word not in _SKIP]


def _find_paper(query: str, papers: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, bool]:
    asked = _norm(query)
    ranked: list[tuple[int, str]] = []
    for paper in papers:
        job_id = str(paper.get("job_id") or "")
        if not job_id:
            continue
        title = _norm(str(paper.get("title") or ""))
        arxiv = _norm(str(paper.get("arxiv_id") or ""))
        score = 0
        if arxiv and arxiv in asked:
            score = 100
        elif title and title in asked:
            score = 80
        else:
            tokens = _tokens(title)
            hits = [token for token in tokens if re.search(rf"\b{re.escape(token)}\b", asked)]
            if not hits:
                continue
            if len(hits) == len(tokens):
                score = 70
            elif len(tokens) == 1:
                score = 60
            elif len(hits) >= 2:
                score = 50 + len(hits)
            elif len(hits[0]) >= 5:
                score = 40
            else:
                continue
        ranked.append((score, job_id))
    if not ranked:
        return None, False
    ranked.sort(key=lambda item: item[0], reverse=True)
    best = ranked[0][0]
    leaders = {job_id for score, job_id in ranked if score == best}
    if len(leaders) > 1:
        return None, True
    found = next(paper for paper in papers if str(paper.get("job_id") or "") == next(iter(leaders)))
    return found, False


def _show(view: str) -> dict[str, Any]:
    say = "Summary." if view == "summary" else "Chat."
    return {"type": "show", "view": view, "say": say}


def _open(paper: dict[str, Any], ask: bool) -> dict[str, Any]:
    title = str(paper.get("title") or paper.get("arxiv_id") or "that paper")
    say = f"Opening {title} with the chatbot." if ask else f"Opening {title}."
    return {
        "type": "open",
        "job_id": str(paper.get("job_id") or ""),
        "arxiv_id": str(paper.get("arxiv_id") or ""),
        "title": title,
        "ask": ask,
        "say": say,
    }


def _error_line(asked: str) -> bool:
    return re.search(r"\b(errors?|issues|findings)\b", asked) is not None


def _chat_prompt(text: str) -> dict[str, Any]:
    return {"type": "prompt", "view": "chat", "text": text}


def screen_command(question: str, papers: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Map a spoken line to a screen. This does not change a stored verdict."""
    asked = _norm(question)
    if not asked:
        return None
    if any(phrase in asked for phrase in _REFUSE_VERDICT):
        return {
            "type": "refuse",
            "say": "The desk does not change a verdict from voice. The stored read stays as it is.",
        }
    ask_chat = re.match(r"^(?:please )?ask(?: the chat| chat) (.+)$", asked)
    if ask_chat and ask_chat.group(1).strip():
        return _chat_prompt(ask_chat.group(1).strip()[:500])
    if _error_line(asked):
        paper, ambiguous = _find_paper(_strip_phrases(asked, _NAV), papers)
        if paper is None and not ambiguous:
            return _chat_prompt("What errors were found in the papers?")
    if not re.search(r"\b(pull up|bring up|show me|switch to|go to|open up|open|show|pull|bring)\b", asked):
        return None
    query = _strip_phrases(asked, _NAV)
    ask = any(phrase in asked for phrase in ("with chatbot", "with the chatbot", "with chat", "chatbot"))
    query = _strip_phrases(query, _CHAT_PHRASES)
    meaningful = [token for token in query.split() if token not in _FILLER]
    if not meaningful:
        if "summary" in asked:
            return _show("summary")
        if "chat" in asked:
            return _show("chat")
        return None
    if _only(query, {"summary", "summaries"}):
        return _show("summary")
    if _only(query, {"chat", "chats", "chatbot", "bot"}):
        return _show("chat")
    paper, ambiguous = _find_paper(query, papers)
    if ambiguous:
        return {"type": "clarify", "say": "Which paper?"}
    if paper:
        return _open(paper, ask or "chat" in asked)
    if re.search(r"\bsummar(y|ies)\b", query):
        return _show("summary")
    if re.search(r"\bchats?\b", query):
        return _show("chat")
    return None


def client_secret() -> dict[str, Any] | None:
    """Mint a short-lived realtime token. The API key never leaves the server."""
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    try:
        import httpx

        response = httpx.post(
            "https://api.x.ai/v1/realtime/client_secrets",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"expires_after": {"seconds": 300}},
            timeout=20,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except Exception:
        return None
    value = str(body.get("value") or "").strip()
    if not value:
        return None
    expires = body.get("expires_at")
    return {"value": value, "expires_at": expires if isinstance(expires, int) else None}


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
