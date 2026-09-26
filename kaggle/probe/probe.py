"""Frozen MiniLM embeddings and a logistic regression probe.

Writes /kaggle/working/auc.json as {"auc": number} and probe.joblib.
The encoder is loaded with transformers and is not trained. The Kaggle
sentence-transformers build fails while looking up an adapter config.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from transformers import AutoModel, AutoTokenizer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_FILES = (
    "config.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "special_tokens_map.json",
    "vocab.txt",
    "model.safetensors",
)


def _csv_path() -> Path:
    roots = [Path("/kaggle/input"), Path("/kaggle/working")]
    for root in roots:
        if not root.exists():
            continue
        matches = sorted(root.rglob("data_set.csv"))
        if matches:
            return matches[0]
    raise FileNotFoundError("data_set.csv was not mounted from the abstracts dataset")


def _model_dir() -> Path:
    """Use the mounted MiniLM dataset. Download only if that mount is missing."""
    roots = [Path("/kaggle/input"), Path("/tmp/minilm")]
    for root in roots:
        if not root.exists():
            continue
        for config in root.rglob("config.json"):
            folder = config.parent
            if (folder / "pytorch_model.bin").is_file() or (folder / "model.safetensors").is_file():
                print("model", folder, flush=True)
                return folder
    folder = Path("/tmp/minilm")
    folder.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/{MODEL_NAME}/resolve/main/"
    for name in MODEL_FILES:
        dest = folder / name
        if dest.is_file() and dest.stat().st_size > 0:
            continue
        print("download", name, flush=True)
        urllib.request.urlretrieve(base + name, dest)
    return folder


def _embed(texts: list[str]) -> np.ndarray:
    folder = _model_dir()
    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True)
    encoder = AutoModel.from_pretrained(folder, local_files_only=True)
    encoder.eval()
    rows: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(texts), 32):
            batch = texts[start : start + 32]
            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            hidden = encoder(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
            summed = torch.sum(hidden * mask, dim=1)
            counts = torch.clamp(mask.sum(dim=1), min=1e-9)
            pooled = torch.nn.functional.normalize(summed / counts, p=2, dim=1)
            rows.append(pooled.cpu().numpy())
            print("embedded", min(start + 32, len(texts)), "/", len(texts), flush=True)
    return np.vstack(rows)


def main() -> None:
    frame = pd.read_csv(_csv_path())
    texts = frame["abstract"].fillna("").astype(str).tolist()
    labels = frame["is_ai_generated"].astype(int).to_numpy()
    print("rows", len(texts), flush=True)
    vectors = _embed(texts)

    x_train, x_test, y_train, y_test = train_test_split(
        vectors,
        labels,
        test_size=0.25,
        random_state=0,
        stratify=labels,
    )
    classifier = LogisticRegression(max_iter=1000, random_state=0)
    classifier.fit(x_train, y_train)
    scores = classifier.predict_proba(x_test)[:, 1]
    auc = float(roc_auc_score(y_test, scores))
    payload = {"auc": auc}

    out = Path("/kaggle/working")
    out.mkdir(parents=True, exist_ok=True)
    (out / "auc.json").write_text(json.dumps(payload), encoding="utf-8")
    joblib.dump(classifier, out / "probe.joblib")
    print(json.dumps(payload))
    print("n_rows", len(labels), "n_test", int(np.size(y_test)))


if __name__ == "__main__":
    main()
