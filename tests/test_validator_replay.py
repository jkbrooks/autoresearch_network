from __future__ import annotations

from types import SimpleNamespace

from autoresearch.experiment_runner import RunResult
from autoresearch.mock import MockSubmissionFactory
from autoresearch.validator.replay import (
    ReplaySampler,
    ReplayStats,
    compare_replay,
    maybe_replay_submission,
    update_replay_stats,
)


def test_replay_sampler_is_deterministic() -> None:
    sampler = ReplaySampler(sample_rate=0.2)
    first = sampler.should_replay(7, 42)
    second = sampler.should_replay(7, 42)
    assert first is second


def test_replay_sampler_respects_zero_and_full_rates() -> None:
    assert ReplaySampler(sample_rate=0.0).should_replay(1, 1) is False
    assert ReplaySampler(sample_rate=1.0).should_replay(1, 1) is True


def test_compare_replay_within_tolerance_passes() -> None:
    passed, diff = compare_replay(0.997, 0.998, tolerance=0.02)
    assert passed is True
    assert diff < 0.02


def test_compare_replay_outside_tolerance_fails() -> None:
    passed, diff = compare_replay(0.997, 1.050, tolerance=0.02)
    assert passed is False
    assert diff > 0.02


def test_maybe_replay_submission_skips_unselected() -> None:
    submission = MockSubmissionFactory(seed=42).make_submission()
    sampler = ReplaySampler(sample_rate=0.0)
    runner = SimpleNamespace(run=lambda source: RunResult(status="success", val_bpb=0.9))
    result = maybe_replay_submission(
        submission=submission,
        miner_uid=0,
        step=1,
        sampler=sampler,
        runner=runner,
        tolerance=0.02,
    )
    assert result.selected is False
    assert result.executed is False
    assert result.reason == "not_selected"


def test_maybe_replay_submission_records_match() -> None:
    submission = MockSubmissionFactory(seed=42).make_submission(
        baseline_val_bpb=1.0,
        improvement=0.01,
    )
    runner = SimpleNamespace(
        run=lambda source: RunResult(status="success", val_bpb=submission.val_bpb + 0.001)
    )
    result = maybe_replay_submission(
        submission=submission,
        miner_uid=0,
        step=1,
        sampler=ReplaySampler(sample_rate=1.0),
        runner=runner,
        tolerance=0.02,
    )
    assert result.selected is True
    assert result.executed is True
    assert result.passed is True
    assert result.reason == "match"


def test_maybe_replay_submission_records_failure_on_replay_crash() -> None:
    submission = MockSubmissionFactory(seed=42).make_submission()
    runner = SimpleNamespace(
        run=lambda source: RunResult(status="crash", run_log_tail="traceback")
    )
    result = maybe_replay_submission(
        submission=submission,
        miner_uid=0,
        step=1,
        sampler=ReplaySampler(sample_rate=1.0),
        runner=runner,
        tolerance=0.02,
    )
    assert result.selected is True
    assert result.executed is True
    assert result.passed is False
    assert result.reason == "replay_crash"


def test_update_replay_stats_tracks_attempts() -> None:
    stats: dict[str, ReplayStats] = {}
    submission = MockSubmissionFactory(seed=42).make_submission(
        baseline_val_bpb=1.0,
        improvement=0.01,
    )
    result = maybe_replay_submission(
        submission=submission,
        miner_uid=0,
        step=1,
        sampler=ReplaySampler(sample_rate=1.0),
        runner=SimpleNamespace(
            run=lambda source: RunResult(status="success", val_bpb=submission.val_bpb + 0.001)
        ),
        tolerance=0.02,
    )
    update_replay_stats(
        stats,
        hotkey="miner-a",
        replay_result=result,
        observed_at="2026-03-14T00:00:00+00:00",
    )
    assert stats["miner-a"].attempts == 1
    assert stats["miner-a"].passes == 1
    assert stats["miner-a"].last_seen == "2026-03-14T00:00:00+00:00"


def test_update_replay_stats_ignores_skipped() -> None:
    stats: dict[str, ReplayStats] = {}
    skipped = maybe_replay_submission(
        submission=MockSubmissionFactory(seed=42).make_submission(),
        miner_uid=0,
        step=1,
        sampler=ReplaySampler(sample_rate=0.0),
        runner=SimpleNamespace(run=lambda source: RunResult(status="success", val_bpb=0.99)),
        tolerance=0.02,
    )
    update_replay_stats(stats, hotkey="miner-a", replay_result=skipped)
    assert stats == {}
