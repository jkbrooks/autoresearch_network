"""Launch the AutoResearch miner on Modal for subnet 193.

This script is intentionally optimized for a short best-effort GPU validation run, not
for permanent production hosting.

Prerequisites:
- `pip install modal`
- `modal setup`
- local wallet directory at `~/.bittensor/wallets/my-miner`
- run from the repo workspace root

Important caveats:
- This reuses the existing `my-miner/default` wallet and uploads it into a Modal image.
  That is operationally risky and should only be used for short-lived testnet validation.
- Modal raw TCP exposure is best-effort for Bittensor because the network still expects a
  routable literal IP address to be advertised on-chain.
"""

from __future__ import annotations

import argparse
import os
import shlex
import socket
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
REMOTE_REPO_ROOT = "/root/autoresearchnetwork"
REMOTE_WALLET_ROOT = "/root/.bittensor/wallets"
REMOTE_WALLET_DIR = f"{REMOTE_WALLET_ROOT}/my-miner"
DEFAULT_WALLET_DIR = Path.home() / ".bittensor" / "wallets" / "my-miner"
DEFAULT_GPU = "L4"
DEFAULT_HOURS = 2
DEFAULT_CPU = 2.0
DEFAULT_MEMORY_MB = 8192
MINER_PORT = 8091
NETUID = 193
WALLET_NAME = "my-miner"
WALLET_HOTKEY = "default"
STARTUP_TIMEOUT_SECONDS = 30 * 60
IGNORE_NAMES = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".uv-cache",
    ".validator-state",
    ".validator-state-smoke",
    "__pycache__",
}
SUCCESS_MARKERS = (
    "Serving miner axon on test netuid=193",
    "AxonInfo(",
    "test:193",
    "Miner starting at block:",
)
FAILURE_MARKERS = (
    "[HEALTH FAIL]",
    "Traceback (most recent call last):",
    "Experiment runner setup failed.",
)


class LauncherError(RuntimeError):
    """Raised when launcher prerequisites or runtime steps fail."""


@dataclass(frozen=True)
class LaunchConfig:
    repo_root: Path
    wallet_dir: Path
    gpu: str = DEFAULT_GPU
    hours: int = DEFAULT_HOURS
    mutation_provider: str | None = None
    mutation_model: str | None = None
    mutation_base_url: str | None = None
    debug_skip_health_check: bool = False
    debug_allow_non_validator_queries: bool = False
    debug_min_validator_stake: float | None = None

    @property
    def timeout_seconds(self) -> int:
        return self.hours * 60 * 60


@dataclass(frozen=True)
class LaunchSummary:
    sandbox_id: str
    forwarded_host: str
    forwarded_port: int
    advertised_ip: str
    advertised_port: int
    miner_command: str
    terminate_command: str
    wallet_overview_command: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the AutoResearch miner on Modal.")
    subparsers = parser.add_subparsers(dest="command")

    launch_parser = subparsers.add_parser("launch", help="Launch the Modal sandbox miner")
    launch_parser.add_argument("--gpu", default=DEFAULT_GPU)
    launch_parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    launch_parser.add_argument("--mutation-provider", default=None)
    launch_parser.add_argument("--mutation-model", default=None)
    launch_parser.add_argument("--mutation-base-url", default=None)
    launch_parser.add_argument("--debug-skip-health-check", action="store_true")
    launch_parser.add_argument(
        "--debug-allow-non-validator-queries",
        action="store_true",
        help="Disable validator permit enforcement for smoke-test queries.",
    )
    launch_parser.add_argument(
        "--debug-min-validator-stake",
        type=float,
        default=None,
        help="Override the miner minimum validator stake for debugging.",
    )
    launch_parser.add_argument(
        "--wallet-dir",
        default=str(DEFAULT_WALLET_DIR),
        help="Local wallet directory to upload into the sandbox.",
    )
    launch_parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repo root to upload into the sandbox.",
    )

    terminate_parser = subparsers.add_parser("terminate", help="Terminate an existing sandbox")
    terminate_parser.add_argument("--sandbox-id", required=True)

    parser.set_defaults(command="launch")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "terminate":
        sandbox_id = terminate_sandbox(args.sandbox_id)
        print(f"Terminated sandbox {sandbox_id}")
        return 0

    config = LaunchConfig(
        repo_root=Path(args.repo_root).expanduser().resolve(),
        wallet_dir=Path(args.wallet_dir).expanduser().resolve(),
        gpu=args.gpu,
        hours=args.hours,
        mutation_provider=args.mutation_provider,
        mutation_model=args.mutation_model,
        mutation_base_url=args.mutation_base_url,
        debug_skip_health_check=args.debug_skip_health_check,
        debug_allow_non_validator_queries=args.debug_allow_non_validator_queries,
        debug_min_validator_stake=args.debug_min_validator_stake,
    )
    summary = launch_sandbox(config)
    print("")
    print("Modal miner launch summary")
    print(f"  Sandbox ID:        {summary.sandbox_id}")
    print(f"  Forwarded host:    {summary.forwarded_host}")
    print(f"  Forwarded port:    {summary.forwarded_port}")
    print(f"  Advertised IP:     {summary.advertised_ip}")
    print(f"  Advertised port:   {summary.advertised_port}")
    print(f"  Miner command:     {summary.miner_command}")
    print(f"  Terminate command: {summary.terminate_command}")
    print(f"  Wallet inspect:    {summary.wallet_overview_command}")
    return 0


