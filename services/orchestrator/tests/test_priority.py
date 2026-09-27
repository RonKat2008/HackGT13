"""T10: Jev escalation order and drain queue order."""

from __future__ import annotations

import inspect

import desk
from models import NUMBER_LOCK, deterministic_final
from verify import judge_with_lya

FAKE_OPENROUTER = "test-openrouter-key-not-real"


def _enable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "priority.sqlite"))
    monkeypatch.setenv("ARX_LYA", "live")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER)
    monkeypatch.setenv("LYA_THRESHOLD", "0.90")
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key-not-real")


def _claim(text: str, claim_type: str = "semantic", **extra) -> dict:
    return {
        "claim_id": extra.get("claim_id", text[:8]),
        "job_id": "job-priority",
        "text": text,
        "page": 1,
        "section": extra.get("section", "abstract"),
        "claim_type": claim_type,
        "verdict": extra.get("verdict", "not_checked"),
        "confidence": extra.get("confidence", 0.0),
        "depth": "consistency",
        "rounds": 0,
        "reason": extra.get("reason", ""),
        "evidence": extra.get("evidence", []),
        "steps": list(extra.get("steps", ["Located claim on page 1"])),
        "catalog": extra.get("catalog"),
        "computation": extra.get("computation"),
    }


def _low_confidence_lya(monkeypatch) -> None:
    def judge_claims(pairs):
        return [
            {"verdict": "not_mentioned", "confidence": 0.4, "not_run": False}
            for _ in pairs
        ]

    monkeypatch.setattr("lya.judge_claims", judge_claims)


def _script_jev(monkeypatch) -> list[str]:
    order: list[str] = []

    def judge(claim_text, source_text, transport=None, api_key=None):
        order.append(claim_text)
        return {
            "label": "not_mentioned",
            "confidence": 0.55,
            "probs": {"not_mentioned": 0.55},
            "not_run": False,
        }

    monkeypatch.setattr("jev.judge_claim", judge)
    return order


def test_jev_prioritizes_number_miss_over_plain_uncertain(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)
    _low_confidence_lya(monkeypatch)
    jev_order = _script_jev(monkeypatch)

    plain = _claim("The method generalizes to unseen domains.", claim_id="plain")
    number_miss = _claim(
        "Accuracy reached 95.2% on the benchmark.",
        "numerical",
        claim_id="number",
        verdict="contradicted",
        evidence=[
            {
                "page": 2,
                "section": "results",
                "text": "The model accuracy was 61.0%.",
                "role": "contradicts",
                "source": "paper",
            }
        ],
    )
    assert not deterministic_final(number_miss)

    judge_with_lya([plain, number_miss])
    assert jev_order[0] == number_miss["text"]
    assert plain["text"] in jev_order


def test_deterministic_final_not_sent_to_jev(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)
    _low_confidence_lya(monkeypatch)
    jev_order = _script_jev(monkeypatch)

    locked = _claim(
        "Accuracy reached 95.2% on the benchmark.",
        "numerical",
        claim_id="locked",
        verdict="contradicted",
        steps=["Located claim on page 1", NUMBER_LOCK],
    )
    open_claim = _claim("A semantic claim needs review.", claim_id="open")
    assert deterministic_final(locked)

    judge_with_lya([locked, open_claim])
    assert jev_order == [open_claim["text"]]
    assert "Jev judgment" not in locked.get("steps", [])


def test_jev_prioritizes_unresolved_citation_over_plain(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)
    _low_confidence_lya(monkeypatch)
    jev_order = _script_jev(monkeypatch)

    plain = _claim("Training used a standard optimizer.", claim_id="plain")
    unresolved = _claim(
        "We build on Smith et al. (2019).",
        claim_id="unresolved",
        verdict="unresolved",
        catalog={
            "reference": "Smith et al. (2019)",
            "queried": [
                {"catalog": "crossref", "status": "no_match", "score": 0.0},
                {"catalog": "openalex", "status": "no_match", "score": 0.0},
            ],
        },
    )

    judge_with_lya([plain, unresolved])
    assert jev_order[0] == unresolved["text"]
    assert plain["text"] in jev_order


def test_jev_order_number_miss_unresolved_then_plain(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch, tmp_path)
    _low_confidence_lya(monkeypatch)
    jev_order = _script_jev(monkeypatch)

    plain = _claim("The ablation removes batch norm.", claim_id="plain")
    unresolved = _claim(
        "Prior work is Jones (2020).",
        claim_id="unresolved",
        verdict="unresolved",
        catalog={
            "reference": "Jones (2020)",
            "queried": [{"catalog": "crossref", "status": "no_match", "score": 0.0}],
        },
    )
    number_miss = _claim(
        "F1 score is 0.91 in the abstract.",
        "numerical",
        claim_id="number",
        verdict="contradicted",
        evidence=[
            {
                "page": 3,
                "section": "results",
                "text": "F1 was 0.71 on the test set.",
                "role": "contradicts",
                "source": "paper",
            }
        ],
    )

    judge_with_lya([plain, unresolved, number_miss])
    assert number_miss["text"] == jev_order[0]
    assert unresolved["text"] == jev_order[1]
    assert plain["text"] == jev_order[2]


def test_drain_query_keeps_paper_jobs_position_order() -> None:
    source = inspect.getsource(desk._drain)
    assert "ORDER BY paper_jobs.position ASC" in source


def test_conference_metrics_one_bucket_per_claim(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "metrics.sqlite"))
    from desk import _db, _ensure_desk, conference_metrics

    conference_id = "conf-metrics"
    job_id = "job-metrics"
    with _db() as conn:
        _ensure_desk(conn)
        conn.execute(
            "INSERT INTO conferences (conference_id, name, contact_email) VALUES (?, ?, ?)",
            (conference_id, "Test", "chairs@example.edu"),
        )
        conn.execute(
            """
            INSERT INTO batches (batch_id, kind, name, arxiv_ids, conference_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("batch-1", "desk", "b", "[]", conference_id, "2026-01-01T00:00:00+00:00"),
        )
        conn.execute(
            """
            INSERT INTO paper_jobs (
                job_id, batch_id, arxiv_id, status, issue_count, position
            ) VALUES (?, ?, ?, 'done', 0, 0)
            """,
            (job_id, "batch-1", "0000.00001"),
        )
        conn.execute(
            """
            INSERT INTO paper_claims (
                claim_id, job_id, position, text, claim_type, verdict, depth,
                steps_json, rounds, computation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "c-det",
                job_id,
                0,
                "Locked number",
                "numerical",
                "contradicted",
                "consistency",
                '["Located claim", "Compared the abstract number with the results."]',
                0,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_claims (
                claim_id, job_id, position, text, claim_type, verdict, depth,
                steps_json, rounds, computation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "c-jev",
                job_id,
                1,
                "Jev claim",
                "semantic",
                "not_mentioned",
                "consistency",
                '["Located claim", "Lya verdict", "Jev judgment"]',
                2,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_claims (
                claim_id, job_id, position, text, claim_type, verdict, depth,
                steps_json, rounds, computation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "c-lya",
                job_id,
                2,
                "Lya claim",
                "semantic",
                "supported",
                "consistency",
                '["Located claim", "Lya verdict"]',
                0,
                None,
            ),
        )
        conn.commit()

    metrics = conference_metrics(conference_id)
    assert metrics["resolved_deterministic"] == 1
    assert metrics["escalated_jev"] == 1
    assert metrics["resolved_lya"] == 1
    assert metrics["citation_cache_hits"] == 0
    assert metrics["paper_cache_hits"] == 0
