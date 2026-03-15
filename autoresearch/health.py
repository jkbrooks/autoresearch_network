"""Health checks for miner startup and local runtime validation."""

from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from bittensor.core.subtensor import Subtensor
from bittensor_wallet.wallet import Wallet

from autoresearch.experiment_runner import RunResult, run_experiment
from autoresearch.hardware import detect_hardware

LOGGER = logging.getLogger(__name__)


@dataclass
class HealthResult:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class HealthCheckResult:
    """Single ordered health check result for the local runner stack."""

    name: str
    healthy: bool
    message: str


HEALTH_CHECK_ORDER: tuple[str, ...] = (
    "prepare_script",
    "program_manifest",
    "data_pyproject",
    "hardware",
    "experiment_runner",
)


class HealthCheck:
    """Startup health checks used by the miner CLI."""

    def __init__(
        self,
        config: Any,
        *,
        cache_dir: str | None = None,
        uv_command: str = "uv",
    ) -> None:
        self.config = config
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "autoresearch"
        self.uv_command = uv_command

    def run_all(self) -> list[HealthResult]:
        if getattr(self.config, "skip_health_check", False):
            return []
        return [
            self.check_gpu(),
            self.check_uv(),
            self.check_data_cache(),
            self.check_vram_minimum(),
            self.check_wallet(),
            self.check_bittensor_connection(),
        ]

    def check_gpu(self) -> HealthResult:
        if not torch.cuda.is_available():
            return HealthResult(
                "check_gpu",
                "fail",
                "No CUDA GPU detected. A GPU with ≥8GB VRAM is required to mine.",
            )
        return HealthResult("check_gpu", "ok", "CUDA GPU detected.")

    def check_uv(self) -> HealthResult:
        if shutil.which(self.uv_command) is None:
            return HealthResult(
                "check_uv",
                "fail",
                "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh",
            )
        return HealthResult("check_uv", "ok", "uv available.")

    def check_data_cache(self) -> HealthResult:
        if not _cache_ready(self.cache_dir):
            return HealthResult(
                "check_data_cache",
                "fail",
                "Data cache not found at ~/.cache/autoresearch/. Run: uv run prepare.py",
            )
        return HealthResult("check_data_cache", "ok", "Data cache available.")

    def check_vram_minimum(self) -> HealthResult:
        if not torch.cuda.is_available():
            return HealthResult(
                "check_vram_minimum",
                "warn",
                "CUDA unavailable; VRAM check skipped.",
            )
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        if vram_gb < 8:
            return HealthResult(
                "check_vram_minimum",
                "warn",
                f"GPU VRAM is {vram_gb:.1f}GB, below 8GB minimum for SMALL tier. "
                "Performance will be very limited.",
            )
        return HealthResult("check_vram_minimum", "ok", f"GPU VRAM is {vram_gb:.1f}GB.")

    def check_wallet(self) -> HealthResult:
        wallet = Wallet(
            name=self.config.wallet.name,
            hotkey=self.config.wallet.hotkey,
            path=self.config.wallet.path,
        )
        if not wallet.hotkey_file.exists_on_device():
            return HealthResult(
                "check_wallet",
                "fail",
                f"Wallet '{self.config.wallet.name}' hotkey "
                f"'{self.config.wallet.hotkey}' not found. "
                "Create with: btcli wallet new_hotkey ...",
            )
        return HealthResult("check_wallet", "ok", "Wallet available.")

    def check_bittensor_connection(self) -> HealthResult:
        try:
            subtensor_kwargs: dict[str, Any] = {}
            chain_endpoint = getattr(self.config.subtensor, "chain_endpoint", None)
            network = getattr(self.config.subtensor, "network", None)
            if chain_endpoint and chain_endpoint != network:
                subtensor_kwargs["chain_endpoint"] = chain_endpoint
            else:
                subtensor_kwargs["network"] = network
            subtensor = Subtensor(**subtensor_kwargs)
            subtensor.get_current_block()
        except Exception:
            return HealthResult(
                "check_bittensor_connection",
                "warn",
                f"Could not connect to Bittensor {self.config.subtensor.network}. "
                "Miner will start but may not receive challenges.",
            )
        return HealthResult("check_bittensor_connection", "ok", "Bittensor reachable.")


