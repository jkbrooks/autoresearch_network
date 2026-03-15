"""Minimal miner scaffold derived from the subnet template shape."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BaseMinerNeuron:
    """Thin placeholder for future Bittensor miner behavior."""

    config: object | None = None

    def __enter__(self) -> BaseMinerNeuron:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None
