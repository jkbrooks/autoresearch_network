from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.modal_miner_193 import (
    DEFAULT_WALLET_DIR,
    LaunchConfig,
    LauncherError,
    build_bootstrap_script,
    build_miner_command,
    build_modal_secrets,
    build_tcp_relay_command,
    get_tcp_tunnel,
    resolve_forward_hostname,
    resolve_public_endpoint,
    validate_local_prereqs,
    validate_public_ipv4,
    wait_for_startup_success,
)


def make_config(tmp_path: Path) -> LaunchConfig:
    repo_root = tmp_path / "repo"
    wallet_dir = tmp_path / "wallets" / "my-miner"
    (repo_root / "neurons").mkdir(parents=True)
    (repo_root / "neurons" / "miner.py").write_text("print('ok')\n", encoding="utf-8")
    wallet_dir.mkdir(parents=True)
    return LaunchConfig(repo_root=repo_root, wallet_dir=wallet_dir)


def test_validate_local_prereqs_requires_wallet_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "neurons").mkdir(parents=True)
    (repo_root / "neurons" / "miner.py").write_text("print('ok')\n", encoding="utf-8")
    with pytest.raises(LauncherError, match="Wallet directory does not exist"):
        validate_local_prereqs(repo_root, DEFAULT_WALLET_DIR / "missing")


