"""Operational network check against the current relay-backed AutoResearch miner."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import warnings
from pathlib import Path
from typing import Any, cast

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module=r"pydantic\.plugin\._schema_validator",
)

DEFAULT_NETUID = 193
DEFAULT_NETWORK = "test"
DEFAULT_WALLET_NAME = "my-miner"
DEFAULT_WALLET_HOTKEY = "default"
DEFAULT_TARGET_HOTKEY = "default"
DEFAULT_WALLET_PATH = "~/.bittensor/wallets"
DEFAULT_VALIDATOR_STATE_PATH = ".validator-state-live/global_best.json"


async def _run_probe(
    *,
    wallet_name: str,
    wallet_hotkey: str,
    wallet_path: str,
    target_hotkey: str | None,
    network: str,
    netuid: int,
    timeout: float,
    baseline_train_py: str,
    global_best_val_bpb: float,
) -> dict[str, Any]:
    import bittensor as bt
    from bittensor_wallet.wallet import Wallet

    from autoresearch.protocol import ExperimentSubmission

    wallet = Wallet(name=wallet_name, hotkey=wallet_hotkey, path=wallet_path)
    subtensor = bt.Subtensor(network=network)
    metagraph = subtensor.metagraph(netuid)

    target_ss58 = _resolve_target_ss58(
        wallet_name=wallet_name,
        wallet_path=wallet_path,
        metagraph_hotkeys=list(metagraph.hotkeys),
        target_hotkey=target_hotkey,
        fallback_ss58=wallet.hotkey.ss58_address,
    )
    target_uid = metagraph.hotkeys.index(target_ss58)
    target_axon = metagraph.axons[target_uid]
    target_endpoint = f"{target_axon.ip}:{target_axon.port}"

    dendrite = bt.Dendrite(wallet=wallet)
    synapse = ExperimentSubmission(
        task_id="network_check",
        baseline_train_py=baseline_train_py,
        global_best_val_bpb=global_best_val_bpb,
    )
    response = await dendrite.call(
        target_axon,
        synapse=synapse,
        timeout=timeout,
        deserialize=False,
    )
    await dendrite.aclose_session()

    return {
        "wallet_hotkey_ss58": wallet.hotkey.ss58_address,
        "target_uid": target_uid,
        "target_endpoint": target_endpoint,
        "dendrite_status": getattr(response.dendrite, "status_code", None),
        "dendrite_message": getattr(response.dendrite, "status_message", None),
        "axon_status": getattr(response.axon, "status_code", None),
        "axon_message": getattr(response.axon, "status_message", None),
        "val_bpb": response.val_bpb,
        "hardware_tier": response.hardware_tier,
        "elapsed_wall_seconds": response.elapsed_wall_seconds,
        "peak_vram_mb": response.peak_vram_mb,
        "train_py_len": len(response.train_py) if response.train_py else None,
        "run_log_tail": response.run_log_tail,
    }


def _load_validator_state(path: str) -> dict[str, Any] | None:
    state_path = Path(path)
    if not state_path.exists():
        return None
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Validator state file {state_path} does not contain a JSON object")
    return cast(dict[str, Any], payload)


def _load_probe_challenge(validator_state_path: str) -> dict[str, Any]:
    metadata_path = Path(validator_state_path)
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Validator state metadata file not found: {metadata_path}"
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    global_best_val_bpb = metadata.get("val_bpb")
    if not isinstance(global_best_val_bpb, (int, float)):
        raise ValueError(
            f"Validator state file {metadata_path} is missing a numeric val_bpb."
        )

    best_train_path = metadata_path.with_name("best_train.py")
    if not best_train_path.exists():
        raise FileNotFoundError(
            f"Validator state train file not found: {best_train_path}"
        )

    baseline_train_py = best_train_path.read_text(encoding="utf-8")
    if not baseline_train_py.strip():
        raise ValueError(f"Validator state train file is empty: {best_train_path}")

    return {
        "baseline_train_py": baseline_train_py,
        "best_train_path": str(best_train_path),
        "global_best_val_bpb": float(global_best_val_bpb),
        "metadata_path": str(metadata_path),
    }


def _resolve_target_ss58(
    *,
    wallet_name: str,
    wallet_path: str,
    metagraph_hotkeys: list[str],
    target_hotkey: str | None,
    fallback_ss58: str,
) -> str:
    if not target_hotkey:
        return fallback_ss58
    if target_hotkey in metagraph_hotkeys:
        return target_hotkey

    from bittensor_wallet.wallet import Wallet

    try:
        local_wallet = Wallet(name=wallet_name, hotkey=target_hotkey, path=wallet_path)
        local_ss58 = local_wallet.hotkey.ss58_address
    except Exception as exc:  # pragma: no cover - defensive for local wallet variance
        raise ValueError(f"Unknown target hotkey '{target_hotkey}'.") from exc

    if local_ss58 not in metagraph_hotkeys:
        raise ValueError(
            f"Target hotkey '{target_hotkey}' resolved to {local_ss58}, "
            "but that hotkey is not registered on the target metagraph."
        )
    return local_ss58


def run_network_check(
    *,
    as_json: bool = False,
    include_validator_state: bool = True,
    wallet_name: str = DEFAULT_WALLET_NAME,
    wallet_hotkey: str = DEFAULT_WALLET_HOTKEY,
    wallet_path: str = DEFAULT_WALLET_PATH,
    target_hotkey: str | None = DEFAULT_TARGET_HOTKEY,
    network: str = DEFAULT_NETWORK,
    netuid: int = DEFAULT_NETUID,
    timeout: float = 120.0,
    validator_state_path: str = DEFAULT_VALIDATOR_STATE_PATH,
) -> int:
    from autoresearch.demo_format import (
        CYAN,
        demo_pacing,
        emit_block,
        emit_loading_state,
        run_with_spinner,
        style,
    )

    is_interactive = sys.stdout.isatty()
    line_delay, section_delay, loading_pause = demo_pacing(is_interactive)
    started_at = time.perf_counter()
    challenge = _load_probe_challenge(validator_state_path)
    if not as_json:
        emit_block(
            [
                "═══════════════════════════════════════════════════════",
                f"  {style('AUTORESEARCH NETWORK — Network Check', CYAN, bold=True)}",
                "═══════════════════════════════════════════════════════",
                "",
                style("[DISCOVERY] Inspecting the currently advertised miner endpoint", bold=True),
                f"  Wallet hotkey:      {wallet_hotkey}",
                f"  Target hotkey:      {target_hotkey or wallet_hotkey}",
                f"  Network / netuid:   {network} / {netuid}",
                "",
            ],
            line_delay=line_delay,
            section_delay=section_delay,
        )

        emit_block(
            [
                style("[PROBE] Sending a signed Dendrite request through the relay", bold=True),
                "  Request shape:      ExperimentSubmission",
                "  Probe baseline:     current validator best_train.py",
                f"  Current best bpb:   {challenge['global_best_val_bpb']:.6f}",
                "",
            ],
            line_delay=line_delay,
            section_delay=0.0,
        )
        emit_loading_state(
            total_duration=loading_pause,
            phases=[
                "wallet loaded: signed caller hotkey ready",
                "metagraph synced: target axon discovered",
                "relay path opened: public endpoint dialed",
            ],
            is_interactive=is_interactive,
        )

    payload = run_with_spinner(
        lambda: asyncio.run(
            _run_probe(
                wallet_name=wallet_name,
                wallet_hotkey=wallet_hotkey,
                wallet_path=wallet_path,
                target_hotkey=target_hotkey,
                network=network,
                netuid=netuid,
                timeout=timeout,
                baseline_train_py=challenge["baseline_train_py"],
                global_best_val_bpb=challenge["global_best_val_bpb"],
            )
        ),
        label="awaiting miner response",
        enabled=not as_json,
    )
    payload["challenge"] = {
        "global_best_val_bpb": challenge["global_best_val_bpb"],
        "best_train_path": challenge["best_train_path"],
        "metadata_path": challenge["metadata_path"],
        "baseline_train_py_len": len(challenge["baseline_train_py"]),
    }
    if include_validator_state:
        payload["validator_state"] = _load_validator_state(validator_state_path)

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    validator_state = payload.get("validator_state")
    val_bpb = payload.get("val_bpb")
    peak_vram_mb = payload.get("peak_vram_mb")
    emit_block(
        [
            f"  Target endpoint:    {payload['target_endpoint']}",
            f"  Dendrite status:    {payload['dendrite_status']} ({payload['dendrite_message']})",
            f"  Axon status:        {payload['axon_status']} ({payload['axon_message']})",
            (
                f"  Returned val_bpb:   {val_bpb:.6f}"
                if isinstance(val_bpb, (int, float))
                else "  Returned val_bpb:   <none>"
            ),
            f"  Hardware tier:      {payload['hardware_tier']}",
            f"  Elapsed wall time:  {payload['elapsed_wall_seconds']} seconds",
            (
                f"  Peak VRAM:          {peak_vram_mb:,.1f} MB"
                if isinstance(peak_vram_mb, (int, float))
                else "  Peak VRAM:          <none>"
            ),
            "",
        ],
        line_delay=line_delay,
        section_delay=section_delay,
    )
    if include_validator_state and validator_state is not None:
        emit_block(
            [
                style("[STATE] Current validator state file", bold=True),
                f"  val_bpb:            {validator_state.get('val_bpb')}",
                f"  achieved_by:        {validator_state.get('achieved_by')}",
                "",
            ],
            line_delay=line_delay,
            section_delay=section_delay,
        )

    emit_block(
        [
            "═══════════════════════════════════════════════════════",
            f"  Network check complete in {time.perf_counter() - started_at:.2f} seconds",
            "═══════════════════════════════════════════════════════",
        ],
        line_delay=line_delay,
        section_delay=0.0,
    )
    return 0


def run_live_relay_proof(**kwargs: Any) -> int:
    """Backwards-compatible alias for the older command/function name."""

    return run_network_check(**kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Operational network check for the current AutoResearch miner"
    )
    parser.add_argument("--json", action="store_true", help="Render the probe result as JSON.")
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Skip loading the validator state file and show only the signed miner probe.",
    )
    parser.add_argument("--wallet-name", default=DEFAULT_WALLET_NAME)
    parser.add_argument("--wallet-hotkey", default=DEFAULT_WALLET_HOTKEY)
    parser.add_argument("--wallet-path", default=DEFAULT_WALLET_PATH)
    parser.add_argument(
        "--target-hotkey",
        default=DEFAULT_TARGET_HOTKEY,
        help="Target miner hotkey name or SS58. Defaults to the serving `default` miner hotkey.",
    )
    parser.add_argument("--network", default=DEFAULT_NETWORK)
    parser.add_argument("--netuid", type=int, default=DEFAULT_NETUID)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--validator-state-path", default=DEFAULT_VALIDATOR_STATE_PATH)
    args = parser.parse_args(argv)
    try:
        return run_network_check(
            as_json=args.json,
            include_validator_state=not args.probe_only,
            wallet_name=args.wallet_name,
            wallet_hotkey=args.wallet_hotkey,
            wallet_path=args.wallet_path,
            target_hotkey=args.target_hotkey,
            network=args.network,
            netuid=args.netuid,
            timeout=args.timeout,
            validator_state_path=args.validator_state_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
