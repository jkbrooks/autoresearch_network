from __future__ import annotations

import numpy as np
import pytest

from autoresearch.constants import MAX_SCORE, PARTICIPATION_SCORE, HardwareTier
from autoresearch.mock import MockSubmissionFactory
from autoresearch.protocol import ExperimentSubmission
from autoresearch.validator.reward import get_rewards, score_submission


def test_score_invalid_submission_returns_zero_for_all_factory_failures() -> None:
    factory = MockSubmissionFactory(seed=42)

    reasons = [
        "bogus_bpb",
        "missing_train_py",
        "identical_train_py",
        "impossible_improvement",
        "invalid_tier",
        "elapsed_too_short",
        "elapsed_too_long",
    ]

    for reason in reasons:
        assert score_submission(factory.make_invalid_submission(reason), 1.1) == 0.0


def test_score_no_improvement_returns_participation() -> None:
    factory = MockSubmissionFactory(seed=42)
    submission = factory.make_submission(
        baseline_val_bpb=1.0,
        tier=HardwareTier.LARGE,
        improvement=0.0,
    )

    assert score_submission(submission, 1.0) == PARTICIPATION_SCORE


def test_score_regression_returns_participation() -> None:
    factory = MockSubmissionFactory(seed=42)
    submission = factory.make_submission(
        baseline_val_bpb=1.0,
        tier=HardwareTier.LARGE,
        improvement=-0.01,
    )

    assert score_submission(submission, 1.0) == PARTICIPATION_SCORE


def test_score_null_submission_returns_zero() -> None:
    submission = ExperimentSubmission(
        task_id="round_20260315_001",
        baseline_train_py="print('baseline')\n",
        global_best_val_bpb=1.0,
    )

    assert score_submission(submission, 1.0) == 0.0


@pytest.mark.parametrize(
    ("improvement", "expected"),
    [
        (0.005, 0.1),
        (0.025, 0.5),
        (0.05, 1.0),
    ],
)
def test_score_valid_improvement_matches_formula(improvement: float, expected: float) -> None:
    factory = MockSubmissionFactory(seed=42)
    submission = factory.make_submission(
        baseline_val_bpb=1.0,
        tier=HardwareTier.LARGE,
        improvement=improvement,
    )

    assert score_submission(submission, 1.0) == pytest.approx(expected)


def test_score_is_capped_at_max_score() -> None:
    factory = MockSubmissionFactory(seed=42)
    submission = factory.make_submission(
        baseline_val_bpb=1.0,
        tier=HardwareTier.LARGE,
        improvement=0.09,
    )

    assert score_submission(submission, 1.0) == MAX_SCORE


def test_get_rewards_batch_returns_expected_shape_and_values() -> None:
    factory = MockSubmissionFactory(seed=42)
    submissions = [
        factory.make_submission(
            baseline_val_bpb=1.0,
            tier=HardwareTier.LARGE,
            improvement=0.025,
        ),
        factory.make_submission(
            baseline_val_bpb=1.0,
            tier=HardwareTier.LARGE,
            improvement=0.0,
        ),
        ExperimentSubmission(
            task_id="round_20260315_999",
            baseline_train_py="print('baseline')\n",
            global_best_val_bpb=1.0,
        ),
    ]

    rewards = get_rewards(submissions, 1.0)

    assert isinstance(rewards, np.ndarray)
    assert rewards.shape == (3,)
    assert rewards.tolist() == pytest.approx([0.5, PARTICIPATION_SCORE, 0.0])


def test_get_rewards_empty_returns_empty_array() -> None:
    rewards = get_rewards([], 1.0)

    assert isinstance(rewards, np.ndarray)
    assert rewards.shape == (0,)
