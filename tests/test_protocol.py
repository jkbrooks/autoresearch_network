from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from autoresearch import __main__ as autoresearch_main
from autoresearch.constants import (
    MAX_ELAPSED_SECONDS,
    MAX_SCORE,
    MAX_SINGLE_STEP_IMPROVEMENT,
    MAX_VAL_BPB,
    MIN_ELAPSED_SECONDS,
    MIN_PLAUSIBLE_VAL_BPB,
    PARTICIPATION_SCORE,
    TIER_PLAUSIBILITY,
    HardwareTier,
)
from autoresearch.mock import MockSubmissionFactory
from autoresearch.protocol import (
    ExperimentSubmission,
    _demo_pacing,
    _emit_block,
    _emit_loading_state,
    _format_elapsed,
    _hardware_tier_label,
    _progress_bar,
    preview_score,
)
from autoresearch.protocol import main as protocol_main


def make_valid_submission() -> ExperimentSubmission:
    return ExperimentSubmission(
        task_id="round_20260315_001",
        baseline_train_py=(
            "import torch\n"
            "DEPTH = 8\n"
            "LEARNING_RATE = 0.02\n"
            "def train_step():\n"
            "    return DEPTH, LEARNING_RATE\n"
        ),
        global_best_val_bpb=1.1,
        val_bpb=1.02,
        train_py=(
            "import torch\n"
            "DEPTH = 10\n"
            "LEARNING_RATE = 0.02\n"
            "def train_step():\n"
            "    return DEPTH, LEARNING_RATE\n"
        ),
        hardware_tier=HardwareTier.LARGE.value,
        elapsed_wall_seconds=300,
        peak_vram_mb=24000.0,
        run_log_tail=(
            "---\n"
            "val_bpb:          1.020000\n"
            "training_seconds: 300.0\n"
            "total_seconds:    315.0\n"
            "peak_vram_mb:     24000.0\n"
            "mfu_percent:      38.40\n"
            "total_tokens_M:   140.2\n"
            "num_steps:        900\n"
            "num_params_M:     50.3\n"
            "depth:            10\n"
        ),
    )


def test_experiment_submission_instantiates_with_validator_fields_only() -> None:
    submission = ExperimentSubmission(
        task_id="test",
        baseline_train_py="print('hello')\n",
        global_best_val_bpb=0.997,
    )

    assert submission.val_bpb is None
    assert submission.train_py is None
    assert submission.hardware_tier is None
    assert submission.elapsed_wall_seconds is None
    assert submission.peak_vram_mb is None
    assert submission.run_log_tail is None


def test_experiment_submission_deserialize_returns_miner_fields() -> None:
    submission = make_valid_submission()

    assert submission.deserialize() == {
        "val_bpb": 1.02,
        "train_py": submission.train_py,
        "hardware_tier": HardwareTier.LARGE.value,
        "elapsed_wall_seconds": 300,
        "peak_vram_mb": 24000.0,
        "run_log_tail": submission.run_log_tail,
    }


def test_experiment_submission_round_trip_reconstruction() -> None:
    original = make_valid_submission()

    reconstructed = ExperimentSubmission.model_validate(original.model_dump())

    assert reconstructed.model_dump() == original.model_dump()


def test_experiment_submission_invalid_float_type_raises() -> None:
    with pytest.raises(ValidationError):
        ExperimentSubmission(
            task_id="test",
            baseline_train_py="print('hello')\n",
            global_best_val_bpb=0.997,
            val_bpb="not_a_float",
        )


def test_validate_missing_val_bpb() -> None:
    submission = make_valid_submission()
    submission.val_bpb = None

    with pytest.raises(ValueError, match="Missing val_bpb — miner did not return a result"):
        submission.validate()


def test_validate_val_bpb_too_low() -> None:
    submission = make_valid_submission()
    submission.val_bpb = 0.1

    with pytest.raises(
        ValueError,
        match=rf"val_bpb 0\.1 is below minimum plausible threshold {MIN_PLAUSIBLE_VAL_BPB}",
    ):
        submission.validate()


def test_validate_val_bpb_too_high() -> None:
    submission = make_valid_submission()
    submission.val_bpb = 6.0

    with pytest.raises(
        ValueError,
        match=rf"val_bpb 6\.0 exceeds maximum plausible value {MAX_VAL_BPB}",
    ):
        submission.validate()


def test_validate_missing_train_py() -> None:
    submission = make_valid_submission()
    submission.train_py = None

    with pytest.raises(ValueError, match="Missing train_py — miner did not return modified source"):
        submission.validate()


def test_validate_identical_train_py() -> None:
    submission = make_valid_submission()
    submission.train_py = submission.baseline_train_py

    with pytest.raises(
        ValueError,
        match="train_py is identical to baseline — miner made no changes",
    ):
        submission.validate()


