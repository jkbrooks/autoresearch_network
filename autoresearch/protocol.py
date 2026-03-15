"""Protocol contract and demo entrypoint for AutoResearch Network."""

from __future__ import annotations

import difflib
import sys
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from autoresearch.constants import (
    MAX_ELAPSED_SECONDS,
    MAX_SCORE,
    MAX_SINGLE_STEP_IMPROVEMENT,
    MAX_VAL_BPB,
    MIN_ELAPSED_SECONDS,
    MIN_PLAUSIBLE_VAL_BPB,
    TIER_PLAUSIBILITY,
    HardwareTier,
)

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"

if TYPE_CHECKING:
    class SynapseBase:
        """Static typing stub for the runtime Bittensor synapse base."""

        def __init__(self, **data: object) -> None:
            ...
else:
    import bittensor as bt

    SynapseBase = bt.Synapse


class ExperimentSubmission(SynapseBase):
    """Typed validator-to-miner experiment challenge and response envelope."""

    task_id: str
    baseline_train_py: str
    global_best_val_bpb: float

    val_bpb: float | None = None
    train_py: str | None = None
    hardware_tier: str | None = None
    elapsed_wall_seconds: int | None = None
    peak_vram_mb: float | None = None
    run_log_tail: str | None = None

    def deserialize(self) -> dict[str, float | int | str | None]:
        """Return the miner-populated response fields."""

        return {
            "val_bpb": self.val_bpb,
            "train_py": self.train_py,
            "hardware_tier": self.hardware_tier,
            "elapsed_wall_seconds": self.elapsed_wall_seconds,
            "peak_vram_mb": self.peak_vram_mb,
            "run_log_tail": self.run_log_tail,
        }

    def validate(self) -> None:
        """Validate all miner-submitted fields and raise on the first protocol violation."""

        if self.val_bpb is None:
            raise ValueError("Missing val_bpb — miner did not return a result")
        if self.val_bpb < MIN_PLAUSIBLE_VAL_BPB:
            raise ValueError(
                "val_bpb "
                f"{self.val_bpb} is below minimum plausible threshold {MIN_PLAUSIBLE_VAL_BPB}"
            )
        if self.val_bpb > MAX_VAL_BPB:
            raise ValueError(
                f"val_bpb {self.val_bpb} exceeds maximum plausible value {MAX_VAL_BPB}"
            )
        if self.train_py in {None, ""}:
            raise ValueError("Missing train_py — miner did not return modified source")
        if self.train_py == self.baseline_train_py:
            raise ValueError("train_py is identical to baseline — miner made no changes")
        try:
            tier = HardwareTier(self.hardware_tier)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid hardware_tier: {self.hardware_tier}") from None
        if self.elapsed_wall_seconds is None or not (
            MIN_ELAPSED_SECONDS <= self.elapsed_wall_seconds <= MAX_ELAPSED_SECONDS
        ):
            raise ValueError(
                f"elapsed_wall_seconds {self.elapsed_wall_seconds} outside valid range "
                f"[{MIN_ELAPSED_SECONDS}, {MAX_ELAPSED_SECONDS}]"
            )
        relative_improvement = (self.global_best_val_bpb - self.val_bpb) / self.global_best_val_bpb
        if relative_improvement > MAX_SINGLE_STEP_IMPROVEMENT:
            raise ValueError(
                "Improvement of "
                f"{relative_improvement * 100:.1f}% exceeds maximum single-step threshold of "
                f"{MAX_SINGLE_STEP_IMPROVEMENT * 100}%"
            )
        bounds = TIER_PLAUSIBILITY[tier]
        if not (bounds.min_val_bpb <= self.val_bpb <= bounds.max_val_bpb):
            raise ValueError(
                f"val_bpb {self.val_bpb} outside plausible range "
                f"[{bounds.min_val_bpb}, {bounds.max_val_bpb}] for tier {tier.value}"
            )
        if self.peak_vram_mb is None or not (
            bounds.min_vram_mb <= self.peak_vram_mb <= bounds.max_vram_mb
        ):
            raise ValueError(
                f"peak_vram_mb {self.peak_vram_mb} outside plausible range "
                f"[{bounds.min_vram_mb}, {bounds.max_vram_mb}] for tier {tier.value}"
            )


def preview_score(*, global_best: float, submitted: float) -> float:
    """Preview-only demo formula for a submission score."""

    improvement = global_best - submitted
    return min(MAX_SCORE, (improvement / global_best) * 200)


def _style(text: str, color: str = "", *, bold: bool = False) -> str:
    prefix = f"{BOLD if bold else ''}{color}"
    return f"{prefix}{text}{RESET}" if prefix else text


