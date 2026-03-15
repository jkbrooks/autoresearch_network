"""Validator entrypoint scaffold for local and testnet validator runs."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any

import numpy as np
from numpy.typing import NDArray

from autoresearch.base import BaseValidatorNeuron
from autoresearch.hardware import detect_hardware
from autoresearch.validator.best_tracker import BestTracker
from autoresearch.validator.forward import forward as validator_forward
from autoresearch.validator.stats import MinerStats

LOGGER = logging.getLogger(__name__)


def _make_runtime_wallet(wallet_name: str, wallet_hotkey: str) -> Any:
    """Create a minimal local wallet object for mock-runtime CLI runs."""

    return type(
        "Wallet",
        (),
        {
            "name": wallet_name,
            "hotkey": type("Hotkey", (), {"ss58_address": wallet_hotkey})(),
        },
    )()


class Validator(BaseValidatorNeuron):
    """Validator scaffold with stable runtime-owned state containers."""

    def __init__(self, config: object | None = None) -> None:
        super().__init__(config=config)
        self.submission_hashes: dict[str, str] = {}
        self.miner_stats: dict[str, MinerStats] = {}
        self.log_messages: list[str] = []
        self.last_round: dict[str, object] = {}
        self.tracker = BestTracker(state_dir=self.neuron_path)
        self.load_state()

    @property
    def skip_health_check(self) -> bool:
        if isinstance(self.config, dict):
            return bool(self.config.get("skip_health_check", False))
        return bool(getattr(self.config, "skip_health_check", False))

    @property
    def guards_state_path(self) -> Any:
        return self.neuron_path / "submission_hashes.json"

    @property
    def miner_stats_path(self) -> Any:
        return self.neuron_path / "miner_stats.json"

    def _save_guards_state(self) -> None:
        self.guards_state_path.write_text(
            json.dumps(self.submission_hashes, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_guards_state(self) -> None:
        if not self.guards_state_path.exists():
            self.submission_hashes = {}
            return
        self.submission_hashes = json.loads(self.guards_state_path.read_text(encoding="utf-8"))

    def _save_miner_stats(self) -> None:
        payload = {hotkey: asdict(stats) for hotkey, stats in self.miner_stats.items()}
        self.miner_stats_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_miner_stats(self) -> None:
        if not self.miner_stats_path.exists():
            self.miner_stats = {}
            return
        raw = json.loads(self.miner_stats_path.read_text(encoding="utf-8"))
        self.miner_stats = {
            hotkey: MinerStats(**stats_payload) for hotkey, stats_payload in raw.items()
        }

    def save_state(self) -> None:
        super().save_state()
        self.tracker.save()
        self._save_guards_state()
        self._save_miner_stats()

    def load_state(self) -> None:
        super().load_state()
        self.tracker.load()
        self._load_guards_state()
        self._load_miner_stats()

    def _log_health(self, level: str, name: str, message: str) -> None:
        suffix = f": {message}" if message else ""
        rendered = f"[HEALTH {level.upper()}] {name}{suffix}"
        self.log_messages.append(rendered)
        if level == "fail":
            LOGGER.error(rendered)
        elif level == "warn":
            LOGGER.warning(rendered)
        else:
            LOGGER.info(rendered)

    def _check_wallet(self) -> tuple[str, str]:
        hotkey = getattr(getattr(self.wallet, "hotkey", None), "ss58_address", "")
        has_hotkey_file = hasattr(self.wallet, "hotkey_file")
        has_exists = has_hotkey_file and hasattr(self.wallet.hotkey_file, "exists_on_device")
        if has_exists:
            exists = bool(self.wallet.hotkey_file.exists_on_device())
            if not exists:
                return "fail", "Wallet hotkey file does not exist on device"
            return "ok", hotkey or str(getattr(self.wallet, "hotkey_str", ""))
        if hotkey:
            return "ok", hotkey
        return "fail", "Wallet hotkey is missing"

    def _check_connection(self) -> tuple[str, str]:
        try:
            block = self.subtensor.get_current_block()
        except Exception as exc:  # pragma: no cover - exercised via tests
            return "fail", str(exc)
        return "ok", f"block={block}"

    def _check_stake(self) -> tuple[str, str]:
        stakes = getattr(self.metagraph, "S", [])
        if not stakes:
            return "warn", "No metagraph stake data available"
        if 0 <= self.uid < len(stakes):
            stake = float(stakes[self.uid])
        else:
            stake = float(stakes[0])
        if stake < 1000.0:
            return "warn", f"stake {stake:.1f} below validator minimum 1000.0"
        return "ok", f"stake={stake:.1f}"

    def _check_gpu(self) -> tuple[str, str]:
        hardware = detect_hardware()
        if hardware.vram_mb is None:
            return "warn", "No CUDA GPU detected; replay verification disabled"
        if hardware.vram_mb < 8_192.0:
            return "fail", f"GPU VRAM {hardware.vram_mb:.1f} MB below replay minimum 8192.0 MB"
        return "ok", f"vram_mb={hardware.vram_mb:.1f}"

    def _run_health_check(self) -> None:
        if self.skip_health_check:
            return
        failures: list[str] = []
        checks = (
            ("wallet_exists", self._check_wallet),
            ("network_connection", self._check_connection),
            ("stake_minimum", self._check_stake),
            ("gpu_for_replay", self._check_gpu),
        )
        for name, check in checks:
            status, message = check()
            self._log_health(status, name, message)
            if status == "fail":
                failures.append(name)
        if failures:
            raise SystemExit(f"Validator startup failed: {failures}")

    async def forward(self) -> NDArray[np.float64]:
        """Run one validator tempo against the current runtime surfaces."""

        result: NDArray[np.float64] = await validator_forward(self)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoResearch validator scaffold")
    parser.add_argument("--netuid", type=int, default=1)
    parser.add_argument("--network", dest="subtensor_network_alias", default=None)
    parser.add_argument("--subtensor.network", dest="subtensor.network", default="finney")
    parser.add_argument("--wallet.name", dest="wallet.name", default="default")
    parser.add_argument("--wallet.hotkey", dest="wallet.hotkey", default="default")
    parser.add_argument("--wallet.path", dest="wallet.path", default="~/.bittensor/wallets")
    parser.add_argument("--logging.debug", dest="logging.debug", action="store_true")
    parser.add_argument("--subtensor._mock", dest="subtensor._mock", action="store_true")
    parser.add_argument("--uid", type=int, default=0)
    parser.add_argument("--skip-health-check", action="store_true")
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--wallet-hotkey", default=None)
    parser.add_argument("--neuron.full-path", dest="neuron_full_path", default=".validator-state")
    parser.add_argument(
        "--neuron.moving-average-alpha",
        dest="moving_average_alpha",
        type=float,
        default=0.3,
    )
    args = parser.parse_args()
    if getattr(args, "logging.debug"):
        logging.basicConfig(level=logging.DEBUG)

    wallet_name = getattr(args, "wallet.name")
    wallet_hotkey = getattr(args, "wallet.hotkey")
    if args.wallet_hotkey:
        wallet_hotkey = args.wallet_hotkey
    network = args.subtensor_network_alias or getattr(args, "subtensor.network")
    mock_runtime = bool(getattr(args, "subtensor._mock"))

    config = {
        "netuid": args.netuid,
        "uid": args.uid,
        "skip_health_check": args.skip_health_check,
        "wallet.name": wallet_name,
        "wallet.hotkey": wallet_hotkey,
        "wallet.path": getattr(args, "wallet.path"),
        "subtensor.network": network,
        "subtensor._mock": mock_runtime,
        "neuron": {
            "full_path": args.neuron_full_path,
            "moving_average_alpha": args.moving_average_alpha,
        },
    }
    if mock_runtime:
        config["wallet"] = _make_runtime_wallet(wallet_name, wallet_hotkey)

    validator = Validator(config=config)
    validator._run_health_check()
    print(
        "AutoResearch validator scaffold loaded:",
        f"uid={validator.uid}",
        f"netuid={validator.netuid}",
        f"network={validator.network}",
        "hotkey="
        f"{getattr(getattr(validator.wallet, 'hotkey', None), 'ss58_address', wallet_hotkey)}",
        f"metagraph_n={validator.metagraph.n}",
        f"runtime={validator.runtime_mode}",
    )
    if args.run_once:
        final_scores = asyncio.run(validator.forward())
        print("Round complete:", final_scores.tolist())
    validator.save_state()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
