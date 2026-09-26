from pathlib import Path

import pytest

from shelf import enabled, record_event, save_batch

REPO_ROOT = Path(__file__).resolve().parents[3]
SQL_PATH = REPO_ROOT / "supabase" / "migrations" / "001_shelf.sql"


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
