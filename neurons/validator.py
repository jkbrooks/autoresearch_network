"""Thin validator entrypoint kept importable for future subnet integration."""

from __future__ import annotations

from autoresearch.base import BaseValidatorNeuron
from autoresearch.validator.forward import build_demo_submission


class Validator(BaseValidatorNeuron):
    """Placeholder validator that can build a demo submission."""

    def forward(self) -> str:
        submission = build_demo_submission()
        return submission.task_id


def main() -> int:
    validator = Validator()
    print(
        "AutoResearch validator scaffold loaded. Demo task:",
        validator.forward(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
