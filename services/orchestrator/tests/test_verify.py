import hashlib
import os
from pathlib import Path

os.environ["ARX_EMBEDDER"] = "hash"

from jev import DEFAULT_CAP
from models import Evidence, is_finding
from paper_audit import audit_paper
from verify import build_source_text, cache_key, finished_sentence, judge_claims, review_uncertain

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HALLUCINATED = FIXTURES / "hallucinated.pdf"
JUDGED = {"label": "contradicted", "confidence": 0.82, "probs": {"contradicted": 0.82}, "not_run": False}


def _recorder():
    calls: list[tuple[str, str, str, str]] = []

    def record(job_id: str, specialist: str, state: str, detail: str) -> None:
        calls.append((job_id, specialist, state, detail))

    return calls, record


def _claim(
    text: str,
    claim_type: str,
    evidence: list[dict] | None = None,
    *,
    section: str = "abstract",
    claim_id: str = "c1",
) -> dict:
    return {
        "claim_id": claim_id,
        "job_id": "job-a4",
        "text": text,
        "page": 1,
        "section": section,
        "claim_type": claim_type,
        "verdict": "not_checked",
        "confidence": 0.0,
        "depth": "consistency",
        "rounds": 0,
        "reason": "",
        "evidence": evidence or [],
        "steps": ["Located claim on page 1"],
        "catalog": None,
        "computation": None,
    }


def _scripted(monkeypatch, answers):
    calls: list[tuple[str, str]] = []

    def judge(claim_text, source_text, transport=None, api_key=None):
        calls.append((claim_text, source_text))
        answer = answers(claim_text, source_text) if callable(answers) else answers
        return dict(answer)

    monkeypatch.setattr("jev.judge_claim", judge)
    return calls


def test_source_text_tags_support_and_notes_a_missing_number() -> None:
    claim = _claim(
        "Accuracy reached 95.2% on the public benchmark.",
        "numerical",
        [
            {
                "page": 1,
                "section": "results",
                "text": "The model accuracy was 61.0%.",
                "role": "supports",
                "source": "paper",
            },
            {
                "page": 1,
                "section": "results",
                "text": "The model accuracy was 61.0%.",
                "role": "contradicts",
                "source": "paper",
            },
        ],
    )
    source = build_source_text(claim)
    assert "[p.1] The model accuracy was 61.0%." in source
    assert "61.0" in source
    assert "Missing: 95.2" in source
    assert cache_key(claim["text"], source) == hashlib.sha256((claim["text"] + source).encode()).hexdigest()


def test_comparison_and_semantic_source_text() -> None:
    comparison = _claim(
        "The model improves by 7.8 percentage points over the strongest baseline.",
        "numerical_comparison",
        [
            {
                "page": 4,
                "section": "results",
                "text": "Ours reaches 89.2 and the strongest baseline reaches 84.7.",
                "role": "supports",
                "source": "paper",
            },
            {
                "page": 4,
                "section": "results",
                "text": "The gap in the table is 4.5 points.",
                "role": "contradicts",
                "source": "paper",
            },
        ],
        section="results",
    )
    comparison_source = build_source_text(comparison)
    assert "[p.4] Ours reaches 89.2 and the strongest baseline reaches 84.7." in comparison_source
    assert "4.5" in comparison_source
    assert "Missing: 7.8" in comparison_source

    semantic = _claim(
        "We show the method is robust under distribution shift.",
        "semantic",
        [
            {
                "page": 3,
                "section": "results",
                "text": "The method stayed stable when the input shifted.",
                "role": "supports",
                "source": "paper",
            }
        ],
        section="discussion",
    )
    semantic_source = build_source_text(semantic)
    assert "[p.3] The method stayed stable when the input shifted." in semantic_source
    assert "Missing:" not in semantic_source

    empty = _claim(
        "We demonstrate that the bound holds for every trial we ran.",
        "semantic",
        [],
        section="discussion",
    )
    assert build_source_text(empty).startswith("Missing:")


