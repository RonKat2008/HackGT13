import json
from pathlib import Path

import httpx
import pytest

from shelf import (
    cap_rows,
    default_shelf_path,
    embed_texts,
    enabled,
    load_rows,
    load_shelf,
    record_event,
    save_batch,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SQL_PATH = REPO_ROOT / "supabase" / "migrations" / "001_shelf.sql"
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "shelf_abstracts.csv"


@pytest.fixture
def no_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)


def test_disabled_writer_is_noop(no_supabase: None) -> None:
    import shelf

    assert enabled() is False
    assert record_event("job-1", "ingest", "started", "begin") is None
    assert save_batch({"kind": "links", "arxiv_ids": ["2301.00001"]}) is None
    assert "httpx" not in vars(shelf)


def test_enabled_is_true_only_for_nonempty_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "")
    assert enabled() is False
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    assert enabled() is True


def test_migration_names_shelf_tables_and_batch_kind() -> None:
    sql = SQL_PATH.read_text()
    for name in (
        "reference_items",
        "conferences",
        "batches",
        "paper_jobs",
        "job_events",
        "probe_meta",
    ):
        assert name in sql
    assert "links" in sql
    assert "batch" in sql
    assert "kind" in sql
    assert "create extension if not exists vector" in sql
    assert "vector(384)" in sql
    assert "enable row level security" in sql
    assert "for insert" not in sql.lower()
    assert "to anon" in sql


def _fake_embedder(text: str) -> list[float]:
    return [float(len(text)), 0.25, -0.5]


def test_fixture_loads_four_rows_two_human_two_ai() -> None:
    rows = load_rows(FIXTURE_PATH)
    assert len(rows) == 4
    assert all(set(row) >= {"title", "text", "label"} for row in rows)
    labels = [row["label"] for row in rows]
    assert labels.count("human") == 2
    assert labels.count("ai") == 2
    assert set(labels) == {"human", "ai"}


def test_load_rows_skips_blank_abstracts_and_maps_flags(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    path.write_text(
        "title,abstract,is_ai_generated\n"
        "Blank,,0\n"
        "Spaces,   ,false\n"
        "Human Flag,human text,0\n"
        "True Flag,ai true text,True\n"
        "One Flag,ai one text,1\n",
        encoding="utf-8",
    )
    rows = load_rows(path)
    assert [row["label"] for row in rows] == ["human", "ai", "ai"]
    assert [row["text"] for row in rows] == [
        "human text",
        "ai true text",
        "ai one text",
    ]


def test_cap_rows_keeps_one_of_each_label_in_order() -> None:
    rows = [
        {"title": "h1", "text": "a", "label": "human"},
        {"title": "h2", "text": "b", "label": "human"},
        {"title": "h3", "text": "c", "label": "human"},
        {"title": "a1", "text": "d", "label": "ai"},
    ]
    capped = cap_rows(rows, per_label=1)
    assert [row["label"] for row in capped] == ["human", "ai"]
    assert [row["title"] for row in capped] == ["h1", "a1"]
    assert sum(1 for row in capped if row["label"] == "human") == 1
    assert sum(1 for row in capped if row["label"] == "ai") == 1


def test_fake_embedder_is_used_and_same_text_matches() -> None:
    vectors = embed_texts(["same text", "same text", "other"], _fake_embedder)
    assert vectors[0] == vectors[1]
    assert vectors[0] == [9.0, 0.25, -0.5]
    assert vectors[2] != vectors[0]


def test_default_embedder_is_deterministic_hash_384() -> None:
    first = embed_texts(["same text"])[0]
    second = embed_texts(["same text"])[0]
    other = embed_texts(["other text"])[0]
    assert first == second
    assert len(first) == 384
    assert all(-1.0 <= value <= 1.0 for value in first)
    assert other != first


def test_load_shelf_does_not_construct_httpx_without_keys(
    no_supabase: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("httpx.Client must not be constructed")

    monkeypatch.setattr(httpx, "Client", boom)
    rows = load_shelf(FIXTURE_PATH, embedder=_fake_embedder)
    assert len(rows) == 4
    assert all("embedding" in row for row in rows)


def test_load_shelf_posts_once_with_human_or_ai_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")

    captured: list[tuple[str, dict, object]] = []

    class FakeClient:
        def post(self, url: str, **kwargs: object) -> httpx.Response:
            captured.append((url, kwargs.get("headers") or {}, kwargs.get("json")))
            return httpx.Response(201)

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("httpx.Client must not be constructed when client is passed")

    monkeypatch.setattr(httpx, "Client", boom)
    rows = load_shelf(
        FIXTURE_PATH,
        embedder=_fake_embedder,
        client=FakeClient(),
    )
    assert len(rows) == 4
    assert len(captured) == 1
    url, headers, items = captured[0]
    assert url == "https://example.supabase.co/rest/v1/reference_items?on_conflict=source,external_id"
    assert headers["Authorization"] == "Bearer service-role-test-key"
    assert headers["apikey"] == "service-role-test-key"
    assert headers["Prefer"] == "resolution=merge-duplicates,return=minimal"
    if isinstance(items, (bytes, str)):
        items = json.loads(items)
    assert all(isinstance(item["embedding"], str) and item["embedding"].startswith("[") for item in items)
    labels = {item["label"] for item in items}
    assert labels <= {"human", "ai"}
    assert labels == {"human", "ai"}


def test_default_shelf_path_is_existing_csv() -> None:
    path = default_shelf_path()
    assert path.suffix == ".csv"
    assert path.is_file()
