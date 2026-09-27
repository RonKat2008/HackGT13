"""T0: frozen progress and metrics field names. No audit, no network."""

from dataclasses import fields

import pytest

from models import PAPER_PHASES, ConferenceProgress, PaperProgress, ThroughputMetrics

PAPER_FIELDS = (
    "parsed",
    "claims_total",
    "claims_done",
    "findings_so_far",
    "lya_done",
    "jev_running",
    "phase",
)

CONFERENCE_FIELDS = (
    "papers_total",
    "papers_done",
    "papers_with_findings",
    "papers_running",
    "papers_queued",
)

METRICS_FIELDS = (
    "conference_id",
    "papers",
    "claims",
    "resolved_deterministic",
    "resolved_lya",
    "escalated_jev",
    "avg_jev_rounds",
    "citation_cache_hits",
    "citation_cache_misses",
    "paper_cache_hits",
    "paper_cache_misses",
    "lya_batches",
    "claims_per_lya_batch",
    "time_to_first_finding_ms",
    "median_paper_ms",
)


def _names(value: object) -> tuple[str, ...]:
    return tuple(item.name for item in fields(value))


def test_paper_progress_field_names() -> None:
    for phase in PAPER_PHASES:
        progress = PaperProgress(
            parsed=True,
            claims_total=4,
            claims_done=2,
            findings_so_far=1,
            lya_done=1,
            jev_running=0,
            phase=phase,
        )
        assert _names(progress) == PAPER_FIELDS
        assert progress.phase == phase
    with pytest.raises(ValueError):
        PaperProgress(
            parsed=False,
            claims_total=0,
            claims_done=0,
            findings_so_far=0,
            lya_done=0,
            jev_running=0,
            phase="stamp",
        )


def test_conference_progress_field_names() -> None:
    progress = ConferenceProgress(
        papers_total=10,
        papers_done=3,
        papers_with_findings=2,
        papers_running=1,
        papers_queued=6,
    )
    assert _names(progress) == CONFERENCE_FIELDS


def test_throughput_metrics_field_names() -> None:
    metrics = ThroughputMetrics(
        conference_id="conf-1",
        papers=0,
        claims=0,
        resolved_deterministic=0,
        resolved_lya=0,
        escalated_jev=0,
        avg_jev_rounds=0,
        citation_cache_hits=0,
        citation_cache_misses=0,
        paper_cache_hits=0,
        paper_cache_misses=0,
        lya_batches=0,
        claims_per_lya_batch=0,
        time_to_first_finding_ms=None,
        median_paper_ms=None,
    )
    assert _names(metrics) == METRICS_FIELDS
    assert metrics.time_to_first_finding_ms is None
    assert metrics.median_paper_ms is None
