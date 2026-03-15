from __future__ import annotations

import pytest

from autoresearch.constants import (
    MAX_SCORE,
    MAX_SINGLE_STEP_IMPROVEMENT,
    MAX_VAL_BPB,
    MIN_ELAPSED_SECONDS,
    MIN_PLAUSIBLE_VAL_BPB,
    PARTICIPATION_SCORE,
    REPLAY_SAMPLE_RATE,
    TIER_PLAUSIBILITY,
    HardwareTier,
)


def test_hardware_tier_parses_from_strings() -> None:
    assert HardwareTier("small") is HardwareTier.SMALL
    assert HardwareTier("medium") is HardwareTier.MEDIUM
    assert HardwareTier("large") is HardwareTier.LARGE
    assert HardwareTier("xl") is HardwareTier.XL


def test_hardware_tier_invalid_value_raises() -> None:
    with pytest.raises(ValueError):
        HardwareTier("invalid")


def test_tier_plausibility_covers_every_tier() -> None:
    assert set(TIER_PLAUSIBILITY) == set(HardwareTier)


def test_tier_ranges_are_positive_and_ordered() -> None:
    for tier_range in TIER_PLAUSIBILITY.values():
        assert tier_range.min_val_bpb > 0
        assert tier_range.max_val_bpb > 0
        assert tier_range.min_vram_mb > 0
        assert tier_range.max_vram_mb > 0
        assert tier_range.min_tokens_m > 0
        assert tier_range.max_tokens_m > 0
        assert tier_range.min_val_bpb < tier_range.max_val_bpb
        assert tier_range.min_vram_mb < tier_range.max_vram_mb
        assert tier_range.min_tokens_m < tier_range.max_tokens_m


def test_score_constants_have_expected_relationships() -> None:
    assert MIN_PLAUSIBLE_VAL_BPB > 0
    assert MAX_VAL_BPB > MIN_PLAUSIBLE_VAL_BPB
    assert MIN_ELAPSED_SECONDS > 0
    assert MAX_SINGLE_STEP_IMPROVEMENT > 0
    assert REPLAY_SAMPLE_RATE > 0
    assert PARTICIPATION_SCORE > 0
    assert PARTICIPATION_SCORE < MAX_SCORE
