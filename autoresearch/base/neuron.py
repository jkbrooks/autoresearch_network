"""Shared base neuron primitives for AutoResearch."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import SimpleNamespace
from typing import Any

import bittensor as bt
from bittensor.core.subtensor import Subtensor
from bittensor_wallet.mock import get_mock_wallet
from bittensor_wallet.wallet import Wallet

from autoresearch.utils.config import build_config, check_config


class _MockSubtensor:
    def __init__(self, wallet: Any, netuid: int) -> None:
        self.chain_endpoint = "mock"
        self._wallet = wallet
        self._netuid = netuid
        self._metagraph = SimpleNamespace(
            hotkeys=[wallet.hotkey.ss58_address],
            validator_permit=[True],
            S=[5_000.0],
            last_update=[0],
        )

    def is_hotkey_registered(self, netuid: int, hotkey_ss58: str) -> bool:
        return netuid == self._netuid and hotkey_ss58 in self._metagraph.hotkeys

    def metagraph(self, netuid: int) -> Any:
        if netuid != self._netuid:
            raise ValueError(f"Unknown mock netuid: {netuid}")
        return self._metagraph

    def get_current_block(self) -> int:
        return 0


class BaseNeuron(ABC):
    """Small compatibility layer over the modern Bittensor APIs."""

    neuron_type = "BaseNeuron"

    def __init__(self, config: Any = None) -> None:
        self.config = config if config is not None else build_config()
        check_config(self.config)
        self.device = self.config.neuron.device

        if self.config.mock:
            self.wallet = get_mock_wallet()
            self.subtensor = _MockSubtensor(self.wallet, self.config.netuid)
            self.metagraph = self.subtensor.metagraph(self.config.netuid)
        else:
            self.wallet = Wallet(
                name=self.config.wallet.name,
                hotkey=self.config.wallet.hotkey,
                path=self.config.wallet.path,
            )
            self.subtensor = Subtensor(network=self.config.subtensor.network)
            self.metagraph = self.subtensor.metagraph(self.config.netuid)

        self.uid = (
            self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
            if self.wallet.hotkey.ss58_address in self.metagraph.hotkeys
            else 0
        )
        bt.logging.info(f"Wallet hotkey: {self.wallet.hotkey.ss58_address}")
        bt.logging.info(f"UID: {self.uid}")
        bt.logging.info(f"Subtensor network: {self.config.subtensor.network}")

    @property
    def block(self) -> int:
        try:
            return int(self.subtensor.get_current_block())
        except Exception:
            return 0

    def ensure_registered(self) -> None:
        if self.config.mock:
            return
        if not self.subtensor.is_hotkey_registered(
            netuid=self.config.netuid,
            hotkey_ss58=self.wallet.hotkey.ss58_address,
        ):
            raise RuntimeError(
                f"Wallet hotkey {self.wallet.hotkey.ss58_address} is not registered on netuid "
                f"{self.config.netuid}"
            )

    def save_state(self) -> None:
        return None

    def load_state(self) -> None:
        return None

    @abstractmethod
    async def forward(self, synapse: Any) -> Any:
        ...
