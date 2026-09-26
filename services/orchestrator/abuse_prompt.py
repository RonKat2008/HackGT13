"""Signs of abused papers, and the prompt that asks a model to find them.

AI-assisted writing is not a flag. A flag needs a quoted span and a checkable
failure: a fabricated citation, a number the results do not contain, a dataset
or test that does not exist, a tortured phrase, or a one-shot pattern that
only counts when another fabrication is already present.
"""

from __future__ import annotations

import json
import re
from typing import Any

FABRICATION_KINDS = frozenset({"citation", "number", "dataset", "test", "support"})
ISSUE_KINDS = FABRICATION_KINDS
WRITING_ONLY = re.compile(
    r"\b(written by (an )?ai|ai-generated prose|sounds like (gpt|a model)|"
    r"llm writing style|high ai-likeness)\b",
    re.I,
)

SYSTEM_PROMPT = """You audit one research paper for fabricated claims and one-shot abuse. AI-assisted writing is normal. Do not flag fluent prose, grammar help, an LLM-usage disclosure, or an AI-likeness score.

Return JSON only: {"flags":[{"kind":"...","evidence_span":"...","reason":"..."}]}
kind is one of: citation, number, dataset, test, support, one_shot.
evidence_span is a short quote copied from the paper. If you cannot quote it, omit the flag.
reason is one sentence a chair can read. Never say the paper is fraudulent. Never say it was written by AI.

Flag only these, and only with the quote:

citation — NeurIPS 2025 failure modes, from the study of 100 fabricated citations:
- Total fabrication: authors, title, venue, and identifier do not match any real work.
- Partial attribute corruption: some metadata is real and the rest is wrong (real authors, wrong title or year).
- Identifier hijacking: a real arXiv id or DOI points at a different paper than the one named.
- Placeholder: "Firstname Lastname", "arXiv:XXXX", "to be updated", or an unfilled template.
- Semantic hallucination: a plausible title in the right field that does not exist.
A citation that exists but does not say what the sentence claims is still a citation flag.

number — a percent, p-value, error bar, or metric in the abstract or introduction that the results section does not contain. Invented "confidence scores" or "novelty scores" with no table are numbers.

dataset — a named dataset, benchmark, or code release that the methods never specify, or that does not resolve to a public dataset.

test — the paper claims a rerun, ablation, or metric on a public dataset and the test log disagrees, or the method describes a procedure that cannot produce the claimed measurement.

support — a tortured phrase: an established technical term replaced by a nonsensical synonym (for example "counterfeit consciousness" for "artificial intelligence"). Quote both the weird phrase and say the established term. Do not flag ordinary synonyms or style.

one_shot — use this only together with at least one citation, number, dataset, test, or support flag. It means the paper looks like a single generated pass: several broken citations, or a SOTA number with no dataset, split, or sample size. One typo is not one_shot. AI-like prose alone is not one_shot.

If nothing above is present, return {"flags":[]}.
"""


def parse_model_flags(raw: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a model JSON reply into chair-facing flags. Drops style-only hits."""
    payload = raw if isinstance(raw, dict) else _load(raw)
    items = payload.get("flags") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    kept: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        span = str(item.get("evidence_span") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if kind == "placeholder":
            kind = "citation"
        if kind not in ISSUE_KINDS and kind != "one_shot":
            continue
        if not span or not reason:
            continue
        if WRITING_ONLY.search(reason):
            continue
        kept.append({"kind": kind, "evidence_span": span, "reason": reason})

    fabrications = [flag for flag in kept if flag["kind"] in FABRICATION_KINDS]
    if not fabrications:
        return []
    return kept


def _load(raw: str) -> dict[str, Any]:
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
