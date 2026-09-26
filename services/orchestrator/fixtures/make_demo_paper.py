"""Generate fixtures/demo_paper.pdf, the ArxAudit demo paper (arXiv id 0000.00003).

Run from services/orchestrator:

    .venv/bin/python fixtures/make_demo_paper.py

Every key sentence is written as one text line so it survives ``page.get_text()``
verbatim; tables are drawn with cell borders so ``page.find_tables()`` detects them.
"""

from __future__ import annotations

from pathlib import Path

import fitz

OUT_PATH = Path(__file__).resolve().parent / "demo_paper.pdf"

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
MARGIN_X = 60
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
TOP_Y = 80
FONT = "helv"
BODY_SIZE = 10.5
BODY_LEADING = 15
REFERENCE_SIZE = 9.5
REFERENCE_LEADING = 13
HEADING_SIZE = 14
TITLE_SIZE = 20
CELL_HEIGHT = 20
COLUMN_WIDTHS = (220, 120)

Line = tuple[str, str]  # (kind, text); kind is title | author | heading | body | blank | caption | reference


def _lines(*items: str | Line) -> list[Line]:
    return [item if isinstance(item, tuple) else ("body", item) for item in items]


PAGES: list[dict] = [
    {
        "lines": _lines(
            ("title", "Adaptive Reasoning Systems"),
            ("author", "Mira Example"),
            ("blank", ""),
            ("heading", "Abstract"),
            "We present an adaptive reasoning system that routes each query through a",
            "learned controller before a reasoning head produces the final answer.",
            "Our model achieves 95.2% accuracy on the held-out benchmark.",
            "Our attention layer follows the design introduced by Vaswani et al. (2017).",
            "The controller is a lightweight transformer block (Vaswani et al., 2017).",
            "This result extends the calibration bound of Smith (2099).",
            "The bound is stated for adaptive estimators (Smith, 2099).",
            ("blank", ""),
            ("heading", "Introduction"),
            "Reasoning systems are increasingly asked to handle inputs of varying difficulty.",
            "A fixed computation budget wastes effort on easy queries and starves hard ones.",
            "We study a router that allocates reasoning steps per query and report its effect on accuracy.",
        ),
    },
    {
        "lines": _lines(
            ("heading", "Related Work"),
            "Attention-based sequence models were introduced by (Vaswani et al., 2017) and have",
            "since become the standard backbone for language understanding.",
            "Bidirectional pretraining (Devlin et al., 2019) showed that a single pretrained encoder",
            "transfers to many downstream tasks with little task-specific architecture.",
            "Adaptive computation has been explored through early-exit classifiers and",
            "mixture-of-experts routing; our router differs in that it is trained jointly",
            "with the reasoning head rather than fitted afterwards.",
        ),
    },
    {
        "lines": _lines(
            ("heading", "Methods"),
            "We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset).",
            "Of the 891 passengers, 342 survived.",
            "317 passengers travelled in first class.",
            "Each passenger record is converted to a short textual description and the",
            "system predicts survival from that description.",
            "The router and the reasoning head are optimised jointly with a shared learning rate schedule.",
            "We train for at most 20k steps with a batch size of 64 and report the mean of three seeds.",
        ),
    },
    {
        "lines": _lines(
            ("heading", "Results"),
            "Table 2 reports accuracy on the held-out benchmark for our method and two baselines.",
            ("blank", ""),
            ("caption", "Table 2: Accuracy on the held-out benchmark."),
        ),
        "table": [("Method", "Accuracy"), ("Baseline A", "82.1"), ("Baseline B", "84.7"), ("Ours", "89.2")],
        "after": _lines(
            ("blank", ""),
            "Our method improves performance by 7.8 percentage points over the strongest baseline.",
            "Our proposed model achieves 61.0% accuracy on the held-out benchmark.",
            "Convergence is reached at step 12k for our system and 19k for the baseline.",
        ),
    },
    {
        "lines": _lines(
            "All experiments use the in-distribution split of the benchmark.",
            "Latency measurements were taken on the development server.",
            ("blank", ""),
            ("caption", "Table 3: Ablation of the router."),
        ),
        "table": [("Configuration", "Accuracy"), ("With router", "89.2"), ("Without router", "83.4")],
        "after": _lines(
            ("blank", ""),
            "Removing the router reduces accuracy on the same split, as shown in Table 3.",
        ),
    },
    {
        "lines": _lines(
            ("heading", "Discussion"),
            "Training converges in fewer steps than the baseline because the router is trained jointly.",
            "The system is robust to distribution shift across all evaluated domains.",
            "Inference latency stays under 40 ms on a single GPU.",
            "Removing the router lowers accuracy by more than five points.",
            "We leave a study of larger reasoning heads to future work.",
        ),
    },
    {
        "lines": _lines(
            ("heading", "References"),
            (
                "reference",
                "1. Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, L., and Polosukhin, I. (2017). Attention is all you need. Advances in Neural Information Processing Systems 30. doi:10.48550/arXiv.1706.03762",
            ),
            (
                "reference",
                "2. Devlin, J., Chang, M.-W., Lee, K., and Toutanova, K. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. Proceedings of NAACL-HLT 2019. doi:10.18653/v1/N19-1423",
            ),
            (
                "reference",
                "3. Smith, J. (2099). Calibration bounds for adaptive reasoning. Journal of Future Learning, 12(3), 44-61.",
            ),
        ),
    },
]


