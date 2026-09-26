"""A1: the desk verification contract. Both tracks build against this."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import batches
import desk
import paper_audit
from models import (
    FINDING_VERDICTS,
    STAGES,
    ClaimType,
    DeskClaim,
    Depth,
    Verdict,
    is_finding,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXAMPLE = json.loads((FIXTURES / "desk_paper_example.json").read_text())


def test_stage_names_are_fixed() -> None:
    assert STAGES == [
        "parse",
        "claims",
        "evidence",
        "citations",
        "numbers",
        "tables",
        "dataset",
        "reproduce",
        "verify",
        "critic",
        "stamp",
    ]
    assert paper_audit.SPECIALISTS == STAGES


def test_example_claims_validate_and_cover_every_verdict() -> None:
    claims = [DeskClaim.model_validate(item) for item in EXAMPLE["claims"]]
    assert len(claims) == 12
    seen = {claim.verdict for claim in claims}
    assert seen == set(Verdict)
    assert {claim.claim_type for claim in claims} == set(ClaimType)
    assert {claim.depth for claim in claims} == set(Depth)
    for claim in claims:
        assert 0 <= claim.rounds <= 3
        for item in claim.evidence:
            assert item.text.strip()
    with_catalog = [claim for claim in claims if claim.catalog is not None]
    with_computation = [claim for claim in claims if claim.computation is not None]
    assert with_catalog and with_computation


def test_example_summary_matches_the_claims() -> None:
    summary = desk.summarize_claims(EXAMPLE["claims"])
    assert summary == EXAMPLE["summary"]
    assert desk.finding_count(EXAMPLE["claims"], []) == EXAMPLE["finding_count"]


def test_finding_rule() -> None:
    for verdict in FINDING_VERDICTS:
        assert is_finding({"verdict": verdict, "claim_type": "citation"})
    assert not is_finding({"verdict": "supported", "claim_type": "semantic"})
    assert not is_finding({"verdict": "not_checked", "claim_type": "numerical"})
    assert is_finding({"verdict": "not_mentioned", "claim_type": "semantic", "confidence": 0.79})
    assert not is_finding({"verdict": "not_mentioned", "claim_type": "semantic", "confidence": 0.4})
    assert not is_finding({"verdict": "not_mentioned", "claim_type": "numerical", "confidence": 0.9})


def test_extra_fields_are_rejected() -> None:
    bad = {**EXAMPLE["claims"][0], "likeness": 0.9}
    with pytest.raises(Exception):
        DeskClaim.model_validate(bad)


def test_demo_paper_is_registered() -> None:
    assert "0000.00003" in batches.LOCAL_PAPERS
    path, author = batches.LOCAL_PAPERS["0000.00003"]
    assert path.name == "demo_paper.pdf"
    assert author


def test_paper_claims_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "contract.sqlite"))
    with batches._db() as conn:
        desk._ensure_desk(conn)
        columns = desk._columns(conn, "paper_issues")
        assert {"claim_id", "confidence", "depth", "verdict"} <= columns
        desk._persist_claims(conn, "job-x", EXAMPLE["claims"])
        conn.commit()
        loaded = desk._claims_for_job(conn, "job-x")
    assert [claim["claim_id"] for claim in loaded] == [
        claim["claim_id"] for claim in EXAMPLE["claims"]
    ]
    for stored, original in zip(loaded, EXAMPLE["claims"]):
        assert stored["verdict"] == original["verdict"]
        assert stored["evidence"] == original["evidence"]
        assert stored["computation"] == original["computation"]
        assert stored["catalog"] == original["catalog"]
    assert desk.summarize_claims(loaded) == EXAMPLE["summary"]


def test_paper_desk_carries_claims_and_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "contract.sqlite"))
    monkeypatch.setenv("ARXIV_LISTINGS", "0")
    from app import app

    client = TestClient(app)
    conf = client.post("/conferences", json={"name": "Contract", "contact_email": "c@x.org"})
    assert conf.status_code == 200, conf.text
    conference_id = conf.json()["conference_id"]
    added = client.post(
        f"/desk/conferences/{conference_id}/submissions", json={"lines": ["0000.00001"]}
    )
    assert added.status_code == 200, added.text
    paper = client.get(f"/desk/conferences/{conference_id}").json()["papers"][0]
    assert paper["claims"] == []
    assert paper["summary"] == desk._empty_summary()
    assert paper["finding_count"] == 0
    with batches._db() as conn:
        desk._persist_claims(conn, paper["job_id"], EXAMPLE["claims"])
        conn.commit()
    body = client.get(f"/desk/papers/{paper['job_id']}").json()
    assert body["summary"] == EXAMPLE["summary"]
    assert body["finding_count"] == EXAMPLE["finding_count"]
    assert len(body["claims"]) == 12
