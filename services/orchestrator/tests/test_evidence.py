import os
from pathlib import Path

os.environ["ARX_EMBEDDER"] = "hash"

import pytest

import evidence
import paper_cache
from claims import extract_claims
from evidence import PaperIndex, conflicts
from paper_audit import load_paper, split_sections

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HALLUCINATED = FIXTURES / "hallucinated.pdf"


def test_neighbors_join_the_evidence_lya_sees_first() -> None:
    from evidence import merge_neighbors

    claim = {
        "text": "Training converges in fewer steps than the baseline because the router is trained jointly.",
        "page": 3,
        "section": "results",
        "evidence": [{"text": "The baselines use the same head without the router.", "section": "results"}],
        "_neighbors": [
            {"page": 3, "section": "results", "text": "Convergence is reached at step 12k for our system and 19k for the baseline."},
            {"page": 3, "section": "results", "text": "The baselines use the same head without the router."},
        ],
    }
    merge_neighbors(claim)
    texts = [item["text"] for item in claim["evidence"]]
    assert "Convergence is reached at step 12k for our system and 19k for the baseline." in texts
    assert texts.count("The baselines use the same head without the router.") == 1
    assert claim["text"] not in texts


def test_number_conflict_requires_a_shared_unit() -> None:
    assert conflicts("Accuracy reached 95.2% on the benchmark.", "The model score was 61.0%.")
    assert not conflicts(
        "Accuracy reached 95.2% on the benchmark.",
        "Accuracy reached 95.2% on the benchmark.",
    )
    assert not conflicts("The room had 12 chairs.", "The room had 4 chairs.")


def test_falsifier_ranks_the_disagreeing_accuracy_first() -> None:
    sections = split_sections(load_paper(HALLUCINATED))
    claim = next(
        item
        for item in extract_claims(HALLUCINATED, "job-a3", sections)
        if "95.2" in item["text"] and item["section"] == "abstract"
    )
    index = PaperIndex(HALLUCINATED, sections)
    hits = index.falsifier(claim)
    assert hits
    assert "61.0" in hits[0]["text"]
    assert hits[0]["section"] != "abstract"
    assert len(index.retrieve(claim["text"], k=5)) <= 5


def test_one_matrix_covers_every_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARX_EMBEDDER", "hash")
    monkeypatch.setenv("RUN_DB", str(tmp_path / "runs.sqlite"))
    sections = split_sections(load_paper(HALLUCINATED))
    claims = extract_claims(HALLUCINATED, "job-matrix", sections)
    claims.extend(
        [
            {
                "text": "Training converges in fewer steps than the baseline because the router is trained jointly.",
                "section": "results",
                "page": 2,
                "claim_type": "semantic",
                "steps": [],
                "evidence": [],
            },
            {
                "text": "Our method improves performance by 7.8 percentage points over the strongest baseline.",
                "section": "results",
                "page": 2,
                "claim_type": "numerical_comparison",
                "steps": [],
                "evidence": [],
            },
        ]
    )
    targets = [claim for claim in claims if claim.get("claim_type") in evidence._EVIDENCE_TYPES]
    claim_texts = [str(claim.get("text") or "") for claim in targets]
    assert len(claim_texts) >= 2

    calls: list[list[str]] = []
    real_embed = evidence._embed_claim_texts

    def wrapped_embed(texts: list[str]):
        calls.append([str(item) for item in texts])
        return real_embed(texts)

    shapes: list[tuple[int, int]] = []
    real_similarity = evidence._similarity_matrix

    def wrapped_similarity(queries, matrix):
        scores = real_similarity(queries, matrix)
        shapes.append((int(scores.shape[0]), int(scores.shape[1])))
        return scores

    windows: list[int] = []
    real_around = evidence.PaperIndex.around

    def wrapped_around(self, text: str, n: int = 2):
        windows.append(n)
        return real_around(self, text, n)

    monkeypatch.setattr(evidence, "_embed_claim_texts", wrapped_embed)
    monkeypatch.setattr(evidence, "_similarity_matrix", wrapped_similarity)
    monkeypatch.setattr(evidence.PaperIndex, "around", wrapped_around)

    digest = paper_cache.file_hash(HALLUCINATED)
    paper_cache.put(
        digest,
        text="cached",
        sections={"abstract": "cached"},
        page_count=1,
        tables=[],
        references=[],
    )
    evidence.attach(HALLUCINATED, sections, claims)

    assert calls == [claim_texts]
    assert shapes == [(len(claim_texts), shapes[0][1])]
    assert shapes[0][1] > 0
    assert windows == [6] * len(targets)

    stored = paper_cache.load_chunk_matrix(digest)
    assert stored is not None
    matrix, mode, _fingerprint = stored
    assert mode == "hash"
    assert matrix.ndim == 2
    assert matrix.shape == (shapes[0][1], 384)

    accuracy = next(
        claim for claim in targets if "95.2" in claim["text"] and claim["section"] == "abstract"
    )
    contradicts = [row for row in accuracy["evidence"] if row["role"] == "contradicts"]
    assert contradicts
    assert "61.0" in contradicts[0]["text"]
    assert any(str(row.get("role")) == "context" for row in accuracy["evidence"])
