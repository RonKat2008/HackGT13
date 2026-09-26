"""Run the Titanic claim pytest and write results.json for kernels output.

Kaggle uploads only this code file, so the test source is written to /tmp
before pytest. Locally, the copy next to this script is used instead.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLAIM_ID = "claim_titanic_001"
KERNEL_SLUG = "arxaudit/arxaudit-claim"

# Kept in sync with test_claims.py. Kaggle does not upload that sibling file.
EMBEDDED_TEST = '''
"""Claim on yasserh/titanic-dataset: 342 of 891 passengers survived."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

CLAIM_ID = "claim_titanic_001"
DATASET_SLUG = "yasserh/titanic-dataset"
TARGET_COLUMN = "Survived"
EXPECTED_ROWS = 891
EXPECTED_SURVIVED = 342


def titanic_csv() -> Path | None:
    override = os.environ.get("TITANIC_CSV")
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates.extend(
        [
            Path("/kaggle/input/titanic-dataset/Titanic-Dataset.csv"),
            Path("/kaggle/working/Titanic-Dataset.csv"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    rooted = Path("/kaggle/input")
    if rooted.exists():
        found = sorted(rooted.rglob("Titanic-Dataset.csv"))
        if found:
            return found[0]
    return None


def test_survived_count_matches_claim() -> None:
    path = titanic_csv()
    if path is None:
        pytest.fail(
            f"missing_row: {DATASET_SLUG} CSV is not available for {CLAIM_ID}"
        )
    frame = pd.read_csv(path)
    if TARGET_COLUMN not in frame.columns:
        pytest.fail(f"missing_row: {TARGET_COLUMN} is not in {path.name}")
    rows = len(frame)
    survived = int(frame[TARGET_COLUMN].sum())
    assert rows == EXPECTED_ROWS, (
        f"mismatch: expected {EXPECTED_ROWS} rows on {DATASET_SLUG}, found {rows}"
    )
    assert survived == EXPECTED_SURVIVED, (
        f"mismatch: expected {EXPECTED_SURVIVED} survivors, found {survived}"
    )
'''


def _ensure_pytest() -> None:
    try:
        import pytest  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pytest"])


def _test_path() -> Path:
    sibling = Path(__file__).resolve().parent / "test_claims.py"
    if sibling.is_file() and not Path("/kaggle/working").exists():
        return sibling
    target = Path("/tmp/test_claims.py")
    source = sibling.read_text(encoding="utf-8") if sibling.is_file() else EMBEDDED_TEST
    target.write_text(source, encoding="utf-8")
    return target


def main() -> None:
    _ensure_pytest()
    test_path = _test_path()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(test_path),
        ],
        cwd="/tmp",
        capture_output=True,
        text=True,
    )
    log_text = (completed.stdout or "") + (completed.stderr or "")
    lines = [line for line in log_text.splitlines() if line.strip()]
    tail = "\n".join(lines[-40:])
    if completed.returncode == 0:
        status = "match"
    elif "missing_row" in log_text:
        status = "missing_row"
    else:
        status = "mismatch"
    payload = {
        "claim_id": CLAIM_ID,
        "dataset_slug": "yasserh/titanic-dataset",
        "where": "kaggle",
        "status": status,
        "log": tail,
        "kernel_url": f"https://www.kaggle.com/code/{KERNEL_SLUG}",
    }
    out = Path("/kaggle/working/results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
