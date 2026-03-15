"""Thin miner entrypoint kept importable for future subnet integration."""

from __future__ import annotations

from autoresearch.base import BaseMinerNeuron
from autoresearch.protocol import ExperimentSubmission


class Miner(BaseMinerNeuron):
    """Placeholder miner that simply echoes the submission envelope."""

    def forward(self, synapse: ExperimentSubmission) -> ExperimentSubmission:
        return synapse


def main() -> int:
    print(
        "AutoResearch miner scaffold loaded. Protocol behavior is not wired to a live subnet yet."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
