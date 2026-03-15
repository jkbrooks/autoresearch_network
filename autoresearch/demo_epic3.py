"""Repeatable local demo for Epic 3 miner functionality."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from autoresearch.experiment_runner import RunResult
from autoresearch.protocol import ExperimentSubmission
from autoresearch.utils.config import build_config
from neurons.miner import Miner


def _build_demo_synapse() -> ExperimentSubmission:
    return ExperimentSubmission(
        task_id="demo_epic3_round",
        baseline_train_py="print('baseline')\n",
        global_best_val_bpb=1.1,
    )


def _build_demo_result() -> RunResult:
    return RunResult(
        val_bpb=1.01,
        total_seconds=301.0,
        peak_vram_mb=24_000.0,
        run_log_tail="demo ok",
        status="success",
    )


async def _run_demo() -> dict[str, Any]:
    synapse = _build_demo_synapse()

    with patch("neurons.miner.ExperimentRunner.setup", lambda self: True):
        miner = Miner(config=build_config(["--mock", "--skip-health-check"]))

    miner._last_baseline = synapse.baseline_train_py
    miner.strategy = SimpleNamespace(
        propose=lambda _: "print('baseline')\nprint('mutated')\n"
    )
    miner.runner = SimpleNamespace(run=lambda _: _build_demo_result())

    with patch("neurons.miner.detect_hardware_tier", lambda **_: SimpleNamespace(value="large")):
        result = await miner.forward(synapse)

    payload = result.deserialize()
    assert payload["val_bpb"] == 1.01
    assert payload["hardware_tier"] == "large"
    assert payload["elapsed_wall_seconds"] == 301
    assert payload["peak_vram_mb"] == 24_000.0
    return payload


def main() -> int:
    payload = asyncio.run(_run_demo())
    print("Epic 3 demo succeeded.")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
