from __future__ import annotations

from types import SimpleNamespace

from autoresearch.constants import HardwareTier
from autoresearch.experiment_runner import RunResult
from autoresearch.hardware import check_throughput_consistency, detect_hardware_tier, get_vram_tier


def test_vram_tier_small() -> None:
    assert get_vram_tier(6 * 1024**3) is HardwareTier.SMALL


def test_vram_tier_medium() -> None:
    assert get_vram_tier(12 * 1024**3) is HardwareTier.MEDIUM


def test_vram_tier_large() -> None:
    assert get_vram_tier(24 * 1024**3) is HardwareTier.LARGE


def test_vram_tier_xl() -> None:
    assert get_vram_tier(80 * 1024**3) is HardwareTier.XL


def test_vram_tier_boundaries() -> None:
    assert get_vram_tier(8 * 1024**3) is HardwareTier.SMALL
    assert get_vram_tier(16 * 1024**3) is HardwareTier.MEDIUM
    assert get_vram_tier(36 * 1024**3) is HardwareTier.LARGE


def test_config_override_takes_precedence() -> None:
    assert detect_hardware_tier(config_override="xl") is HardwareTier.XL


def test_throughput_consistent_returns_true() -> None:
    result = RunResult(total_tokens_m=120.0, training_seconds=300.0)
    assert check_throughput_consistency(HardwareTier.LARGE, result) is True


def test_throughput_inconsistent_returns_false() -> None:
    result = RunResult(total_tokens_m=600.0, training_seconds=10.0)
    assert check_throughput_consistency(HardwareTier.SMALL, result) is False


def test_throughput_missing_data_returns_true() -> None:
    assert check_throughput_consistency(HardwareTier.SMALL, RunResult()) is True


def test_no_cuda_fallback(monkeypatch) -> None:
    monkeypatch.setattr("autoresearch.hardware.torch.cuda.is_available", lambda: False)
    monkeypatch.setattr(
        "autoresearch.hardware.psutil.virtual_memory",
        lambda: SimpleNamespace(total=16 * 1024**3),
    )
    assert detect_hardware_tier() is HardwareTier.SMALL
