"""Preview reward helpers for the protocol demo."""

from __future__ import annotations

from autoresearch.protocol import preview_score


def score_submission(global_best_val_bpb: float, submitted_val_bpb: float) -> float:
    """Compute the demo reward preview for a submission."""

    return preview_score(global_best=global_best_val_bpb, submitted=submitted_val_bpb)
