"""Batch Lya: one generate_many for local misses; Jev only on rejects."""

import lya
from lya import DEFAULT_THRESHOLD, judge_claims, threshold
from models import NUMBER_LOCK, deterministic_final
from verify import judge_with_lya

FAKE_OPENROUTER = "test-openrouter-key-not-real"


def _claim(text: str, claim_type: str, evidence: list[dict] | None = None, **extra) -> dict:
    return {
        "claim_id": extra.get("claim_id", "c1"),
        "job_id": "job-batch",
        "text": text,
        "page": 1,
        "section": extra.get("section", "abstract"),
        "claim_type": claim_type,
        "verdict": extra.get("verdict", "not_checked"),
        "confidence": extra.get("confidence", 0.0),
        "depth": "consistency",
        "rounds": 0,
        "reason": "",
        "evidence": evidence or [],
        "steps": ["Located claim on page 1"],
        "catalog": None,
        "computation": extra.get("computation"),
    }


def _enable_local(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "lya.sqlite"))
    monkeypatch.setenv("ARX_LYA", "live")
    monkeypatch.setenv("LYA_MODEL", "local")
    monkeypatch.setenv("LYA_THRESHOLD", "0.90")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER)
    monkeypatch.setattr("lya_local.adapter_dir", lambda _model: tmp_path)


def _fake_generate_many(monkeypatch) -> dict:
    state = {"calls": [], "users": []}

    def generate_many(_path, _system, users: list[str]) -> list[str]:
        state["calls"].append(len(users))
        state["users"] = list(users)
        return [
            '{"verdict": "supported", "confidence": 0.95}'
            for _ in users
        ]

    monkeypatch.setattr("lya_local.generate_many", generate_many)
    return state


def test_lya_threshold_remains_ninety() -> None:
    assert DEFAULT_THRESHOLD == 0.90
    assert threshold() == 0.90


def test_two_uncached_claims_one_generate_many_batch(tmp_path, monkeypatch) -> None:
    _enable_local(monkeypatch, tmp_path)
    batch = _fake_generate_many(monkeypatch)
    c1 = _claim(
        "Accuracy reached 95.2%.",
        "numerical",
        claim_id="b1",
        evidence=[{"section": "results", "text": "61.0% accuracy."}],
    )
    c2 = _claim(
        "Recall was 88.1%.",
        "numerical",
        claim_id="b2",
        evidence=[{"section": "results", "text": "Recall 88.1%."}],
    )
    judge_with_lya([c1, c2])
    assert batch["calls"] == [2]
    assert c1["verdict"] == "supported"
    assert c2["verdict"] == "supported"
    assert "Lya verdict" in c1["steps"]
    assert "Jev judgment" not in c1["steps"]


def test_cached_claim_skipped_in_generate_many(tmp_path, monkeypatch) -> None:
    _enable_local(monkeypatch, tmp_path)
    evidence = [{"section": "results", "text": "The model accuracy was 61.0%."}]
    model = "local"
    key = lya.cache_key("Accuracy reached 61.0%.", evidence, model)
    conn = lya._connect()
    try:
        conn.execute(
            "INSERT INTO lya_cache (cache_key, verdict, confidence, created_at) VALUES (?, ?, ?, ?)",
            (key, "supported", 0.97, "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    batch = _fake_generate_many(monkeypatch)
    cached = _claim("Accuracy reached 61.0%.", "numerical", evidence=evidence, claim_id="cached")
    fresh = _claim(
        "F1 was 0.91.",
        "numerical",
        claim_id="fresh",
        evidence=[{"section": "results", "text": "F1 0.91."}],
    )
    judge_with_lya([cached, fresh])
    assert batch["calls"] == [1]
    assert cached["verdict"] == "supported"
    assert cached["confidence"] == 0.97
    assert fresh["verdict"] == "supported"


def test_deterministic_final_not_sent_to_generate_many(tmp_path, monkeypatch) -> None:
    _enable_local(monkeypatch, tmp_path)
    batch = _fake_generate_many(monkeypatch)
    locked = _claim(
        "Accuracy reached 95.2%.",
        "numerical",
        claim_id="locked",
        verdict="contradicted",
        confidence=1.0,
        evidence=[{"section": "results", "text": "61.0%."}],
    )
    locked["steps"].append(NUMBER_LOCK)
    assert deterministic_final(locked)

    rerun = _claim(
        "Of the 891 passengers, 342 survived.",
        "dataset",
        claim_id="rerun",
        verdict="reproduced",
        confidence=1.0,
        computation={"status": "reproduced", "actual": 342, "expected": 342, "formula": "x"},
    )
    assert deterministic_final(rerun)

    open_claim = _claim(
        "We improve over the baseline.",
        "semantic",
        claim_id="open",
        evidence=[{"section": "abstract", "text": "Our method."}],
    )
    judge_with_lya([locked, rerun, open_claim])
    assert batch["calls"] == [1]
    assert locked["verdict"] == "contradicted"
    assert rerun["verdict"] == "reproduced"
    assert open_claim["verdict"] == "supported"


def test_high_confidence_lya_accept_does_not_call_jev(tmp_path, monkeypatch) -> None:
    _enable_local(monkeypatch, tmp_path)

    def generate_many(_path, _system, users: list[str]) -> list[str]:
        return [
            '{"verdict": "contradicted", "confidence": 0.96}'
            for _ in users
        ]

    monkeypatch.setattr("lya_local.generate_many", generate_many)

    def boom(*_args, **_kwargs):
        raise AssertionError("Jev must not run when Lya accepts")

    monkeypatch.setattr("jev.judge_claim", boom)
    claim = _claim(
        "Accuracy reached 95.2%.",
        "numerical",
        evidence=[{"section": "results", "text": "61.0%.", "role": "contradicts", "source": "paper"}],
    )
    judge_with_lya([claim])
    assert claim["verdict"] == "contradicted"
    assert claim["confidence"] == 0.96
    assert "Lya verdict" in claim["steps"]
    assert "Jev judgment" not in claim["steps"]


def test_judge_claims_api_path_uses_judge_claim(monkeypatch) -> None:
    monkeypatch.delenv("LYA_MODEL", raising=False)
    calls: list[str] = []

    def fake_judge(claim_text, evidence=None, **_kwargs):
        calls.append(claim_text)
        return {"verdict": "supported", "confidence": 0.92, "not_run": False}

    monkeypatch.setattr("lya.judge_claim", fake_judge)
    pairs = [
        ("Claim A.", [{"text": "ev A"}]),
        ("Claim B.", [{"text": "ev B"}]),
    ]
    results = judge_claims(pairs)
    assert len(results) == 2
    assert calls == ["Claim A.", "Claim B."]
    assert results[0]["verdict"] == "supported"


def test_generate_many_empty_returns_empty_list() -> None:
    from pathlib import Path

    from lya_local import generate_many

    assert generate_many(Path("/tmp"), "sys", []) == []