def test_judge_stores_verdict_confidence_and_steps(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    calls = _scripted(monkeypatch, JUDGED)
    claim = _claim(
        "Accuracy reached 95.2% on the public benchmark.",
        "numerical",
        [
            {
                "page": 2,
                "section": "results",
                "text": "The model accuracy was 61.0%.",
                "role": "contradicts",
                "source": "paper",
            }
        ],
    )
    claim["steps"] = [
        "Located claim on page 1",
        "Retrieved supporting evidence",
        "Searched for contradictory evidence",
    ]
    judge_claims([claim])
    assert len(calls) == 1
    assert "[p.2]" in calls[0][1]
    assert "Missing: 95.2" in calls[0][1]
    assert claim["verdict"] == "contradicted"
    assert claim["confidence"] == 0.82
    assert claim["evidence"][0]["role"] == "contradicts"
    Evidence.model_validate(claim["evidence"][0])
    located = next(index for index, step in enumerate(claim["steps"]) if "Located claim" in step)
    support = claim["steps"].index("Retrieved supporting evidence")
    searched = claim["steps"].index("Searched for contradictory evidence")
    judged = claim["steps"].index("Jev judgment")
    assert located < support < searched < judged
    assert is_finding(claim)


def test_cache_skips_a_second_identical_call(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    calls = _scripted(monkeypatch, JUDGED)
    evidence = [
        {
            "page": 1,
            "section": "results",
            "text": "The model accuracy was 61.0%.",
            "role": "contradicts",
            "source": "paper",
        }
    ]
    text = "Accuracy reached 95.2% on the public benchmark."
    first = _claim(text, "numerical", evidence, claim_id="first")
    second = _claim(text, "numerical", evidence, claim_id="second")
    judge_claims([first])
    judge_claims([second])
    assert len(calls) == 1
    assert second["verdict"] == "contradicted"
    assert second["confidence"] == 0.82
    assert "Jev judgment" in second["steps"]

    changed = _claim(
        text,
        "numerical",
        [
            {
                "page": 3,
                "section": "discussion",
                "text": "A different passage with no shared figure.",
                "role": "supports",
                "source": "paper",
            }
        ],
        claim_id="third",
    )
    judge_claims([changed])
    assert len(calls) == 2

    import sqlite3

    conn = sqlite3.connect(tmp_path / "cache.sqlite")
    rows = conn.execute("SELECT cache_key, label, confidence FROM jev_cache").fetchall()
    conn.close()
    assert len(rows) == 2
    stored = {row[0] for row in rows}
    assert cache_key(text, build_source_text(first)) in stored


def test_claims_past_the_default_cap_are_not_sent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    calls = _scripted(
        monkeypatch,
        {"label": "supported", "confidence": 0.8, "probs": {}, "not_run": False},
    )
    claims = []
    for index in range(DEFAULT_CAP + 1):
        claims.append(
            _claim(
                f"Trial {index} reached {index}.5% accuracy on the held-out split.",
                "numerical",
                [
                    {
                        "page": 1,
                        "section": "results",
                        "text": f"Trial {index} reached {index}.5% accuracy on the held-out split.",
                        "role": "supports",
                        "source": "paper",
                    }
                ],
                section="methods",
                claim_id=f"c{index}",
            )
        )
    judge_claims(claims)
    assert len(calls) == DEFAULT_CAP
    assert claims[0]["verdict"] == "supported"
    assert claims[DEFAULT_CAP]["verdict"] == "not_checked"
    assert claims[DEFAULT_CAP]["confidence"] == 0.0
    assert not is_finding(claims[DEFAULT_CAP])
    assert "Jev judgment" not in claims[DEFAULT_CAP]["steps"]


def test_missing_key_is_not_checked_and_keeps_the_number_issue(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("Jev must not be called without a key")

    monkeypatch.setattr("jev.judge_claim", boom)
    monkeypatch.setattr("httpx.Client", boom)
    calls, record = _recorder()
    result = audit_paper(HALLUCINATED, "job-offline", recorder=record)
    numerical = next(
        claim
        for claim in result["claims"]
        if claim["claim_type"] == "numerical" and "95.2" in claim["text"]
    )
    assert numerical["verdict"] == "contradicted"
    assert numerical["confidence"] == 1.0
    assert "Jev not configured" in numerical["steps"]
    assert "Jev judgment" not in numerical["steps"]
    assert is_finding(numerical)
    assert any("results" in step for step in numerical["steps"])
    number = next(issue for issue in result["issues"] if issue["issue_type"] == "number")
    assert "95.2" in number["claim_text"] or "95.2" in number["evidence_span"]
    assert number["jev_label"] == "contradicted"
    detail = next(item[3] for item in calls if item[1] == "verify" and item[2] == "finished")
    assert detail != "Jev is not wired to this desk yet."
    assert "not configured" in detail.lower()
    assert finished_sentence(result["claims"]) == detail

    from batches import _db
    from desk import _ensure_desk

    with _db() as conn:
        _ensure_desk(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "jev_cache" in tables


def test_hallucinated_metric_is_contradicted_when_jev_says_so(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    seen: list[str] = []

    def judge(claim_text, source_text, transport=None, api_key=None):
        seen.append(source_text)
        if "95.2" in claim_text:
            return dict(JUDGED)
        if claim_text.startswith("We show"):
            return {"label": "not_mentioned", "confidence": 0.7, "probs": {}, "not_run": False}
        return {"label": "supported", "confidence": 0.4, "probs": {}, "not_run": False}

    monkeypatch.setattr("jev.judge_claim", judge)
    calls, record = _recorder()
    result = audit_paper(HALLUCINATED, "job-jev", recorder=record)
    numerical = next(
        claim
        for claim in result["claims"]
        if claim["claim_type"] == "numerical" and "95.2" in claim["text"]
    )
    source = next(text for text in seen if "Missing: 95.2" in text)
    assert "[p." in source
    assert "61.0" in source
    assert numerical["verdict"] == "contradicted"
    assert numerical["confidence"] == 0.82
    assert is_finding(numerical)
    for item in numerical["evidence"]:
        Evidence.model_validate(item)
    for marker in (
        "Located claim",
        "Retrieved supporting evidence",
        "Searched for contradictory evidence",
        "Jev judgment",
    ):
        assert any(marker in step for step in numerical["steps"])
    detail = next(item[3] for item in calls if item[1] == "verify" and item[2] == "finished")
    assert detail != "Jev is not wired to this desk yet."
    assert "judged" in detail.lower()
    number = next(issue for issue in result["issues"] if issue["issue_type"] == "number")
    assert number["jev_label"] == "contradicted"

    from batches import _db
    from desk import _claims_for_job, _ensure_desk, _persist_claims

    with _db() as conn:
        _ensure_desk(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "jev_cache" in tables
        _persist_claims(conn, "job-jev", result["claims"])
        conn.commit()
        stored = _claims_for_job(conn, "job-jev")
    saved = next(claim for claim in stored if claim["claim_id"] == numerical["claim_id"])
    assert saved["verdict"] == "contradicted"
    assert saved["confidence"] == 0.82
    assert saved["evidence"]
    assert any("Jev judgment" in step for step in saved["steps"])


def test_network_failure_is_not_checked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    _scripted(
        monkeypatch,
        {"label": "not_mentioned", "confidence": 0.0, "probs": {}, "not_run": True},
    )
    claim = _claim("Accuracy reached 95.2% on the public benchmark.", "numerical")
    judge_claims([claim])
    assert claim["verdict"] == "not_checked"
    assert claim["verdict"] != "unresolved"
    assert claim["confidence"] == 0.0


def test_findings_follow_the_verdict_rules(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    answers = {
        "low": {"label": "not_mentioned", "confidence": 0.69, "probs": {}, "not_run": False},
        "high": {"label": "not_mentioned", "confidence": 0.70, "probs": {}, "not_run": False},
    }

    def judge(claim_text, source_text, transport=None, api_key=None):
        key = "high" if "high confidence" in claim_text else "low"
        return dict(answers[key])

    monkeypatch.setattr("jev.judge_claim", judge)
    low = _claim(
        "We show a low confidence semantic result here.",
        "semantic",
        [{"page": 2, "section": "results", "text": "An unrelated clause.", "role": "supports", "source": "paper"}],
        section="discussion",
        claim_id="low",
    )
    high = _claim(
        "We show a high confidence semantic result here.",
        "semantic",
        [{"page": 2, "section": "results", "text": "An unrelated clause.", "role": "supports", "source": "paper"}],
        section="discussion",
        claim_id="high",
    )
    citation = _claim("Smith reports a prior result (Smith, 2099).", "citation", claim_id="cite")
    judge_claims([low, high, citation])
    assert low["verdict"] == "not_mentioned"
    assert high["verdict"] == "not_mentioned"
    assert is_finding(high)
    assert not is_finding(low)
    assert citation["verdict"] == "not_checked"
    assert not is_finding(citation)
    ambiguous = dict(high)
    ambiguous["verdict"] = "ambiguous"
    assert not is_finding(ambiguous)


def test_only_numerical_comparison_and_semantic_are_sent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    calls = _scripted(
        monkeypatch,
        {"label": "supported", "confidence": 0.55, "probs": {}, "not_run": False},
    )
    claims = [
        _claim("Accuracy reached 12.0% on the split.", "numerical", claim_id="n"),
        _claim("The model improves by 3.0 points over the baseline.", "numerical_comparison", claim_id="cmp"),
        _claim("We show the training run is robust.", "semantic", claim_id="sem"),
        _claim("Prior work is cited here (Lee, 2020).", "citation", claim_id="cite"),
        _claim("The table contains 891 rows in the public release.", "dataset", claim_id="data"),
    ]
    judge_claims(claims)
    assert len(calls) == 3
    assert {claim["verdict"] for claim in claims[:3]} == {"supported"}
    assert claims[3]["verdict"] == "not_checked"
    assert claims[4]["verdict"] == "not_checked"


def test_number_contradiction_survives_a_disagreeing_jev(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    claim = _claim("Our model achieves 95.2% accuracy on the held-out benchmark.", "numerical")
    claim["verdict"] = "contradicted"
    claim["confidence"] = 1.0
    claim["steps"].append("Compared the abstract number with the results.")

    def judge(*_args, **_kwargs):
        return {"label": "not_mentioned", "confidence": 0.02, "probs": {}, "not_run": False}

    monkeypatch.setattr("jev.judge_claim", judge)
    judge_claims([claim])
    assert claim["verdict"] == "contradicted"
    assert claim["confidence"] == 1.0
    assert "Jev judgment" in claim["steps"]
    assert is_finding(claim)


def test_critic_does_not_reopen_a_number_contradiction(monkeypatch) -> None:
    monkeypatch.setenv("ARX_ROUNDS", "live")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    claim = _claim("Our model achieves 95.2% accuracy on the held-out benchmark.", "numerical")
    claim["verdict"] = "contradicted"
    claim["confidence"] = 0.02
    claim["steps"].extend(
        [
            "Compared the abstract number with the results.",
            "Jev judgment",
        ]
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("a settled number contradiction must stay settled")

    monkeypatch.setattr("verify.critic", boom)
    monkeypatch.setattr("jev.judge_claim", boom)
    review_uncertain([claim])
    assert claim["verdict"] == "contradicted"
