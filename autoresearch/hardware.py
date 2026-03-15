"""Hardware detection helpers used by validator/health checks."""

from __future__ import annotations

from dataclasses import dataclass

from autoresearch.constants import TIER_PLAUSIBILITY, HardwareTier


@dataclass(frozen=True)
class DetectedHardware:
    """Collapsed hardware detection result."""

    tier: HardwareTier
    vram_mb: float | None
    throughput_tokens_per_sec: float | None
    source: str


def _tier_from_vram(vram_mb: float | None) -> HardwareTier:
    if vram_mb is None:
        return HardwareTier.SMALL

    if vram_mb <= TIER_PLAUSIBILITY[HardwareTier.SMALL].max_vram_mb:
        return HardwareTier.SMALL
    if vram_mb <= TIER_PLAUSIBILITY[HardwareTier.MEDIUM].max_vram_mb:
        return HardwareTier.MEDIUM
    if vram_mb <= TIER_PLAUSIBILITY[HardwareTier.LARGE].max_vram_mb:
        return HardwareTier.LARGE
    return HardwareTier.XL


def _estimate_throughput(tier: HardwareTier) -> float:
    throughput_map = {
        HardwareTier.SMALL: 80.0,
        HardwareTier.MEDIUM: 160.0,
        HardwareTier.LARGE: 280.0,
        HardwareTier.XL: 520.0,
    }
    return throughput_map[tier]


def detect_vram_mb() -> float | None:
    """Best-effort attempt to infer total GPU VRAM in MB from torch."""

    try:
        import torch
    except Exception:
        return None

    if not torch.cuda.is_available():
        return None
    try:
        props = torch.cuda.get_device_properties(0)
        return props.total_memory / (1024 * 1024)
    except Exception:
        return None


def detect_hardware(
    *,
    override_tier: HardwareTier | str | None = None,
    override_vram_mb: float | None = None,
    override_throughput: float | None = None,
) -> DetectedHardware:
    """Detect hardware capacity with override and fallback heuristics."""

    if override_tier is not None:
        return DetectedHardware(
            tier=HardwareTier(override_tier),
            vram_mb=override_vram_mb,
            throughput_tokens_per_sec=override_throughput
            if override_throughput is not None
            else _estimate_throughput(HardwareTier(override_tier)),
            source="override_tier",
        )

    vram_mb = override_vram_mb if override_vram_mb is not None else detect_vram_mb()
    tier = _tier_from_vram(vram_mb)
    throughput = (
        override_throughput if override_throughput is not None else _estimate_throughput(tier)
    )
    source = "vram" if vram_mb is not None else "default"

    return DetectedHardware(
        tier=tier,
        vram_mb=vram_mb,
        throughput_tokens_per_sec=throughput,
        source=source,
    )