def launch_sandbox(config: LaunchConfig) -> LaunchSummary:
    modal = _import_modal()
    validate_local_prereqs(config.repo_root, config.wallet_dir)
    print("Validated local repo and wallet prerequisites.", flush=True)
    image = build_image(modal, config.repo_root, config.wallet_dir)
    secrets = build_modal_secrets(modal, config)
    modal_app = modal.App.lookup("autoresearch-modal-miner-193", create_if_missing=True)
    print(
        f"Using Modal app autoresearch-modal-miner-193 with gpu={config.gpu} "
        f"for {config.hours} hour(s).",
        flush=True,
    )

    sandbox = modal.Sandbox.create(
        "bash",
        "-lc",
        "sleep infinity",
        app=modal_app,
        image=image,
        timeout=config.timeout_seconds,
        idle_timeout=config.timeout_seconds,
        gpu=config.gpu,
        cpu=DEFAULT_CPU,
        memory=DEFAULT_MEMORY_MB,
        workdir=REMOTE_REPO_ROOT,
        secrets=secrets,
        unencrypted_ports=[MINER_PORT],
    )
    print(f"Created sandbox {sandbox.object_id}. Waiting for tunnel metadata...", flush=True)
    tunnel = get_tcp_tunnel(sandbox, MINER_PORT)
    forwarded_host = tunnel.unencrypted_host or tunnel.host
    forwarded_port = tunnel.unencrypted_port or tunnel.port
    print(f"Resolved tunnel endpoint {forwarded_host}:{forwarded_port}.", flush=True)
    advertised_ip = resolve_forward_hostname(forwarded_host)
    print(f"Resolved advertised IPv4 {advertised_ip}.", flush=True)

    miner_command = build_miner_command(config, advertised_ip, forwarded_port)
    bootstrap_script = build_bootstrap_script(miner_command)
    print("Starting sandbox bootstrap and miner process...", flush=True)
    process = sandbox.exec(
        "bash",
        "-lc",
        bootstrap_script,
        bufsize=1,
        text=True,
    )

    wait_for_startup_success(process, startup_timeout_seconds=STARTUP_TIMEOUT_SECONDS)
    return LaunchSummary(
        sandbox_id=sandbox.object_id,
        forwarded_host=forwarded_host,
        forwarded_port=forwarded_port,
        advertised_ip=advertised_ip,
        advertised_port=forwarded_port,
        miner_command=shlex.join(miner_command),
        terminate_command=(
            "python scripts/modal_miner_193.py terminate "
            f"--sandbox-id {sandbox.object_id}"
        ),
        wallet_overview_command=(
            "uv run --with bittensor-cli btcli wallet overview "
            f"--wallet-name {WALLET_NAME} --network test"
        ),
    )


def terminate_sandbox(sandbox_id: str) -> str:
    modal = _import_modal()
    sandbox = modal.Sandbox.from_id(sandbox_id)
    sandbox.terminate(wait=True)
    return sandbox_id


def validate_local_prereqs(repo_root: Path, wallet_dir: Path) -> None:
    if not repo_root.exists():
        raise LauncherError(f"Repo root does not exist: {repo_root}")
    if not (repo_root / "neurons" / "miner.py").exists():
        raise LauncherError(f"Repo root does not look valid: {repo_root}")
    if not wallet_dir.exists():
        raise LauncherError(f"Wallet directory does not exist: {wallet_dir}")


def build_image(modal: Any, repo_root: Path, wallet_dir: Path) -> Any:
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install("uv")
        .add_local_dir(
            repo_root,
            REMOTE_REPO_ROOT,
            ignore=repo_ignore_filter,
        )
        .add_local_dir(
            wallet_dir,
            REMOTE_WALLET_DIR,
            ignore=wallet_ignore_filter,
        )
    )
    return image


