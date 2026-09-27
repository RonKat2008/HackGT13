import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from desk import DEMO_CONFERENCE_ID

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "playbook.sqlite"))
    monkeypatch.setenv("ARXIV_LISTINGS", "0")
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    return TestClient(app)


def _wait(client: TestClient, job_id: str) -> dict:
    paper = {}
    for _ in range(80):
        response = client.get(f"/author/papers/{job_id}")
        assert response.status_code == 200
        paper = response.json()
        if paper["status"] in {"passed", "contradicted", "error"}:
            return paper
        time.sleep(0.05)
    return paper


def test_a_shelf_is_reused_and_stays_off_the_chair_list(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    first = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00001"})
    assert first.status_code == 200
    body = first.json()
    assert body["arxiv_id"] == "0000.00001"
    assert body["job_id"]
    assert body["status"] in {"queued", "running", "contradicted"}

    second = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00002"})
    assert second.status_code == 200
    assert second.json()["job_id"] != body["job_id"]

    listed = client.get("/author/papers", params={"owner": "author-a"})
    assert listed.status_code == 200
    ids = [paper["arxiv_id"] for paper in listed.json()["papers"]]
    assert ids == ["0000.00001", "0000.00002"]

    other = client.get("/author/papers", params={"owner": "author-b"})
    assert other.json()["papers"] == []

    chair = client.get("/desk/conferences")
    assert chair.status_code == 200
    assert [item["conference_id"] for item in chair.json()] == [DEMO_CONFERENCE_ID]


def test_get_returns_the_read_and_hides_the_chair_paper(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    added = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00001"})
    job_id = added.json()["job_id"]
    paper = _wait(client, job_id)
    assert paper["status"] == "contradicted"
    assert paper["claims"]
    assert any(issue["issue_type"] == "number" for issue in paper["issues"])
    assert "conference_id" not in paper or paper.get("conference_id") != DEMO_CONFERENCE_ID

    missing = client.get("/author/papers/not-a-paper")
    assert missing.status_code == 404


def test_add_requires_an_owner_and_an_id(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    assert client.post("/author/papers", json={"owner": "  ", "arxiv_id": "0000.00001"}).status_code == 400
    assert client.post("/author/papers", json={"owner": "author-a", "arxiv_id": ""}).status_code == 400
    assert client.get("/author/papers", params={"owner": ""}).status_code == 400


def test_upload_starts_on_the_same_shelf(tmp_path, monkeypatch) -> None:
    from author import add_author_paper, list_author_papers

    monkeypatch.setenv("RUN_DB", str(tmp_path / "playbook.sqlite"))
    monkeypatch.setenv("ARXIV_LISTINGS", "0")
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    added = add_author_paper("author-a", pdf=(FIXTURES / "human.pdf").read_bytes())
    assert added["arxiv_id"].startswith("upload-")
    assert added["status"] in {"queued", "running", "passed", "contradicted"}
    papers = list_author_papers("author-a")["papers"]
    assert papers[0]["job_id"] == added["job_id"]


def test_multipart_pdf_upload_starts_a_paper(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    with (FIXTURES / "human.pdf").open("rb") as handle:
        response = client.post(
            "/author/papers",
            params={"owner": "author-upload"},
            files={"pdf": ("human.pdf", handle, "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]
    assert body["status"] in {"queued", "running", "passed", "contradicted"}


_BANNED = ("fake", "fraudulent", "fabricated", "ai-written")
_FIRST_MARK = "Smith, 2099"
_SECOND_MARK = "Lee, 2020"


def test_ask_stays_on_one_paper_and_keeps_history(tmp_path, monkeypatch) -> None:
    import author as author_mod

    client = _client(tmp_path, monkeypatch)
    first = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00001"})
    second = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00002"})
    first_id = first.json()["job_id"]
    second_id = second.json()["job_id"]
    _wait(client, first_id)
    _wait(client, second_id)

    seen: dict = {}

    def fake_grok(paper, question, history):
        messages = author_mod._grok_messages(paper, question, history)
        seen["messages"] = messages
        seen["history"] = history
        blob = json.dumps(messages)
        assert _FIRST_MARK in blob or "95.2" in blob
        assert _SECOND_MARK not in blob
        assert "61.0" not in blob
        return "The stored number on this paper needs a check against the table."

    monkeypatch.setattr(author_mod, "_author_grok", fake_grok)

    asked = client.post(
        f"/author/papers/{first_id}/ask",
        json={"question": "What failed on this paper?"},
    )
    assert asked.status_code == 200
    body = asked.json()
    assert body["answer"]
    assert "action" in body
    assert "quotes" in body and "trace" in body
    for word in _BANNED:
        assert word not in body["answer"].lower()
    assert _SECOND_MARK not in body["answer"]

    follow = client.post(
        f"/author/papers/{first_id}/ask",
        json={"question": "Which citation is the problem?"},
    )
    assert follow.status_code == 200
    hist_blob = json.dumps(seen["messages"])
    assert "What failed on this paper?" in hist_blob
    assert any(turn["text"] == "What failed on this paper?" for turn in seen["history"])

    other_thread = client.get(f"/author/papers/{second_id}/messages")
    assert other_thread.status_code == 200
    assert other_thread.json()["messages"] == []

    thread = client.get(f"/author/papers/{first_id}/messages")
    assert thread.status_code == 200
    texts = [item["text"] for item in thread.json()["messages"]]
    assert texts[0] == "What failed on this paper?"
    assert texts[2] == "Which citation is the problem?"


def test_verdict_change_is_refused_without_grok(tmp_path, monkeypatch) -> None:
    import author as author_mod

    client = _client(tmp_path, monkeypatch)
    added = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00001"})
    job_id = added.json()["job_id"]
    _wait(client, job_id)

    def boom(*_args, **_kwargs):
        raise AssertionError("Grok must not run for a verdict edit")

    monkeypatch.setattr(author_mod, "_author_grok", boom)

    for question in ("Please change the verdict", "mark it supported"):
        response = client.post(f"/author/papers/{job_id}/ask", json={"question": question})
        assert response.status_code == 200
        body = response.json()
        assert body["action"]["type"] == "refuse"
        assert body["answer"] == (
            "The desk does not change a verdict from chat. The stored read stays as it is."
        )
        for word in _BANNED:
            assert word not in body["answer"].lower()


def test_empty_question_is_400_and_chair_job_is_404(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    added = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00001"})
    job_id = added.json()["job_id"]

    empty = client.post(f"/author/papers/{job_id}/ask", json={"question": "   "})
    assert empty.status_code == 400

    missing = client.post("/author/papers/not-a-paper/ask", json={"question": "What failed?"})
    assert missing.status_code == 404

    chair_add = client.post(
        f"/desk/conferences/{DEMO_CONFERENCE_ID}/submissions",
        json={"lines": ["0000.00002"]},
    )
    assert chair_add.status_code == 200
    chair = client.get(f"/desk/conferences/{DEMO_CONFERENCE_ID}")
    chair_job = next(
        paper["job_id"] for paper in chair.json()["papers"] if paper["arxiv_id"] == "0000.00002"
    )
    wrong = client.post(f"/author/papers/{chair_job}/ask", json={"question": "What failed?"})
    assert wrong.status_code == 404


def test_reset_clears_one_author_thread(tmp_path, monkeypatch) -> None:
    import author as author_mod

    client = _client(tmp_path, monkeypatch)
    first = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00001"})
    second = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00002"})
    first_id = first.json()["job_id"]
    second_id = second.json()["job_id"]

    def boom(*_args, **_kwargs):
        raise AssertionError("Grok must not run for a verdict edit")

    monkeypatch.setattr(author_mod, "_author_grok", boom)
    asked = client.post(
        f"/author/papers/{first_id}/ask",
        json={"question": "Please change the verdict"},
    )
    other = client.post(
        f"/author/papers/{second_id}/ask",
        json={"question": "mark it supported"},
    )
    assert asked.status_code == 200
    assert other.status_code == 200

    cleared = client.delete(f"/author/papers/{first_id}/messages")
    assert cleared.status_code == 200
    assert cleared.json()["cleared"] == 2
    assert client.get(f"/author/papers/{first_id}/messages").json()["messages"] == []
    kept = client.get(f"/author/papers/{second_id}/messages").json()["messages"]
    assert kept[0]["text"] == "mark it supported"
    missing = client.delete("/author/papers/not-a-paper/messages")
    assert missing.status_code == 404


def test_claim_findings_open_as_page_quotes(tmp_path, monkeypatch) -> None:
    import author as author_mod

    monkeypatch.delenv("XAI_API_KEY", raising=False)
    client = _client(tmp_path, monkeypatch)
    added = client.post("/author/papers", json={"owner": "author-a", "arxiv_id": "0000.00001"})
    job_id = added.json()["job_id"]
    paper = {
        "job_id": job_id,
        "arxiv_id": "2503.18421",
        "title": "4DGC",
        "status": "contradicted",
        "conference_id": "author-shelf",
        "paper_text": "Extensive experiments demonstrate that 4DGC supports variable bitrates.",
        "issues": [],
        "claims": [
            {
                "claim_type": "numerical_comparison",
                "verdict": "insufficient_evidence",
                "text": "Extensive experiments demonstrate that 4DGC supports variable bitrates.",
                "reason": "Requires human review",
                "page": 1,
                "confidence": 0.4,
            },
            {
                "claim_type": "citation",
                "verdict": "not_checked",
                "text": "A citation that was not checked.",
                "reason": "",
                "page": 2,
            },
        ],
    }
    monkeypatch.setattr(author_mod, "paper_desk", lambda _job_id: paper)

    response = client.post(
        f"/author/papers/{job_id}/ask",
        json={"question": "What should I look at?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "number: Requires human review" in body["answer"]
    assert "not_checked" not in body["answer"]
    quote = next(item for item in body["quotes"] if item["issue_type"] == "number")
    assert quote["page"] == 1
    assert "4DGC" in quote["text"]
    assert any(step["kind"] == "quote" and step["quote_id"] == quote["quote_id"] for step in body["trace"])
