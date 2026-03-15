"""AutoResearch miner neuron."""

import os
import threading
from typing import Any, Tuple

import bittensor as bt

from autoresearch.base import BaseMinerNeuron
from autoresearch.experiment_runner import ExperimentRunner
from autoresearch.hardware import detect_hardware_tier
from autoresearch.health import HealthCheck
from autoresearch.mutations import LLMMutationStrategy, StructuredMutationStrategy
from autoresearch.protocol import ExperimentSubmission
from autoresearch.utils.config import build_config

MIN_VALIDATOR_STAKE = 1000.0


class Miner(BaseMinerNeuron):
    """Miner implementation for AutoResearch experiments."""

    def __init__(self, config: Any = None) -> None:
        effective_config = config if config is not None else build_config()
        if not effective_config.skip_health_check:
            health = HealthCheck(effective_config)
            results = health.run_all()
            for result in results:
                if result.status == "fail":
                    bt.logging.error(f"[HEALTH FAIL] {result.name}: {result.message}")
                elif result.status == "warn":
                    bt.logging.warning(f"[HEALTH WARN] {result.name}: {result.message}")
                else:
                    bt.logging.info(f"[HEALTH OK] {result.name}: {result.message}")
            if any(result.status == "fail" for result in results):
                raise SystemExit(1)

        super().__init__(config=effective_config)
        self._experiment_lock = threading.Lock()
        self.runner = ExperimentRunner()
        if not self.runner.setup():
            raise SystemExit("Experiment runner setup failed.")
        self._last_baseline: str | None = None
        self.strategy = self._build_strategy()
        bt.logging.info(f"Miner UID: {self.uid}")
        bt.logging.info(f"Hotkey: {self.wallet.hotkey.ss58_address}")
        bt.logging.info(f"Network: {self.config.subtensor.network}")

    def _build_strategy(self) -> StructuredMutationStrategy | LLMMutationStrategy:
        provider = (self.config.mutation_provider or "none").lower()
        if provider in {"", "none"}:
            return StructuredMutationStrategy()
        if provider not in {"anthropic", "openai", "openai-compatible"}:
            bt.logging.error(
                f"Unsupported mutation provider '{provider}'. "
                "Falling back to structured mutations."
            )
            return StructuredMutationStrategy()

        env_name = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        api_key = os.environ.get(env_name)
        if not api_key:
            bt.logging.error(
                f"Mutation provider '{provider}' selected but {env_name} is missing. "
                "Falling back to structured mutations."
            )
            return StructuredMutationStrategy()

        return LLMMutationStrategy(
            provider=provider,
            api_key=api_key,
            model=self.config.mutation_model,
            base_url=self.config.mutation_base_url,
        )

    async def forward(self, synapse: ExperimentSubmission) -> ExperimentSubmission:
        bt.logging.info(
            f"Received challenge: task_id={synapse.task_id} "
            f"global_best={synapse.global_best_val_bpb}"
        )
        if not self._experiment_lock.acquire(blocking=False):
            bt.logging.warning(f"Experiment already running, rejecting {synapse.task_id}")
            return synapse

        try:
            if synapse.baseline_train_py != self._last_baseline:
                self.strategy = self._build_strategy()
                self._last_baseline = synapse.baseline_train_py

            modified_source = self.strategy.propose(synapse.baseline_train_py)
            if modified_source == synapse.baseline_train_py:
                bt.logging.warning("All mutations exhausted for current baseline.")
                return synapse

            result = self.runner.run(modified_source)
            synapse.train_py = modified_source
            synapse.run_log_tail = result.run_log_tail
            synapse.peak_vram_mb = result.peak_vram_mb
            synapse.elapsed_wall_seconds = (
                int(result.total_seconds) if result.total_seconds is not None else None
            )

            if result.status != "success" or result.val_bpb is None:
                bt.logging.warning(
                    f"Experiment failed: task={synapse.task_id} "
                    f"status={result.status} return_code={result.return_code}"
                )
                return synapse

            tier = detect_hardware_tier(
                config_override=self.config.hardware_tier,
                run_result=result,
            )
            synapse.val_bpb = result.val_bpb
            synapse.hardware_tier = tier.value

            delta = synapse.global_best_val_bpb - result.val_bpb
            bt.logging.info(
                f"Experiment complete: task={synapse.task_id} val_bpb={result.val_bpb} "
                f"delta={delta} tier={tier.value} status={result.status}"
            )
            return synapse
        finally:
            self._experiment_lock.release()

    async def blacklist(self, synapse: ExperimentSubmission) -> Tuple[bool, str]:
        hotkey = _extract_hotkey(getattr(synapse, "dendrite", None))
        if hotkey is None:
            return True, "Missing dendrite or hotkey"

        self._refresh_metagraph()
        if hotkey not in self.metagraph.hotkeys:
            if self.config.blacklist.allow_non_registered:
                return False, "Non-registered allowed (dev mode)"
            return True, "Unrecognized hotkey"

        uid = self.metagraph.hotkeys.index(hotkey)
        if (
            self.config.blacklist.force_validator_permit
            and not self.metagraph.validator_permit[uid]
        ):
            return True, "Not a validator"
        if float(self.metagraph.S[uid]) < MIN_VALIDATOR_STAKE:
            return True, f"Insufficient stake: {self.metagraph.S[uid]} < {MIN_VALIDATOR_STAKE}"
        return False, "Recognized validator"

    async def priority(self, synapse: ExperimentSubmission) -> float:
        hotkey = _extract_hotkey(getattr(synapse, "dendrite", None))
        if hotkey is None:
            return 0.0
        self._refresh_metagraph()
        try:
            uid = self.metagraph.hotkeys.index(hotkey)
        except ValueError:
            return 0.0
        return float(self.metagraph.S[uid])

    def _refresh_metagraph(self) -> None:
        if self.config.mock:
            return
        sync = getattr(self.metagraph, "sync", None)
        if callable(sync):
            try:
                sync(subtensor=self.subtensor)
            except TypeError:
                sync()


def _extract_hotkey(dendrite: Any) -> str | None:
    if dendrite is None:
        return None
    if isinstance(dendrite, dict):
        hotkey = dendrite.get("hotkey")
        return str(hotkey) if hotkey is not None else None
    hotkey = getattr(dendrite, "hotkey", None)
    return str(hotkey) if hotkey is not None else None


def main() -> int:
    with Miner() as miner:
        while True:
            bt.logging.info(f"Miner running... block={miner.block}")
            threading.Event().wait(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
