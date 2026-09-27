import json
from pathlib import Path

import httpx

from lya import accepts, judge_claim
from models import TOOL_NAMES, ToolEvidence, deterministic_final, is_finding
from verify import judge_with_lya

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FAKE_XAI = "test-xai-key-not-real"
FAKE_OPENROUTER = "test-openrouter-key-not-real"


def _claim(text: str, claim_type: str, evidence: list[dict] | None = None, **extra) -> dict:
    claim = {
        "claim_id": extra.get("claim_id", "c1"),
        "job_id": "job-lya",
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
    return claim


def _enable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "lya.sqlite"))
    monkeypatch.setenv("ARX_LYA", "live")
    monkeypatch.setenv("XAI_API_KEY", FAKE_XAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER)
    monkeypatch.setenv("LYA_THRESHOLD", "0.90")


def _script_lya(monkeypatch, answer: dict) -> list:
    calls: list[str] = []

    def judge(claim_text, evidence=None, **_kwargs):
        calls.append(claim_text)
        return dict(answer)

    monkeypatch.setattr("lya.judge_claim", judge)
    return calls


def _script_jev(monkeypatch, answers) -> list:
    calls: list[str] = []

    def judge(claim_text, source_text, transport=None, api_key=None):
        calls.append(source_text)
        answer = answers(len(calls), source_text) if callable(answers) else answers
        return dict(answer)

    monkeypatch.setattr("jev.judge_claim", judge)
    return calls


