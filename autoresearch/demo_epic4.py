"""Repeatable local demo for Epic 4 validator functionality."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np

from autoresearch.constants import HardwareTier
from autoresearch.protocol import ExperimentSubmission
from neurons.validator import Validator


@dataclass
class DemoHotkey:
    ss58_address: str


@dataclass
class DemoWallet:
    hotkey: DemoHotkey


@dataclass
class DemoAxon:
    hotkey: str
    is_serving: bool = True


class DemoMetagraph:
    def __init__(self) -> None:
        self.hotkeys = ["miner-alpha"]
        self.axons = [DemoAxon(hotkey="miner-alpha")]
        self.validator_permit = [True]
        self.S = [1_500.0]
        self.uids = np.arange(len(self.hotkeys), dtype=int)

    @property
    def n(self) -> int:
        return len(self.hotkeys)


class DemoSubtensor:
    def __init__(self) -> None:
        self.set_weights_called = False
        self.last_set_weights: dict[str, Any] | None = None

    def get_current_block(self) -> int:
        return 123_456

    def set_weights(self, **kwargs: Any) -> bool:
        self.set_weights_called = True
        self.last_set_weights = kwargs
        return True


class DemoDendrite:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        axons: list[Any],
        synapse: ExperimentSubmission,
        deserialize: bool = False,
        timeout: float = 0.0,
    ) -> list[ExperimentSubmission]:
        self.calls.append(
            {
                "axons": axons,
                "task_id": synapse.task_id,
                "deserialize": deserialize,
                "timeout": timeout,
            }
        )
        response = ExperimentSubmission(
            task_id=synapse.task_id,
            baseline_train_py=synapse.baseline_train_py,
            global_best_val_bpb=synapse.global_best_val_bpb,
            val_bpb=1.08,
            train_py=synapse.baseline_train_py + "\n# demo mutation: widen search\n",
            hardware_tier=HardwareTier.LARGE.value,
            elapsed_wall_seconds=301,
            peak_vram_mb=24_000.0,
            run_log_tail=(
                "---\n"
                "val_bpb:          1.080000\n"
                "training_seconds: 301.0\n"
                "total_seconds:    319.7\n"
                "peak_vram_mb:     24000.0\n"
                "mfu_percent:      38.40\n"
                "total_tokens_M:   140.2\n"
                "num_steps:        900\n"
                "num_params_M:     50.3\n"
                "depth:            8\n"
            ),
        )
        return [response]


def _build_config(state_dir: Path) -> tuple[dict[str, Any], DemoSubtensor, DemoDendrite]:
    subtensor = DemoSubtensor()
    dendrite = DemoDendrite()
    config = {
        "uid": 0,
        "wallet": DemoWallet(DemoHotkey("validator-hotkey")),
        "subtensor": subtensor,
        "metagraph": DemoMetagraph(),
        "dendrite": dendrite,
        "neuron": {
            "full_path": str(state_dir),
            "moving_average_alpha": 0.3,
        },
    }
    return config, subtensor, dendrite


def _existing_state_files(state_dir: Path) -> list[str]:
    return sorted(path.name for path in state_dir.iterdir() if path.is_file())


async def _run_demo() -> dict[str, Any]:
    with TemporaryDirectory(prefix="autoresearch-epic4-demo-") as tmp_dir:
        state_dir = Path(tmp_dir)
        config, subtensor, dendrite = _build_config(state_dir)
        validator = Validator(config=config)

        final_scores = await validator.forward()
        validator.save_state()

        assert subtensor.set_weights_called is True
        assert validator.tracker.achieved_by == "miner-alpha"
        assert validator.tracker.val_bpb == 1.08
        assert len(dendrite.calls) == 1

        payload = {
            "runtime_mode": validator.runtime_mode,
            "final_scores": final_scores.round(3).tolist(),
            "ema_scores": validator.scores.round(3).tolist(),
            "global_best": {
                "val_bpb": validator.tracker.val_bpb,
                "achieved_by": validator.tracker.achieved_by,
            },
            "weights_submitted": subtensor.last_set_weights["weights"]
            if subtensor.last_set_weights is not None
            else None,
            "state_files": _existing_state_files(state_dir),
        }
        return payload


def main() -> int:
    payload = asyncio.run(_run_demo())
    print("Epic 4 demo succeeded.")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
