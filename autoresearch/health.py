"""Startup health checks for miners."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from bittensor.core.subtensor import Subtensor
from bittensor_wallet.wallet import Wallet

LOGGER = logging.getLogger(__name__)


@dataclass
class HealthResult:
    name: str
    status: str
    message: str


class HealthCheck:
    def __init__(
        self,
        config: Any,
        *,
        cache_dir: str | None = None,
        uv_command: str = "uv",
    ) -> None:
        self.config = config
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "autoresearch"
        self.uv_command = uv_command

    def run_all(self) -> list[HealthResult]:
        if getattr(self.config, "skip_health_check", False):
            return []
        return [
            self.check_gpu(),
            self.check_uv(),
            self.check_data_cache(),
            self.check_vram_minimum(),
            self.check_wallet(),
            self.check_bittensor_connection(),
        ]

    def check_gpu(self) -> HealthResult:
        if not torch.cuda.is_available():
            return HealthResult(
                "check_gpu",
                "fail",
                "No CUDA GPU detected. A GPU with ≥8GB VRAM is required to mine.",
            )
        return HealthResult("check_gpu", "ok", "CUDA GPU detected.")

    def check_uv(self) -> HealthResult:
        if shutil.which(self.uv_command) is None:
            return HealthResult(
                "check_uv",
                "fail",
                "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh",
            )
        return HealthResult("check_uv", "ok", "uv available.")

    def check_data_cache(self) -> HealthResult:
        if not self.cache_dir.exists() or not any(self.cache_dir.rglob("*.bin")):
            return HealthResult(
                "check_data_cache",
                "fail",
                "Data cache not found at ~/.cache/autoresearch/. Run: uv run prepare.py",
            )
        return HealthResult("check_data_cache", "ok", "Data cache available.")

    def check_vram_minimum(self) -> HealthResult:
        if not torch.cuda.is_available():
            return HealthResult(
                "check_vram_minimum",
                "warn",
                "CUDA unavailable; VRAM check skipped.",
            )
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        if vram_gb < 8:
            return HealthResult(
                "check_vram_minimum",
                "warn",
                f"GPU VRAM is {vram_gb:.1f}GB, below 8GB minimum for SMALL tier. "
                "Performance will be very limited.",
            )
        return HealthResult("check_vram_minimum", "ok", f"GPU VRAM is {vram_gb:.1f}GB.")

    def check_wallet(self) -> HealthResult:
        wallet = Wallet(
            name=self.config.wallet.name,
            hotkey=self.config.wallet.hotkey,
            path=self.config.wallet.path,
        )
        if not wallet.hotkey_file.exists_on_device():
            return HealthResult(
                "check_wallet",
                "fail",
                f"Wallet '{self.config.wallet.name}' hotkey "
                f"'{self.config.wallet.hotkey}' not found. "
                "Create with: btcli wallet new_hotkey ...",
            )
        return HealthResult("check_wallet", "ok", "Wallet available.")

    def check_bittensor_connection(self) -> HealthResult:
        try:
            subtensor = Subtensor(network=self.config.subtensor.network)
            subtensor.get_current_block()
        except Exception:
            return HealthResult(
                "check_bittensor_connection",
                "warn",
                f"Could not connect to Bittensor {self.config.subtensor.network}. "
                "Miner will start but may not receive challenges.",
            )
        return HealthResult("check_bittensor_connection", "ok", "Bittensor reachable.")
