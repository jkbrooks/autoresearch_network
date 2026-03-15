from __future__ import annotations

import sys
from pathlib import Path

from autoresearch.experiment_runner import ExperimentRunner, RunResult, parse_metrics

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


def test_parse_metrics_missing_fields() -> None:
    parsed = parse_metrics("val_bpb:          0.9\n")
    assert parsed["val_bpb"] == 0.9
    assert parsed["depth"] is None


def test_parse_metrics_empty_log() -> None:
    parsed = parse_metrics("")
    assert all(value is None for value in parsed.values())


def test_run_result_dataclass_defaults() -> None:
    result = RunResult()
    assert result.val_bpb is None
    assert result.run_log_tail == ""
    assert result.status == "pending"


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
    prepare = tmp_path / "prepare.py"
    prepare.write_text(
        f"from pathlib import Path\nPath(r'{cache_dir}').mkdir(parents=True, exist_ok=True)\n"
        f"Path(r'{cache_dir / 'shard_00000.bin'}').write_text('ok')\n",
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
    assert (cache_dir / "shard_00000.bin").exists()
    assert runner.setup() is True
