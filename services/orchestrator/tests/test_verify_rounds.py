import os

os.environ["ARX_EMBEDDER"] = "hash"

from loop import retry_guard_dropped
from models import Claim, PatchKind
from roles import critic
from verify import judge_claims, review_uncertain


def _claim(text: str, claim_type: str, evidence: list[dict] | None = None) -> dict:
    return {
        "claim_id": "round-1",
        "job_id": "job-a5",
        "text": text,
        "page": 1,
        "section": "discussion",
        "claim_type": claim_type,
        "verdict": "not_checked",
        "confidence": 0.0,
        "depth": "evidence",
        "rounds": 0,
        "reason": "",
        "evidence": evidence or [],
        "steps": ["Located claim on page 1"],
        "catalog": None,
        "computation": None,
    }


def _scripted(monkeypatch, answers):
    calls: list[str] = []

    def judge(claim_text, source_text, transport=None, api_key=None):
        calls.append(source_text)
        answer = answers(claim_text, source_text) if callable(answers) else answers
        return dict(answer)

    monkeypatch.setattr("jev.judge_claim", judge)
    return calls


def test_evidence_critic_drafts_a_span_window() -> None:
    patch = critic(
        Claim(
            id="c1",
            text="The metric is 0.81",
            type="number",
            evidence_span="The metric is 0.81",
            source_id="desk",
            source_kind="paper",
        ),
        "not_mentioned",
        ["evidence"],
    )
    assert patch.kind == PatchKind.SPAN_WINDOW
    assert patch.target == "evidence"
    assert patch.body == "neighbors:2"


def test_uncertain_claim_is_confident_on_round_two(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "rounds.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.setenv("ARX_ROUNDS", "live")
    calls = _scripted(
        monkeypatch,
        lambda _claim_text, source: (
            {"label": "supported", "confidence": 0.91, "probs": {}, "not_run": False}
            if "Neighbor window" in source
            else {"label": "not_mentioned", "confidence": 0.4, "probs": {}, "not_run": False}
        ),
    )
    claim = _claim(
        "We show the method is robust under distribution shift.",
        "semantic",
        [{"page": 3, "section": "results", "text": "An early clause.", "role": "supports", "source": "paper"}],
    )
    original = claim["text"]
    judge_claims([claim])
    review_uncertain([claim])
    assert claim["verdict"] == "supported"
    assert claim["confidence"] == 0.91
    assert "Round 2: widened to ±2 sentences" in claim["steps"]
    assert claim["rounds"] == 2
    assert claim["text"] == original
    assert not retry_guard_dropped(original, claim["text"])
    assert len(calls) == 2


def test_three_uncertain_rounds_require_human_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "rounds.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.setenv("ARX_ROUNDS", "live")
    _scripted(
        monkeypatch,
        {"label": "not_mentioned", "confidence": 0.4, "probs": {}, "not_run": False},
    )
    claim = _claim("We show the bound holds for every trial we ran.", "semantic")
    original = claim["text"]
    judge_claims([claim])
    review_uncertain([claim])
    assert claim["verdict"] == "insufficient_evidence"
    assert claim["reason"] == "Requires human review"
    assert claim["rounds"] == 3
    assert "Round 2: widened to ±2 sentences" in claim["steps"]
    assert "Round 3: widened to ±2 sentences" in claim["steps"]
    assert claim["text"] == original
    assert not retry_guard_dropped(original, claim["text"])


def test_widen_keeps_the_real_neighbor_and_the_window_marker() -> None:
    from verify import _widen

    claim = _claim("We show the bound holds for every trial we ran.", "semantic")
    claim["_neighbors"] = [
        {"page": 2, "section": "results", "text": "The previous sentence names the training split."},
        {"page": 2, "section": "results", "text": "The next sentence reports the held-out score."},
    ]
    _widen(claim, 2)
    texts = [item["text"] for item in claim["evidence"]]
    assert "The previous sentence names the training split." in texts
    assert "The next sentence reports the held-out score." in texts
    assert any(text.startswith("Neighbor window ±2") for text in texts)
