import json
from pathlib import Path
from unittest.mock import patch

from sklearn.linear_model import LogisticRegression

from probe import (
    HIDE_BELOW,
    auc_path,
    read_stored_auc,
    resolve_probe,
    should_hide,
    train_probe,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _separable_vectors() -> list[list[float]]:
    humans = [[0.02 * i, -0.01 * i] for i in range(8)]
    ais = [[10.0 + 0.02 * i, 10.0 - 0.01 * i] for i in range(8)]
    return humans + ais


def _separable_labels() -> list[str]:
    return ["human"] * 8 + ["ai"] * 8


def test_hide_threshold_is_sixty() -> None:
    assert HIDE_BELOW == 0.60
    assert should_hide(0.60) is False
    assert should_hide(0.59) is True


def test_auc_path_points_at_repo_kaggle_output() -> None:
    expected = REPO_ROOT / "kaggle" / "output" / "probe" / "auc.json"
    assert auc_path() == expected
    assert not str(auc_path()).startswith(str(Path("/tmp")))


def test_separable_data_is_visible() -> None:
    result = train_probe(_separable_vectors(), _separable_labels())
    assert set(result) == {"auc", "hidden", "n_rows"}
    assert result["n_rows"] == 16
    assert result["auc"] >= 0.60
    assert result["hidden"] is False


def test_stored_auc_skips_fit_and_hides(tmp_path: Path) -> None:
    auc_file = tmp_path / "auc.json"
    auc_file.write_text(json.dumps({"auc": 0.41}), encoding="utf-8")

    with patch.object(LogisticRegression, "fit") as fit:
        result = resolve_probe(
            _separable_vectors(),
            _separable_labels(),
            auc_file=auc_file,
        )
        fit.assert_not_called()

    assert result["auc"] == 0.41
    assert result["hidden"] is True
    assert result["n_rows"] == 16


def test_missing_auc_file_does_not_raise(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "auc.json"
    assert not missing.exists()
    assert read_stored_auc(missing) is None
    result = resolve_probe(
        _separable_vectors(),
        _separable_labels(),
        auc_file=missing,
    )
    assert result["auc"] >= 0.60
    assert result["hidden"] is False


def test_read_stored_auc_missing_key_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "auc.json"
    path.write_text(json.dumps({"score": 0.99}), encoding="utf-8")
    assert read_stored_auc(path) is None


def test_single_class_falls_back_to_half() -> None:
    result = train_probe([[0.0, 0.0]] * 8, ["human"] * 8)
    assert result["auc"] == 0.5
    assert result["hidden"] is True
    assert result["n_rows"] == 8
