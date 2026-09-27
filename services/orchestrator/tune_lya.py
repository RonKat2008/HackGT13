"""Fine-tune the local Lya adapter on fixtures/lya_train.jsonl.

The holdout file is not written into the training directory. Run from
services/orchestrator:

    .venv/bin/python tune_lya.py
    .venv/bin/python tune_lya.py --score
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from lya import SYSTEM, user_prompt
from lya_local import ADAPTER_DIR, BASE_MODEL

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DATA_DIR = ADAPTER_DIR / "data"
SCIFACT_DIR = Path("/tmp/scifact/data")
LABELS = {"SUPPORT": "supported", "CONTRADICT": "contradicted"}


def target_confidence(label: str) -> float:
    if label == "ambiguous":
        return 0.55
    return 0.96


def message_row(row: dict) -> dict:
    answer = {"verdict": row["label"], "confidence": target_confidence(row["label"])}
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt(row["claim"], row["evidence"])},
            {"role": "assistant", "content": json.dumps(answer)},
        ]
    }


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text[:900]


def _abstract_text(corpus: dict[str, list[str]], doc_id: str, indexes: list[int]) -> str:
    sentences = corpus.get(str(doc_id)) or []
    if not sentences:
        return ""
    if indexes:
        picked = [sentences[i] for i in indexes if 0 <= i < len(sentences)]
    else:
        picked = sentences[:3]
    return _clip(" ".join(picked))


def public_rows() -> tuple[list[dict], list[dict]]:
    """SciFact train rows, plus a dev slice that is never trained on."""
    claims = SCIFACT_DIR / "claims_train.jsonl"
    corpus_path = SCIFACT_DIR / "corpus.jsonl"
    if not claims.is_file() or not corpus_path.is_file():
        return [], []
    corpus: dict[str, list[str]] = {}
    for line in corpus_path.read_text().splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        corpus[str(doc["doc_id"])] = list(doc.get("abstract") or [])

    def convert(path: Path) -> list[dict]:
        rows: list[dict] = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            claim = json.loads(line)
            evidence = claim.get("evidence") or {}
            if not evidence:
                cited = claim.get("cited_doc_ids") or []
                text = _abstract_text(corpus, str(cited[0]), []) if cited else ""
                if text:
                    rows.append(
                        {
                            "claim": claim["claim"],
                            "evidence": [{"section": "paper", "text": text}],
                            "label": "not_mentioned",
                        }
                    )
                continue
            for doc_id, notes in evidence.items():
                for note in notes:
                    label = LABELS.get(str(note.get("label") or ""))
                    text = _abstract_text(corpus, str(doc_id), list(note.get("sentences") or []))
                    if label and text:
                        rows.append(
                            {
                                "claim": claim["claim"],
                                "evidence": [{"section": "paper", "text": text}],
                                "label": label,
                            }
                        )
        return rows

    train_rows = convert(claims)
    dev_path = SCIFACT_DIR / "claims_dev.jsonl"
    dev_rows = convert(dev_path) if dev_path.is_file() else []
    return train_rows, dev_rows


def write_training_files(use_public: bool) -> int:
    local = load_jsonl(FIXTURES / "lya_train.jsonl")
    public: list[dict] = []
    dev: list[dict] = []
    if use_public:
        public, dev = public_rows()
        # Keep the hand-written hard cases from being drowned by the public set.
        mixed = local * 5 + public
    else:
        mixed = local
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(message_row(row)) for row in mixed]
    (DATA_DIR / "train.jsonl").write_text("\n".join(lines) + "\n")
    (DATA_DIR / "valid.jsonl").write_text("\n".join(lines[:8]) + "\n")
    if dev:
        (ADAPTER_DIR / "scifact_dev.jsonl").write_text("".join(json.dumps(row) + "\n" for row in dev))
    print(f"local {len(local)}, public {len(public)}, train messages {len(lines)}, dev {len(dev)}")
    return len(lines)


def train(use_public: bool = False) -> None:
    count = write_training_files(use_public)
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    iters = min(480, max(80, (count // 4) * 2))
    command = [
        sys.executable,
        "-m",
        "mlx_lm",
        "lora",
        "--model",
        BASE_MODEL,
        "--train",
        "--mask-prompt",
        "--data",
        str(DATA_DIR),
        "--adapter-path",
        str(ADAPTER_DIR),
        "--iters",
        str(iters),
        "--batch-size",
        "4",
        "--num-layers",
        "8",
        "--learning-rate",
        "1e-5",
        "--max-seq-length",
        "512",
        "--steps-per-report",
        "40",
        "--steps-per-eval",
        "120",
        "--save-every",
        str(iters),
        "--seed",
        "0",
    ]
    print("iters", iters)
    subprocess.run(command, check=True)


def score() -> None:
    from lya import _parse
    from lya_local import generate

    path = ADAPTER_DIR
    rows = load_jsonl(FIXTURES / "lya_holdout.jsonl")
    correct = 0
    high_wrong = 0
    high = 0
    for row in rows:
        content = generate(path, SYSTEM, user_prompt(row["claim"], row["evidence"]))
        parsed = _parse(content) or {"verdict": "unparsed", "confidence": 0.0}
        match = parsed["verdict"] == row["label"]
        correct += int(match)
        if parsed["confidence"] >= 0.90:
            high += 1
            high_wrong += int(not match)
        print(
            f"{parsed['verdict']:16} {parsed['confidence']:.2f}  "
            f"label={row['label']:16} {'ok' if match else 'MISS'}  {row['claim'][:72]}"
        )
    print(f"holdout {correct}/{len(rows)} verdicts")
    print(f"high_confidence {high} wrong {high_wrong}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--public", action="store_true", help="Also train on SciFact if /tmp/scifact/data is present.")
    args = parser.parse_args()
    if args.score:
        score()
    else:
        train(use_public=args.public)


if __name__ == "__main__":
    main()