def check_prepare_script(data_dir: Path) -> HealthCheckResult:
    prepare_path = data_dir / "prepare.py"
    if not prepare_path.exists():
        return HealthCheckResult("prepare_script", False, f"missing: {prepare_path}")
    if not prepare_path.is_file():
        return HealthCheckResult("prepare_script", False, f"not a file: {prepare_path}")
    return HealthCheckResult("prepare_script", True, f"found: {prepare_path}")


def check_program_manifest(data_dir: Path) -> HealthCheckResult:
    program_path = data_dir / "program.md"
    if not program_path.exists():
        return HealthCheckResult("program_manifest", False, f"missing: {program_path}")
    content = program_path.read_text(encoding="utf-8").strip()
    if not content:
        return HealthCheckResult("program_manifest", False, f"empty manifest: {program_path}")
    return HealthCheckResult("program_manifest", True, f"loaded manifest: {program_path}")


def check_data_pyproject(data_dir: Path) -> HealthCheckResult:
    pyproject_path = data_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return HealthCheckResult("data_pyproject", False, f"missing: {pyproject_path}")
    try:
        text = pyproject_path.read_text(encoding="utf-8")
    except OSError as exc:
        return HealthCheckResult("data_pyproject", False, f"read error: {exc}")
    if "[tool.poetry]" not in text and "[project]" not in text:
        return HealthCheckResult(
            "data_pyproject",
            False,
            f"missing [project] metadata in {pyproject_path}",
        )
    return HealthCheckResult("data_pyproject", True, f"pyproject parse-ready: {pyproject_path}")


def check_hardware() -> HealthCheckResult:
    hardware = detect_hardware()
    return HealthCheckResult(
        "hardware",
        True,
        "tier="
        f"{hardware.tier.value}, "
        f"vram_mb={hardware.vram_mb}, "
        f"throughput={hardware.throughput_tokens_per_sec}",
    )


def _probe_experiment_runner(
    *,
    runner: Callable[..., RunResult],
) -> HealthCheckResult:
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = Path(temp_dir) / "probe.py"
            probe.write_text("print('ok')", encoding="utf-8")
            result = runner(command=[sys.executable, str(probe)], timeout_seconds=2.0)
    except Exception as exc:
        return HealthCheckResult("experiment_runner", False, f"runner raised: {exc}")

    healthy = result.return_code == 0 and "ok" in result.stdout
    message = "runner execution failed" if not healthy else "runner executed successfully"
    return HealthCheckResult("experiment_runner", healthy, message)


def run_health_checks(
    *,
    data_dir: Path | str = Path("autoresearch/data"),
    checks: tuple[str, ...] | None = None,
    run_runner: Callable[..., RunResult] = run_experiment,
) -> list[HealthCheckResult]:
    """Execute the local runner stack checks in a deterministic order."""

    data_path = Path(data_dir)
    check_order = checks if checks is not None else HEALTH_CHECK_ORDER
    mapping: dict[str, Callable[[], HealthCheckResult]] = {
        "prepare_script": lambda: check_prepare_script(data_path),
        "program_manifest": lambda: check_program_manifest(data_path),
        "data_pyproject": lambda: check_data_pyproject(data_path),
        "hardware": check_hardware,
        "experiment_runner": lambda: _probe_experiment_runner(runner=run_runner),
    }
    results: list[HealthCheckResult] = []
    for name in check_order:
        checker = mapping.get(name)
        if checker is None:
            results.append(HealthCheckResult(name, False, f"unknown check: {name}"))
            continue
        results.append(checker())
    return results


def _cache_ready(cache_dir: Path) -> bool:
    if not cache_dir.exists():
        return False
    if any(cache_dir.rglob("*.parquet")):
        return True
    return any(cache_dir.rglob("*.bin"))
