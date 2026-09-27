import time

from fastapi.testclient import TestClient

import desk
import imagine
from app import app
from imagine import (
    desk_summary,
    generate_clip,
    motion_prompt,
    parse_imagine,
    render_still,
)


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


def test_normal_question_returns_none() -> None:
    assert parse_imagine("What are the citation issues?") is None


def test_bare_imagine_returns_empty() -> None:
    assert parse_imagine("/Imagine") == ""
    assert parse_imagine("  /Imagine  ") == ""


def test_imagine_at_start() -> None:
    assert parse_imagine("/Imagine the citations") == "the citations"


def test_imagine_in_middle() -> None:
    assert parse_imagine("give me /Imagine a tour of the queue") == (
        "give me a tour of the queue"
    )


def test_imagine_at_end() -> None:
    assert parse_imagine("a tour /Imagine") == "a tour"


def test_imagination_is_not_the_command() -> None:
    assert parse_imagine("imagination") is None


def test_lowercase_imagine_is_not_the_command() -> None:
    assert parse_imagine("/imagine the citations") is None


def test_imagines_suffix_is_not_the_command() -> None:
    assert parse_imagine("/Imagines the citations") is None


def test_desk_summary_empty_includes_conference_name() -> None:
    text = desk_summary("NeurIPS Desk", [])
    assert "NeurIPS Desk" in text
    assert "no papers" in text.lower()


def test_desk_summary_empty_without_name() -> None:
    text = desk_summary("", [])
    assert "no papers" in text.lower()


def test_desk_summary_counts_issues_by_type() -> None:
    papers = [
        {
            "title": "Attention Is All You Need",
            "arxiv_id": "1706.03762",
            "status": "done",
            "issues": [
                {"issue_type": "citation"},
                {"issue_type": "number"},
                {"issue_type": "number"},
            ],
        }
    ]
    text = desk_summary("NeurIPS Desk", papers)
    assert "Attention Is All You Need" in text
    assert "done" in text
    assert "citation 1" in text
    assert "number 2" in text


def test_desk_summary_skips_ai_likeness() -> None:
    papers = [
        {
            "title": "Sample Paper",
            "arxiv_id": "1234.5678",
            "status": "done",
            "issues": [
                {"issue_type": "ai_likeness"},
                {"issue_type": "citation"},
            ],
        }
    ]
    text = desk_summary("Desk", papers)
    assert "ai_likeness" not in text
    assert "citation 1" in text


def test_desk_summary_uses_arxiv_id_without_title() -> None:
    papers = [
        {
            "arxiv_id": "1706.03762",
            "status": "queued",
            "issues": [],
        }
    ]
    text = desk_summary("Desk", papers)
    assert "1706.03762" in text
    assert "queued" in text


def test_ask_imagine_skips_grok_and_stores_payload(tmp_path, monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("_grok_answer should not be called")

    monkeypatch.setattr(desk, "_grok_answer", boom)
    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001", "0000.00002"]},
    )
    client.post(f"/desk/conferences/{conference_id}/run", json={"cap": 1})
    paper = None
    for _ in range(400):
        desk_body = client.get(f"/desk/conferences/{conference_id}").json()
        paper = desk_body["papers"][0]
        if paper["status"] in {"contradicted", "passed"}:
            break
        time.sleep(0.05)
    assert paper is not None
    assert paper["status"] in {"contradicted", "passed"}

    response = client.post(
        f"/desk/conferences/{conference_id}/ask",
        json={"question": "/Imagine the citations"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imagine"]["prompt"] == "the citations"
    assert body["imagine"]["url"] is None
    assert body["imagine"]["label"] == "Generated from this desk. Not a finding."
    assert "citation" in body["imagine"]["summary"]
    assert "The clip was not generated." in body["answer"]
    assert body["quotes"] == []
    assert body["trace"] == []
    assert body["action"] is None

    history = client.get(f"/desk/conferences/{conference_id}/messages")
    assert history.status_code == 200
    messages = history.json()["messages"]
    desk_msg = next(item for item in messages if item["role"] == "desk")
    assert desk_msg["imagine"]["prompt"] == "the citations"
    assert desk_msg["imagine"]["url"] is None
    assert desk_msg["imagine"]["label"] == "Generated from this desk. Not a finding."
    assert "citation" in desk_msg["imagine"]["summary"]

    monkeypatch.setattr(desk, "_grok_answer", lambda *_args, **_kwargs: None)
    normal = client.post(
        f"/desk/conferences/{conference_id}/ask",
        json={"question": "What failed on @0000.00001?", "mentions": ["0000.00001"]},
    )
    assert normal.status_code == 200
    assert "imagine" not in normal.json()


def test_render_still_is_png_and_varies_by_summary() -> None:
    a = render_still("ICLR desk", "Paper A: queued; no issues")
    b = render_still("ICLR desk", "Paper B: done; citation 1")
    assert a.startswith(b"\x89PNG\r\n\x1a\n")
    assert b.startswith(b"\x89PNG\r\n\x1a\n")
    assert a != b


def test_generate_clip_skips_network_without_key(monkeypatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("_xai_video should not be called")

    monkeypatch.setattr(imagine, "_xai_video", boom)
    assert generate_clip(b"\x89PNG", "animate") is None


def test_xai_video_posts_and_polls_with_fake_httpx(monkeypatch) -> None:
    import httpx as httpx_mod

    posts: list[dict] = []
    gets: list[str] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, headers=None, json=None):
            posts.append({"url": url, "headers": headers, "json": json})
            return FakeResponse({"request_id": "req-1"})

        def get(self, url, headers=None):
            gets.append(url)
            return FakeResponse(
                {"status": "done", "video": {"url": "https://example.test/clip.mp4"}}
            )

    monkeypatch.setattr(httpx_mod, "Client", FakeClient)

    still = render_still("Desk", "one line")
    url = imagine._xai_video("test-key", still, "animate the citations")
    assert url == "https://example.test/clip.mp4"
    assert len(posts) == 1
    body = posts[0]["json"]
    assert body["model"] == "grok-imagine-video-1.5"
    assert body["duration"] == 6
    assert body["image"]["url"].startswith("data:image/png;base64,")
    assert gets == ["https://api.x.ai/v1/videos/req-1"]


def test_ask_imagine_fills_url_from_clip(tmp_path, monkeypatch) -> None:
    recorded: list[tuple[bytes, str]] = []

    def fake_xai(_key: str, still: bytes, prompt: str) -> str:
        recorded.append((still, prompt))
        return "https://example.test/clip.mp4"

    monkeypatch.setenv("XAI_API_KEY", "test-not-real")
    monkeypatch.setattr(imagine, "_xai_video", fake_xai)
    monkeypatch.setattr(desk, "_grok_answer", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no grok")))

    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001"]},
    )

    response = client.post(
        f"/desk/conferences/{conference_id}/ask",
        json={"question": "/Imagine the citations"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imagine"]["url"] == "https://example.test/clip.mp4"
    assert body["answer"].endswith("The clip is ready.")
    assert len(recorded) == 1
    still, prompt = recorded[0]
    assert still.startswith(b"\x89PNG\r\n\x1a\n")
    assert "the citations" in prompt
    assert "papers" in prompt.lower() and "numbers" in prompt.lower() and "verdicts" in prompt.lower()


def test_motion_prompt_includes_wish_and_guardrails() -> None:
    text = motion_prompt("Paper A: queued; no issues", "the citations")
    assert "the citations" in text
    assert "Paper A" in text
    assert "papers" in text.lower()
    assert "numbers" in text.lower()
    assert "verdicts" in text.lower()
