import threading
import time

import desk
import paper_audit
import verify as claim_verify
from app import app
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "playbook.sqlite"))
    monkeypatch.setenv("ARXIV_LISTINGS", "0")
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    return TestClient(app)


def _conference(client: TestClient) -> str:
    response = client.post(
        "/conferences",
        json={"name": "ICLR desk", "contact_email": "chairs@example.edu"},
    )
    assert response.status_code == 200
    return response.json()["conference_id"]

METRICS_KEYS = {
    "conference_id",
    "papers",
    "claims",
    "resolved_deterministic",
    "resolved_lya",
    "escalated_jev",
    "avg_jev_rounds",
    "citation_cache_hits",
    "citation_cache_misses",
    "paper_cache_hits",
    "paper_cache_misses",
    "lya_batches",
    "claims_per_lya_batch",
    "time_to_first_finding_ms",
    "median_paper_ms",
}


def test_running_paper_streams_deterministic_claim_and_progress(tmp_path, monkeypatch):
    release = threading.Event()
    original = claim_verify.judge_with_lya

    def slow_judge(*args, **kwargs):
        if not release.wait(timeout=5):
            return
        return original(*args, **kwargs)

    monkeypatch.setattr(claim_verify, "judge_with_lya", slow_judge)
    monkeypatch.setattr(paper_audit.claim_verify, "judge_with_lya", slow_judge)

    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    submit = client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001"]},
    )
    assert submit.status_code == 200
    job_id = client.get(f"/desk/conferences/{conference_id}").json()["papers"][0]["job_id"]

    client.post(f"/desk/conferences/{conference_id}/run", json={})

    saw_claim = False
    for _ in range(200):
        paper = client.get(f"/desk/papers/{job_id}").json()
        if paper["status"] == "running" and any(
            "95.2" in str(c.get("text") or "") for c in paper.get("claims") or []
        ):
            saw_claim = True
            break
        time.sleep(0.05)

    release.set()

    assert saw_claim, "95.2 claim should appear while the paper is still running"

    desk = client.get(f"/desk/conferences/{conference_id}").json()
    progress = desk.get("progress") or {}
    assert progress.get("papers_running", 0) >= 1

    metrics = client.get(f"/desk/metrics?conference_id={conference_id}").json()
    assert METRICS_KEYS <= set(metrics.keys())
