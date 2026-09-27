import os

from fastapi.testclient import TestClient

import voice
from app import app


def _paper() -> dict:
    return {
        "job_id": "job",
        "arxiv_id": "0000.00003",
        "title": "Demo",
        "summary": {"analyzed": 2, "supported": 1},
        "issues": [],
        "claims": [
            {
                "text": "We show the model generalizes.",
                "claim_type": "semantic",
                "verdict": "insufficient_evidence",
                "confidence": 0.2,
                "reason": "The passage was too short.",
                "page": 1,
                "evidence": [{"text": "The model was trained on WMT."}],
                "computation": None,
            },
            {
                "text": "Smith 2099 reported the result.",
                "claim_type": "citation",
                "verdict": "unresolved",
                "page": 2,
                "evidence": [],
                "computation": None,
            },
            {
                "text": "Ours improves by 7.8.",
                "claim_type": "numerical_comparison",
                "verdict": "contradicted",
                "page": 3,
                "evidence": [],
                "computation": {"formula": "89.2 - 84.7 = 4.5"},
            },
        ],
    }


def test_briefing_names_the_verdict_and_skips_banned_words():
    script = voice.briefing(_paper())
    assert "Demo" in script
    assert "Needs a person" in script
    assert "Unresolved citation" in script
    for banned in ("fake", "fraudulent", "fabricated", "ai-written"):
        assert banned not in script.lower()


def test_why_script_uses_the_open_claim_and_its_passage():
    script = voice.why_script(_paper(), "Why is this one here?", "We show the model generalizes.")
    assert "We show the model generalizes." in script
    assert "insufficient evidence" in script
    assert "trained on WMT" in script
    assert "stayed unsure" in script


def test_bot_refuses_a_verdict_change_and_can_open_or_explain():
    paper = _paper()

    def boom(*_args, **_kwargs):
        raise AssertionError("the model should not be asked to change a verdict")

    answer, action = voice.finish("Please change the verdict to supported", [paper], boom, boom, "ICLR")
    assert action["type"] == "refuse"
    assert "does not change a verdict" in answer

    opened = voice.desk_action("Open the finding", [paper])
    assert opened["type"] == "open"
    assert opened["page"] == 1

    explained = voice.desk_action("Explain the formula", [paper])
    assert explained["formula"] == "89.2 - 84.7 = 4.5"
    prose, explain = voice.finish("Explain the formula", [paper], lambda *_a, **_k: None, lambda _papers: "Stored.", "ICLR")
    assert explain["type"] == "explain"
    assert "89.2 - 84.7 = 4.5" in prose

    missing, empty = voice.finish(
        "Explain the formula",
        [{**paper, "claims": []}],
        lambda *_a, **_k: None,
        lambda _papers: "Stored.",
        "ICLR",
    )
    assert empty["formula"] == ""
    assert "No stored formula" in missing


def test_tts_stays_quiet_without_a_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert voice.tts("Hello from the desk") is None
    assert "XAI_API_KEY" not in os.environ


def test_speak_route_returns_a_script_without_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_DB", str(tmp_path / "playbook.sqlite"))
    monkeypatch.setenv("ARXIV_LISTINGS", "0")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    client = TestClient(app)
    conference = client.post(
        "/conferences",
        json={"name": "ICLR desk", "contact_email": "chairs@example.edu"},
    ).json()["conference_id"]
    added = client.post(
        f"/desk/conferences/{conference}/submissions",
        json={"lines": ["0000.00003"]},
    )
    assert added.status_code == 200
    job_id = client.get(f"/desk/conferences/{conference}").json()["papers"][0]["job_id"]
    spoken = client.post(f"/desk/papers/{job_id}/speak", json={"question": "", "claim": ""})
    assert spoken.status_code == 200
    body = spoken.json()
    assert body["audio"] is None
    assert body["voice"] == "browser"
    assert body["script"]
    lowered = body["script"].lower()
    for banned in ("fake", "fraudulent", "fabricated", "ai-written"):
        assert banned not in lowered
