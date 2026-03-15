from __future__ import annotations

import sys
from pathlib import Path

from autoresearch.experiment_runner import (
    ExperimentRunner,
    RunResult,
    parse_metrics,
    run_experiment,
)

VALID_LOG = """---
val_bpb:          0.997900
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     45060.2
mfu_percent:      39.80
total_tokens_M:   499.6
num_steps:        953
num_params_M:     50.3
depth:            8
"""


def make_runner(tmp_path: Path, timeout_seconds: float = 1.0) -> ExperimentRunner:
    prepare = tmp_path / "prepare.py"
    prepare.write_text("print('prepare ok')\n", encoding="utf-8")
    runner_pyproject = tmp_path / "pyproject.toml"
    runner_pyproject.write_text("[project]\nname='runner'\nversion='0.1.0'\n", encoding="utf-8")
    runner = ExperimentRunner(
        prepare_py_path=str(prepare),
        data_cache_dir=str(tmp_path / "cache"),
        runner_pyproject_path=str(runner_pyproject),
        timeout_seconds=timeout_seconds,
    )
    runner.command_prefix = [sys.executable]
    return runner


def test_parse_metrics_valid_log() -> None:
    parsed = parse_metrics(VALID_LOG)
    assert parsed["val_bpb"] == 0.9979
    assert parsed["training_seconds"] == 300.1
    assert parsed["total_seconds"] == 325.9
    assert parsed["peak_vram_mb"] == 45060.2
    assert parsed["mfu_percent"] == 39.8
    assert parsed["total_tokens_m"] == 499.6
    assert parsed["num_steps"] == 953
    assert parsed["num_params_m"] == 50.3
    assert parsed["depth"] == 8


def test_parse_metrics_reads_generic_key_value_lines() -> None:
    log = "\n".join(
        [
            "val_bpb: 1.023400",
            "training_seconds: 123.45",
            "peak_vram_mb: 2048.0",
            "throughput toks: 11.2",
        ]
    )
    metrics = parse_metrics(log)
    assert metrics["val_bpb"] == 1.0234
    assert metrics["training_seconds"] == 123.45
    assert metrics["peak_vram_mb"] == 2048.0
    assert metrics["throughput_toks"] == 11.2


def test_parse_metrics_missing_fields() -> None:
    parsed = parse_metrics("val_bpb:          0.9\n")
    assert parsed["val_bpb"] == 0.9
    assert parsed["depth"] is None


def test_parse_metrics_empty_log() -> None:
    parsed = parse_metrics("")
    assert all(parsed[key] is None for key in parsed if key in {
        "val_bpb",
        "training_seconds",
        "total_seconds",
        "peak_vram_mb",
        "mfu_percent",
        "total_tokens_m",
        "num_steps",
        "num_params_m",
        "depth",
    })


def test_run_result_dataclass_defaults() -> None:
    result = RunResult()
    assert result.val_bpb is None
    assert result.run_log_tail == ""
    assert result.status == "pending"
    assert result.command == ()


def test_run_experiment_captures_command_output(tmp_path: Path) -> None:
    script = tmp_path / "print_metrics.py"
    script.write_text("print('done')\n", encoding="utf-8")

    result = run_experiment(
        command=[sys.executable, str(script)],
        timeout_seconds=2.0,
    )

    assert isinstance(result, RunResult)
    assert result.return_code == 0
    assert result.stdout.strip() == "done"
    assert result.stderr == ""
    assert not result.timed_out
    assert result.elapsed_seconds >= 0
    assert result.command == (sys.executable, str(script))


def test_run_experiment_times_out_and_marks_result(tmp_path: Path) -> None:
    script = tmp_path / "hang.py"
    script.write_text("import time\ntime.sleep(5)\nprint('late')\n", encoding="utf-8")

    result = run_experiment(
        command=[sys.executable, str(script)],
        timeout_seconds=0.1,
    )

    assert result.timed_out
    assert result.return_code != 0
    assert result.process_group is None or result.process_group > 0


def test_runner_returns_timeout_on_slow_script(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, timeout_seconds=0.1)
    result = runner.run("import time\ntime.sleep(1)\n")
    assert result.status == "timeout"


def test_runner_returns_crash_on_invalid_python(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    result = runner.run("raise RuntimeError('test crash')\n")
    assert result.status == "crash"
    assert "RuntimeError: test crash" in result.run_log_tail


def test_runner_cleans_up_temp_dir(tmp_path: Path, monkeypatch) -> None:
    runner = make_runner(tmp_path)
    work_dir = tmp_path / "runner-work"
    work_dir.mkdir()
    monkeypatch.setattr(
        "autoresearch.experiment_runner.tempfile.mkdtemp",
        lambda prefix: str(work_dir),
    )
    runner.run("print('hello')\n")
    assert not work_dir.exists()


def test_runner_successful_run_populates_metrics(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    script = (
        "print('---')\n"
        "print('val_bpb:          0.997900')\n"
        "print('training_seconds: 300.1')\n"
        "print('total_seconds:    325.9')\n"
        "print('peak_vram_mb:     45060.2')\n"
        "print('mfu_percent:      39.80')\n"
        "print('total_tokens_M:   499.6')\n"
        "print('num_steps:        953')\n"
        "print('num_params_M:     50.3')\n"
        "print('depth:            8')\n"
    )
    result = runner.run(script)
    assert result.status == "success"
    assert result.val_bpb == 0.9979
    assert result.depth == 8


def test_setup_runs_prepare_only_if_cache_missing(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    data_dir = cache_dir / "data"
    shard_path = data_dir / "shard_00000.parquet"
    prepare = tmp_path / "prepare.py"
    prepare.write_text(
        f"from pathlib import Path\nPath(r'{data_dir}').mkdir(parents=True, exist_ok=True)\n"
        f"Path(r'{shard_path}').write_text('ok')\n",
        encoding="utf-8",
    )
    runner_pyproject = tmp_path / "pyproject.toml"
    runner_pyproject.write_text("[project]\nname='runner'\nversion='0.1.0'\n", encoding="utf-8")
    runner = ExperimentRunner(
        prepare_py_path=str(prepare),
        data_cache_dir=str(cache_dir),
        runner_pyproject_path=str(runner_pyproject),
    )
    runner.command_prefix = [sys.executable]
    assert runner.setup() is True
    assert (cache_dir / "data" / "shard_00000.parquet").exists()
    assert runner.setup() is True
