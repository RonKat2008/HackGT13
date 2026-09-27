import threading

from models import TOOL_NAMES, ToolEvidence
from tools import run_tool, run_tools, tools_for


class _Index:
    def __init__(self) -> None:
        self.barrier = threading.Barrier(2)

    def verifier(self, _claim, k=5):
        self.barrier.wait(timeout=2)
        return [{"page": 2, "section": "results", "text": "The model accuracy was 61.0%.", "score": 0.8}]

    def retrieve(self, _text, k=5, sections=None, prefer_conflicts=False):
        self.barrier.wait(timeout=2)
        section = next(iter(sections)) if sections else "methods"
        return [{"page": 3, "section": section, "text": "Methods used a public benchmark.", "score": 0.4}]


def _claim(text: str, claim_type: str) -> dict:
    return {
        "claim_id": "c-tool",
        "text": text,
        "page": 1,
        "section": "abstract",
        "claim_type": claim_type,
        "evidence": [],
        "steps": [],
    }


def test_parallel_search_returns_allowlisted_rows() -> None:
    claim = _claim("Accuracy reached 95.2% on the public benchmark.", "numerical")
    index = _Index()
    rows = run_tools(claim, tools_for(claim), {"index": index, "path": "", "sections": {}})
    assert [name for name in tools_for(claim)] == ["search_paper", "search_section"]
    assert len(rows) == 2
    texts = {row["text"] for row in rows}
    assert "The model accuracy was 61.0%." in texts
    assert "Methods used a public benchmark." in texts
    for row in rows:
        ToolEvidence.model_validate(row)
        assert row["source_type"] == "paper"
        assert row["evidence_id"]


def test_unknown_tool_is_ignored() -> None:
    claim = _claim("A semantic sentence.", "semantic")
    assert run_tool("invent_a_tool", claim, {}) == []
    assert "invent_a_tool" not in TOOL_NAMES


def test_resolve_dataset_uses_the_known_titanic_table(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("resolve_dataset must not execute the table")

    monkeypatch.setattr("repro.reproduce", boom)
    claim = _claim(
        "We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset).",
        "dataset",
    )
    rows = run_tool("resolve_dataset", claim, {"sections": {}})
    assert len(rows) == 1
    ToolEvidence.model_validate(rows[0])
    assert rows[0]["metadata"]["dataset_slug"] == "yasserh/titanic-dataset"
    assert claim.get("computation") is None


def test_execute_dataset_claim_uses_the_repro_seam(monkeypatch) -> None:
    def reproduce(claims, _sections, model=None, pusher=None):
        return [
            {
                "claim_id": claims[0]["claim_id"],
                "status": "could_not_reproduce",
                "actual": 216,
                "expected": 317,
                "formula": "COUNT_EQ(Pclass, 1)",
                "log": "computed 216, claimed 317",
            }
        ]

    monkeypatch.setattr("repro.reproduce", reproduce)
    claim = _claim("317 passengers travelled in first class.", "dataset")
    rows = run_tool("execute_dataset_claim", claim, {"sections": {}})
    assert rows[0]["metadata"]["actual"] == 216
    assert claim["verdict"] == "could_not_reproduce"
    assert claim["computation"]["expected"] == 317
