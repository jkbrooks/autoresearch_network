"""Experiment execution environment for miner training runs."""

from __future__ import annotations

import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass
class RunResult:
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


def parse_metrics(log: str) -> dict[str, Any]:
    patterns: dict[str, tuple[str, type[Any]]] = {
        "val_bpb": (r"^val_bpb:\s+([\d.]+)", float),
        "training_seconds": (r"^training_seconds:\s+([\d.]+)", float),
        "total_seconds": (r"^total_seconds:\s+([\d.]+)", float),
        "peak_vram_mb": (r"^peak_vram_mb:\s+([\d.]+)", float),
        "mfu_percent": (r"^mfu_percent:\s+([\d.]+)", float),
        "total_tokens_m": (r"^total_tokens_M:\s+([\d.]+)", float),
        "num_steps": (r"^num_steps:\s+(\d+)", int),
        "num_params_m": (r"^num_params_M:\s+([\d.]+)", float),
        "depth": (r"^depth:\s+(\d+)", int),
    }
    parsed: dict[str, Any] = {}
    for key, (pattern, caster) in patterns.items():
        match = re.search(pattern, log, re.MULTILINE)
        parsed[key] = caster(match.group(1)) if match else None
    return parsed


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
        result = subprocess.run(
            self.command_prefix + [self.prepare_py_path.name],
            cwd=self.prepare_py_path.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            LOGGER.error("prepare.py failed: %s", result.stderr or result.stdout)
            return False
        return True

    def run(self, train_py_source: str) -> RunResult:
        work_dir = Path(tempfile.mkdtemp(prefix="autoresearch-run-"))
        result = RunResult()
        process: subprocess.Popen[str] | None = None
        try:
            (work_dir / "train.py").write_text(train_py_source, encoding="utf-8")
            shutil.copy2(self.prepare_py_path, work_dir / "prepare.py")
            shutil.copy2(self.runner_pyproject_path, work_dir / "pyproject.toml")

            process = subprocess.Popen(
                self.command_prefix + ["train.py"],
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, _ = process.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                if process.pid is not None:
                    os.killpg(process.pid, signal.SIGTERM)
                stdout, _ = process.communicate()
                result.run_log_tail = self._tail(stdout)
                result.status = "timeout"
                return result

            result.run_log_tail = self._tail(stdout)
            if process.returncode != 0:
                result.status = "crash"
                return result

            parsed = parse_metrics(stdout)
            result = RunResult(
                val_bpb=parsed["val_bpb"],
                training_seconds=parsed["training_seconds"],
                total_seconds=parsed["total_seconds"],
                peak_vram_mb=parsed["peak_vram_mb"],
                mfu_percent=parsed["mfu_percent"],
                total_tokens_m=parsed["total_tokens_m"],
                num_steps=parsed["num_steps"],
                num_params_m=parsed["num_params_m"],
                depth=parsed["depth"],
                run_log_tail=self._tail(stdout),
                status="success",
            )
            return result
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _cache_ready(self) -> bool:
        if not self.data_cache_dir.exists():
            return False
        return any(self.data_cache_dir.rglob("*.bin"))

    @staticmethod
    def _tail(log: str, lines: int = 100) -> str:
        split = log.splitlines()
        return "\n".join(split[-lines:])
