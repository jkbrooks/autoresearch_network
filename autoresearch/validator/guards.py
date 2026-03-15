"""Validator-side anti-gaming guards."""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Iterable, MutableMapping

from autoresearch.constants import TIER_PLAUSIBILITY, HardwareTier
from autoresearch.experiment_runner import parse_metrics
from autoresearch.protocol import ExperimentSubmission

EXACT_DUPLICATE_MULTIPLIER = 0.0
NEAR_DUPLICATE_MULTIPLIER = 0.1
THROUGHPUT_INCONSISTENT_MULTIPLIER = 0.5
GUARD_NO_OP_MULTIPLIER = 1.0
DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.95


def source_hash(train_py: str) -> str:
    """Return a stable hash for a train script source string."""

    return hashlib.sha256(train_py.strip().encode("utf-8")).hexdigest()[:16]


def check_exact_duplicate(
    train_py: str,
    submission_hashes: MutableMapping[str, str],
    submitter_hotkey: str,
) -> float:
    """Return zero for a repeated source and record new sources."""

    hashed_source = source_hash(train_py)
    original_submitter = submission_hashes.get(hashed_source)
    if original_submitter is not None:
        return EXACT_DUPLICATE_MULTIPLIER

    submission_hashes[hashed_source] = submitter_hotkey
    return GUARD_NO_OP_MULTIPLIER


def check_near_duplicate(
    train_py: str,
    recent_submissions: Iterable[str],
    *,
    threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
) -> float:
    """Return a heavy penalty when a source is almost identical to a recent one."""

    for previous_source in recent_submissions:
        similarity = difflib.SequenceMatcher(None, train_py, previous_source).ratio()
        if similarity >= threshold:
            return NEAR_DUPLICATE_MULTIPLIER
    return GUARD_NO_OP_MULTIPLIER


def _throughput_bounds(tier: HardwareTier) -> tuple[float, float]:
    plausible = TIER_PLAUSIBILITY[tier]
    expected_min = (plausible.min_tokens_m * 1_000_000.0) / 300.0
    expected_max = (plausible.max_tokens_m * 1_000_000.0) / 300.0
    # Keep a wide tolerance band because logs are self-reported and runs are noisy.
    return expected_min * 0.5, expected_max * 2.0


def check_throughput(submission: ExperimentSubmission) -> float:
    """Return a half-score penalty when self-reported throughput is implausible."""

    if not submission.run_log_tail or not submission.hardware_tier:
        return GUARD_NO_OP_MULTIPLIER

    try:
        tier = HardwareTier(submission.hardware_tier)
    except ValueError:
        return GUARD_NO_OP_MULTIPLIER

    metrics = parse_metrics(submission.run_log_tail)
    total_tokens_m = metrics.get("total_tokens_m")
    training_seconds = metrics.get("training_seconds")
    if total_tokens_m is None or training_seconds is None or training_seconds <= 0:
        return GUARD_NO_OP_MULTIPLIER

    tokens_per_second = (total_tokens_m * 1_000_000.0) / training_seconds
    expected_min, expected_max = _throughput_bounds(tier)
    if expected_min <= tokens_per_second <= expected_max:
        return GUARD_NO_OP_MULTIPLIER
    return THROUGHPUT_INCONSISTENT_MULTIPLIER


def check_guards(
    submission: ExperimentSubmission,
    submission_hashes: MutableMapping[str, str],
    recent_submissions: Iterable[str] | None = None,
    *,
    submitter_hotkey: str = "unknown",
) -> float:
    """Apply all guard multipliers to a single submission."""

    if submission.val_bpb is None or not submission.train_py:
        return GUARD_NO_OP_MULTIPLIER

    exact_multiplier = check_exact_duplicate(
        submission.train_py,
        submission_hashes,
        submitter_hotkey,
    )
    near_multiplier = check_near_duplicate(
        submission.train_py,
        [] if recent_submissions is None else recent_submissions,
    )
    throughput_multiplier = check_throughput(submission)
    return exact_multiplier * near_multiplier * throughput_multiplier
