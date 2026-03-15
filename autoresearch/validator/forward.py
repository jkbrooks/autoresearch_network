"""Validator-side protocol helpers."""

from __future__ import annotations

from autoresearch.constants import HardwareTier
from autoresearch.mock import MockSubmissionFactory
from autoresearch.protocol import ExperimentSubmission


def build_demo_submission() -> ExperimentSubmission:
    """Create the canonical demo submission used by the package CLI."""

    factory = MockSubmissionFactory(seed=42)
    return factory.make_submission(
        baseline_val_bpb=0.9979,
        tier=HardwareTier.LARGE,
        improvement=0.0037,
        task_id="round_20260315_001",
    )
