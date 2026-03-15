"""Hardware detection helpers for miner and validator flows."""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass

import torch

from autoresearch.constants import TIER_PLAUSIBILITY, HardwareTier
from autoresearch.experiment_runner import RunResult

LOGGER = logging.getLogger(__name__)

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency in constrained environments
    psutil = None


@dataclass(frozen=True)
class DetectedHardware:
    """Collapsed hardware detection result."""

    tier: HardwareTier
    vram_mb: float | None
    throughput_tokens_per_sec: float | None
    source: str


def get_vram_tier(total_vram_bytes: int) -> HardwareTier:
    """Map total VRAM bytes to the protocol hardware tier."""

    vram_gb = total_vram_bytes / (1024**3)
    if vram_gb <= 8:
        return HardwareTier.SMALL
    if vram_gb <= 16:
        return HardwareTier.MEDIUM
    if vram_gb <= 36:
        return HardwareTier.LARGE
    return HardwareTier.XL


def check_throughput_consistency(tier: HardwareTier, run_result: RunResult) -> bool:
    """Check whether self-reported throughput is broadly consistent with a tier."""

    if run_result.total_tokens_m is None or run_result.training_seconds is None:
        return True
    if run_result.training_seconds <= 0:
        return False
    tokens_per_sec = (run_result.total_tokens_m * 1_000_000.0) / run_result.training_seconds
    plausible = TIER_PLAUSIBILITY[tier]
    expected_min = (plausible.min_tokens_m * 1_000_000.0) / 300.0
    expected_max = (plausible.max_tokens_m * 1_000_000.0) / 300.0
    return expected_min * 0.5 <= tokens_per_sec <= expected_max * 2.0


def detect_vram_mb() -> float | None:
    """Best-effort attempt to infer total GPU VRAM in MB from torch."""

    if not torch.cuda.is_available():
        return None
    try:
        props = torch.cuda.get_device_properties(0)
    except Exception:  # pragma: no cover - defensive against local CUDA variance
        return None
    return props.total_memory / (1024 * 1024)


def detect_hardware_tier(
    config_override: str | None = None,
    run_result: RunResult | None = None,
) -> HardwareTier:
    """Detect the protocol tier, honoring explicit override first."""

    if config_override is not None:
        return HardwareTier(config_override)

    if not torch.cuda.is_available():
        total_ram_gb = (
            psutil.virtual_memory().total / (1024**3) if psutil is not None else 0.0
        )
        LOGGER.warning(
            "No CUDA device found on %s with %.1fGB system RAM. Defaulting to SMALL tier. "
            "Performance will be limited.",
            platform.processor() or "unknown CPU",
            total_ram_gb,
        )
        return HardwareTier.SMALL

    props = torch.cuda.get_device_properties(0)
    tier = get_vram_tier(props.total_memory)
    if run_result is not None and not check_throughput_consistency(tier, run_result):
        LOGGER.warning("Throughput is inconsistent with detected tier %s", tier.value)
    return tier


def detect_hardware(
    *,
    override_tier: HardwareTier | str | None = None,
    override_vram_mb: float | None = None,
    override_throughput: float | None = None,
) -> DetectedHardware:
    """Return a richer detection payload for validator-side health and reporting."""

    if override_tier is not None:
        tier = HardwareTier(override_tier)
        throughput = (
            override_throughput
            if override_throughput is not None
            else _estimate_throughput(tier)
        )
        return DetectedHardware(
            tier=tier,
            vram_mb=override_vram_mb,
            throughput_tokens_per_sec=throughput,
            source="override_tier",
        )

    vram_mb = override_vram_mb if override_vram_mb is not None else detect_vram_mb()
    tier = HardwareTier.SMALL if vram_mb is None else get_vram_tier(int(vram_mb * 1024 * 1024))
    throughput = (
        override_throughput
        if override_throughput is not None
        else _estimate_throughput(tier)
    )
    return DetectedHardware(
        tier=tier,
        vram_mb=vram_mb,
        throughput_tokens_per_sec=throughput,
        source="vram" if vram_mb is not None else "default",
    )


def _estimate_throughput(tier: HardwareTier) -> float:
    throughput_map = {
        HardwareTier.SMALL: 80.0,
        HardwareTier.MEDIUM: 160.0,
        HardwareTier.LARGE: 280.0,
        HardwareTier.XL: 520.0,
    }
    return throughput_map[tier]
