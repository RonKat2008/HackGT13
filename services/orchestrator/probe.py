from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

HIDE_BELOW = 0.60
REPO_ROOT = Path(__file__).resolve().parents[2]


def should_hide(auc: float) -> bool:
    return float(auc) < HIDE_BELOW


def auc_path() -> Path:
    return REPO_ROOT / "kaggle" / "output" / "probe" / "auc.json"


def read_stored_auc(path: str | Path) -> float | None:
    file = Path(path)
    if not file.is_file():
        return None
    payload = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "auc" not in payload:
        return None
    return float(payload["auc"])


def train_probe(vectors: Any, labels: list[str]) -> dict[str, Any]:
    n_rows = len(labels)
    y = [1 if label == "ai" else 0 for label in labels]
    positives = sum(y)
    negatives = n_rows - positives
    if positives == 0 or negatives == 0:
        return {"auc": 0.5, "hidden": should_hide(0.5), "n_rows": n_rows}

    try:
        x_train, x_test, y_train, y_test = train_test_split(
            vectors,
            y,
            test_size=0.25,
            random_state=0,
            stratify=y,
        )
    except ValueError:
        return {"auc": 0.5, "hidden": should_hide(0.5), "n_rows": n_rows}

    if len(set(y_train)) < 2 or len(set(y_test)) < 2:
        return {"auc": 0.5, "hidden": should_hide(0.5), "n_rows": n_rows}

    model = LogisticRegression(random_state=0)
    model.fit(x_train, y_train)
    scores = model.predict_proba(x_test)[:, 1]
    auc = float(roc_auc_score(y_test, scores))
    return {"auc": auc, "hidden": should_hide(auc), "n_rows": n_rows}


def resolve_probe(
    vectors: Any,
    labels: list[str],
    auc_file: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(auc_file) if auc_file is not None else auc_path()
    stored = read_stored_auc(path)
    if stored is not None:
        return {
            "auc": stored,
            "hidden": should_hide(stored),
            "n_rows": len(labels),
        }
    return train_probe(vectors, labels)
