from __future__ import annotations

import asyncio
import logging

import pytest
from validator_test_utils import MockDendrite, MockMetagraph, make_custom_validator_config

from autoresearch.constants import PARTICIPATION_SCORE, HardwareTier
from autoresearch.mock import MockSubmissionFactory
from neurons.validator import Validator


def _make_response(
    *,
    baseline: float,
    improvement: float,
    tier: HardwareTier = HardwareTier.LARGE,
    seed: int = 42,
):
    factory = MockSubmissionFactory(seed=seed)
    return factory.make_submission(
        baseline_val_bpb=baseline,
        tier=tier,
        improvement=improvement,
    )


def test_forward_queries_all_active_miners(tmp_path) -> None:
    responses = [
        _make_response(baseline=1.0, improvement=0.01),
        _make_response(baseline=1.0, improvement=0.0),
        _make_response(baseline=1.0, improvement=-0.01),
    ]
    dendrite = MockDendrite(responses)
    metagraph = MockMetagraph(["miner-a", "miner-b", "miner-c"])
    config = make_custom_validator_config(tmp_path, uid=0, metagraph=metagraph, dendrite=dendrite)
    validator = Validator(config=config)
    validator.tracker.val_bpb = 1.0
    validator.tracker.train_py = "print('baseline')\n"

    asyncio.run(validator.forward())

    assert len(dendrite.calls) == 1
    assert len(dendrite.calls[0]["axons"]) == 3
    assert validator.last_round["miner_uids"] == [0, 1, 2]


def test_forward_scores_and_updates_global_best(tmp_path) -> None:
    responses = [
        _make_response(baseline=1.0, improvement=0.02, seed=42),
        _make_response(baseline=1.0, improvement=0.0, seed=7),
    ]
    responses[1].train_py = "print('very different source')\n"
    config = make_custom_validator_config(
        tmp_path,
        uid=0,
        metagraph=MockMetagraph(["miner-a", "miner-b"]),
        dendrite=MockDendrite(responses),
    )
    validator = Validator(config=config)
    validator.tracker.val_bpb = 1.0
    validator.tracker.train_py = "print('baseline')\n"

    final_scores = asyncio.run(validator.forward())

    assert final_scores[0] > PARTICIPATION_SCORE
    assert final_scores[1] == PARTICIPATION_SCORE
    assert validator.tracker.val_bpb == pytest.approx(0.98)
    assert validator.tracker.achieved_by == "miner-a"
    assert validator.scores[0] == pytest.approx(final_scores[0] * 0.3)


def test_forward_non_responder_scores_zero_and_sets_weights(tmp_path) -> None:
    responses = [
        _make_response(baseline=1.0, improvement=0.0),
        type(
            "Response",
            (),
            {"val_bpb": None, "train_py": None, "run_log_tail": None, "hardware_tier": None},
        )(),
    ]
    config = make_custom_validator_config(
        tmp_path,
        uid=0,
        metagraph=MockMetagraph(["miner-a", "miner-b"]),
        dendrite=MockDendrite(responses),
    )
    validator = Validator(config=config)
    validator.tracker.val_bpb = 1.0
    validator.tracker.train_py = "print('baseline')\n"

    final_scores = asyncio.run(validator.forward())

    assert final_scores[1] == 0.0
    assert validator.subtensor.set_weights_called is True


def test_forward_near_duplicate_submission_is_penalized(tmp_path) -> None:
    first = _make_response(baseline=1.0, improvement=0.02, seed=42)
    second = _make_response(baseline=1.0, improvement=0.015, seed=7)
    second.train_py = (first.train_py or "").replace("depth_sweep_seed_42", "depth_sweep_seed_43")
    config = make_custom_validator_config(
        tmp_path,
        uid=0,
        metagraph=MockMetagraph(["miner-a", "miner-b"]),
        dendrite=MockDendrite([first, second]),
    )
    validator = Validator(config=config)
    validator.tracker.val_bpb = 1.0
    validator.tracker.train_py = "print('baseline')\n"

    final_scores = asyncio.run(validator.forward())

    assert final_scores[0] > 0.0
    assert final_scores[1] > 0.0
    assert final_scores[1] < final_scores[0]


def test_forward_no_active_miners_returns_empty(tmp_path, caplog) -> None:
    caplog.set_level(logging.WARNING)
    metagraph = MockMetagraph(["miner-a"], serving=[False])
    config = make_custom_validator_config(tmp_path, uid=0, metagraph=metagraph)
    validator = Validator(config=config)

    final_scores = asyncio.run(validator.forward())

    assert final_scores.shape == (0,)
    assert "Queried 0 miners | 0 responded" in caplog.text
