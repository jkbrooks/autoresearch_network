"""Deploy the AutoResearch miner on Modal as a persistent HTTP endpoint.

Usage:
    AUTORESEARCH_PUBLIC_IP=<relay-ip> modal deploy scripts/modal_miner_193_http.py

This app is intended to sit behind a tiny stable-IP VM reverse proxy. The Modal endpoint keeps the
GPU-backed Axon/FastAPI surface available on a stable `modal.run` URL while the VM owns the public
numeric IP:port that Bittensor validators dial.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

import bittensor as bt
import modal

from autoresearch.utils.config import build_config
from neurons.miner import Miner
from scripts.modal_miner_193 import (
    DEFAULT_CPU,
    DEFAULT_GPU,
    DEFAULT_MEMORY_MB,
    DEFAULT_WALLET_DIR,
    NETUID,
    REMOTE_REPO_ROOT,
    REPO_ROOT,
    build_image,
    build_miner_cli_args,
    build_modal_secrets,
)
from scripts.modal_miner_193_web_support import (
    DEFAULT_ENDPOINT_LABEL,
    DEFAULT_FUNCTION_TIMEOUT_SECONDS,
    DEFAULT_MIN_CONTAINERS,
    DEFAULT_STARTUP_TIMEOUT_SECONDS,
    load_web_endpoint_config,
)

DEPLOY_REPO_ROOT = (
    Path(os.environ.get("AUTORESEARCH_REPO_ROOT", str(REPO_ROOT))).expanduser().resolve()
)
DEPLOY_WALLET_DIR = Path(
    os.environ.get("AUTORESEARCH_WALLET_DIR", str(DEFAULT_WALLET_DIR))
).expanduser().resolve()
DEPLOY_GPU = os.environ.get("AUTORESEARCH_MODAL_GPU", DEFAULT_GPU)
DEPLOY_MIN_CONTAINERS = int(
    os.environ.get("AUTORESEARCH_MODAL_MIN_CONTAINERS", str(DEFAULT_MIN_CONTAINERS))
)
DEPLOY_STARTUP_TIMEOUT = int(
    os.environ.get(
        "AUTORESEARCH_MODAL_STARTUP_TIMEOUT",
        str(DEFAULT_STARTUP_TIMEOUT_SECONDS),
    )
)
DEPLOY_FUNCTION_TIMEOUT = int(
    os.environ.get(
        "AUTORESEARCH_MODAL_FUNCTION_TIMEOUT",
        str(DEFAULT_FUNCTION_TIMEOUT_SECONDS),
    )
)
DEPLOY_ENDPOINT_LABEL = os.environ.get(
    "AUTORESEARCH_MODAL_ENDPOINT_LABEL",
    DEFAULT_ENDPOINT_LABEL,
)
DEPLOY_REQUIRES_PROXY_AUTH = (
    os.environ.get("AUTORESEARCH_MODAL_PROXY_AUTH", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
RUNTIME_ENV_KEYS = (
    "AUTORESEARCH_PUBLIC_IP",
    "AUTORESEARCH_PUBLIC_PORT",
    "AUTORESEARCH_WALLET_DIR",
    "AUTORESEARCH_NETWORK",
    "AUTORESEARCH_MODAL_GPU",
    "AUTORESEARCH_MUTATION_PROVIDER",
    "AUTORESEARCH_MUTATION_MODEL",
    "AUTORESEARCH_MUTATION_BASE_URL",
    "AUTORESEARCH_SKIP_HEALTH_CHECK",
    "AUTORESEARCH_DEBUG_ALLOW_NON_VALIDATOR_QUERIES",
    "AUTORESEARCH_DEBUG_MIN_VALIDATOR_STAKE",
    "AUTORESEARCH_MODAL_ENDPOINT_LABEL",
    "AUTORESEARCH_MODAL_MIN_CONTAINERS",
    "AUTORESEARCH_MODAL_STARTUP_TIMEOUT",
    "AUTORESEARCH_MODAL_FUNCTION_TIMEOUT",
    "AUTORESEARCH_MODAL_PROXY_AUTH",
)
RUNTIME_ENV = {
    key: value
    for key in RUNTIME_ENV_KEYS
    if (value := os.environ.get(key)) is not None
}

IMAGE = build_image(
    modal,
    DEPLOY_REPO_ROOT,
    DEPLOY_WALLET_DIR,
    copy_local=True,
).run_commands(
    f"cd {shlex.quote(REMOTE_REPO_ROOT)} && uv pip install --system --editable .",
    f"cd {shlex.quote(REMOTE_REPO_ROOT)} && python prepare.py",
)
SECRETS = build_modal_secrets(
    modal,
    load_web_endpoint_config(
        env=RUNTIME_ENV,
        repo_root=DEPLOY_REPO_ROOT,
    ).to_launch_config(),
)
app = modal.App("autoresearch-modal-miner-193-http")
_modal_miner: Miner | None = None


def _create_miner() -> Miner:
    web_config = load_web_endpoint_config(repo_root=DEPLOY_REPO_ROOT)
    launch_config = web_config.to_launch_config()
    cli_args = build_miner_cli_args(
        launch_config,
        web_config.public_ip,
        web_config.public_port,
    )
    config = build_config(args=cli_args)
    miner = Miner(config=config)
    miner.ensure_registered()
    bt.logging.info(
        "Serving Modal HTTP miner endpoint on "
        f"{config.subtensor.network} netuid={config.netuid} "
        f"advertised_as={web_config.public_ip}:{web_config.public_port}"
    )
    miner.axon.serve(netuid=NETUID, subtensor=miner.subtensor)
    return miner


@app.function(
    image=IMAGE,
    env=RUNTIME_ENV,
    secrets=SECRETS,
    gpu=DEPLOY_GPU,
    cpu=DEFAULT_CPU,
    memory=DEFAULT_MEMORY_MB,
    min_containers=DEPLOY_MIN_CONTAINERS,
    max_containers=1,
    startup_timeout=DEPLOY_STARTUP_TIMEOUT,
    timeout=DEPLOY_FUNCTION_TIMEOUT,
)
@modal.asgi_app(
    label=DEPLOY_ENDPOINT_LABEL,
    requires_proxy_auth=DEPLOY_REQUIRES_PROXY_AUTH,
)
def miner_asgi():
    global _modal_miner
    if _modal_miner is None:
        os.chdir(REMOTE_REPO_ROOT)
        _modal_miner = _create_miner()
    return _modal_miner.axon.app
