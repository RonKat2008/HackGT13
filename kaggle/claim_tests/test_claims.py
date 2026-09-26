"""Claim on yasserh/titanic-dataset: 342 of 891 passengers survived.

The target column is Survived. A missing CSV is missing_row. A wrong count
is mismatch. A passing run is match.
"""

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
            Path(__file__).resolve().parents[1] / "downloads" / "Titanic-Dataset.csv",
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
