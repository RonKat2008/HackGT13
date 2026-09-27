import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app import app
from desk import DEMO_CONFERENCE_ID, DESK_OWNER


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


def test_more_than_eight_ids_stay_queued(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    lines = [f"0000.0000{index}" for index in range(1, 3)]
    lines.extend(f"2401.0000{index}" for index in range(9))

    response = client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": lines},
    )

    assert response.status_code == 200
    assert response.json()["added"] == 11
    desk = client.get(f"/desk/conferences/{conference_id}")
    assert desk.status_code == 200
    assert len(desk.json()["papers"]) == 11
    assert all(paper["status"] == "queued" for paper in desk.json()["papers"])


def test_cap_audits_one_fixture_and_leaves_the_rest(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001", "0000.00002", "9999.99999"]},
    )

    started = client.post(
        f"/desk/conferences/{conference_id}/run",
        json={"cap": 1},
    )
    assert started.status_code == 200

    paper = None
    for _ in range(50):
        desk = client.get(f"/desk/conferences/{conference_id}").json()
        paper = desk["papers"][0]
        if paper["status"] in {"passed", "contradicted", "error"}:
            break
        time.sleep(0.05)

    assert paper is not None
    assert paper["status"] == "contradicted"
    assert paper["paper_text"]
    assert "95.2" in paper["paper_text"]
    assert any(issue["issue_type"] == "citation" for issue in paper["issues"])
    statuses = [
        item["status"]
        for item in client.get(f"/desk/conferences/{conference_id}").json()["papers"]
    ]
    assert statuses[1:] == ["queued", "queued"]


