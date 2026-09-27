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