def test_validate_invalid_hardware_tier() -> None:
    submission = make_valid_submission()
    submission.hardware_tier = "quantum"

    with pytest.raises(ValueError, match="Invalid hardware_tier: quantum"):
        submission.validate()


def test_validate_elapsed_too_short() -> None:
    submission = make_valid_submission()
    submission.elapsed_wall_seconds = 10
    pattern = (
        "elapsed_wall_seconds 10 outside valid range "
        rf"\[{MIN_ELAPSED_SECONDS}, {MAX_ELAPSED_SECONDS}\]"
    )

    with pytest.raises(
        ValueError,
        match=pattern,
    ):
        submission.validate()


def test_validate_elapsed_too_long() -> None:
    submission = make_valid_submission()
    submission.elapsed_wall_seconds = 1000
    pattern = (
        "elapsed_wall_seconds 1000 outside valid range "
        rf"\[{MIN_ELAPSED_SECONDS}, {MAX_ELAPSED_SECONDS}\]"
    )

    with pytest.raises(
        ValueError,
        match=pattern,
    ):
        submission.validate()


def test_validate_improvement_too_large() -> None:
    submission = make_valid_submission()
    submission.global_best_val_bpb = 1.0
    submission.val_bpb = 0.85
    threshold_pct = MAX_SINGLE_STEP_IMPROVEMENT * 100

    with pytest.raises(
        ValueError,
        match=rf"Improvement of 15\.0% exceeds maximum single-step threshold of {threshold_pct}%",
    ):
        submission.validate()


def test_validate_bpb_outside_tier_range() -> None:
    submission = make_valid_submission()
    submission.hardware_tier = HardwareTier.SMALL.value
    submission.val_bpb = 1.0

    bounds = TIER_PLAUSIBILITY[HardwareTier.SMALL]
    pattern = (
        "val_bpb 1\\.0 outside plausible range "
        rf"\[{bounds.min_val_bpb}, {bounds.max_val_bpb}\] for tier small"
    )
    with pytest.raises(
        ValueError,
        match=pattern,
    ):
        submission.validate()


def test_validate_vram_outside_tier_range() -> None:
    submission = make_valid_submission()
    submission.hardware_tier = HardwareTier.SMALL.value
    submission.val_bpb = 1.6
    submission.peak_vram_mb = 9000.0

    bounds = TIER_PLAUSIBILITY[HardwareTier.SMALL]
    pattern = (
        "peak_vram_mb 9000\\.0 outside plausible range "
        rf"\[{bounds.min_vram_mb}, {bounds.max_vram_mb}\] for tier small"
    )
    with pytest.raises(
        ValueError,
        match=pattern,
    ):
        submission.validate()


def test_validate_good_submission_passes() -> None:
    submission = make_valid_submission()

    assert submission.validate() is None


def test_mock_factory_valid_submission_passes_validation() -> None:
    factory = MockSubmissionFactory(seed=42)
    submission = factory.make_submission(
        baseline_val_bpb=1.1,
        tier=HardwareTier.LARGE,
        improvement=0.02,
    )

    assert submission.validate() is None


def test_mock_factory_improvement_math() -> None:
    factory = MockSubmissionFactory(seed=42)

    improved = factory.make_submission(
        baseline_val_bpb=1.1,
        tier=HardwareTier.LARGE,
        improvement=0.02,
    )
    regressed = factory.make_submission(
        baseline_val_bpb=1.1,
        tier=HardwareTier.LARGE,
        improvement=-0.02,
    )

    assert improved.val_bpb is not None
    assert regressed.val_bpb is not None
    assert improved.val_bpb < 1.1
    assert regressed.val_bpb > 1.1


def test_mock_factory_deterministic() -> None:
    left = MockSubmissionFactory(seed=7).make_submission(
        baseline_val_bpb=1.1,
        tier=HardwareTier.MEDIUM,
        improvement=0.01,
    )
    right = MockSubmissionFactory(seed=7).make_submission(
        baseline_val_bpb=1.1,
        tier=HardwareTier.MEDIUM,
        improvement=0.01,
    )

    assert left.model_dump() == right.model_dump()


@pytest.mark.parametrize(
    ("reason", "pattern"),
    [
        ("bogus_bpb", "below minimum plausible threshold"),
        ("missing_train_py", "Missing train_py"),
        ("identical_train_py", "identical to baseline"),
        ("invalid_tier", "Invalid hardware_tier"),
        ("elapsed_too_short", "outside valid range"),
        ("elapsed_too_long", "outside valid range"),
    ],
)
def test_mock_factory_invalid_variants_fail_validation(reason: str, pattern: str) -> None:
    submission = MockSubmissionFactory(seed=99).make_invalid_submission(reason=reason)

    with pytest.raises(ValueError, match=pattern):
        submission.validate()