def build_modal_secrets(modal: Any, config: LaunchConfig) -> list[Any]:
    env: dict[str, str] = {}
    provider = (config.mutation_provider or "").lower()
    if provider == "anthropic":
        value = os.environ.get("ANTHROPIC_API_KEY")
        if not value:
            raise LauncherError("ANTHROPIC_API_KEY is required for anthropic mutation mode.")
        env["ANTHROPIC_API_KEY"] = value
    elif provider in {"openai", "openai-compatible"}:
        value = os.environ.get("OPENAI_API_KEY")
        if not value:
            raise LauncherError("OPENAI_API_KEY is required for openai mutation mode.")
        env["OPENAI_API_KEY"] = value
    return [modal.Secret.from_dict(env)] if env else []


def build_miner_command(
    config: LaunchConfig,
    advertised_ipv4: str,
    forwarded_port: int,
) -> list[str]:
    command = [
        "uv",
        "run",
        "python",
        "neurons/miner.py",
        "--netuid",
        str(NETUID),
        "--network",
        "test",
        "--wallet.name",
        WALLET_NAME,
        "--wallet.hotkey",
        WALLET_HOTKEY,
        "--wallet.path",
        REMOTE_WALLET_ROOT,
        "--logging.debug",
        "--axon.port",
        str(MINER_PORT),
        "--axon.external-ip",
        advertised_ipv4,
        "--axon.external-port",
        str(forwarded_port),
    ]
    if config.mutation_provider:
        command.extend(["--mutation-provider", config.mutation_provider])
    if config.mutation_model:
        command.extend(["--mutation-model", config.mutation_model])
    if config.mutation_base_url:
        command.extend(["--mutation-base-url", config.mutation_base_url])
    if config.debug_skip_health_check:
        command.append("--skip-health-check")
    if config.debug_allow_non_validator_queries:
        command.append("--no-blacklist.force-validator-permit")
    if config.debug_min_validator_stake is not None:
        command.extend(["--blacklist.min-stake", str(config.debug_min_validator_stake)])
    return command


def build_bootstrap_script(miner_command: list[str]) -> str:
    return "\n".join(
        [
            "set -euo pipefail",
            f"cd {shlex.quote(REMOTE_REPO_ROOT)}",
            "echo '[bootstrap] syncing dependencies'",
            "uv sync --dev --python 3.11",
            "echo '[bootstrap] preparing autoresearch cache'",
            "uv run prepare.py",
            "echo '[bootstrap] starting miner'",
            f"exec {shlex.join(miner_command)}",
        ]
    )


def get_tcp_tunnel(sandbox: Any, port: int) -> Any:
    tunnels = sandbox.tunnels(timeout=50)
    if port not in tunnels:
        raise LauncherError(f"No tunnel published for port {port}")
    return tunnels[port]


def resolve_forward_hostname(hostname: str) -> str:
    try:
        return socket.gethostbyname(hostname)
    except OSError as exc:
        raise LauncherError(f"Could not resolve tunnel host '{hostname}' to IPv4") from exc


def wait_for_startup_success(process: Any, *, startup_timeout_seconds: int) -> None:
    started_at = time.monotonic()
    ring = deque(maxlen=80)
    saw_serving = False
    saw_axon = False
    saw_ready = False

    stdout_iter = iter(process.stdout)
    stderr_iter = iter(process.stderr)
    while True:
        for stream_name, iterator in (("stdout", stdout_iter), ("stderr", stderr_iter)):
            try:
                line = next(iterator)
            except StopIteration:
                continue
            text = str(line)
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()
            ring.append(f"{stream_name}: {text.rstrip()}")
            if SUCCESS_MARKERS[0] in text:
                saw_serving = True
            if SUCCESS_MARKERS[1] in text and SUCCESS_MARKERS[2] in text:
                saw_axon = True
            if SUCCESS_MARKERS[3] in text:
                saw_ready = True
            if any(marker in text for marker in FAILURE_MARKERS):
                raise LauncherError("Miner startup failed:\n" + "\n".join(ring))

        if saw_serving and saw_axon and saw_ready:
            return

        exit_code = process.poll()
        if exit_code is not None:
            raise LauncherError(
                f"Bootstrap/miner process exited with code {exit_code}:\n" + "\n".join(ring)
            )

        if time.monotonic() - started_at > startup_timeout_seconds:
            raise LauncherError(
                f"Miner did not reach serving state within {startup_timeout_seconds} seconds."
            )
        time.sleep(0.25)


def repo_ignore_filter(path: Path) -> bool:
    return any(part in IGNORE_NAMES for part in path.parts) or path.name == ".coverage"


def wallet_ignore_filter(path: Path) -> bool:
    return any(part in {"__pycache__", ".DS_Store"} for part in path.parts)


def _import_modal() -> Any:
    try:
        import modal
    except ImportError as exc:  # pragma: no cover - exercised in real operator environments
        raise LauncherError(
            "Modal is not installed. Run `pip install modal` and `modal setup` first."
        ) from exc
    return modal


if __name__ == "__main__":
    raise SystemExit(main())
