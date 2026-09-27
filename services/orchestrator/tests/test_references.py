import os

os.environ["ARX_EMBEDDER"] = "hash"

from references import match_entry, parse_references

VASWANI = (
    "1. Vaswani, A., Shazeer, N., Parmar, N. (2017). Attention is all you need. "
    "doi:10.48550/arXiv.1706.03762"
)
SMITH = "3. Smith, J. (2099). Calibration bounds for adaptive reasoning. Journal of Future Learning."


def test_parse_splits_numbered_entries_and_keeps_title_year_and_doi() -> None:
    entries = parse_references(f"{VASWANI}\n{SMITH}")
    vaswani = next(entry for entry in entries if entry["year"] == "2017")
    smith = next(entry for entry in entries if entry["year"] == "2099")
    assert vaswani["number"] == "1"
    assert "Vaswani" in vaswani["authors"]
    assert vaswani["title"].lower().startswith("attention is all you need")
    assert "10.48550/arxiv.1706.03762" in vaswani["doi"].lower()
    assert smith["authors"] == ["Smith"]
    assert "calibration bounds" in smith["title"].lower()


def test_prose_bibliography_keeps_the_title_and_authors() -> None:
    from catalogs import score_candidate

    entries = parse_references(
        "[13] Sepp Hochreiter and Jürgen Schmidhuber. Long short-term memory. "
        "Neural computation, 9(8):1735–1780, 1997."
    )
    entry = entries[0]
    assert entry["number"] == "13"
    assert entry["year"] == "1997"
    assert "Hochreiter" in entry["authors"]
    assert "Schmidhuber" in entry["authors"]
    assert entry["title"].lower().startswith("long short-term memory")
    score = score_candidate(
        entry,
        {"title": "Long Short-Term Memory", "year": "1997", "authors": ["Hochreiter"], "doi": ""},
    )
    assert score >= 0.85
    partial = score_candidate(
        {"title": "A decomposable attention model", "year": "2016", "authors": ["Parikh"], "doi": ""},
        {
            "title": "A Decomposable Attention Model for Natural Language Inference",
            "year": "2016",
            "authors": ["Parikh"],
            "doi": "",
        },
    )
    assert partial >= 0.85


def test_match_parenthetical_and_bracket_citations() -> None:
    entries = parse_references(f"[1] {VASWANI[3:]}\n\n{SMITH}")
    parenthetical = match_entry("The design follows (Vaswani et al., 2017).", entries)
    narrative = match_entry("Smith (2099) states the bound.", entries)
    bracket = match_entry("See the transformer block in the earlier work [1].", entries)
    assert parenthetical is not None and parenthetical["year"] == "2017"
    assert narrative is not None and narrative["year"] == "2099"
    assert bracket is not None and bracket["number"] == "1"
