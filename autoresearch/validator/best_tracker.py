"""Persistent tracker for the validator's global-best train.py and score."""

from __future__ import annotations

import ast
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from autoresearch.constants import MAX_SINGLE_STEP_IMPROVEMENT, MIN_PLAUSIBLE_VAL_BPB


def _default_train_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "train.py"


def _load_default_train_py() -> str:
    return _default_train_path().read_text(encoding="utf-8")


@dataclass
class BestTracker:
    """Track the current global-best submission and persist it across restarts."""

    state_dir: str | Path
    val_bpb: float = float("inf")
    train_py: str = ""
    achieved_by: str = "baseline"
    achieved_at: str = ""
    _default_train_py: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        self.state_dir = Path(self.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._default_train_py = _load_default_train_py()
        if not self.train_py:
            self.train_py = self._default_train_py

    @property
    def metadata_path(self) -> Path:
        return Path(self.state_dir) / "global_best.json"

    @property
    def source_path(self) -> Path:
        return Path(self.state_dir) / "best_train.py"

    def update(self, val_bpb: float, train_py: str, miner_hotkey: str) -> bool:
        """Attempt to record a new global best and persist it immediately."""

        if val_bpb >= self.val_bpb:
            return False
        if val_bpb <= MIN_PLAUSIBLE_VAL_BPB:
            return False
        if not train_py.strip():
            return False
        try:
            ast.parse(train_py)
        except SyntaxError:
            return False

        if math.isfinite(self.val_bpb):
            relative_improvement = (self.val_bpb - val_bpb) / self.val_bpb
            if relative_improvement > MAX_SINGLE_STEP_IMPROVEMENT:
                return False

        self.val_bpb = float(val_bpb)
        self.train_py = train_py
        self.achieved_by = miner_hotkey
        self.achieved_at = datetime.now(timezone.utc).isoformat()
        self.save()
        return True

    def save(self) -> None:
        """Persist both metadata and best-source state."""

        metadata = {
            "val_bpb": self.val_bpb,
            "achieved_by": self.achieved_by,
            "achieved_at": self.achieved_at,
        }
        self.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        self.source_path.write_text(self.train_py, encoding="utf-8")

    def load(self) -> None:
        """Load tracker state from disk, defaulting gracefully on missing files."""

        if not self.metadata_path.exists() or not self.source_path.exists():
            self.val_bpb = float("inf")
            self.train_py = self._default_train_py
            self.achieved_by = "baseline"
            self.achieved_at = ""
            return

        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self.val_bpb = float(metadata.get("val_bpb", float("inf")))
        self.achieved_by = str(metadata.get("achieved_by", "baseline"))
        self.achieved_at = str(metadata.get("achieved_at", ""))
        self.train_py = self.source_path.read_text(encoding="utf-8")
