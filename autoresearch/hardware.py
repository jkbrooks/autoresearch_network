"""Hardware tier detection helpers."""

from __future__ import annotations

import logging
import platform

import torch

from autoresearch.constants import TIER_PLAUSIBILITY, HardwareTier
from autoresearch.experiment_runner import RunResult

LOGGER = logging.getLogger(__name__)

try:
    import psutil
except ImportError:  # pragma: no cover - exercised indirectly via fallback behavior
    psutil = None


def get_vram_tier(total_vram_bytes: int) -> HardwareTier:
    vram_gb = total_vram_bytes / (1024**3)
    if vram_gb <= 8:
        return HardwareTier.SMALL
    if vram_gb <= 16:
        return HardwareTier.MEDIUM
    if vram_gb <= 36:
        return HardwareTier.LARGE
    return HardwareTier.XL


def check_throughput_consistency(tier: HardwareTier, run_result: RunResult) -> bool:
    if run_result.total_tokens_m is None or run_result.training_seconds is None:
        return True
    tokens_per_sec = (run_result.total_tokens_m * 1e6) / run_result.training_seconds
    plausible = TIER_PLAUSIBILITY[tier]
    expected_min = (plausible.min_tokens_m * 1e6) / 300
    expected_max = (plausible.max_tokens_m * 1e6) / 300
    return expected_min * 0.5 <= tokens_per_sec <= expected_max * 2.0


def detect_hardware_tier(
    config_override: str | None = None,
    run_result: RunResult | None = None,
) -> HardwareTier:
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
