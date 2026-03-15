from __future__ import annotations

import numpy as np
from validator_test_utils import MockMetagraph, make_validator_config

from autoresearch.base import BaseValidatorNeuron
from autoresearch.mock import MockSubmissionFactory
from autoresearch.validator.stats import (
    MinerStats,
    ensure_miner_stats_entry,
    format_leaderboard,
    update_miner_stats,
)


def test_ema_single_update(tmp_path) -> None:
    validator = BaseValidatorNeuron(config=make_validator_config(tmp_path, alpha=0.3))

    validator.update_scores([1.0, 0.5], [0, 1])

    assert validator.scores.tolist() == [0.3, 0.15, 0.0]


def test_ema_converges(tmp_path) -> None:
    validator = BaseValidatorNeuron(config=make_validator_config(tmp_path, alpha=0.3))

    for _ in range(20):
        validator.update_scores([1.0], [0])

    assert validator.scores[0] > 0.99


def test_new_uid_gets_zero_after_resync(tmp_path) -> None:
    validator = BaseValidatorNeuron(config=make_validator_config(tmp_path))
    validator.scores = np.asarray([0.8, 0.4, 0.2], dtype=float)

    validator.resync_metagraph(MockMetagraph(["miner-a", "miner-b", "miner-c", "miner-d"]))

    assert validator.scores.tolist() == [0.8, 0.4, 0.2, 0.0]


def test_ensure_miner_stats_entry_reuses_existing_entry() -> None:
    miner_stats: dict[str, MinerStats] = {}

    created = ensure_miner_stats_entry(miner_stats, hotkey="miner-a", uid=3)
    reused = ensure_miner_stats_entry(miner_stats, hotkey="miner-a", uid=5)

    assert created is reused
    assert reused.uid == 5
    assert len(miner_stats) == 1


def test_miner_stats_increments_experiment(tmp_path) -> None:
    factory = MockSubmissionFactory(seed=42)
    response = factory.make_submission()
    metagraph = MockMetagraph(["miner-a"])
    miner_stats: dict[str, MinerStats] = {}

    update_miner_stats(
        miner_stats,
        responses=[response],
        miner_uids=[0],
        metagraph=metagraph,
        current_best_bpb=1.5,
        observed_at="2026-03-14T12:00:00+00:00",
    )

    assert miner_stats["miner-a"].total_experiments == 1
    assert miner_stats["miner-a"].last_seen == "2026-03-14T12:00:00+00:00"


def test_miner_stats_increments_improvement(tmp_path) -> None:
    factory = MockSubmissionFactory(seed=7)
    response = factory.make_submission(baseline_val_bpb=1.2, improvement=0.1)
    metagraph = MockMetagraph(["miner-a"])
    miner_stats: dict[str, MinerStats] = {}

    update_miner_stats(
        miner_stats,
        responses=[response],
        miner_uids=[0],
        metagraph=metagraph,
        current_best_bpb=1.2,
    )

    assert miner_stats["miner-a"].total_improvements == 1
    assert miner_stats["miner-a"].best_val_bpb == response.val_bpb


def test_miner_stats_no_increment_for_null_response() -> None:
    response = type("Response", (), {"val_bpb": None})()
    metagraph = MockMetagraph(["miner-a"])
    miner_stats: dict[str, MinerStats] = {}

    update_miner_stats(
        miner_stats,
        responses=[response],
        miner_uids=[0],
        metagraph=metagraph,
        current_best_bpb=1.2,
    )

    assert miner_stats == {}


def test_format_leaderboard_orders_by_improvements_then_experiments() -> None:
    miner_stats = {
        "miner-b": MinerStats(
            hotkey="miner-b",
            uid=1,
            total_experiments=4,
            total_improvements=1,
            best_val_bpb=1.01,
        ),
        "miner-a": MinerStats(
            hotkey="miner-a",
            uid=0,
            total_experiments=7,
            total_improvements=2,
            best_val_bpb=0.99,
        ),
        "miner-c": MinerStats(
            hotkey="miner-c",
            uid=2,
            total_experiments=9,
            total_improvements=2,
            best_val_bpb=1.0,
        ),
    }

    lines = format_leaderboard(miner_stats, top_n=2)

    assert lines[0].startswith("1. miner-c")
    assert lines[1].startswith("2. miner-a")
