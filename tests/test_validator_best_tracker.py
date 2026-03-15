from __future__ import annotations

from pathlib import Path

from autoresearch.validator.best_tracker import BestTracker


def _default_train_py() -> str:
    train_path = Path(__file__).resolve().parents[1] / "autoresearch" / "data" / "train.py"
    return train_path.read_text(encoding="utf-8")


def test_tracker_initial_state_uses_bundled_baseline(tmp_path) -> None:
    tracker = BestTracker(state_dir=tmp_path)

    assert tracker.val_bpb == float("inf")
    assert tracker.achieved_by == "baseline"
    assert tracker.train_py == _default_train_py()


def test_tracker_update_improves_and_persists(tmp_path) -> None:
    tracker = BestTracker(state_dir=tmp_path)

    updated = tracker.update(0.99, "print('new best')\n", "miner-hotkey")

    assert updated is True
    assert tracker.val_bpb == 0.99
    assert tracker.achieved_by == "miner-hotkey"
    assert tracker.metadata_path.exists()
    assert tracker.source_path.exists()


def test_tracker_update_regression_rejected(tmp_path) -> None:
    tracker = BestTracker(state_dir=tmp_path)
    tracker.val_bpb = 1.0

    updated = tracker.update(1.01, "print('regression')\n", "miner-hotkey")

    assert updated is False
    assert tracker.val_bpb == 1.0


def test_tracker_update_implausible_bpb_rejected(tmp_path) -> None:
    tracker = BestTracker(state_dir=tmp_path)

    updated = tracker.update(0.01, "print('bogus')\n", "miner-hotkey")

    assert updated is False
    assert tracker.val_bpb == float("inf")


def test_tracker_update_impossible_improvement_rejected(tmp_path) -> None:
    tracker = BestTracker(state_dir=tmp_path, val_bpb=1.0, train_py="print('base')\n")

    updated = tracker.update(0.8, "print('too good')\n", "miner-hotkey")

    assert updated is False
    assert tracker.val_bpb == 1.0


def test_tracker_update_invalid_python_rejected(tmp_path) -> None:
    tracker = BestTracker(state_dir=tmp_path)

    updated = tracker.update(0.99, "def broken(", "miner-hotkey")

    assert updated is False
    assert tracker.val_bpb == float("inf")


def test_tracker_save_load_roundtrip(tmp_path) -> None:
    tracker = BestTracker(state_dir=tmp_path)
    tracker.update(0.995, "print('persisted')\n", "miner-hotkey")

    restored = BestTracker(state_dir=tmp_path)
    restored.load()

    assert restored.val_bpb == 0.995
    assert restored.train_py == "print('persisted')\n"
    assert restored.achieved_by == "miner-hotkey"


def test_tracker_missing_files_defaults(tmp_path) -> None:
    tracker = BestTracker(state_dir=tmp_path)
    tracker.load()

    assert tracker.val_bpb == float("inf")
    assert tracker.achieved_by == "baseline"
    assert tracker.train_py == _default_train_py()