def test_validate_local_prereqs_requires_repo_shape(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    wallet_dir = tmp_path / "wallet"
    wallet_dir.mkdir()
    with pytest.raises(LauncherError, match="Repo root does not look valid"):
        validate_local_prereqs(repo_root, wallet_dir)


def test_build_miner_command_contains_required_flags(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    command = build_miner_command(config, "1.2.3.4", 45678)
    rendered = " ".join(command)
    assert "--netuid 193" in rendered
    assert "--network test" in rendered
    assert "--wallet.name my-miner" in rendered
    assert "--wallet.hotkey default" in rendered
    assert "--axon.port 8091" in rendered
    assert "--axon.external-ip 1.2.3.4" in rendered
    assert "--axon.external-port 45678" in rendered


def test_build_miner_command_includes_optional_mutation_flags(tmp_path: Path) -> None:
    config = LaunchConfig(
        repo_root=tmp_path,
        wallet_dir=tmp_path,
        mutation_provider="openai-compatible",
        mutation_model="local-model",
        mutation_base_url="http://localhost:8000",
        debug_skip_health_check=True,
        debug_allow_non_validator_queries=True,
        debug_min_validator_stake=0.0,
    )
    command = build_miner_command(config, "1.2.3.4", 45678)
    rendered = " ".join(command)
    assert "--mutation-provider openai-compatible" in rendered
    assert "--mutation-model local-model" in rendered
    assert "--mutation-base-url http://localhost:8000" in rendered
    assert "--skip-health-check" in rendered
    assert "--no-blacklist.force-validator-permit" in rendered
    assert "--blacklist.min-stake 0.0" in rendered


def test_resolve_forward_hostname_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.modal_miner_193.socket.gethostbyname", lambda host: "1.2.3.4")
    assert resolve_forward_hostname("example.test") == "1.2.3.4"


def test_resolve_forward_hostname_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(host: str) -> str:
        raise OSError("nope")

    monkeypatch.setattr("scripts.modal_miner_193.socket.gethostbyname", boom)
    with pytest.raises(LauncherError, match="Could not resolve tunnel host"):
        resolve_forward_hostname("example.test")


def test_validate_public_ipv4_accepts_literal_ipv4() -> None:
    assert validate_public_ipv4("203.0.113.10") == "203.0.113.10"


def test_validate_public_ipv4_rejects_hostname() -> None:
    with pytest.raises(LauncherError, match="literal IPv4 address"):
        validate_public_ipv4("relay.example.com")


def test_resolve_public_endpoint_defaults_to_modal_forwarding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr("scripts.modal_miner_193.socket.gethostbyname", lambda host: "1.2.3.4")
    advertised_ip, advertised_port, relay_command = resolve_public_endpoint(
        config,
        forwarded_host="modal.test",
        forwarded_port=45678,
    )
    assert advertised_ip == "1.2.3.4"
    assert advertised_port == 45678
    assert relay_command is None


def test_resolve_public_endpoint_uses_configured_stable_frontend(tmp_path: Path) -> None:
    config = LaunchConfig(
        repo_root=tmp_path,
        wallet_dir=tmp_path,
        public_ip="198.51.100.7",
    )
    advertised_ip, advertised_port, relay_command = resolve_public_endpoint(
        config,
        forwarded_host="modal.test",
        forwarded_port=45678,
    )
    assert advertised_ip == "198.51.100.7"
    assert advertised_port == 8091
    assert relay_command == "socat TCP-LISTEN:8091,reuseaddr,fork TCP:modal.test:45678"


def test_resolve_public_endpoint_requires_public_ip_when_port_only(tmp_path: Path) -> None:
    config = LaunchConfig(
        repo_root=tmp_path,
        wallet_dir=tmp_path,
        public_port=8091,
    )
    with pytest.raises(LauncherError, match="--public-port requires --public-ip"):
        resolve_public_endpoint(
            config,
            forwarded_host="modal.test",
            forwarded_port=45678,
        )


def test_build_tcp_relay_command_renders_expected_socat_command() -> None:
    assert (
        build_tcp_relay_command(
            listen_port=8091,
            forwarded_host="modal.test",
            forwarded_port=45678,
        )
        == "socat TCP-LISTEN:8091,reuseaddr,fork TCP:modal.test:45678"
    )


def test_wait_for_startup_success_detects_serving_logs() -> None:
    process = SimpleNamespace(
        stdout=iter(
            [
                "setup ok\n",
                "Serving miner axon on test netuid=193\n",
                "AxonInfo(abc, 1.2.3.4:8091) -> test:193\n",
                "Miner starting at block: 12345\n",
            ]
        ),
        stderr=iter([]),
        poll=lambda: None,
    )
    wait_for_startup_success(process, startup_timeout_seconds=5)


def test_wait_for_startup_success_hard_fails_on_failure_marker() -> None:
    process = SimpleNamespace(
        stdout=iter(["[HEALTH FAIL] check_gpu: boom\n"]),
        stderr=iter([]),
        poll=lambda: None,
    )
    with pytest.raises(LauncherError, match="Miner startup failed"):
        wait_for_startup_success(process, startup_timeout_seconds=5)


def test_get_tcp_tunnel_targets_expected_port() -> None:
    sandbox = SimpleNamespace(tunnels=lambda timeout=50: {8091: "tcp-tunnel"})
    assert get_tcp_tunnel(sandbox, 8091) == "tcp-tunnel"


def test_get_tcp_tunnel_raises_when_missing() -> None:
    sandbox = SimpleNamespace(tunnels=lambda timeout=50: {})
    with pytest.raises(LauncherError, match="No tunnel published for port 8091"):
        get_tcp_tunnel(sandbox, 8091)


def test_build_bootstrap_script_includes_prepare_and_exec(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    script = build_bootstrap_script(build_miner_command(config, "1.2.3.4", 45678))
    assert "uv sync --dev --python 3.11" in script
    assert "uv run prepare.py" in script
    assert "neurons/miner.py" in script


def test_build_modal_secrets_returns_empty_when_no_provider(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    fake_modal = SimpleNamespace(Secret=SimpleNamespace(from_dict=lambda env: env))
    assert build_modal_secrets(fake_modal, config) == []


def test_build_modal_secrets_requires_provider_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = LaunchConfig(
        repo_root=tmp_path,
        wallet_dir=tmp_path,
        mutation_provider="anthropic",
    )
    fake_modal = SimpleNamespace(Secret=SimpleNamespace(from_dict=lambda env: env))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LauncherError, match="ANTHROPIC_API_KEY is required"):
        build_modal_secrets(fake_modal, config)
