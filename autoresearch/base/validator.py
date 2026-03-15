"""Minimal validator scaffold derived from the subnet template shape."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BaseValidatorNeuron:
    """Thin placeholder for future Bittensor validator behavior."""

    config: object | None = None

    def __enter__(self) -> BaseValidatorNeuron:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None
