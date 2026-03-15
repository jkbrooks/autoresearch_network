"""Deterministic mock data generation for protocol tests and demos."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from autoresearch.constants import (
    MIN_ELAPSED_SECONDS,
    TIER_PLAUSIBILITY,
    HardwareTier,
)
from autoresearch.protocol import ExperimentSubmission


def _build_baseline_train_py() -> str:
    return (
        "\n".join(
            [
                "import math",
                "import torch",
                "",
                "DEPTH = 8",
                "WIDTH = 768",
                "LEARNING_RATE = 0.0200",
                'EXPERIMENT_NOTE = "baseline"',
                "",
                "def configure_run():",
                "    return {",
                '        "depth": DEPTH,',
                '        "width": WIDTH,',
                '        "learning_rate": LEARNING_RATE,',
                '        "note": EXPERIMENT_NOTE,',
                "    }",
                "",
                "def score_hint(loss: float) -> float:",
                "    return loss / math.sqrt(DEPTH)",
            ]
        )
        + "\n"
    )


def _build_modified_train_py(
    baseline_train_py: str,
    depth: int,
    learning_rate: float,
    note: str,
) -> str:
    return (
        baseline_train_py.replace("DEPTH = 8", f"DEPTH = {depth}")
        .replace("LEARNING_RATE = 0.0200", f"LEARNING_RATE = {learning_rate:.4f}")
        .replace('EXPERIMENT_NOTE = "baseline"', f'EXPERIMENT_NOTE = "{note}"')
    )


@dataclass
class MockSubmissionFactory:
    """Build deterministic, tier-plausible submissions for tests and demos."""

    seed: int
    _random: random.Random = field(init=False, repr=False)
    _counter: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._random = random.Random(self.seed)

    def make_submission(
        self,
        *,
        baseline_val_bpb: float = 1.1,
        tier: HardwareTier = HardwareTier.LARGE,
        improvement: float = 0.02,
        task_id: str | None = None,
    ) -> ExperimentSubmission:
        """Create a deterministic, valid synthetic submission."""

        self._counter += 1
        bounds = TIER_PLAUSIBILITY[tier]
        submitted_val_bpb = baseline_val_bpb - improvement
        depth = 10 if tier in {HardwareTier.LARGE, HardwareTier.XL} else 8
        learning_rate = 0.018 + self._random.uniform(-0.0015, 0.0015)
        note = f"depth_sweep_seed_{self.seed}"
        peak_vram_mb = round(
            self._random.uniform(bounds.min_vram_mb * 1.05, bounds.max_vram_mb * 0.8),
            1,
        )
        elapsed_wall_seconds = self._random.randint(max(290, MIN_ELAPSED_SECONDS), 310)
        total_tokens_m = round(
            self._random.uniform(bounds.min_tokens_m * 1.1, bounds.max_tokens_m * 0.75),
            1,
        )
        mfu_percent = round(self._random.uniform(31.0, 46.0), 2)
        num_steps = self._random.randint(820, 960)
        num_params_m = round(self._random.uniform(42.0, 58.0), 1)
        baseline_train_py = _build_baseline_train_py()
        train_py = _build_modified_train_py(baseline_train_py, depth, learning_rate, note)
        run_log_tail = "\n".join(
            [
                "step 900 | sampling summary complete",
                "validator handoff prepared",
                "---",
                f"val_bpb:          {submitted_val_bpb:.6f}",
                f"training_seconds: {elapsed_wall_seconds:.1f}",
                f"total_seconds:    {elapsed_wall_seconds + 18.7:.1f}",
                f"peak_vram_mb:     {peak_vram_mb:.1f}",
                f"mfu_percent:      {mfu_percent:.2f}",
                f"total_tokens_M:   {total_tokens_m:.1f}",
                f"num_steps:        {num_steps}",
                f"num_params_M:     {num_params_m:.1f}",
                f"depth:            {depth}",
            ]
        )
        submission = ExperimentSubmission(
            task_id=task_id or f"round_20260315_{self._counter:03d}",
            baseline_train_py=baseline_train_py,
            global_best_val_bpb=baseline_val_bpb,
            val_bpb=submitted_val_bpb,
            train_py=train_py,
            hardware_tier=tier.value,
            elapsed_wall_seconds=elapsed_wall_seconds,
            peak_vram_mb=peak_vram_mb,
            run_log_tail=run_log_tail,
        )
        return submission

    def make_invalid_submission(self, reason: str) -> ExperimentSubmission:
        """Create a submission with a targeted validation failure."""

        if reason == "bogus_bpb":
            submission = self.make_submission()
            submission.val_bpb = 0.1
            return submission
        if reason == "missing_train_py":
            submission = self.make_submission()
            submission.train_py = None
            return submission
        if reason == "identical_train_py":
            submission = self.make_submission()
            submission.train_py = submission.baseline_train_py
            return submission
        if reason == "impossible_improvement":
            baseline = 1.2
            improvement = 0.13
            return self.make_submission(
                baseline_val_bpb=baseline,
                tier=HardwareTier.LARGE,
                improvement=improvement,
            )
        if reason == "invalid_tier":
            submission = self.make_submission()
            submission.hardware_tier = "quantum"
            return submission
        if reason == "elapsed_too_short":
            submission = self.make_submission()
            submission.elapsed_wall_seconds = 10
            return submission
        if reason == "elapsed_too_long":
            submission = self.make_submission()
            submission.elapsed_wall_seconds = 1_200
            return submission
        raise ValueError(f"Unknown invalid submission reason: {reason}")