def test_ask_uses_the_mentioned_paper(tmp_path, monkeypatch):
    monkeypatch.setattr("desk._grok_answer", lambda *_args, **_kwargs: None)
    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001", "0000.00002"]},
    )
    client.post(f"/desk/conferences/{conference_id}/run", json={"cap": 1})
    paper = None
    for _ in range(50):
        desk = client.get(f"/desk/conferences/{conference_id}").json()
        paper = desk["papers"][0]
        if paper["status"] == "contradicted":
            break
        time.sleep(0.05)

    response = client.post(
        f"/desk/conferences/{conference_id}/ask",
        json={"question": "What failed on @0000.00001?", "mentions": ["0000.00001"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["papers"] == ["0000.00001"]
    assert "Smith, 2099" in body["answer"]
    smith = next(quote for quote in body["quotes"] if "Smith, 2099" in quote["text"])
    assert isinstance(smith["page"], int)
    assert any(
        step["kind"] == "quote" and step["quote_id"] == smith["quote_id"]
        for step in body["trace"]
    )
    by_name = client.post(
        f"/desk/conferences/{conference_id}/ask",
        json={"question": "What failed on Reported Accuracy on a Public Benchmark?", "mentions": []},
    )
    assert by_name.status_code == 200
    assert by_name.json()["papers"] == ["0000.00001"]
    assert paper is not None
    history = client.get(f"/desk/conferences/{conference_id}/messages")
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert [item["role"] for item in messages] == ["you", "desk", "you", "desk"]
    assert messages[0]["text"] == "What failed on @0000.00001?"
    assert "Smith, 2099" in messages[1]["text"]
    assert any(step["kind"] == "quote" for step in messages[1]["trace"])


def test_listing_ignores_who_is_signed_in(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    added = client.post(
        f"/desk/conferences/{DEMO_CONFERENCE_ID}/submissions",
        json={"lines": ["0000.00001"]},
    )
    assert added.status_code == 200
    created = client.post(
        "/conferences",
        json={"name": "Ada track", "contact_email": "ada@example.edu"},
    )
    assert created.status_code == 200
    ada = client.get("/desk/conferences", params={"owner": "11111111-1111-4111-8111-111111111111"})
    lin = client.get("/desk/conferences", params={"owner": "22222222-2222-4222-8222-222222222222"})
    assert ada.status_code == 200
    assert [item["conference_id"] for item in ada.json()] == [DEMO_CONFERENCE_ID]
    assert lin.json() == ada.json()
    papers = client.get(f"/desk/conferences/{DEMO_CONFERENCE_ID}").json()["papers"]
    assert [paper["arxiv_id"] for paper in papers] == ["0000.00001"]
    refused = client.delete(f"/desk/conferences/{DEMO_CONFERENCE_ID}")
    assert refused.status_code == 409
    papers = client.get(f"/desk/conferences/{DEMO_CONFERENCE_ID}").json()["papers"]
    assert [paper["arxiv_id"] for paper in papers] == ["0000.00001"]


def test_second_signup_does_not_create_a_list(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    db_path = tmp_path / "playbook.sqlite"

    first = client.post(
        "/desk/signup",
        json={"email": "ada@example.edu", "password": "password1"},
    )
    second = client.post(
        "/desk/signup",
        json={"email": "lin@example.edu", "password": "password2"},
    )
    assert first.status_code == 200
    assert second.status_code == 200

    listed = client.get("/desk/conferences")
    assert listed.status_code == 200
    assert [item["conference_id"] for item in listed.json()] == [DEMO_CONFERENCE_ID]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT conference_id, owner FROM conferences"
        ).fetchall()
        assert rows == [(DEMO_CONFERENCE_ID, DESK_OWNER)]

    linked = client.post(
        "/desk/accounts/link",
        json={
            "user_id": str(uuid4()),
            "email": "linked@example.edu",
        },
    )
    assert linked.status_code == 200
    listed = client.get("/desk/conferences")
    assert [item["conference_id"] for item in listed.json()] == [DEMO_CONFERENCE_ID]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT conference_id, owner FROM conferences"
        ).fetchall()
        assert rows == [(DEMO_CONFERENCE_ID, DESK_OWNER)]


def test_linked_account_can_own_a_conference(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    user_id = "11111111-1111-4111-8111-111111111111"
    linked = client.post(
        "/desk/accounts/link",
        json={"user_id": user_id, "email": "chair@example.edu"},
    )
    assert linked.status_code == 200
    created = client.post(
        "/desk/accounts/conferences",
        json={
            "owner": user_id,
            "name": "Desk review",
            "contact_email": "chair@example.edu",
        },
    )
    assert created.status_code == 409
    listed = client.get("/desk/conferences", params={"owner": user_id})
    assert [item["conference_id"] for item in listed.json()] == [DEMO_CONFERENCE_ID]
    with sqlite3.connect(tmp_path / "playbook.sqlite") as conn:
        rows = conn.execute(
            "SELECT conference_id, owner FROM conferences"
        ).fetchall()
        assert rows == [(DEMO_CONFERENCE_ID, DESK_OWNER)]


def test_paper_shelf_is_context_not_an_issue(tmp_path, monkeypatch):
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "shelf_abstracts.csv"
    monkeypatch.setattr("shelf.default_shelf_path", lambda: fixture)
    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001"]},
    )
    job_id = client.get(f"/desk/conferences/{conference_id}").json()["papers"][0]["job_id"]
    unread = client.get(f"/desk/papers/{job_id}")
    assert unread.status_code == 200
    assert unread.json()["neighbors"] == []

    client.post(f"/desk/conferences/{conference_id}/run", json={"cap": 1})
    paper = None
    for _ in range(50):
        paper = client.get(f"/desk/papers/{job_id}").json()
        if paper["status"] in {"passed", "contradicted", "error"}:
            break
        time.sleep(0.05)

    assert paper is not None
    assert paper["status"] == "contradicted"
    assert len(paper["neighbors"]) == 3
    assert {item["label"] for item in paper["neighbors"]} <= {"human", "generated"}
    assert all(issue["issue_type"] != "ai_likeness" for issue in paper["issues"])


def test_notebook_cell_runs_python(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/desk/cells", json={"code": "print(20 + 22)"})

    assert response.status_code == 200
    assert "42" in response.json()["output"]
    assert response.json()["ok"] is True


def test_judged_paper_report_and_zip(tmp_path, monkeypatch):
    import io
    import zipfile

    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001", "0000.00002"]},
    )
    client.post(f"/desk/conferences/{conference_id}/run", json={})
    papers = []
    for _ in range(80):
        papers = client.get(f"/desk/conferences/{conference_id}").json()["papers"]
        if papers and all(item["status"] in {"passed", "contradicted", "error"} for item in papers):
            break
        time.sleep(0.05)

    assert len(papers) == 2
    failed = next(item for item in papers if item["arxiv_id"] == "0000.00001")
    report = client.get(f"/desk/papers/{failed['job_id']}/report")
    assert report.status_code == 200
    assert "Smith, 2099" in report.text
    assert "fraudulent" not in report.text.lower()
    assert "What failed" not in report.text
    assert "What passed" not in report.text

    unread = client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["1706.03762"]},
    )
    assert unread.status_code == 200
    waiting = client.get(f"/desk/conferences/{conference_id}").json()["papers"][-1]
    waiting_report = client.get(f"/desk/papers/{waiting['job_id']}/report")
    assert "Not judged yet" in waiting_report.text

    bundle = client.get(f"/desk/conferences/{conference_id}/reports.zip")
    assert bundle.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(bundle.content))
    names = archive.namelist()
    assert "0000.00001.md" in names
    assert "0000.00002.md" in names
    assert "1706.03762.md" not in names
    assert "Smith, 2099" in archive.read("0000.00001.md").decode("utf-8")


