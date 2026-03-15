from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest
from validator_test_utils import (
    MockDendrite,
    MockHotkey,
    MockMetagraph,
    MockSubtensor,
    MockWallet,
    make_custom_validator_config,
)

from autoresearch.mock import MockSubmissionFactory
from autoresearch.validator.stats import MinerStats
from neurons.validator import Validator


def test_full_state_roundtrip(tmp_path) -> None:
    config = make_custom_validator_config(tmp_path, uid=0)
    validator = Validator(config=config)
    validator.scores[:] = [0.2, 0.4, 0.6]
    validator.step = 5
    validator.tracker.update(0.99, "print('best')\n", "miner-a")
    validator.submission_hashes = {"hash-a": "miner-a"}
    validator.miner_stats = {
        "miner-a": MinerStats(
            hotkey="miner-a", uid=0, total_experiments=3, total_improvements=1, best_val_bpb=0.99
        )
    }
    validator.save_state()

    restored = Validator(config=config)

    assert restored.scores.tolist() == [0.2, 0.4, 0.6]
    assert restored.step == 5
    assert restored.tracker.val_bpb == 0.99
    assert restored.submission_hashes == {"hash-a": "miner-a"}
    assert restored.miner_stats["miner-a"].total_experiments == 3


def test_first_run_empty_dir_defaults(tmp_path) -> None:
    validator = Validator(config=make_custom_validator_config(tmp_path, uid=0))

    assert validator.scores.tolist() == [0.0, 0.0, 0.0]
    assert validator.submission_hashes == {}
    assert validator.miner_stats == {}
    assert validator.tracker.achieved_by == "baseline"


def test_health_missing_wallet_exits(tmp_path) -> None:
    config = make_custom_validator_config(
        tmp_path,
        uid=0,
        wallet=MockWallet(MockHotkey("")),
    )
    validator = Validator(config=config)

    with pytest.raises(SystemExit):
        validator._run_health_check()


def test_health_connection_fail_exits(tmp_path) -> None:
    class BrokenSubtensor(MockSubtensor):
        def get_current_block(self) -> int:
            raise RuntimeError("connection failed")

    config = make_custom_validator_config(tmp_path, uid=0, subtensor=BrokenSubtensor())
    validator = Validator(config=config)

    with pytest.raises(SystemExit):
        validator._run_health_check()


def test_health_low_stake_warns(tmp_path, caplog) -> None:
    caplog.set_level(logging.WARNING)
    config = make_custom_validator_config(
        tmp_path,
        uid=0,
        metagraph=MockMetagraph(["miner-a"], stakes=[500.0]),
    )
    validator = Validator(config=config)

    validator._run_health_check()

    assert "stake 500.0 below validator minimum" in caplog.text


def test_health_no_gpu_warns(tmp_path, monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING)
    config = make_custom_validator_config(tmp_path, uid=0)
    validator = Validator(config=config)
    monkeypatch.setattr(
        "neurons.validator.detect_hardware",
        lambda: SimpleNamespace(vram_mb=None, tier=SimpleNamespace(value="small")),
    )

    validator._run_health_check()

    assert "replay verification disabled" in caplog.text


def test_health_skip_flag_bypasses(tmp_path, monkeypatch) -> None:
    config = make_custom_validator_config(tmp_path, uid=0)
    config["skip_health_check"] = True
    validator = Validator(config=config)
    monkeypatch.setattr(
        "neurons.validator.detect_hardware",
        lambda: (_ for _ in ()).throw(RuntimeError("should not run")),
    )

    validator._run_health_check()


def test_periodic_save_every_10_steps(tmp_path) -> None:
    factory = MockSubmissionFactory(seed=42)
    response = factory.make_submission(baseline_val_bpb=1.0, improvement=0.0)
    config = make_custom_validator_config(
        tmp_path,
        uid=0,
        metagraph=MockMetagraph(["miner-a"]),
        dendrite=MockDendrite([response]),
    )
    validator = Validator(config=config)
    validator.tracker.val_bpb = 1.0
    validator.tracker.train_py = "print('baseline')\n"
    validator.step = 9

    asyncio.run(validator.forward())

    assert validator.state_path.exists()
    assert validator.guards_state_path.exists()
    assert validator.miner_stats_path.exists()
