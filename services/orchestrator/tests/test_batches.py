from fastapi.testclient import TestClient

from app import app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("RUN_DB", str(tmp_path / "playbook.sqlite"))
    monkeypatch.setattr(
        "jev.judge_claim",
        lambda *args, **kwargs: {"label": "not_mentioned", "not_run": True},
    )
    return TestClient(app)


def _create_links(client: TestClient, arxiv_ids: list[str]) -> dict:
    response = client.post(
        "/batches",
        json={
            "product": "arxaudit",
            "kind": "links",
            "name": None,
            "arxiv_ids": arxiv_ids,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_kind_batch_missing_name_returns_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/batches",
        json={
            "product": "arxaudit",
            "kind": "batch",
            "name": None,
            "arxiv_ids": ["0000.00001"],
        },
    )

    assert response.status_code == 400


def test_kind_batch_blank_name_returns_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/batches",
        json={
            "product": "arxaudit",
            "kind": "batch",
            "name": "   ",
            "arxiv_ids": ["0000.00001"],
        },
    )

    assert response.status_code == 400


def test_kind_links_name_null_returns_jobs_in_order(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = _create_links(client, ["0000.00001", "0000.00002"])
    batch_id = created["batch_id"]

    response = client.get(f"/batches/{batch_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"] == batch_id
    assert body["kind"] == "links"
    assert body["name"] is None
    assert body["arxiv_ids"] == ["0000.00001", "0000.00002"]
    jobs = body["jobs"]
    assert [job["arxiv_id"] for job in jobs] == ["0000.00001", "0000.00002"]
    assert all(job["batch_id"] == batch_id for job in jobs)


def test_missing_id_errors_and_next_paper_still_runs(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = _create_links(client, ["missing-id", "0000.00002"])
    body = client.get(f"/batches/{created['batch_id']}").json()
    jobs = body["jobs"]

    assert jobs[0]["arxiv_id"] == "missing-id"
    assert jobs[0]["status"] == "error"
    assert jobs[0]["specialist"] is None
    assert jobs[0]["fitness"] == 0.0
    assert jobs[0]["author_name"] is None
    assert jobs[0]["author_email"] is None
    assert jobs[0]["contacted_at"] is None
    assert jobs[1]["arxiv_id"] == "0000.00002"
    assert jobs[1]["status"] == "passed"
    assert jobs[1]["issue_count"] == 0
    assert jobs[1]["fitness"] == 1.0
    assert jobs[1]["specialist"] == "jev"
    assert jobs[1]["author_name"] == "Lin Example"


def test_hallucinated_paper_is_contradicted_without_fraudulent_reason(
    tmp_path, monkeypatch
):
    client = _client(tmp_path, monkeypatch)

    created = _create_links(client, ["0000.00001"])
    body = client.get(f"/batches/{created['batch_id']}").json()
    job = body["jobs"][0]
    claims = body["claims"]

    assert job["status"] == "contradicted"
    assert job["issue_count"] >= 1
    assert job["fitness"] == 0.0
    assert job["specialist"] == "jev"
    assert job["author_name"] == "Ada Example"
    assert any(claim["issue_type"] in {"citation", "number"} for claim in claims)
    assert all("fraudulent" not in claim["reason"].lower() for claim in claims)
    assert job["issue_count"] == len(claims)


def test_kind_links_with_conference_id_returns_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/batches",
        json={
            "product": "arxaudit",
            "kind": "links",
            "name": None,
            "arxiv_ids": ["0000.00001"],
            "conference_id": "conf-1",
        },
    )

    assert response.status_code == 400


def test_conference_lists_batch_paper_and_issue_reasons(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    conference = client.post(
        "/conferences",
        json={"name": "HackGT Chairs", "contact_email": "chairs@example.com"},
    )
    assert conference.status_code == 200
    conference_body = conference.json()
    conference_id = conference_body["conference_id"]
    assert conference_body["name"] == "HackGT Chairs"
    assert conference_body["contact_email"] == "chairs@example.com"

    created = client.post(
        "/batches",
        json={
            "product": "arxaudit",
            "kind": "batch",
            "name": "Chair review",
            "arxiv_ids": ["0000.00001"],
            "conference_id": conference_id,
        },
    )
    assert created.status_code == 200

    response = client.get(f"/conferences/{conference_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["conference_id"] == conference_id
    assert body["name"] == "HackGT Chairs"
    papers = body["papers"]
    assert len(papers) == 1
    paper = papers[0]
    assert paper["arxiv_id"] == "0000.00001"
    assert paper["author_name"] == "Ada Example"
    assert paper["status"] == "contradicted"
    reasons = paper["issues"]
    assert reasons
    assert any(issue["issue_type"] in {"citation", "number"} for issue in reasons)
    assert all("fraudulent" not in issue["reason"].lower() for issue in reasons)


def test_patch_paper_updates_contact_fields_on_conference(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    conference_id = client.post(
        "/conferences",
        json={"name": "HackGT Chairs", "contact_email": "chairs@example.com"},
    ).json()["conference_id"]
    created = client.post(
        "/batches",
        json={
            "product": "arxaudit",
            "kind": "batch",
            "name": "Chair review",
            "arxiv_ids": ["0000.00001"],
            "conference_id": conference_id,
        },
    ).json()
    job_id = created["jobs"][0]["job_id"]
    contacted_at = "2026-09-26T16:00:00+00:00"

    response = client.patch(
        f"/papers/{job_id}",
        json={"author_email": "ada@example.com", "contacted_at": contacted_at},
    )

    assert response.status_code == 200
    job = response.json()
    assert job["job_id"] == job_id
    assert job["author_email"] == "ada@example.com"
    assert job["contacted_at"] == contacted_at

    paper = client.get(f"/conferences/{conference_id}").json()["papers"][0]
    assert paper["author_email"] == "ada@example.com"
    assert paper["contacted_at"] == contacted_at


def test_monkeypatched_jev_label_is_stored(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    calls: list[tuple[str, str]] = []

    def fake_judge(claim_text: str, evidence_span: str, **kwargs: object) -> dict:
        calls.append((claim_text, evidence_span))
        return {"label": "contradicted", "not_run": False}

    monkeypatch.setattr("jev.judge_claim", fake_judge)

    created = _create_links(client, ["0000.00001"])
    claims = client.get(f"/batches/{created['batch_id']}").json()["claims"]

    assert calls
    assert claims
    assert all(claim["jev_label"] == "contradicted" for claim in claims)


def test_nine_arxiv_ids_returns_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/batches",
        json={
            "product": "arxaudit",
            "kind": "links",
            "name": None,
            "arxiv_ids": [f"0000.0000{i}" for i in range(9)],
        },
    )

    assert response.status_code == 400


def test_product_other_than_arxaudit_returns_400(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/batches",
        json={
            "product": "stormcite",
            "kind": "links",
            "name": None,
            "arxiv_ids": ["0000.00001"],
        },
    )

    assert response.status_code == 400


def test_fixture_ids_do_not_download(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("fixture ids stay on disk")

    monkeypatch.setattr("batches.urllib.request.urlopen", refuse)
    from batches import resolve_paper

    path, author = resolve_paper("0000.00001")

    assert author == "Ada Example"
    assert path.name == "hallucinated.pdf"


def test_new_arxiv_id_downloads_pdf_and_author(tmp_path, monkeypatch):
    monkeypatch.setenv("ARXIV_CACHE", str(tmp_path / "cache"))
    feed = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Attention Is All You Need</title>
        <author><name>Ashish Vaswani</name></author>
      </entry>
    </feed>"""

    class _Body:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def read(self) -> bytes:
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def urlopen(request, timeout=0, context=None):
        url = request.full_url
        if "api/query" in url:
            return _Body(feed)
        if url.endswith("/pdf/1706.03762"):
            return _Body(b"%PDF-1.4\n")
        raise AssertionError(url)

    monkeypatch.setattr("batches.urllib.request.urlopen", urlopen)
    from batches import resolve_paper

    path, author = resolve_paper("1706.03762")

    assert author == "Ashish Vaswani"
    assert path.read_bytes().startswith(b"%PDF")
    assert path.parent == tmp_path / "cache"


def test_missing_arxiv_record_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ARXIV_CACHE", str(tmp_path / "cache"))
    feed = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Error</title><summary>id not found</summary></entry>
    </feed>"""

    class _Body:
        def read(self) -> bytes:
            return feed

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("batches.urllib.request.urlopen", lambda *_a, **_k: _Body())
    from batches import PaperLoadError, resolve_paper

    try:
        resolve_paper("9999.99999")
    except PaperLoadError as exc:
        assert "no record" in str(exc)
    else:
        raise AssertionError("expected PaperLoadError")


def test_unknown_batch_conference_and_paper_are_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    assert client.get("/batches/missing-batch").status_code == 404
    assert client.get("/conferences/missing-conf").status_code == 404
    assert (
        client.patch(
            "/papers/missing-job",
            json={"author_email": "a@b.com", "contacted_at": "2026-09-26T16:00:00+00:00"},
        ).status_code
        == 404
    )