def test_demo_paper_report_has_claims_and_no_banned_words(tmp_path, monkeypatch):
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    def no_catalog(_claims, _references_text, transport=None):
        return None

    def no_lookup(_query, _entry, transport=None):
        return {"queried": [], "reference": ""}

    def no_jev(*_args, **_kwargs):
        return {"label": "not_mentioned", "confidence": 0.0, "probs": {}, "not_run": True}

    monkeypatch.setattr("references.attach", no_catalog)
    monkeypatch.setattr("catalogs.lookup", no_lookup)
    monkeypatch.setattr("jev.judge_claim", no_jev)

    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00003"]},
    )
    client.post(f"/desk/conferences/{conference_id}/run", json={})
    paper = None
    for _ in range(120):
        papers = client.get(f"/desk/conferences/{conference_id}").json()["papers"]
        if papers and papers[0]["status"] in {"passed", "contradicted", "error"}:
            paper = papers[0]
            break
        time.sleep(0.1)

    assert paper is not None
    assert paper["status"] in {"passed", "contradicted", "error"}
    report = client.get(f"/desk/papers/{paper['job_id']}/report")
    assert report.status_code == 200
    body = report.text
    assert "claims analyzed" in body
    lowered = body.lower()
    for banned in ("fake", "fraudulent", "fabricated", "ai-written"):
        assert banned not in lowered


def test_second_add_keeps_one_copy_with_title_and_delete(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_fetch(url, timeout=45):
        calls["n"] += 1
        assert "1706.03762" in url
        assert "max_results=1" in url
        return b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models.</summary>
    <author><name>Ashish Vaswani</name></author>
  </entry>
</feed>"""

    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("ARXIV_LISTINGS", "1")
    monkeypatch.setattr("batches._arxiv_fetch", fake_fetch)
    conference_id = _conference(client)

    first = client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001", "1706.03762", "0000.00001"]},
    )
    assert first.status_code == 200
    assert first.json()["added"] == 2
    papers = client.get(f"/desk/conferences/{conference_id}").json()["papers"]
    assert [paper["arxiv_id"] for paper in papers] == ["0000.00001", "1706.03762"]
    assert papers[0]["title"] == "Reported Accuracy on a Public Benchmark"
    assert "95.2" in papers[0]["abstract"]
    assert papers[1]["title"] == "Attention Is All You Need"
    assert papers[1]["abstract"] == "The dominant sequence transduction models."
    assert papers[1]["author_name"] == "Ashish Vaswani"
    assert calls["n"] == 1

    again = client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001", "1706.03762"]},
    )
    assert again.status_code == 200
    assert again.json()["added"] == 0
    assert len(client.get(f"/desk/conferences/{conference_id}").json()["papers"]) == 2
    assert calls["n"] == 1

    empty = client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["not a paper"]},
    )
    assert empty.status_code == 400

    removed = client.delete(
        f"/desk/conferences/{conference_id}/papers/{papers[1]['job_id']}"
    )
    assert removed.status_code == 200
    left = client.get(f"/desk/conferences/{conference_id}").json()["papers"]
    assert [paper["arxiv_id"] for paper in left] == ["0000.00001"]
    missing = client.delete(
        f"/desk/conferences/{conference_id}/papers/{papers[1]['job_id']}"
    )
    assert missing.status_code == 404


def test_delete_conference_removes_the_list_and_its_papers(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    added = client.post(
        f"/desk/conferences/{conference_id}/submissions",
        json={"lines": ["0000.00001"]},
    )
    assert added.status_code == 200
    removed = client.delete(f"/desk/conferences/{conference_id}")
    assert removed.status_code == 200
    assert removed.json()["deleted"] == conference_id
    assert client.get(f"/desk/conferences/{conference_id}").status_code == 404
    again = client.delete(f"/desk/conferences/{conference_id}")
    assert again.status_code == 404
