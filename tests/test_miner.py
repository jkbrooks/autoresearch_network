from __future__ import annotations

import asyncio
from types import SimpleNamespace

from autoresearch.experiment_runner import RunResult
from autoresearch.protocol import ExperimentSubmission
from autoresearch.utils.config import build_config
from neurons.miner import MIN_VALIDATOR_STAKE, Miner


def make_synapse() -> ExperimentSubmission:
    return ExperimentSubmission(
        task_id="round_test_001",
        baseline_train_py="print('baseline')\n",
        global_best_val_bpb=1.1,
    )


def build_mock_config() -> SimpleNamespace:
    return build_config(["--mock", "--skip-health-check"])


def make_miner(monkeypatch) -> Miner:
    monkeypatch.setattr("neurons.miner.ExperimentRunner.setup", lambda self: True)
    return Miner(config=build_mock_config())


def test_miner_imports_cleanly() -> None:
    from neurons.miner import Miner as ImportedMiner

    assert ImportedMiner is Miner


def test_miner_instantiates_with_mock_config(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    assert miner.uid == 0
    assert miner.wallet.hotkey.ss58_address in miner.metagraph.hotkeys


def test_forward_successful_run(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    synapse = make_synapse()
    miner._last_baseline = synapse.baseline_train_py
    miner.strategy = SimpleNamespace(propose=lambda _: "print('mutated')\n")
    miner.runner = SimpleNamespace(
        run=lambda _: RunResult(
            val_bpb=1.01,
            total_seconds=301.0,
            peak_vram_mb=24_000.0,
            run_log_tail="ok",
            status="success",
        )
    )
    monkeypatch.setattr(
        "neurons.miner.detect_hardware_tier",
        lambda **_: SimpleNamespace(value="large"),
    )

    synapse = asyncio.run(miner.forward(synapse))

    assert synapse.val_bpb == 1.01
    assert synapse.train_py == "print('mutated')\n"
    assert synapse.hardware_tier == "large"
    assert synapse.elapsed_wall_seconds == 301
    assert synapse.peak_vram_mb == 24_000.0
    assert synapse.run_log_tail == "ok"


def test_forward_concurrent_request_returns_unfilled(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    miner._experiment_lock.acquire()
    try:
        synapse = asyncio.run(miner.forward(make_synapse()))
    finally:
        miner._experiment_lock.release()
    assert synapse.val_bpb is None
    assert synapse.train_py is None


def test_forward_crash_returns_unfilled(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    synapse = make_synapse()
    miner._last_baseline = synapse.baseline_train_py
    miner.strategy = SimpleNamespace(propose=lambda _: "print('mutated')\n")
    miner.runner = SimpleNamespace(
        run=lambda _: RunResult(
            total_seconds=302.0,
            peak_vram_mb=24_000.0,
            run_log_tail="traceback",
            status="crash",
        )
    )
    monkeypatch.setattr(
        "neurons.miner.detect_hardware_tier",
        lambda **_: SimpleNamespace(value="large"),
    )

    synapse = asyncio.run(miner.forward(synapse))
    assert synapse.val_bpb is None
    assert synapse.run_log_tail == "traceback"


def test_forward_mutations_exhausted_returns_unfilled(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    baseline = "print('baseline')\n"
    miner.strategy = SimpleNamespace(propose=lambda _: baseline)
    synapse = make_synapse()
    synapse.baseline_train_py = baseline
    result = asyncio.run(miner.forward(synapse))
    assert result.train_py is None


def test_forward_baseline_change_resets_strategy(monkeypatch) -> None:
    created: list[object] = []

    class FakeStrategy:
        def propose(self, baseline: str) -> str:
            return baseline + "# mutated\n"

    def fake_build(self):
        strategy = FakeStrategy()
        created.append(strategy)
        return strategy

    monkeypatch.setattr("neurons.miner.ExperimentRunner.setup", lambda self: True)
    monkeypatch.setattr(Miner, "_build_strategy", fake_build)
    monkeypatch.setattr(
        "neurons.miner.detect_hardware_tier",
        lambda **_: SimpleNamespace(value="large"),
    )
    miner = Miner(config=build_mock_config())
    miner.runner = SimpleNamespace(run=lambda _: RunResult(status="success", val_bpb=1.0))

    first = make_synapse()
    second = make_synapse()
    second.baseline_train_py = "print('other')\n"
    asyncio.run(miner.forward(first))
    asyncio.run(miner.forward(second))

    assert len(created) == 3  # __init__, first baseline, second baseline


def test_blacklist_missing_dendrite(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    synapse = make_synapse()
    synapse.dendrite = None
    blocked, _ = asyncio.run(miner.blacklist(synapse))
    assert blocked is True


def test_blacklist_unknown_hotkey(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    synapse = make_synapse()
    synapse.dendrite = {"hotkey": "unknown"}
    blocked, reason = asyncio.run(miner.blacklist(synapse))
    assert blocked is True
    assert reason == "Unrecognized hotkey"


def test_blacklist_low_stake(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    hotkey = miner.wallet.hotkey.ss58_address
    miner.metagraph = SimpleNamespace(
        hotkeys=[hotkey],
        validator_permit=[True],
        S=[MIN_VALIDATOR_STAKE - 1],
    )
    synapse = make_synapse()
    synapse.dendrite = {"hotkey": hotkey}
    blocked, reason = asyncio.run(miner.blacklist(synapse))
    assert blocked is True
    assert "Insufficient stake" in reason


def test_blacklist_valid_validator(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    hotkey = miner.wallet.hotkey.ss58_address
    miner.metagraph = SimpleNamespace(hotkeys=[hotkey], validator_permit=[True], S=[5_000.0])
    synapse = make_synapse()
    synapse.dendrite = {"hotkey": hotkey}
    blocked, reason = asyncio.run(miner.blacklist(synapse))
    assert blocked is False
    assert reason == "Recognized validator"


def test_blacklist_allow_non_registered(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    miner.config.blacklist.allow_non_registered = True
    synapse = make_synapse()
    synapse.dendrite = {"hotkey": "unknown"}
    blocked, reason = asyncio.run(miner.blacklist(synapse))
    assert blocked is False
    assert "Non-registered allowed" in reason


def test_blacklist_skip_validator_permit(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    hotkey = miner.wallet.hotkey.ss58_address
    miner.config.blacklist.force_validator_permit = False
    miner.metagraph = SimpleNamespace(hotkeys=[hotkey], validator_permit=[False], S=[5_000.0])
    synapse = make_synapse()
    synapse.dendrite = {"hotkey": hotkey}
    blocked, _ = asyncio.run(miner.blacklist(synapse))
    assert blocked is False


def test_priority_returns_stake(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    hotkey = miner.wallet.hotkey.ss58_address
    miner.metagraph = SimpleNamespace(hotkeys=[hotkey], validator_permit=[True], S=[5_000.0])
    synapse = make_synapse()
    synapse.dendrite = {"hotkey": hotkey}
    assert asyncio.run(miner.priority(synapse)) == 5_000.0


def test_priority_unknown_hotkey(monkeypatch) -> None:
    miner = make_miner(monkeypatch)
    synapse = make_synapse()
    synapse.dendrite = {"hotkey": "unknown"}
    assert asyncio.run(miner.priority(synapse)) == 0.0
