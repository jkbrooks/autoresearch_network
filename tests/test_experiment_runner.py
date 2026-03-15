from __future__ import annotations

import sys
from pathlib import Path

from autoresearch.experiment_runner import RunResult, parse_metrics, run_experiment


def test_parse_metrics_reads_key_value_lines() -> None:
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
    script.write_text(
        "import time\ntime.sleep(5)\nprint('late')\n",
        encoding="utf-8",
    )

    result = run_experiment(
        command=[sys.executable, str(script)],
        timeout_seconds=0.1,
    )

    assert result.timed_out
    assert result.return_code != 0
    assert result.process_group is None or result.process_group > 0
