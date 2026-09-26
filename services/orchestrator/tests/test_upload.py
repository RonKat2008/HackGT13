from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from batches import resolve_paper

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "demo_paper.pdf"


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "playbook.sqlite"))
    monkeypatch.setenv("ARXIV_LISTINGS", "0")
    monkeypatch.setenv("ARXIV_CACHE", str(tmp_path / "arxiv-cache"))
    return TestClient(app)


def _conference(client: TestClient) -> str:
    response = client.post(
        "/conferences",
        json={"name": "ICLR desk", "contact_email": "chairs@example.edu"},
    )
    assert response.status_code == 200
    return response.json()["conference_id"]


def test_upload_pdf_lists_once_and_resolves(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    conference_id = _conference(client)
    pdf_bytes = FIXTURE.read_bytes()

    first = client.post(
        f"/desk/conferences/{conference_id}/uploads",
        files={"file": ("demo_paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["added"] == 1
    assert body["arxiv_id"].startswith("upload-")
    assert body["title"]
    arxiv_id = body["arxiv_id"]

    desk = client.get(f"/desk/conferences/{conference_id}")
    assert desk.status_code == 200
    papers = desk.json()["papers"]
    assert len(papers) == 1
    assert papers[0]["status"] == "queued"
    assert papers[0]["arxiv_id"] == arxiv_id
    assert papers[0]["title"] == body["title"]

    second = client.post(
        f"/desk/conferences/{conference_id}/uploads",
        files={"file": ("demo_paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert second.status_code == 200
    assert second.json()["added"] == 0
    assert len(client.get(f"/desk/conferences/{conference_id}").json()["papers"]) == 1

    bad = client.post(
        f"/desk/conferences/{conference_id}/uploads",
        files={"file": ("note.txt", b"not a pdf", "text/plain")},
    )
    assert bad.status_code == 400

    path, _author = resolve_paper(arxiv_id)
    assert path.read_bytes().startswith(b"%PDF")
