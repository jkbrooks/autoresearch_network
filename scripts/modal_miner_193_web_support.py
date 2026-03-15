"""Support utilities for the long-lived Modal HTTP miner deployment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from scripts.modal_miner_193 import (
    DEFAULT_GPU,
    DEFAULT_WALLET_DIR,
    MINER_PORT,
    REPO_ROOT,
    LaunchConfig,
    validate_public_ipv4,
)

DEFAULT_ENDPOINT_LABEL = "autoresearch-miner-193"
DEFAULT_MIN_CONTAINERS = 1
DEFAULT_STARTUP_TIMEOUT_SECONDS = 20 * 60
DEFAULT_FUNCTION_TIMEOUT_SECONDS = 60 * 60


@dataclass(frozen=True)
class WebEndpointConfig:
    repo_root: Path
    wallet_dir: Path
    public_ip: str
    public_port: int = MINER_PORT
    gpu: str = DEFAULT_GPU
    network: str = "test"
    mutation_provider: str | None = None
    mutation_model: str | None = None
    mutation_base_url: str | None = None
    debug_skip_health_check: bool = False
    debug_allow_non_validator_queries: bool = False
    debug_min_validator_stake: float | None = None
    endpoint_label: str = DEFAULT_ENDPOINT_LABEL
    min_containers: int = DEFAULT_MIN_CONTAINERS
    startup_timeout_seconds: int = DEFAULT_STARTUP_TIMEOUT_SECONDS
    function_timeout_seconds: int = DEFAULT_FUNCTION_TIMEOUT_SECONDS
    requires_proxy_auth: bool = False

    def to_launch_config(self) -> LaunchConfig:
        return LaunchConfig(
            repo_root=self.repo_root,
            wallet_dir=self.wallet_dir,
            gpu=self.gpu,
            public_ip=self.public_ip,
            public_port=self.public_port,
            mutation_provider=self.mutation_provider,
            mutation_model=self.mutation_model,
            mutation_base_url=self.mutation_base_url,
            debug_skip_health_check=self.debug_skip_health_check,
            debug_allow_non_validator_queries=self.debug_allow_non_validator_queries,
            debug_min_validator_stake=self.debug_min_validator_stake,
        )


def load_web_endpoint_config(
    *,
    env: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> WebEndpointConfig:
    data = dict(os.environ if env is None else env)
    resolved_repo_root = (repo_root or REPO_ROOT).expanduser().resolve()
    wallet_dir_value = data.get("AUTORESEARCH_WALLET_DIR", str(DEFAULT_WALLET_DIR))
    public_ip_value = data.get("AUTORESEARCH_PUBLIC_IP")
    if not public_ip_value:
        raise RuntimeError(
            "AUTORESEARCH_PUBLIC_IP is required for the Modal HTTP miner deployment."
        )

    public_ip = validate_public_ipv4(public_ip_value)
    wallet_dir = Path(wallet_dir_value).expanduser().resolve()
    return WebEndpointConfig(
        repo_root=resolved_repo_root,
        wallet_dir=wallet_dir,
        public_ip=public_ip,
        public_port=_env_int(data, "AUTORESEARCH_PUBLIC_PORT", MINER_PORT),
        gpu=data.get("AUTORESEARCH_MODAL_GPU", DEFAULT_GPU),
        network=data.get("AUTORESEARCH_NETWORK", "test"),
        mutation_provider=data.get("AUTORESEARCH_MUTATION_PROVIDER"),
        mutation_model=data.get("AUTORESEARCH_MUTATION_MODEL"),
        mutation_base_url=data.get("AUTORESEARCH_MUTATION_BASE_URL"),
        debug_skip_health_check=_env_bool(data, "AUTORESEARCH_SKIP_HEALTH_CHECK", False),
        debug_allow_non_validator_queries=_env_bool(
            data,
            "AUTORESEARCH_DEBUG_ALLOW_NON_VALIDATOR_QUERIES",
            False,
        ),
        debug_min_validator_stake=_env_float(
            data,
            "AUTORESEARCH_DEBUG_MIN_VALIDATOR_STAKE",
        ),
        endpoint_label=data.get("AUTORESEARCH_MODAL_ENDPOINT_LABEL", DEFAULT_ENDPOINT_LABEL),
        min_containers=_env_int(
            data,
            "AUTORESEARCH_MODAL_MIN_CONTAINERS",
            DEFAULT_MIN_CONTAINERS,
        ),
        startup_timeout_seconds=_env_int(
            data,
            "AUTORESEARCH_MODAL_STARTUP_TIMEOUT",
            DEFAULT_STARTUP_TIMEOUT_SECONDS,
        ),
        function_timeout_seconds=_env_int(
            data,
            "AUTORESEARCH_MODAL_FUNCTION_TIMEOUT",
            DEFAULT_FUNCTION_TIMEOUT_SECONDS,
        ),
        requires_proxy_auth=_env_bool(data, "AUTORESEARCH_MODAL_PROXY_AUTH", False),
    )


def render_nginx_reverse_proxy_config(
    upstream_url: str,
    *,
    listen_port: int = MINER_PORT,
    requires_proxy_auth: bool = False,
) -> str:
    parsed = urlparse(upstream_url)
    host_header = parsed.netloc or upstream_url
    lines = [
        "server {",
        f"    listen {listen_port};",
        "    server_name _;",
        "",
        "    location / {",
        f"        proxy_pass {upstream_url};",
        "        proxy_http_version 1.1;",
        "        proxy_ssl_server_name on;",
        f"        proxy_set_header Host {host_header};",
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "        proxy_set_header X-Forwarded-Proto http;",
        "        proxy_request_buffering off;",
        "        proxy_buffering off;",
        "        proxy_read_timeout 15s;",
        "        proxy_send_timeout 15s;",
    ]
    if requires_proxy_auth:
        lines.extend(
            [
                "",
                "        # Uncomment if the Modal endpoint is private:",
                "        # proxy_set_header Modal-Key YOUR_MODAL_KEY;",
                "        # proxy_set_header Modal-Secret YOUR_MODAL_SECRET;",
            ]
        )
    lines.extend(
        [
            "    }",
            "}",
        ]
    )
    return "\n".join(lines)


def build_runtime_env(config: WebEndpointConfig) -> dict[str, str]:
    env = {
        "AUTORESEARCH_PUBLIC_IP": config.public_ip,
        "AUTORESEARCH_PUBLIC_PORT": str(config.public_port),
        "AUTORESEARCH_WALLET_DIR": str(config.wallet_dir),
        "AUTORESEARCH_MODAL_GPU": config.gpu,
        "AUTORESEARCH_NETWORK": config.network,
        "AUTORESEARCH_SKIP_HEALTH_CHECK": _bool_string(config.debug_skip_health_check),
        "AUTORESEARCH_DEBUG_ALLOW_NON_VALIDATOR_QUERIES": _bool_string(
            config.debug_allow_non_validator_queries
        ),
        "AUTORESEARCH_MODAL_ENDPOINT_LABEL": config.endpoint_label,
        "AUTORESEARCH_MODAL_MIN_CONTAINERS": str(config.min_containers),
        "AUTORESEARCH_MODAL_STARTUP_TIMEOUT": str(config.startup_timeout_seconds),
        "AUTORESEARCH_MODAL_FUNCTION_TIMEOUT": str(config.function_timeout_seconds),
        "AUTORESEARCH_MODAL_PROXY_AUTH": _bool_string(config.requires_proxy_auth),
    }
    if config.mutation_provider:
        env["AUTORESEARCH_MUTATION_PROVIDER"] = config.mutation_provider
    if config.mutation_model:
        env["AUTORESEARCH_MUTATION_MODEL"] = config.mutation_model
    if config.mutation_base_url:
        env["AUTORESEARCH_MUTATION_BASE_URL"] = config.mutation_base_url
    if config.debug_min_validator_stake is not None:
        env["AUTORESEARCH_DEBUG_MIN_VALIDATOR_STAKE"] = str(config.debug_min_validator_stake)
    return env


def _env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    value = env.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(env: Mapping[str, str], key: str, default: int) -> int:
    value = env.get(key)
    return default if value is None else int(value)


def _env_float(env: Mapping[str, str], key: str) -> float | None:
    value = env.get(key)
    return None if value is None else float(value)


def _bool_string(value: bool) -> str:
    return "true" if value else "false"
