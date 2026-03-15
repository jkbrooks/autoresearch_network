from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from autoresearch.live_relay_proof import _resolve_target_ss58, run_live_relay_proof


def test_resolve_target_ss58_accepts_registered_ss58() -> None:
    result = _resolve_target_ss58(
        wallet_name="my-miner",
        wallet_path="~/.bittensor/wallets",
        metagraph_hotkeys=["5abc"],
        target_hotkey="5abc",
        fallback_ss58="5fallback",
    )
    assert result == "5abc"


def test_resolve_target_ss58_resolves_local_hotkey_name(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeWallet:
        def __init__(self, name: str, hotkey: str, path: str) -> None:
            assert name == "my-miner"
            assert hotkey == "default"
            assert path == "~/.bittensor/wallets"
            self.hotkey = SimpleNamespace(ss58_address="5resolved")

    monkeypatch.setattr("bittensor_wallet.wallet.Wallet", FakeWallet)
    result = _resolve_target_ss58(
        wallet_name="my-miner",
        wallet_path="~/.bittensor/wallets",
        metagraph_hotkeys=["5resolved"],
        target_hotkey="default",
        fallback_ss58="5fallback",
    )
    assert result == "5resolved"


def test_resolve_target_ss58_rejects_unknown_hotkey(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeWallet:
        def __init__(self, name: str, hotkey: str, path: str) -> None:
            self.hotkey = SimpleNamespace(ss58_address="5other")

    monkeypatch.setattr("bittensor_wallet.wallet.Wallet", FakeWallet)
    with pytest.raises(ValueError, match="not registered on the target metagraph"):
        _resolve_target_ss58(
            wallet_name="my-miner",
            wallet_path="~/.bittensor/wallets",
            metagraph_hotkeys=["5resolved"],
            target_hotkey="default",
            fallback_ss58="5fallback",
        )


def test_run_live_relay_proof_json_is_machine_readable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_run_probe(**_: object) -> dict[str, object]:
        return {
            "wallet_hotkey_ss58": "5caller",
            "target_uid": 0,
            "target_endpoint": "44.209.235.221:8091",
            "dendrite_status": 200,
            "dendrite_message": "Success",
            "axon_status": 200,
            "axon_message": "Success",
            "val_bpb": 0.9979,
            "hardware_tier": "large",
            "elapsed_wall_seconds": 301,
            "peak_vram_mb": 24000.0,
            "train_py_len": 548,
            "run_log_tail": "ok",
        }

    monkeypatch.setattr("autoresearch.live_relay_proof._run_probe", fake_run_probe)
    monkeypatch.setattr(
        "autoresearch.live_relay_proof._load_validator_state",
        lambda path: {"val_bpb": 0.9979, "achieved_by": "5miner"},
    )

    exit_code = run_live_relay_proof(as_json=True)
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["target_endpoint"] == "44.209.235.221:8091"
    assert payload["dendrite_status"] == 200
    assert payload["validator_state"]["val_bpb"] == 0.9979