def _hardware_tier_label(tier: HardwareTier) -> str:
    if tier is HardwareTier.SMALL:
        return "small (≤8 GB)"
    if tier is HardwareTier.MEDIUM:
        return "medium (≤16 GB)"
    if tier is HardwareTier.LARGE:
        return "large (≤36 GB)"
    return "xl (>36 GB)"


def _first_lines(source: str, limit: int) -> list[str]:
    return source.splitlines()[:limit]


def _diff_preview(before: str, after: str, *, limit: int = 3) -> list[str]:
    changed = [
        line
        for line in difflib.ndiff(before.splitlines(), after.splitlines())
        if line.startswith("- ") or line.startswith("+ ")
    ]
    return changed[:limit]


def run_demo() -> int:
    """Run the self-contained protocol demo."""

    from autoresearch.mock import MockSubmissionFactory

    started_at = time.perf_counter()
    factory = MockSubmissionFactory(seed=42)
    submission = factory.make_submission(
        baseline_val_bpb=0.9979,
        tier=HardwareTier.LARGE,
        improvement=0.0037,
        task_id="round_20260315_001",
    )
    rejected = factory.make_invalid_submission(reason="bogus_bpb")
    tier = HardwareTier(submission.hardware_tier or HardwareTier.LARGE.value)
    improvement = (submission.global_best_val_bpb - (submission.val_bpb or 0.0))
    relative_gain_pct = (improvement / submission.global_best_val_bpb) * 100
    score = preview_score(
        global_best=submission.global_best_val_bpb,
        submitted=submission.val_bpb or submission.global_best_val_bpb,
    )
    diff_lines = _diff_preview(submission.baseline_train_py, submission.train_py or "")

    print("═══════════════════════════════════════════════════════")
    print(f"  {_style('AUTORESEARCH NETWORK — Protocol Demo', CYAN, bold=True)}")
    print("═══════════════════════════════════════════════════════")
    print()
    print(_style("[VALIDATOR] Creating experiment challenge...", bold=True))
    print(f"  Task ID:           {submission.task_id}")
    print(f"  Global best bpb:   {submission.global_best_val_bpb:.6f}")
    print("  Baseline train.py: (first 5 lines shown)")
    for line in _first_lines(submission.baseline_train_py, 5):
        print(f"    │ {line}")
    print()
    print(_style("[MINER] Running AutoResearch experiment loop...", bold=True))
    print(f"  Hardware tier:     {_hardware_tier_label(tier)}")
    print(f"  Elapsed time:      {submission.elapsed_wall_seconds} seconds")
    print(f"  Peak VRAM:         {submission.peak_vram_mb:,.1f} MB")
    print(f"  Result val_bpb:    {submission.val_bpb:.6f}")
    print(f"  Improvement:       -{improvement:.4f} ({relative_gain_pct:.2f}% better)")
    print("  Modified train.py: (first 3 changed lines shown)")
    for line in diff_lines:
        print(f"    │ {line}")
    print()
    print(_style("[VALIDATOR] Validating submission...", bold=True))
    submission.validate()
    for line in [
        "val_bpb in plausible range",
        "train_py differs from baseline",
        "hardware_tier valid",
        "elapsed_wall_seconds in range",
        "improvement within single-step cap",
        "val_bpb within tier plausibility range",
        "peak_vram_mb within tier range",
    ]:
        print(f"  {_style('✓', GREEN, bold=True)} {line}")
    print(f"  Result: {_style('VALID', GREEN, bold=True)}")
    print()
    print(_style("[SCORING] Computing reward...", bold=True))
    print(f"  Improvement delta:  {improvement:.6f}")
    print(f"  Relative gain:      {relative_gain_pct:.2f}%")
    print(f"  Score:              {score:.2f} / {MAX_SCORE:.2f}")
    print()
    print(_style("[DEMO] Showing an invalid submission...", bold=True))
    print("  Reason: bogus_bpb (val_bpb = 0.1)")
    try:
        rejected.validate()
    except ValueError as exc:
        print(f"  Validation result: {_style('✗ REJECTED', RED, bold=True)}")
        print(f'  Error: "{exc}"')
    elapsed = time.perf_counter() - started_at
    print()
    print("═══════════════════════════════════════════════════════")
    print("  Demo complete. No GPU, chain, or wallet required.")
    print(f"  Total time: {elapsed:.2f} seconds.")
    print("═══════════════════════════════════════════════════════")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for the protocol module."""

    args = list(argv if argv is not None else sys.argv[1:])
    if args == ["demo"]:
        return run_demo()
    print("Usage: python -m autoresearch.protocol demo", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