def _fit_size(text: str, size: float, width: float) -> float:
    """Shrink the font so a key sentence stays on one line and inside the page."""
    needed = fitz.get_text_length(text, fontname=FONT, fontsize=size)
    return size if needed <= width else size * width / needed


def _wrap(text: str, size: float, width: float) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and fitz.get_text_length(candidate, fontname=FONT, fontsize=size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _write_lines(page: fitz.Page, lines: list[Line], y: float) -> float:
    for kind, text in lines:
        if kind == "blank":
            y += BODY_LEADING
            continue
        if kind == "title":
            size, leading = TITLE_SIZE, TITLE_SIZE + 10
        elif kind == "heading":
            size, leading = HEADING_SIZE, HEADING_SIZE + 8
        elif kind == "author":
            size, leading = BODY_SIZE + 1, BODY_LEADING + 4
        elif kind == "reference":
            size, leading = REFERENCE_SIZE, REFERENCE_LEADING
        else:
            size, leading = BODY_SIZE, BODY_LEADING

        if kind == "reference":
            # Long entries wrap by word; the leading number marks each entry's start.
            first, *rest = _wrap(text, size, TEXT_WIDTH)
            page.insert_text((MARGIN_X, y), first, fontsize=size, fontname=FONT)
            y += leading
            for continuation in rest:
                page.insert_text((MARGIN_X + 18, y), continuation, fontsize=size, fontname=FONT)
                y += leading
            y += 4
            continue

        size = _fit_size(text, size, TEXT_WIDTH)
        page.insert_text((MARGIN_X, y), text, fontsize=size, fontname=FONT)
        y += leading
    return y


def _row_text(first: str, second: str) -> str:
    """Pad with spaces so the second cell's text starts at the second column.

    Writing the row as one string keeps ``page.get_text()`` on one line per row
    (a lone "Method" line would otherwise be read as a section heading), while the
    drawn grid still lets ``page.find_tables()`` split the cells.
    """
    space = fitz.get_text_length(" ", fontname=FONT, fontsize=BODY_SIZE)
    used = fitz.get_text_length(first, fontname=FONT, fontsize=BODY_SIZE)
    gap = COLUMN_WIDTHS[0] - used
    return first + " " * max(1, round(gap / space)) + second


def _draw_table(page: fitz.Page, rows: list[tuple[str, str]], y: float) -> float:
    x0 = MARGIN_X
    x1 = x0 + COLUMN_WIDTHS[0]
    x2 = x1 + COLUMN_WIDTHS[1]
    for first, second in rows:
        y1 = y + CELL_HEIGHT
        page.draw_rect(fitz.Rect(x0, y, x1, y1), color=(0, 0, 0), width=0.8)
        page.draw_rect(fitz.Rect(x1, y, x2, y1), color=(0, 0, 0), width=0.8)
        page.insert_text((x0 + 6, y1 - 6), _row_text(first, second), fontsize=BODY_SIZE, fontname=FONT)
        y = y1
    return y


def build(out_path: Path = OUT_PATH) -> Path:
    doc = fitz.open()
    for spec in PAGES:
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        y = _write_lines(page, spec["lines"], TOP_Y)
        if "table" in spec:
            y = _draw_table(page, spec["table"], y)
            y = _write_lines(page, spec.get("after", []), y + BODY_LEADING)
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return out_path


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")