def test_mock_factory_invalid_impossible_improvement_is_isolated_to_rule_8() -> None:
    submission = MockSubmissionFactory(seed=99).make_invalid_submission(
        reason="impossible_improvement"
    )

    assert submission.global_best_val_bpb == pytest.approx(1.2)
    assert submission.val_bpb == pytest.approx(1.07)
    assert submission.hardware_tier == HardwareTier.LARGE.value

    large_bounds = TIER_PLAUSIBILITY[HardwareTier.LARGE]
    assert submission.val_bpb is not None
    assert large_bounds.min_val_bpb <= submission.val_bpb <= large_bounds.max_val_bpb

    relative_improvement = (
        submission.global_best_val_bpb - submission.val_bpb
    ) / submission.global_best_val_bpb
    assert relative_improvement > MAX_SINGLE_STEP_IMPROVEMENT

    with pytest.raises(ValueError, match="exceeds maximum single-step threshold"):
        submission.validate()


def test_mock_factory_unknown_reason_raises_value_error() -> None:
    factory = MockSubmissionFactory(seed=5)

    with pytest.raises(ValueError, match="Unknown invalid submission reason"):
        factory.make_invalid_submission(reason="mystery")


def test_preview_score_uses_demo_formula() -> None:
    score = preview_score(global_best=1.0, submitted=0.997)

    assert score == pytest.approx(min(MAX_SCORE, (0.003 / 1.0) * 200))
    assert score > PARTICIPATION_SCORE


@pytest.mark.parametrize(
    ("tier", "label"),
    [
        (HardwareTier.SMALL, "small (≤8 GB)"),
        (HardwareTier.MEDIUM, "medium (≤16 GB)"),
        (HardwareTier.LARGE, "large (≤36 GB)"),
        (HardwareTier.XL, "xl (>36 GB)"),
    ],
)
def test_hardware_tier_label_formats_all_tiers(tier: HardwareTier, label: str) -> None:
    assert _hardware_tier_label(tier) == label


def test_format_elapsed_uses_subsecond_precision() -> None:
    assert _format_elapsed(0.3456) == "0.346 seconds"
    assert _format_elapsed(1.234) == "1.23 seconds"


def test_demo_pacing_differs_for_interactive_output() -> None:
    assert _demo_pacing(True) == (0.2, 0.5, 10.0)
    assert _demo_pacing(False) == (0.0, 0.0, 0.0)


def test_emit_block_prints_all_lines(capsys: pytest.CaptureFixture[str]) -> None:
    _emit_block(["alpha", "beta"], line_delay=0.0, section_delay=0.0)
    assert capsys.readouterr().out == "alpha\nbeta\n"


def test_progress_bar_renders_expected_width() -> None:
    assert _progress_bar(0.5, width=10) == "[█████░░░░░]"


def test_emit_loading_state_is_noop_when_not_interactive(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _emit_loading_state(total_duration=0.0, is_interactive=False)
    assert capsys.readouterr().out == ""


def test_emit_loading_state_prints_progress_when_interactive(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)
    _emit_loading_state(total_duration=0.0, is_interactive=True)
    output = capsys.readouterr().out
    assert output.count("Progress:") == 5
    assert "warmup complete" in output
    assert "payload ready" in output


def test_demo_runs_without_error() -> None:
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "autoresearch"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    elapsed = time.perf_counter() - start

    assert result.returncode == 0, result.stderr
    assert elapsed < 5


def test_demo_output_contains_key_sections() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "autoresearch"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert "VALIDATOR" in result.stdout
    assert "MINER" in result.stdout
    assert "VALID" in result.stdout
    assert "SCORING" in result.stdout
    assert "REJECTED" in result.stdout
    assert "Elapsed time:      298 seconds" in result.stdout
    assert "Validator Submission Cycle" in result.stdout
    assert "reported gain exceeds validator single-step threshold" in result.stdout
    assert "Creating experiment challenge..." in result.stdout
    assert "Candidate state:   validator challenge returned with implausible gain" in result.stdout
    assert "Awaiting next validator round." in result.stdout


def test_protocol_module_demo_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "autoresearch.protocol"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_protocol_main_demo_in_process(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = protocol_main([])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "VALIDATOR" in captured.out
    assert "MINER" in captured.out
    assert "SCORING" in captured.out
    assert "REJECTED" in captured.out
    assert (
        "Reject reason:     reported gain exceeds validator single-step threshold"
        in captured.out
    )


def test_protocol_main_usage_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = protocol_main(["unexpected"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Usage: python -m autoresearch.protocol [demo]" in captured.err


def test_package_main_uses_sys_argv(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["autoresearch"])

    exit_code = autoresearch_main.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "AUTORESEARCH NETWORK" in captured.out
    assert "Validator Submission Cycle" in captured.out


def test_package_main_demo_alias_still_works(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["autoresearch", "demo"])

    exit_code = autoresearch_main.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Validator Submission Cycle" in captured.out
