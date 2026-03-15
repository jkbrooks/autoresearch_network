"""Base miner lifecycle for AutoResearch miners."""

from __future__ import annotations

import threading
import time
from typing import Any

import bittensor as bt
from bittensor.core.axon import Axon

from autoresearch.base.neuron import BaseNeuron


class _MockAxon:
    """Minimal stand-in for Axon during mock/unit-test flows."""

    def __init__(self) -> None:
        self.attached: dict[str, Any] = {}
        self.started = False
        self.served = False

    def attach(self, **kwargs: Any) -> _MockAxon:
        self.attached.update(kwargs)
        return self

    def serve(self, **_: Any) -> _MockAxon:
        self.served = True
        return self

    def start(self) -> _MockAxon:
        self.started = True
        return self

    def stop(self) -> _MockAxon:
        self.started = False
        return self


class BaseMinerNeuron(BaseNeuron):
    """Template-inspired base class for miners."""

    neuron_type = "MinerNeuron"

    def __init__(self, config: Any = None) -> None:
        super().__init__(config=config)
        if self.config.mock:
            self.axon: Axon | _MockAxon = _MockAxon()
        else:
            self.axon = Axon(
                wallet=self.wallet,
                port=self.config.axon.port,
                ip=self.config.axon.ip,
                external_ip=self.config.axon.external_ip,
                external_port=self.config.axon.external_port,
                max_workers=self.config.axon.max_workers,
            )

        self.axon.attach(
            forward_fn=self.forward,
            blacklist_fn=self.blacklist,
            priority_fn=self.priority,
        )
        self.should_exit = False
        self.is_running = False
        self.thread: threading.Thread | None = None

    def run(self) -> None:
        """Start serving the miner axon and keep it alive until shutdown."""

        if not self.config.mock:
            self.ensure_registered()
            bt.logging.info(
                f"Serving miner axon on {self.config.subtensor.network} netuid={self.config.netuid}"
            )
            self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
        self.axon.start()
        bt.logging.info(f"Miner starting at block: {self.block}")
        try:
            while not self.should_exit:
                time.sleep(1)
        except KeyboardInterrupt:
            bt.logging.success("Miner stopped by keyboard interrupt.")
        finally:
            self.axon.stop()

    def run_in_background_thread(self) -> None:
        if self.is_running:
            return
        self.should_exit = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        self.is_running = True

    def stop_run_thread(self) -> None:
        if not self.is_running:
            return
        self.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.is_running = False

    def __enter__(self) -> BaseMinerNeuron:
        self.run_in_background_thread()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop_run_thread()

    async def blacklist(self, synapse: Any) -> tuple[bool, str]:
        raise NotImplementedError

    async def priority(self, synapse: Any) -> float:
        raise NotImplementedError
