from __future__ import annotations

import importlib
import subprocess
import sys

import numpy as np
from validator_test_utils import MockMetagraph, make_validator_config

import autoresearch.base.validator as base_validator_module
from neurons.validator import Validator


def test_validator_imports_cleanly() -> None:
    module = importlib.import_module("neurons.validator")

    assert hasattr(module, "Validator")


def test_validator_instantiates_with_mock(tmp_path) -> None:
    config = make_validator_config(tmp_path=tmp_path)
    validator = Validator(config=config)

    assert validator.wallet.hotkey.ss58_address == "validator-hotkey"
    assert validator.uid == 7


def test_scores_array_shape(tmp_path) -> None:
    validator = Validator(config=make_validator_config(tmp_path))

    assert validator.scores.shape == (validator.metagraph.n,)


def test_state_save_load_roundtrip(tmp_path) -> None:
    config = make_validator_config(tmp_path)
    validator = Validator(config=config)
    validator.scores = np.asarray([0.5, 0.25, 0.75], dtype=float)
    validator.step = 9
    validator.save_state()

    restored = Validator(config=config)
    restored.load_state()

    assert restored.step == 9
    assert restored.scores.tolist() == [0.5, 0.25, 0.75]


def test_hotkey_replacement_resets_score(tmp_path) -> None:
    config = make_validator_config(tmp_path)
    validator = Validator(config=config)
    validator.scores = np.asarray([0.9, 0.4, 0.1], dtype=float)
    validator.resync_metagraph(MockMetagraph(["miner-a", "miner-z", "miner-c"]))

    assert validator.scores.tolist() == [0.9, 0.0, 0.1]


def test_set_weights_records_payload(tmp_path) -> None:
    validator = Validator(config=make_validator_config(tmp_path))
    validator.scores = np.asarray([0.2, 0.3, 0.5], dtype=float)

    submitted = validator.set_weights()

    assert submitted is True
    assert validator.subtensor.set_weights_called
    assert validator.subtensor.last_set_weights is not None
    assert validator.subtensor.last_set_weights["weights"] == [0.2, 0.3, 0.5]


def test_validator_supports_bittensor_runtime_factory(tmp_path, monkeypatch) -> None:
    mock_config = {
        "wallet": make_validator_config(tmp_path)["wallet"],
        "subtensor": make_validator_config(tmp_path)["subtensor"],
        "metagraph": make_validator_config(tmp_path)["metagraph"],
        "dendrite": make_validator_config(tmp_path)["dendrite"],
    }

    def fake_build_runtime(config):
        del config
        return (
            mock_config["wallet"],
            mock_config["subtensor"],
            mock_config["metagraph"],
            mock_config["dendrite"],
        )

    monkeypatch.setattr(base_validator_module, "bt", object())
    monkeypatch.setattr(base_validator_module, "_build_bittensor_runtime", fake_build_runtime)

    validator = Validator(config={"netuid": 11, "subtensor.network": "test"})

    assert validator.runtime_mode == "bittensor"
    assert validator.netuid == 11
    assert validator.network == "test"


def test_validator_cli_accepts_ticket_flags_with_mock_runtime(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "neurons/validator.py",
            "--netuid",
            "11",
            "--subtensor.network",
            "test",
            "--wallet.name",
            "validator-wallet",
            "--wallet.hotkey",
            "validator-hotkey",
            "--subtensor._mock",
            "--skip-health-check",
            "--neuron.full-path",
            str(tmp_path / "validator-state"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "netuid=11" in result.stdout
    assert "network=test" in result.stdout
