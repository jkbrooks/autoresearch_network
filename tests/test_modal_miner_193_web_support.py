from __future__ import annotations

from pathlib import Path

import pytest

from scripts.modal_miner_193_web_support import (
    DEFAULT_ENDPOINT_LABEL,
    build_runtime_env,
    load_web_endpoint_config,
    render_nginx_reverse_proxy_config,
)


def test_load_web_endpoint_config_requires_public_ip(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="AUTORESEARCH_PUBLIC_IP is required"):
        load_web_endpoint_config(
            env={"AUTORESEARCH_WALLET_DIR": str(tmp_path / "wallet")},
            repo_root=tmp_path,
        )


def test_load_web_endpoint_config_reads_expected_values(tmp_path: Path) -> None:
    config = load_web_endpoint_config(
        env={
            "AUTORESEARCH_PUBLIC_IP": "203.0.113.10",
            "AUTORESEARCH_PUBLIC_PORT": "9000",
            "AUTORESEARCH_WALLET_DIR": str(tmp_path / "wallet"),
            "AUTORESEARCH_MODAL_GPU": "A10G",
            "AUTORESEARCH_MUTATION_PROVIDER": "openai-compatible",
            "AUTORESEARCH_MUTATION_MODEL": "local-model",
            "AUTORESEARCH_MUTATION_BASE_URL": "http://host.docker.internal:8000",
            "AUTORESEARCH_SKIP_HEALTH_CHECK": "true",
            "AUTORESEARCH_MODAL_MIN_CONTAINERS": "2",
            "AUTORESEARCH_MODAL_PROXY_AUTH": "yes",
        },
        repo_root=tmp_path,
    )
    assert config.public_ip == "203.0.113.10"
    assert config.public_port == 9000
    assert config.wallet_dir == (tmp_path / "wallet").resolve()
    assert config.gpu == "A10G"
    assert config.mutation_provider == "openai-compatible"
    assert config.mutation_model == "local-model"
    assert config.mutation_base_url == "http://host.docker.internal:8000"
    assert config.debug_skip_health_check is True
    assert config.min_containers == 2
    assert config.requires_proxy_auth is True
    assert config.endpoint_label == DEFAULT_ENDPOINT_LABEL


def test_render_nginx_reverse_proxy_config_includes_modal_host() -> None:
    rendered = render_nginx_reverse_proxy_config(
        "https://workspace--autoresearch-miner-193.modal.run"
    )
    assert "listen 8091;" in rendered
    assert "proxy_pass https://workspace--autoresearch-miner-193.modal.run;" in rendered
    assert "proxy_set_header Host workspace--autoresearch-miner-193.modal.run;" in rendered


def test_render_nginx_reverse_proxy_config_emits_private_endpoint_headers() -> None:
    rendered = render_nginx_reverse_proxy_config(
        "https://workspace--autoresearch-miner-193.modal.run",
        requires_proxy_auth=True,
    )
    assert "proxy_set_header Modal-Key YOUR_MODAL_KEY;" in rendered
    assert "proxy_set_header Modal-Secret YOUR_MODAL_SECRET;" in rendered


def test_build_runtime_env_includes_required_public_values(tmp_path: Path) -> None:
    config = load_web_endpoint_config(
        env={
            "AUTORESEARCH_PUBLIC_IP": "203.0.113.10",
            "AUTORESEARCH_WALLET_DIR": str(tmp_path / "wallet"),
        },
        repo_root=tmp_path,
    )
    runtime_env = build_runtime_env(config)
    assert runtime_env["AUTORESEARCH_PUBLIC_IP"] == "203.0.113.10"
    assert runtime_env["AUTORESEARCH_PUBLIC_PORT"] == "8091"
    assert runtime_env["AUTORESEARCH_WALLET_DIR"] == str((tmp_path / "wallet").resolve())
    assert runtime_env["AUTORESEARCH_MODAL_MIN_CONTAINERS"] == "1"
