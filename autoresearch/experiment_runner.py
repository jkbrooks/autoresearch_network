"""Utilities for executing vendored experiment payloads."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

MetricValue = float | int


@dataclass(frozen=True)
class RunResult:
    """Result model for a single experiment command execution."""

    command: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_seconds: float
    process_group: int | None = None


_METRIC_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9 _./-]*)\s*:\s*("
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|inf|-inf|nan"
    r")\s*$"
)


def parse_metrics(log: str) -> dict[str, float]:
    """Parse key/value metric lines from a training log text block."""

    values: dict[str, float] = {}
    for raw_line in log.splitlines():
        match = _METRIC_RE.match(raw_line)
        if not match:
            continue
        key = (
            match.group(1)
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace(".", "_")
            .replace("/", "_")
        )
        try:
            values[key] = float(match.group(2))
        except ValueError:
            continue
    return values


def _spawn_process_group(
    command: Sequence[str], *, cwd: Path | None, env: Mapping[str, str] | None
) -> subprocess.Popen[str]:
    preexec_fn = None
    if os.name == "posix":
        preexec_fn = os.setsid

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
    os.killpg(process_group, signal.SIGTERM)
    time.sleep(0.05)
    process.kill()


def run_experiment(
    *,
    command: Sequence[str],
    cwd: Path | None = None,
    timeout_seconds: float = 180.0,
    env: Mapping[str, str] | None = None,
    spawn: Callable[..., subprocess.Popen[str]] = _spawn_process_group,
) -> RunResult:
    """Execute an experiment command and return captured output and timing.

    Parameters are intentionally injectable for unit tests:
    * ``command`` to support temporary scripts and shim commands.
    * ``timeout_seconds`` to keep CI stable.
    * ``spawn`` to inject mock subprocess factories.
    """

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
    return_code = process.returncode if process.returncode is not None else 1

    return RunResult(
        command=tuple(command),
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        elapsed_seconds=elapsed_seconds,
        process_group=process_group,
    )


def default_prepare_command(program_path: str | Path, *, timeout: float = 180.0) -> RunResult:
    """Run the vendored ``autoresearch/data/prepare.py`` as a default experiment."""

    command: list[str] = [sys.executable, str(program_path)]
    return run_experiment(command=command, timeout_seconds=timeout)
