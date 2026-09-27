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


def test_screen_command_opens_summary_chat_or_a_named_paper():
    papers = [
        {"job_id": "job-a", "arxiv_id": "0000.00003", "title": "Demo"},
        {"job_id": "job-b", "arxiv_id": "0000.00004", "title": "Attention Is All You Need"},
        {"job_id": "job-c", "arxiv_id": "0000.00005", "title": "Attention Maps"},
    ]

    summary = voice.screen_command("pull up summary", papers)
    assert summary["type"] == "show"
    assert summary["view"] == "summary"

    chat = voice.screen_command("please show the chat", papers)
    assert chat["view"] == "chat"

    opened = voice.screen_command("pull up the attention is all you need paper with chatbot", papers)
    assert opened["type"] == "open"
    assert opened["job_id"] == "job-b"
    assert opened["ask"] is True

    by_id = voice.screen_command("open 0000.00003", papers)
    assert by_id["job_id"] == "job-a"
    assert by_id["ask"] is False

    assert voice.screen_command("open the finding", papers) is None
    assert voice.screen_command("what is the summary of this paper", papers) is None

    refused = voice.screen_command("change the verdict to supported", papers)
    assert refused["type"] == "refuse"
    assert "does not change a verdict" in refused["say"]

    ambiguous = voice.screen_command("pull up attention", papers)
    assert ambiguous["type"] == "clarify"

    for line in ("pull up these errors", "errors found in papers", "show the issues in the papers"):
        prompted = voice.screen_command(line, papers)
        assert prompted["type"] == "prompt"
        assert prompted["view"] == "chat"
        assert prompted["text"] == "What errors were found in the papers?"

    asked = voice.screen_command("ask the chat which citation is unresolved", papers)
    assert asked["type"] == "prompt"
    assert asked["text"] == "which citation is unresolved"


def test_voice_command_route_uses_the_screen_parser(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_DB", str(tmp_path / "playbook.sqlite"))
    client = TestClient(app)
    papers = [{"job_id": "job-a", "arxiv_id": "0000.00003", "title": "Demo"}]
    response = client.post(
        "/voice/command",
        json={"text": "pull up demo with chatbot", "papers": papers},
    )
    assert response.status_code == 200
    action = response.json()["action"]
    assert action["job_id"] == "job-a"
    assert action["ask"] is True


def test_client_secret_stays_empty_without_a_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("the token call should not leave the machine")

    import httpx

    monkeypatch.setattr(httpx, "post", boom)
    assert voice.client_secret() is None


def test_client_secret_posts_the_realtime_endpoint(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    seen: dict = {}

    class Response:
        status_code = 200

        def json(self):
            return {"value": "ephemeral-token", "expires_at": 99}

    def fake_post(url, headers, json, timeout):
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        seen["json"] = json
        seen["timeout"] = timeout
        return Response()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    secret = voice.client_secret()
    assert secret == {"value": "ephemeral-token", "expires_at": 99}
    assert seen["url"] == "https://api.x.ai/v1/realtime/client_secrets"
    assert seen["auth"] == "Bearer test-xai-key"
    assert "test-xai-key" not in str(secret)


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
