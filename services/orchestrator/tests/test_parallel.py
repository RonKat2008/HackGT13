import os
import time
from pathlib import Path

os.environ["ARX_EMBEDDER"] = "hash"

import paper_audit
from paper_audit import SPECIALISTS, audit_paper

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DEMO = FIXTURES / "demo_paper.pdf"


def test_demo_paper_audit_stays_under_60s_with_stable_events(tmp_path, monkeypatch):
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    monkeypatch.setenv("RUN_DB", str(tmp_path / "parallel.sqlite"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")

    def fake_lookup(query, entry, transport=None):
        time.sleep(0.05)
        return {
            "reference": query,
            "queried": [
                {
                    "catalog": "crossref",
                    "status": "no_match",
                    "candidate_title": "",
                    "doi": "",
                    "score": 0.0,
                }
            ],
        }

    def fake_jev(claim_text, source_text, transport=None, api_key=None):
        time.sleep(0.05)
        return {
            "label": "supported",
            "confidence": 0.6,
            "probs": {"supported": 0.6},
            "not_run": False,
        }

    real_attach = paper_audit.reference_index.attach

    def attach_calling_lookup(claims, references_text, transport=None):
        # Bypass the pytest early-return so the monkeypatched lookup runs.
        return real_attach(claims, references_text, transport=object())

    monkeypatch.setattr("catalogs.lookup", fake_lookup)
    monkeypatch.setattr("references.attach", attach_calling_lookup)
    monkeypatch.setattr("jev.judge_claim", fake_jev)

    events: list[tuple[str, str]] = []

    def recorder(job_id: str, specialist: str, state: str, detail: str) -> None:
        events.append((specialist, state))

    started = time.perf_counter()
    result = audit_paper(DEMO, "job-parallel", recorder=recorder)
    elapsed = time.perf_counter() - started
    print(f"audit_paper elapsed seconds: {elapsed:.3f}")

    expected: list[tuple[str, str]] = []
    for name in SPECIALISTS:
        expected.append((name, "started"))
        expected.append((name, "finished"))
    assert events == expected
    assert list(SPECIALISTS) == [name for name, state in events if state == "started"]
    assert elapsed < 60
    assert result["claims"]
