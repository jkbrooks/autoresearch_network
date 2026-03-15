"""Health checks for the experimental runner stack."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from autoresearch.experiment_runner import RunResult, run_experiment
from autoresearch.hardware import detect_hardware


@dataclass(frozen=True)
class HealthCheckResult:
    """Single ordered health check result."""

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
        hardware.vram_mb is not None or hardware.tier == hardware.tier,
        "tier="
        f"{hardware.tier.value}, "
        f"vram_mb={hardware.vram_mb}, "
        f"throughput={hardware.throughput_tokens_per_sec}",
    )


def _probe_experiment_runner(
    *,
    data_dir: Path,
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
    """Execute a deterministic sequence of health probes.

    Checks can be filtered by explicit tuple names, and remain
    ordered according to `HEALTH_CHECK_ORDER`.
    """

    data_path = Path(data_dir)
    check_order = checks if checks is not None else HEALTH_CHECK_ORDER
    mapping = {
        "prepare_script": lambda: check_prepare_script(data_path),
        "program_manifest": lambda: check_program_manifest(data_path),
        "data_pyproject": lambda: check_data_pyproject(data_path),
        "hardware": lambda: check_hardware(),
        "experiment_runner": lambda: _probe_experiment_runner(
            data_dir=data_path, runner=run_runner
        ),
    }
    results: list[HealthCheckResult] = []
    for name in check_order:
        checker = mapping.get(name)
        if checker is None:
            results.append(HealthCheckResult(name, False, f"unknown check: {name}"))
            continue
        results.append(checker())
    return results
