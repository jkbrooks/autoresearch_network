"""Experiment execution environment for miner training runs."""

from __future__ import annotations

import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)

MetricValue = float | int | None
EXPECTED_METRIC_KEYS: tuple[str, ...] = (
    "val_bpb",
    "training_seconds",
    "total_seconds",
    "peak_vram_mb",
    "mfu_percent",
    "total_tokens_m",
    "num_steps",
    "num_params_m",
    "depth",
)

_METRIC_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9 _./-]*)\s*:\s*("
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|inf|-inf|nan"
    r")\s*$",
    re.MULTILINE,
)


@dataclass
class RunResult:
    """Combined result model for low-level execution and parsed experiment metrics."""

    command: tuple[str, ...] = ()
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    elapsed_seconds: float = 0.0
    process_group: int | None = None

    val_bpb: float | None = None
    training_seconds: float | None = None
    total_seconds: float | None = None
    peak_vram_mb: float | None = None
    mfu_percent: float | None = None
    total_tokens_m: float | None = None
    num_steps: int | None = None
    num_params_m: float | None = None
    depth: int | None = None
    run_log_tail: str = ""
    status: str = "pending"


def _normalize_metric_key(raw_key: str) -> str:
    return (
        raw_key.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
        .replace("/", "_")
    )


def parse_metrics(log: str) -> dict[str, MetricValue]:
    """Parse scalar key/value metrics from train.py or helper logs."""

    parsed: dict[str, MetricValue] = {key: None for key in EXPECTED_METRIC_KEYS}
    for match in _METRIC_RE.finditer(log):
        key = _normalize_metric_key(match.group(1))
        raw_value = match.group(2)
        value = float(raw_value)
        if key in {"num_steps", "depth"} and value.is_integer():
            parsed[key] = int(value)
        else:
            parsed[key] = value
    return parsed


def _spawn_process_group(
    command: Sequence[str], *, cwd: Path | None, env: Mapping[str, str] | None
) -> subprocess.Popen[str]:
    preexec_fn = os.setsid if os.name == "posix" else None
    return subprocess.Popen(
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        env=dict(os.environ, **env) if env is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=preexec_fn,
    )


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    if os.name != "posix":
        process.kill()
        return

    if process.pid is None:
        return

    try:
        process_group = os.getpgid(process.pid)
    except ProcessLookupError:
        return

    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(0.05)
    try:
        process.kill()
    except ProcessLookupError:
        return


def run_experiment(
    *,
    command: Sequence[str],
    cwd: Path | None = None,
    timeout_seconds: float = 180.0,
    env: Mapping[str, str] | None = None,
    spawn: Callable[..., subprocess.Popen[str]] = _spawn_process_group,
) -> RunResult:
    """Execute a command with timeout and process-group cleanup."""

    started_at = time.perf_counter()
    process = spawn(command=command, cwd=cwd, env=env)
    process_group: int | None = None
    if os.name == "posix" and process.pid is not None:
        try:
            process_group = os.getpgid(process.pid)
        except ProcessLookupError:
            process_group = None

    timed_out = False
    stdout = ""
    stderr = ""
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_group(process)
        stdout, stderr = process.communicate()

    elapsed_seconds = time.perf_counter() - started_at
    return RunResult(
        command=tuple(command),
        return_code=process.returncode if process.returncode is not None else 1,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        elapsed_seconds=elapsed_seconds,
        process_group=process_group,
    )


class ExperimentRunner:
    """Run training experiments in isolated temp directories."""

    def __init__(
        self,
        prepare_py_path: str | None = None,
        data_cache_dir: str | None = None,
        runner_pyproject_path: str | None = None,
        timeout_seconds: int = 600,
    ) -> None:
        data_dir = Path(__file__).with_name("data")
        self.prepare_py_path = Path(prepare_py_path) if prepare_py_path else data_dir / "prepare.py"
        self.data_cache_dir = (
            Path(data_cache_dir) if data_cache_dir else Path.home() / ".cache" / "autoresearch"
        )
        self.runner_pyproject_path = (
            Path(runner_pyproject_path) if runner_pyproject_path else data_dir / "pyproject.toml"
        )
        self.timeout_seconds = timeout_seconds
        self.command_prefix = ["uv", "run"]

    def setup(self) -> bool:
        if self._cache_ready():
            LOGGER.info("AutoResearch cache present at %s; setup skipped.", self.data_cache_dir)
            return True

        LOGGER.info("AutoResearch cache missing at %s; running prepare.py", self.data_cache_dir)
        prepared = run_experiment(
            command=[*self.command_prefix, self.prepare_py_path.name],
            cwd=self.prepare_py_path.parent,
            timeout_seconds=self.timeout_seconds,
        )
        if prepared.return_code != 0 or prepared.timed_out:
            output = prepared.stderr or prepared.stdout
            LOGGER.error("prepare.py failed: %s", output.strip())
            return False
        return self._cache_ready()

    def run(self, train_py_source: str) -> RunResult:
        work_dir = Path(tempfile.mkdtemp(prefix="autoresearch-run-"))
        try:
            (work_dir / "train.py").write_text(train_py_source, encoding="utf-8")
            shutil.copy2(self.prepare_py_path, work_dir / "prepare.py")
            shutil.copy2(self.runner_pyproject_path, work_dir / "pyproject.toml")

            executed = run_experiment(
                command=[*self.command_prefix, "train.py"],
                cwd=work_dir,
                timeout_seconds=self.timeout_seconds,
            )
            combined_output = executed.stdout
            if executed.stderr:
                combined_output = (
                    f"{combined_output}\n{executed.stderr}"
                    if combined_output
                    else executed.stderr
                )
            metrics = parse_metrics(combined_output)

            status = "success"
            if executed.timed_out:
                status = "timeout"
            elif executed.return_code != 0:
                status = "crash"

            return RunResult(
                command=executed.command,
                return_code=executed.return_code,
                stdout=executed.stdout,
                stderr=executed.stderr,
                timed_out=executed.timed_out,
                elapsed_seconds=executed.elapsed_seconds,
                process_group=executed.process_group,
                val_bpb=_as_float(metrics.get("val_bpb")),
                training_seconds=_as_float(metrics.get("training_seconds")),
                total_seconds=_as_float(metrics.get("total_seconds")),
                peak_vram_mb=_as_float(metrics.get("peak_vram_mb")),
                mfu_percent=_as_float(metrics.get("mfu_percent")),
                total_tokens_m=_as_float(metrics.get("total_tokens_m")),
                num_steps=_as_int(metrics.get("num_steps")),
                num_params_m=_as_float(metrics.get("num_params_m")),
                depth=_as_int(metrics.get("depth")),
                run_log_tail=self._tail(combined_output),
                status=status,
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _cache_ready(self) -> bool:
        if not self.data_cache_dir.exists():
            return False
        if any(self.data_cache_dir.rglob("*.parquet")):
            return True
        return any(self.data_cache_dir.rglob("*.bin"))

    @staticmethod
    def _tail(log: str, lines: int = 100) -> str:
        split = log.splitlines()
        return "\n".join(split[-lines:])


def default_prepare_command(program_path: str | Path, *, timeout: float = 180.0) -> RunResult:
    """Run the vendored prepare script directly through the Python interpreter."""

    return run_experiment(command=[sys.executable, str(program_path)], timeout_seconds=timeout)


def _as_float(value: MetricValue) -> float | None:
    if value is None:
        return None
    return float(value)


def _as_int(value: MetricValue) -> int | None:
    if value is None:
        return None
    return int(value)
