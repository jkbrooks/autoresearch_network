from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class MockHotkey:
    ss58_address: str


@dataclass
class MockWallet:
    hotkey: MockHotkey


@dataclass
class MockAxon:
    hotkey: str
    is_serving: bool = True


class MockMetagraph:
    def __init__(
        self,
        hotkeys: list[str] | None = None,
        *,
        validator_permit: list[bool] | None = None,
        stakes: list[float] | None = None,
        serving: list[bool] | None = None,
    ) -> None:
        self.hotkeys = hotkeys or ["miner-a", "miner-b", "miner-c"]
        serving_flags = serving or [True for _ in self.hotkeys]
        self.axons = [
            MockAxon(hotkey=hotkey, is_serving=serving_flags[index])
            for index, hotkey in enumerate(self.hotkeys)
        ]
        self.validator_permit = validator_permit or [True for _ in self.hotkeys]
        self.S = stakes or [1_500.0 for _ in self.hotkeys]
        self.uids = np.arange(len(self.hotkeys), dtype=int)

    @property
    def n(self) -> int:
        return len(self.hotkeys)


class MockSubtensor:
    def __init__(self) -> None:
        self.set_weights_called = False
        self.last_set_weights: dict[str, Any] | None = None

    def get_current_block(self) -> int:
        return 123456

    def set_weights(self, **kwargs: Any) -> bool:
        self.set_weights_called = True
        self.last_set_weights = kwargs
        return True


class MockDendrite:
    def __init__(self, responses: list[Any] | None = None) -> None:
        self.responses = responses or []
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        axons: list[Any],
        synapse: Any,
        deserialize: bool = False,
        timeout: float = 0.0,
    ) -> list[Any]:
        self.calls.append(
            {
                "axons": axons,
                "synapse": synapse,
                "deserialize": deserialize,
                "timeout": timeout,
            }
        )
        return list(self.responses)


def make_validator_config(tmp_path: Path, *, alpha: float = 0.3) -> dict[str, Any]:
    return make_custom_validator_config(
        tmp_path,
        alpha=alpha,
    )


def make_custom_validator_config(
    tmp_path: Path,
    *,
    alpha: float = 0.3,
    uid: int = 7,
    wallet: MockWallet | None = None,
    subtensor: MockSubtensor | None = None,
    metagraph: MockMetagraph | None = None,
    dendrite: MockDendrite | None = None,
) -> dict[str, Any]:
    return {
        "uid": uid,
        "wallet": wallet or MockWallet(MockHotkey("validator-hotkey")),
        "subtensor": subtensor or MockSubtensor(),
        "metagraph": metagraph or MockMetagraph(),
        "dendrite": dendrite or MockDendrite(),
        "neuron": {
            "full_path": str(tmp_path / "validator-state"),
            "moving_average_alpha": alpha,
        },
    }
