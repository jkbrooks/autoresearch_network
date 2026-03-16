"""Presentation-ready walkthrough for a validator round."""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import numpy as np

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module=r"pydantic\.plugin\._schema_validator",
)


@dataclass
class ShowcaseHotkey:
    ss58_address: str


@dataclass
class ShowcaseWallet:
    hotkey: ShowcaseHotkey


@dataclass
class ShowcaseAxon:
    hotkey: str
    is_serving: bool = True


class ShowcaseMetagraph:
    def __init__(self) -> None:
        self.hotkeys = ["miner-alpha"]
        self.axons = [ShowcaseAxon(hotkey="miner-alpha")]
        self.validator_permit = [True]
        self.S = [1_500.0]
        self.uids = np.arange(len(self.hotkeys), dtype=int)

    @property
    def n(self) -> int:
        return len(self.hotkeys)


class ShowcaseSubtensor:
    def __init__(self) -> None:
        self.set_weights_called = False
        self.last_set_weights: dict[str, Any] | None = None

    def get_current_block(self) -> int:
        return 123_456

    def set_weights(self, **kwargs: Any) -> bool:
        self.set_weights_called = True
        self.last_set_weights = kwargs
        return True


class ShowcaseDendrite:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        axons: list[Any],
        synapse: Any,
        deserialize: bool = False,
        timeout: float = 0.0,
    ) -> list[Any]:
        from autoresearch.constants import HardwareTier
        from autoresearch.protocol import ExperimentSubmission

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
            train_py=synapse.baseline_train_py + "\n# validator round mutation: widen search\n",
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


def _build_config(state_dir: Path) -> tuple[dict[str, Any], ShowcaseSubtensor, ShowcaseDendrite]:
    subtensor = ShowcaseSubtensor()
    dendrite = ShowcaseDendrite()
    config = {
        "uid": 0,
        "wallet": ShowcaseWallet(ShowcaseHotkey("validator-hotkey")),
        "subtensor": subtensor,
        "metagraph": ShowcaseMetagraph(),
        "dendrite": dendrite,
        "neuron": {
            "full_path": str(state_dir),
            "moving_average_alpha": 0.3,
        },
    }
    return config, subtensor, dendrite


def _diff_preview(before: str, after: str, *, limit: int = 4) -> list[str]:
    changed = [
        line
        for line in difflib.ndiff(before.splitlines(), after.splitlines())
        if (line.startswith("- ") or line.startswith("+ ")) and line[2:].strip()
    ]
    return changed[:limit]


def _state_files(state_dir: Path) -> list[str]:
    return sorted(path.name for path in state_dir.iterdir() if path.is_file())


async def _run_showcase() -> dict[str, Any]:
    from autoresearch.experiment_runner import parse_metrics
    from neurons.validator import Validator

    with TemporaryDirectory(prefix="autoresearch-validator-round-") as tmp_dir:
        state_dir = Path(tmp_dir)
        config, subtensor, dendrite = _build_config(state_dir)
        validator = Validator(config=config)
        final_scores = await validator.forward()
        validator.save_state()

        responses = cast(list[Any], validator.last_round["responses"])
        challenge = cast(Any, validator.last_round["challenge"])
        miner_uids = cast(list[int], validator.last_round["miner_uids"])
        response = responses[0]
        metrics = parse_metrics(response.run_log_tail or "")

        payload = {
            "runtime_mode": validator.runtime_mode,
            "task_id": challenge.task_id,
            "queried_miners": len(miner_uids),
            "responding_miners": sum(1 for item in responses if getattr(item, "val_bpb", None)),
            "final_scores": final_scores.round(3).tolist(),
            "ema_scores": validator.scores.round(3).tolist(),
            "global_best": {
                "val_bpb": validator.tracker.val_bpb,
                "achieved_by": validator.tracker.achieved_by,
            },
            "weights_submitted": subtensor.last_set_weights["weights"]
            if subtensor.last_set_weights is not None
            else None,
            "response": {
                "val_bpb": response.val_bpb,
                "hardware_tier": response.hardware_tier,
                "elapsed_wall_seconds": response.elapsed_wall_seconds,
                "peak_vram_mb": response.peak_vram_mb,
                "metrics": metrics,
                "diff_preview": _diff_preview(
                    response.baseline_train_py,
                    response.train_py or "",
                ),
            },
            "state_files": _state_files(state_dir),
            "dendrite_calls": dendrite.calls,
        }
        return payload


def run_showcase(*, as_json: bool = False) -> int:
    from autoresearch.demo_format import CYAN, demo_pacing, emit_block, emit_loading_state, style

    started_at = time.perf_counter()
    is_interactive = sys.stdout.isatty()
    line_delay, section_delay, loading_pause = demo_pacing(is_interactive)
    payload = asyncio.run(_run_showcase())

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    response = payload["response"]
    global_best = payload["global_best"]
    emit_block(
        [
            "═══════════════════════════════════════════════════════",
            f"  {style('AUTORESEARCH NETWORK — Validator Round Walkthrough', CYAN, bold=True)}",
            "═══════════════════════════════════════════════════════",
            "",
            style("[SETUP] Bringing up validator runtime", bold=True),
            f"  Runtime mode:      {payload['runtime_mode']}",
            f"  Active miners:     {payload['queried_miners']}",
            f"  Task ID:           {payload['task_id']}",
            "",
            style("[QUERY] Collecting miner response", bold=True),
            f"  Responded miners:  {payload['responding_miners']}",
            f"  Returned val_bpb:  {response['val_bpb']:.6f}",
            f"  Hardware tier:     {response['hardware_tier']}",
            f"  Elapsed wall time: {response['elapsed_wall_seconds']} seconds",
            f"  Peak VRAM:         {response['peak_vram_mb']:,.1f} MB",
            "",
            style("[MUTATION] Source changes surfaced by the validator", bold=True),
            *[f"    │ {line}" for line in response["diff_preview"]],
            "",
        ],
        line_delay=line_delay,
        section_delay=0.0,
    )
    emit_loading_state(
        total_duration=loading_pause,
        phases=[
            "challenge signed: validator request prepared",
            "relay path stable: request delivered over the public endpoint",
            "miner response received: metrics payload returned",
            "score state committed: tracker and weights updated",
        ],
        is_interactive=is_interactive,
    )
    emit_block(
        [
            style("[SCORING] Validator outcome", bold=True),
            f"  Round score:       {payload['final_scores'][0]:.3f}",
            f"  EMA score:         {payload['ema_scores'][0]:.3f}",
            f"  Weight submitted:  {payload['weights_submitted'][0]:.3f}",
            f"  Global best bpb:   {global_best['val_bpb']:.6f}",
            f"  Best achieved by:  {global_best['achieved_by']}",
            "",
            style("[STATE] Persisted round artifacts", bold=True),
            *[f"  • {name}" for name in payload["state_files"]],
            "",
            "═══════════════════════════════════════════════════════",
            f"  Walkthrough complete in {time.perf_counter() - started_at:.2f} seconds",
            "═══════════════════════════════════════════════════════",
        ],
        line_delay=line_delay,
        section_delay=section_delay,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AutoResearch validator round walkthrough")
    parser.add_argument("--json", action="store_true", help="Render the showcase payload as JSON.")
    args = parser.parse_args(argv)
    return run_showcase(as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
