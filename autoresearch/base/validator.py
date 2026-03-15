"""Validator runtime scaffold with mock and Bittensor-backed surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

try:
    import bittensor as bt  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional at import time for local-only tests
    bt = None


@dataclass
class _Hotkey:
    """Minimal hotkey container used when no runtime wallet is injected."""

    ss58_address: str = "mock-validator-hotkey"


@dataclass
class _Wallet:
    """Minimal wallet placeholder used for local-only validator runs."""

    hotkey: _Hotkey = field(default_factory=_Hotkey)


@dataclass
class _Axon:
    """Minimal serving axon placeholder."""

    hotkey: str = "mock-miner-hotkey"
    is_serving: bool = True


class _Metagraph:
    """Default metagraph placeholder for local validator instantiation."""

    def __init__(self, hotkeys: list[str] | None = None) -> None:
        self.hotkeys = hotkeys or ["mock-miner-hotkey"]
        self.axons = [_Axon(hotkey=hotkey) for hotkey in self.hotkeys]
        self.validator_permit = [True for _ in self.hotkeys]
        self.S = [1_500.0 for _ in self.hotkeys]
        self.uids = np.arange(len(self.hotkeys), dtype=int)

    @property
    def n(self) -> int:
        return len(self.hotkeys)


class _Subtensor:
    """Default subtensor placeholder that records weight submissions."""

    def __init__(self) -> None:
        self.set_weights_called = False
        self.last_set_weights: dict[str, Any] | None = None

    def get_current_block(self) -> int:
        return 1

    def set_weights(self, **kwargs: Any) -> bool:
        self.set_weights_called = True
        self.last_set_weights = kwargs
        return True


class _Dendrite:
    """Default dendrite placeholder for local validator runs."""

    async def __call__(
        self,
        *,
        axons: list[Any],
        synapse: Any,
        deserialize: bool = False,
        timeout: float = 0.0,
    ) -> list[Any]:
        del axons, deserialize, timeout
        return [synapse]


def _has_runtime_components(config: Any) -> bool:
    """Return whether the caller injected explicit runtime objects."""

    required = ("wallet", "subtensor", "metagraph", "dendrite")
    for key in required:
        if _config_value(config, key, None) is None:
            return False
    return True


def _wallet_hotkey_address(wallet: Any) -> str:
    """Best-effort access to a wallet hotkey address without forcing a strict type."""

    try:
        return str(wallet.hotkey.ss58_address)
    except Exception:
        return ""


def _build_mock_wallet(config: Any) -> Any:
    """Create a local wallet placeholder using configured identifiers when available."""

    configured_wallet = _config_value(config, "wallet", None)
    if configured_wallet is not None:
        return configured_wallet

    configured_hotkey = _config_value(config, "wallet.hotkey", "mock-validator-hotkey")
    hotkey_address = (
        configured_hotkey
        if isinstance(configured_hotkey, str)
        else getattr(configured_hotkey, "ss58_address", "mock-validator-hotkey")
    )
    return _Wallet(_Hotkey(str(hotkey_address)))


def _build_bittensor_runtime(config: Any) -> tuple[Any, Any, Any, Any]:
    """Create a real Bittensor wallet/subtensor/metagraph/dendrite runtime."""

    if bt is None:  # pragma: no cover - exercised only when bittensor import fails
        raise RuntimeError("bittensor is not available in this environment")

    wallet_name = _config_value(config, "wallet.name", "default")
    wallet_hotkey = _config_value(config, "wallet.hotkey", "default")
    wallet_path = _config_value(config, "wallet.path", "~/.bittensor/wallets")
    network = _config_value(config, "subtensor.network", "finney")
    use_mock = bool(_config_value(config, "subtensor._mock", False))
    netuid = int(_config_value(config, "netuid", 1))

    wallet = bt.Wallet(name=wallet_name, hotkey=wallet_hotkey, path=wallet_path)
    subtensor = bt.Subtensor(network=network, mock=use_mock)
    metagraph = bt.Metagraph(netuid=netuid, network=network, sync=True, subtensor=subtensor)
    dendrite = bt.Dendrite(wallet)
    return wallet, subtensor, metagraph, dendrite


def _config_value(config: Any, dotted_key: str, default: Any) -> Any:
    """Return a dotted config value from dict-like or attribute-like objects."""

    if config is None:
        return default

    if isinstance(config, dict) and dotted_key in config:
        return config[dotted_key]

    current = config
    for part in dotted_key.split("."):
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
            continue
        if hasattr(current, part):
            current = getattr(current, part)
            continue
        return default
    return current


class BaseValidatorNeuron:
    """Validator scaffold with local mocks and optional real Bittensor wiring."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config or {}
        self.netuid = int(_config_value(self.config, "netuid", 1))
        self.network = str(_config_value(self.config, "subtensor.network", "finney"))
        self.use_mock_runtime = bool(_config_value(self.config, "subtensor._mock", False))
        self.runtime_mode = "mock"

        if _has_runtime_components(self.config):
            self.wallet = _config_value(self.config, "wallet", _Wallet())
            self.subtensor = _config_value(self.config, "subtensor", _Subtensor())
            self.metagraph = _config_value(self.config, "metagraph", _Metagraph())
            self.dendrite = _config_value(self.config, "dendrite", _Dendrite())
            self.runtime_mode = "injected"
        elif bt is not None and not self.use_mock_runtime:
            self.wallet, self.subtensor, self.metagraph, self.dendrite = _build_bittensor_runtime(
                self.config
            )
            self.runtime_mode = "bittensor"
        else:
            self.wallet = _build_mock_wallet(self.config)
            self.subtensor = _Subtensor()
            self.metagraph = _Metagraph()
            self.dendrite = _Dendrite()

        self.uid = int(_config_value(self.config, "uid", 0))
        self.step = int(_config_value(self.config, "step", 0))
        self.moving_average_alpha = float(
            _config_value(self.config, "neuron.moving_average_alpha", 0.3)
        )

        neuron_full_path = _config_value(self.config, "neuron.full_path", ".validator-state")
        self.neuron_path = Path(neuron_full_path)
        self.neuron_path.mkdir(parents=True, exist_ok=True)

        self.scores = np.zeros(self.metagraph.n, dtype=float)
        self._last_hotkeys = list(self.metagraph.hotkeys)
        self.last_set_weights: dict[str, Any] | None = None
        self.hotkey = _wallet_hotkey_address(self.wallet)
        if self.hotkey and self.hotkey in self.metagraph.hotkeys:
            self.uid = self.metagraph.hotkeys.index(self.hotkey)

    @property
    def state_path(self) -> Path:
        """Path to the default validator score state file."""

        return self.neuron_path / "state.npz"

    def __enter__(self) -> BaseValidatorNeuron:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        self.save_state()

    def load_state(self) -> None:
        """Load score state if present, then realign to the current metagraph."""

        if not self.state_path.exists():
            self.resync_metagraph()
            return

        data = np.load(self.state_path, allow_pickle=True)
        try:
            loaded_scores = np.asarray(data["scores"], dtype=float)
            self.scores = loaded_scores
            if "step" in data:
                self.step = int(np.asarray(data["step"]).item())
            if "hotkeys" in data:
                self._last_hotkeys = [str(value) for value in data["hotkeys"].tolist()]
        finally:
            data.close()

        self.resync_metagraph()

    def save_state(self) -> None:
        """Persist score state for later round-trip and restart tests."""

        hotkeys = np.asarray(self.metagraph.hotkeys, dtype=object)
        np.savez(
            self.state_path,
            scores=np.asarray(self.scores, dtype=float),
            step=np.asarray(self.step, dtype=int),
            hotkeys=hotkeys,
        )

    def resync_metagraph(self, metagraph: Any | None = None) -> None:
        """Resize and realign scores to the current metagraph hotkeys."""

        if metagraph is not None:
            self.metagraph = metagraph
        elif self.runtime_mode == "bittensor" and hasattr(self.metagraph, "sync"):
            self.metagraph.sync(subtensor=self.subtensor)

        old_hotkeys = list(self._last_hotkeys)
        old_scores = np.asarray(self.scores, dtype=float)
        old_by_hotkey = {hotkey: old_scores[index] for index, hotkey in enumerate(old_hotkeys)}

        new_hotkeys = list(self.metagraph.hotkeys)
        new_scores = np.zeros(len(new_hotkeys), dtype=float)
        for index, hotkey in enumerate(new_hotkeys):
            if hotkey in old_by_hotkey:
                new_scores[index] = float(old_by_hotkey[hotkey])

        self.scores = new_scores
        self._last_hotkeys = new_hotkeys

    def update_scores(self, rewards: Any, miner_uids: Any) -> None:
        """Apply the standard EMA score update for the provided miner UIDs."""

        self.resync_metagraph()
        rewards_array = np.asarray(list(rewards), dtype=float)
        uid_list = [int(uid) for uid in miner_uids]
        if len(rewards_array) != len(uid_list):
            raise ValueError("Rewards and miner_uids must have the same length")

        for reward, uid in zip(rewards_array, uid_list, strict=True):
            if uid < 0 or uid >= len(self.scores):
                raise IndexError(f"Miner UID {uid} is outside the current metagraph")
            self.scores[uid] = self.moving_average_alpha * float(reward) + (
                1.0 - self.moving_average_alpha
            ) * float(self.scores[uid])

    def set_weights(self, weights: Any | None = None) -> bool:
        """Record and submit the latest weight vector through the runtime subtensor."""

        weights_array = np.asarray(self.scores if weights is None else weights, dtype=float)
        uids = (
            self.metagraph.uids.tolist()
            if hasattr(self.metagraph.uids, "tolist")
            else list(self.metagraph.uids)
        )
        payload = {
            "wallet": self.wallet,
            "netuid": self.netuid,
            "uids": uids,
            "weights": weights_array.tolist(),
        }
        self.last_set_weights = payload

        if hasattr(self.subtensor, "set_weights"):
            return bool(self.subtensor.set_weights(**payload))
        return True
