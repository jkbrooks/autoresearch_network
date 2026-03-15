"""Validator-side replay sampling and comparison helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from autoresearch.constants import REPLAY_SAMPLE_RATE
from autoresearch.experiment_runner import ExperimentRunner
from autoresearch.protocol import ExperimentSubmission


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of a replay decision and, when selected, the replay execution."""

    selected: bool
    executed: bool
    passed: bool | None
    reason: str
    submitted_bpb: float | None = None
    replayed_bpb: float | None = None
    relative_diff: float | None = None
    replay_status: str = "skipped"
    run_log_tail: str = ""


@dataclass
class ReplayStats:
    """Persisted per-miner replay telemetry."""

    hotkey: str
    attempts: int = 0
    passes: int = 0
    failures: int = 0
    last_seen: str = ""
    last_reason: str = ""
    last_diff: float | None = None
    last_submitted_bpb: float | None = None
    last_replayed_bpb: float | None = None


class ReplaySampler:
    """Deterministic validator-side replay sampler."""

    def __init__(self, sample_rate: float = REPLAY_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate

    def should_replay(self, miner_uid: int, step: int) -> bool:
        if self.sample_rate <= 0:
            return False
        if self.sample_rate >= 1:
            return True
        digest = hashlib.sha256(f"{miner_uid}:{step}".encode()).digest()
        value = int.from_bytes(digest[:8], "big") / 2**64
        return value < self.sample_rate


def compare_replay(
    submitted_bpb: float,
    replayed_bpb: float,
    tolerance: float,
) -> tuple[bool, float]:
    """Compare replayed and submitted metrics with a relative-difference tolerance."""

    diff = abs(submitted_bpb - replayed_bpb) / submitted_bpb
    return diff <= tolerance, diff


def maybe_replay_submission(
    *,
    submission: ExperimentSubmission,
    miner_uid: int,
    step: int,
    sampler: ReplaySampler,
    runner: ExperimentRunner,
    tolerance: float,
) -> ReplayResult:
    """Replay a selected submission and compare it to the self-reported result."""

    if submission.val_bpb is None or not submission.train_py:
        return ReplayResult(
            selected=False,
            executed=False,
            passed=None,
            reason="missing_submission",
        )

    try:
        submission.validate()
    except ValueError:
        return ReplayResult(
            selected=False,
            executed=False,
            passed=None,
            reason="invalid_submission",
            submitted_bpb=submission.val_bpb,
        )

    if not sampler.should_replay(miner_uid, step):
        return ReplayResult(
            selected=False,
            executed=False,
            passed=None,
            reason="not_selected",
            submitted_bpb=submission.val_bpb,
        )

    replay_run = runner.run(submission.train_py)
    if replay_run.status != "success" or replay_run.val_bpb is None:
        return ReplayResult(
            selected=True,
            executed=True,
            passed=False,
            reason=f"replay_{replay_run.status}",
            submitted_bpb=submission.val_bpb,
            replay_status=replay_run.status,
            run_log_tail=replay_run.run_log_tail,
        )

    passed, diff = compare_replay(submission.val_bpb, replay_run.val_bpb, tolerance)
    return ReplayResult(
        selected=True,
        executed=True,
        passed=passed,
        reason="match" if passed else "mismatch",
        submitted_bpb=submission.val_bpb,
        replayed_bpb=replay_run.val_bpb,
        relative_diff=diff,
        replay_status=replay_run.status,
        run_log_tail=replay_run.run_log_tail,
    )


def update_replay_stats(
    replay_stats: dict[str, ReplayStats],
    *,
    hotkey: str,
    replay_result: ReplayResult,
    observed_at: str | None = None,
) -> dict[str, ReplayStats]:
    """Update persisted replay telemetry for a miner hotkey."""

    if not replay_result.selected or not replay_result.executed:
        return replay_stats

    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    stats = replay_stats.get(hotkey)
    if stats is None:
        stats = ReplayStats(hotkey=hotkey)
        replay_stats[hotkey] = stats

    stats.attempts += 1
    if replay_result.passed:
        stats.passes += 1
    else:
        stats.failures += 1
    stats.last_seen = timestamp
    stats.last_reason = replay_result.reason
    stats.last_diff = replay_result.relative_diff
    stats.last_submitted_bpb = replay_result.submitted_bpb
    stats.last_replayed_bpb = replay_result.replayed_bpb
    return replay_stats
