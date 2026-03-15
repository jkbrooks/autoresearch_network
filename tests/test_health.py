from __future__ import annotations

from types import SimpleNamespace

from autoresearch.health import HealthCheck
from autoresearch.utils.config import build_config


def test_health_no_cuda_fails(tmp_path, monkeypatch) -> None:
    config = build_config(["--skip-health-check"])
    check = HealthCheck(config, cache_dir=str(tmp_path))
    monkeypatch.setattr("autoresearch.health.torch.cuda.is_available", lambda: False)
    result = check.check_gpu()
    assert result.status == "fail"


def test_health_no_uv_fails(tmp_path, monkeypatch) -> None:
    config = build_config(["--skip-health-check"])
    check = HealthCheck(config, cache_dir=str(tmp_path), uv_command="missing-uv")
    monkeypatch.setattr("autoresearch.health.shutil.which", lambda _: None)
    result = check.check_uv()
    assert result.status == "fail"


def test_health_missing_cache_fails(tmp_path) -> None:
    config = build_config(["--skip-health-check"])
    check = HealthCheck(config, cache_dir=str(tmp_path / "missing"))
    result = check.check_data_cache()
    assert result.status == "fail"


def test_health_low_vram_warns(tmp_path, monkeypatch) -> None:
    config = build_config(["--skip-health-check"])
    check = HealthCheck(config, cache_dir=str(tmp_path))
    monkeypatch.setattr("autoresearch.health.torch.cuda.is_available", lambda: True)
    monkeypatch.setattr(
        "autoresearch.health.torch.cuda.get_device_properties",
        lambda _: SimpleNamespace(total_memory=6 * 1024**3),
    )
    result = check.check_vram_minimum()
    assert result.status == "warn"


def test_health_missing_wallet_fails(tmp_path, monkeypatch) -> None:
    config = build_config(["--skip-health-check"])
    check = HealthCheck(config, cache_dir=str(tmp_path))

    class FakeHotkeyFile:
        def exists_on_device(self) -> bool:
            return False

    class FakeWallet:
        hotkey_file = FakeHotkeyFile()

    monkeypatch.setattr("autoresearch.health.Wallet", lambda **_: FakeWallet())
    result = check.check_wallet()
    assert result.status == "fail"


def test_health_connection_failure_warns(tmp_path, monkeypatch) -> None:
    config = build_config(["--skip-health-check"])
    check = HealthCheck(config, cache_dir=str(tmp_path))

    class FakeSubtensor:
        def __init__(self, **_: object) -> None:
            pass

        def get_current_block(self) -> int:
            raise TimeoutError("boom")

    monkeypatch.setattr("autoresearch.health.Subtensor", FakeSubtensor)
    result = check.check_bittensor_connection()
    assert result.status == "warn"


def test_health_skip_flag_bypasses(tmp_path) -> None:
    config = build_config(["--skip-health-check"])
    check = HealthCheck(config, cache_dir=str(tmp_path))
    assert check.run_all() == []


def test_health_all_pass(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "data.bin").write_text("ok")
    config = build_config([])
    config.skip_health_check = False
    check = HealthCheck(config, cache_dir=str(cache_dir))

    monkeypatch.setattr("autoresearch.health.torch.cuda.is_available", lambda: True)
    monkeypatch.setattr(
        "autoresearch.health.torch.cuda.get_device_properties",
        lambda _: SimpleNamespace(total_memory=24 * 1024**3),
    )
    monkeypatch.setattr("autoresearch.health.shutil.which", lambda _: "/usr/bin/uv")

    class FakeHotkeyFile:
        def exists_on_device(self) -> bool:
            return True

    class FakeWallet:
        hotkey_file = FakeHotkeyFile()

    class FakeSubtensor:
        def __init__(self, **_: object) -> None:
            pass

        def get_current_block(self) -> int:
            return 1

    monkeypatch.setattr("autoresearch.health.Wallet", lambda **_: FakeWallet())
    monkeypatch.setattr("autoresearch.health.Subtensor", FakeSubtensor)
    results = check.run_all()
    assert all(result.status == "ok" for result in results)
