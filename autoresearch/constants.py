"""Shared protocol constants for AutoResearch Network."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HardwareTier(str, Enum):
    """Self-reported hardware capacity buckets used for first-pass plausibility checks."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XL = "xl"


@dataclass(frozen=True)
class TierRange:
    """Immutable plausibility ranges for a hardware tier."""

    min_val_bpb: float
    max_val_bpb: float
    min_vram_mb: float
    max_vram_mb: float
    min_tokens_m: float
    max_tokens_m: float


TIER_PLAUSIBILITY: dict[HardwareTier, TierRange] = {
    HardwareTier.SMALL: TierRange(1.2, 2.5, 2_000.0, 8_000.0, 5.0, 30.0),
    HardwareTier.MEDIUM: TierRange(1.0, 1.8, 4_000.0, 16_000.0, 20.0, 100.0),
    HardwareTier.LARGE: TierRange(0.9, 1.3, 8_000.0, 36_000.0, 50.0, 250.0),
    HardwareTier.XL: TierRange(0.7, 1.1, 16_000.0, 82_000.0, 200.0, 600.0),
}

MIN_PLAUSIBLE_VAL_BPB = 0.5  # Lower values are not believable for a five-minute run.
MAX_VAL_BPB = 5.0  # Anything above this effectively indicates a failed or meaningless training run.
MAX_SINGLE_STEP_IMPROVEMENT = 0.10  # More than 10% relative gain in one short run is suspicious.
MIN_ELAPSED_SECONDS = 60  # A legitimate training attempt cannot complete in less than one minute.
MAX_ELAPSED_SECONDS = 600  # Training plus startup and eval should stay under ten minutes.
REPLAY_SAMPLE_RATE = 0.2  # Replay one in five submissions to spot-check miner honesty.
PARTICIPATION_SCORE = 0.05  # Valid but non-improving miners still receive a small presence reward.
MAX_SCORE = 1.0  # Single-round scores are normalized to the unit interval.