def test_missing_xai_key_does_not_call_the_network(monkeypatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("Lya must not call the network without a key")

    monkeypatch.setattr("httpx.Client", boom)
    result = judge_claim("Accuracy reached 95.2%.", [{"text": "The model accuracy was 61.0%."}])
    assert result["not_run"] is True
    assert result["verdict"] == "not_checked"
    assert not accepts(result)


def test_weak_lya_contradiction_is_not_a_finding(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _script_lya(monkeypatch, {"verdict": "contradicted", "confidence": 0.4, "not_run": False})

    def boom(*_args, **_kwargs):
        raise AssertionError("Jev must not be called without a key")

    monkeypatch.setattr("jev.judge_claim", boom)
    claim = _claim(
        "Accuracy reached 95.2% on the public benchmark.",
        "numerical",
        [{"page": 2, "section": "results", "text": "The model accuracy was 61.0%.", "role": "contradicts", "source": "paper"}],
    )
    judge_with_lya([claim])
    assert claim["verdict"] == "not_checked"
    assert not is_finding(claim)
    assert "Lya verdict" in claim["steps"]
    assert "Jev not configured" in claim["steps"]
    assert claim["text"] == "Accuracy reached 95.2% on the public benchmark."


def test_high_confidence_lya_contradiction_does_not_call_jev(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)
    lya_calls = _script_lya(
        monkeypatch,
        {"verdict": "contradicted", "confidence": 0.96, "not_run": False},
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("Jev must not be called after a sure Lya contradiction")

    monkeypatch.setattr("jev.judge_claim", boom)
    claim = _claim(
        "Accuracy reached 95.2% on the public benchmark.",
        "numerical",
        [{"page": 2, "section": "results", "text": "The model accuracy was 61.0%.", "role": "contradicts", "source": "paper"}],
    )
    original = claim["text"]
    judge_with_lya([claim])
    assert lya_calls == [original]
    assert claim["verdict"] == "contradicted"
    assert claim["confidence"] == 0.96
    assert "Lya verdict" in claim["steps"]
    assert "Jev judgment" not in claim["steps"]
    assert is_finding(claim)
    assert claim["text"] == original


def test_low_confidence_lya_requests_a_table_search_then_jev_supports(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)
    _script_lya(monkeypatch, {"verdict": "ambiguous", "confidence": 0.42, "not_run": False})
    jev_calls = _script_jev(
        monkeypatch,
        lambda count, _source: (
            {"label": "not_mentioned", "confidence": 0.4, "probs": {}, "not_run": False}
            if count == 1
            else {"label": "supported", "confidence": 0.93, "probs": {}, "not_run": False}
        ),
    )
    requested: list[list[str]] = []

    def run_tools(claim, names, _context):
        requested.append(list(names))
        evidence = list(claim.get("evidence") or [])
        evidence.append(
            {
                "page": 4,
                "section": "results",
                "text": "Table 2 lists accuracy 94.1 after the requested table search.",
                "role": "supports",
                "source": "paper",
            }
        )
        claim["evidence"] = evidence
        return []

    monkeypatch.setattr("tools.run_tools", run_tools)
    claim = _claim(
        "Our method improves performance by 7.8 percentage points over the baseline.",
        "numerical_comparison",
        [{"page": 3, "section": "results", "text": "An early clause.", "role": "context", "source": "paper"}],
    )
    original = claim["text"]
    judge_with_lya([claim])
    assert claim["verdict"] == "supported"
    assert claim["confidence"] == 0.93
    assert "Lya verdict" in claim["steps"]
    assert "Jev requested search_tables" in claim["steps"]
    assert "Jev judgment" in claim["steps"]
    assert requested and requested[0][0] == "search_tables"
    assert len(requested[0]) <= 2
    assert all(name in TOOL_NAMES for name in requested[0])
    assert len(jev_calls) == 2
    assert claim["text"] == original
    assert not is_finding(claim)


def test_three_rounds_end_as_insufficient_evidence(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)
    _script_lya(monkeypatch, {"verdict": "not_mentioned", "confidence": 0.3, "not_run": False})
    _script_jev(
        monkeypatch,
        {"label": "not_mentioned", "confidence": 0.4, "probs": {}, "not_run": False},
    )

    def run_tools(claim, names, _context):
        evidence = list(claim.get("evidence") or [])
        evidence.append(
            {
                "page": 5,
                "section": "results",
                "text": f"Extra passage {len(evidence)} after {', '.join(names)}.",
                "role": "context",
                "source": "paper",
            }
        )
        claim["evidence"] = evidence
        return []

    monkeypatch.setattr("tools.run_tools", run_tools)
    claim = _claim("We show the bound holds for every trial we ran.", "semantic")
    original = claim["text"]
    judge_with_lya([claim])
    assert claim["verdict"] == "insufficient_evidence"
    assert claim["reason"] == "Requires human review"
    assert claim["rounds"] == 3
    assert any(step.startswith("Jev requested ") for step in claim["steps"])
    assert claim["text"] == original
    assert is_finding(claim)


def test_demo_titanic_counts_stay_computed(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)

    def boom(*_args, **_kwargs):
        raise AssertionError("a computed count must not be sent to Lya or Jev")

    monkeypatch.setattr("lya.judge_claim", boom)
    monkeypatch.setattr("jev.judge_claim", boom)
    survived = _claim(
        "Of the 891 passengers, 342 survived.",
        "dataset",
        verdict="reproduced",
        confidence=1.0,
        computation={
            "status": "reproduced",
            "actual": 342,
            "expected": 342,
            "formula": "COUNT(Survived, 1)",
        },
    )
    first_class = _claim(
        "317 passengers travelled in first class.",
        "numerical",
        claim_id="c-317",
        verdict="could_not_reproduce",
        confidence=1.0,
        computation={
            "status": "could_not_reproduce",
            "actual": 216,
            "expected": 317,
            "formula": "COUNT_EQ(Pclass, 1)",
        },
    )
    assert deterministic_final(survived)
    assert deterministic_final(first_class)
    judge_with_lya([survived, first_class])
    assert survived["verdict"] == "reproduced"
    assert survived["computation"]["actual"] == 342
    assert first_class["verdict"] == "could_not_reproduce"
    assert first_class["computation"]["actual"] == 216
    assert first_class["computation"]["expected"] == 317


def test_training_jsonl_includes_the_hard_negatives() -> None:
    rows = [
        json.loads(line)
        for line in (FIXTURES / "lya_train.jsonl").read_text().splitlines()
        if line.strip()
    ]
    labels = {row["label"] for row in rows}
    assert labels <= {"supported", "contradicted", "not_mentioned", "ambiguous"}
    claims = [row["claim"] for row in rows]
    assert any("95.2 F1" in claim for claim in claims)
    assert any("percentage points" in claim for claim in claims)
    assert any(row["evidence"][0]["section"] == "abstract" for row in rows)
    assert any("Table 2" in row["claim"] for row in rows)


def test_lya_cache_skips_a_second_identical_call(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "lya.sqlite"))
    hits = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"verdict": "supported", "confidence": 0.95}'}}]},
        )

    evidence = [{"page": 2, "section": "results", "text": "The model accuracy was 61.0%."}]
    first = judge_claim(
        "Accuracy reached 61.0% on the public benchmark.",
        evidence,
        transport=httpx.MockTransport(handler),
        api_key=FAKE_XAI,
    )
    second = judge_claim(
        "Accuracy reached 61.0% on the public benchmark.",
        evidence,
        transport=httpx.MockTransport(handler),
        api_key=FAKE_XAI,
    )
    assert first["verdict"] == "supported"
    assert first["confidence"] == 0.95
    assert second == first
    assert hits["n"] == 1


def test_number_lock_and_table_lock_are_final() -> None:
    number = _claim("Accuracy reached 95.2%.", "numerical", verdict="contradicted", confidence=1.0)
    number["steps"].append("Compared the abstract number with the results.")
    table = _claim("The gain is 7.8 percentage points.", "numerical_comparison", verdict="contradicted", confidence=1.0)
    table["steps"].append("Compared the claimed change with the table.")
    open_claim = _claim("We show the method is robust.", "semantic")
    assert deterministic_final(number)
    assert deterministic_final(table)
    assert not deterministic_final(open_claim)
