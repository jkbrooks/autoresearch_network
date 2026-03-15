from __future__ import annotations

import asyncio

from validator_test_utils import MockDendrite, MockMetagraph, make_custom_validator_config

from autoresearch.constants import PARTICIPATION_SCORE
from autoresearch.mock import MockSubmissionFactory
from neurons.validator import Validator


def _make_validator(tmp_path, *, responses, hotkeys=None, seed_tracker: bool = True) -> Validator:
    metagraph = MockMetagraph(hotkeys or ["miner-a", "miner-b", "miner-c"])
    config = make_custom_validator_config(
        tmp_path,
        uid=0,
        metagraph=metagraph,
        dendrite=MockDendrite(responses),
        alpha=0.3,
    )
    validator = Validator(config=config)
    if seed_tracker:
        validator.tracker.val_bpb = 1.0
        validator.tracker.train_py = "print('baseline')\n"
    return validator


def test_full_integration_cycle(tmp_path) -> None:
    factory = MockSubmissionFactory(seed=42)
    improvement = factory.make_submission(baseline_val_bpb=1.0, improvement=0.02)
    regression = factory.make_submission(baseline_val_bpb=1.0, improvement=-0.01)
    regression.train_py = "print('regression branch')\n"
    non_responder = type(
        "Response",
        (),
        {"val_bpb": None, "train_py": None, "hardware_tier": None, "run_log_tail": None},
    )()
    validator = _make_validator(tmp_path, responses=[improvement, regression, non_responder])

    asyncio.run(validator.forward())

    assert validator.scores[0] > PARTICIPATION_SCORE
    assert validator.scores[1] == PARTICIPATION_SCORE * 0.3
    assert validator.scores[2] == 0.0
    assert validator.tracker.val_bpb == 0.98
    assert validator.tracker.achieved_by == "miner-a"
    assert validator.subtensor.set_weights_called is True


def test_integration_duplicate_source_penalized(tmp_path) -> None:
    factory = MockSubmissionFactory(seed=10)
    first = factory.make_submission(baseline_val_bpb=1.0, improvement=0.02)
    second = factory.make_submission(baseline_val_bpb=1.0, improvement=0.015)
    second.train_py = first.train_py
    validator = _make_validator(tmp_path, responses=[first, second], hotkeys=["miner-a", "miner-b"])

    final_scores = asyncio.run(validator.forward())

    assert final_scores[0] > 0.0
    assert final_scores[1] == 0.0


def test_integration_global_best_propagates(tmp_path) -> None:
    factory = MockSubmissionFactory(seed=12)
    first = factory.make_submission(baseline_val_bpb=1.0, improvement=0.03)
    second = factory.make_submission(baseline_val_bpb=0.97, improvement=0.0)
    validator = _make_validator(tmp_path, responses=[first], hotkeys=["miner-a"])

    asyncio.run(validator.forward())
    validator.dendrite.responses = [second]
    asyncio.run(validator.forward())

    challenge = validator.last_round["challenge"]
    assert challenge.baseline_train_py == first.train_py
    assert challenge.global_best_val_bpb == 0.97


def test_integration_state_persists_across_restart(tmp_path) -> None:
    factory = MockSubmissionFactory(seed=21)
    improvement = factory.make_submission(baseline_val_bpb=1.0, improvement=0.02)
    validator = _make_validator(tmp_path, responses=[improvement], hotkeys=["miner-a"])

    asyncio.run(validator.forward())
    validator.save_state()
    restored = _make_validator(
        tmp_path, responses=[improvement], hotkeys=["miner-a"], seed_tracker=False
    )
    restored.load_state()

    assert restored.tracker.val_bpb == validator.tracker.val_bpb
    assert restored.scores.tolist() == validator.scores.tolist()


def test_integration_no_miners_responding(tmp_path) -> None:
    non_responder = type(
        "Response",
        (),
        {"val_bpb": None, "train_py": None, "hardware_tier": None, "run_log_tail": None},
    )()
    validator = _make_validator(tmp_path, responses=[non_responder], hotkeys=["miner-a"])

    final_scores = asyncio.run(validator.forward())

    assert final_scores.tolist() == [0.0]
    assert validator.tracker.val_bpb == 1.0
