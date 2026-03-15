from __future__ import annotations

from autoresearch.constants import HardwareTier
from autoresearch.mock import MockSubmissionFactory
from autoresearch.protocol import ExperimentSubmission
from autoresearch.validator.guards import (
    EXACT_DUPLICATE_MULTIPLIER,
    GUARD_NO_OP_MULTIPLIER,
    NEAR_DUPLICATE_MULTIPLIER,
    THROUGHPUT_INCONSISTENT_MULTIPLIER,
    check_exact_duplicate,
    check_guards,
    check_near_duplicate,
    check_throughput,
    source_hash,
)


def make_submission(*, tier: HardwareTier = HardwareTier.LARGE) -> ExperimentSubmission:
    factory = MockSubmissionFactory(seed=42)
    return factory.make_submission(baseline_val_bpb=1.1, tier=tier, improvement=0.02)


def test_exact_dup_different_miner() -> None:
    submission = make_submission()
    seen_hashes = {source_hash(submission.train_py or ""): "miner-a"}

    multiplier = check_exact_duplicate(submission.train_py or "", seen_hashes, "miner-b")

    assert multiplier == EXACT_DUPLICATE_MULTIPLIER


def test_exact_dup_self_repeat() -> None:
    submission = make_submission()
    seen_hashes = {source_hash(submission.train_py or ""): "miner-a"}

    multiplier = check_exact_duplicate(submission.train_py or "", seen_hashes, "miner-a")

    assert multiplier == EXACT_DUPLICATE_MULTIPLIER


def test_exact_dup_new_submission_passes_and_records_hash() -> None:
    submission = make_submission()
    seen_hashes: dict[str, str] = {}

    multiplier = check_exact_duplicate(submission.train_py or "", seen_hashes, "miner-a")

    assert multiplier == GUARD_NO_OP_MULTIPLIER
    assert seen_hashes == {source_hash(submission.train_py or ""): "miner-a"}


def test_near_dup_high_similarity() -> None:
    submission = make_submission()
    similar_source = (submission.train_py or "").replace(
        "depth_sweep_seed_42", "depth_sweep_seed_43"
    )

    multiplier = check_near_duplicate(similar_source, [submission.train_py or ""], threshold=0.95)

    assert multiplier == NEAR_DUPLICATE_MULTIPLIER


def test_near_dup_low_similarity() -> None:
    submission = make_submission()
    very_different = "print('completely different source')\n"

    multiplier = check_near_duplicate(very_different, [submission.train_py or ""], threshold=0.95)

    assert multiplier == GUARD_NO_OP_MULTIPLIER


def test_throughput_consistent_returns_one() -> None:
    submission = make_submission(tier=HardwareTier.LARGE)
    submission.run_log_tail = "\n".join(
        [
            "val_bpb: 1.02",
            "training_seconds: 300.0",
            "total_tokens_M: 120.0",
        ]
    )

    multiplier = check_throughput(submission)

    assert multiplier == GUARD_NO_OP_MULTIPLIER


def test_throughput_inconsistent_returns_half() -> None:
    submission = make_submission(tier=HardwareTier.SMALL)
    submission.run_log_tail = "\n".join(
        [
            "val_bpb: 1.6",
            "training_seconds: 60.0",
            "total_tokens_M: 400.0",
        ]
    )

    multiplier = check_throughput(submission)

    assert multiplier == THROUGHPUT_INCONSISTENT_MULTIPLIER


def test_throughput_missing_log_returns_one() -> None:
    submission = make_submission()
    submission.run_log_tail = None

    multiplier = check_throughput(submission)

    assert multiplier == GUARD_NO_OP_MULTIPLIER


def test_guards_compose() -> None:
    submission = make_submission(tier=HardwareTier.SMALL)
    submission.run_log_tail = "\n".join(
        [
            "val_bpb: 1.6",
            "training_seconds: 60.0",
            "total_tokens_M: 400.0",
        ]
    )
    recent_submissions = [
        (submission.train_py or "").replace("depth_sweep_seed_42", "depth_sweep_seed_43")
    ]
    seen_hashes: dict[str, str] = {}

    multiplier = check_guards(
        submission,
        seen_hashes,
        recent_submissions,
        submitter_hotkey="miner-a",
    )

    assert multiplier == NEAR_DUPLICATE_MULTIPLIER * THROUGHPUT_INCONSISTENT_MULTIPLIER


def test_guards_empty_submission_skipped() -> None:
    submission = make_submission()
    submission.val_bpb = None

    multiplier = check_guards(submission, {})

    assert multiplier == GUARD_NO_OP_MULTIPLIER
