"""Validator scoring helpers for miner experiment submissions."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from autoresearch.constants import MAX_SCORE, PARTICIPATION_SCORE
from autoresearch.protocol import ExperimentSubmission


def score_submission(submission: ExperimentSubmission, global_best_bpb: float) -> float:
    """Score a single miner submission in the unit interval."""

    if submission.val_bpb is None:
        return 0.0

    try:
        submission.validate()
    except ValueError:
        return 0.0

    if submission.val_bpb >= global_best_bpb:
        return PARTICIPATION_SCORE

    improvement = global_best_bpb - submission.val_bpb
    relative_gain = improvement / global_best_bpb
    raw_score = relative_gain * 20.0
    return min(MAX_SCORE, raw_score)


def get_rewards(
    submissions: list[ExperimentSubmission],
    global_best_bpb: float,
) -> NDArray[np.float64]:
    """Score all submissions for one validator round."""

    return np.asarray(
        [score_submission(submission, global_best_bpb) for submission in submissions],
        dtype=float,
    )
