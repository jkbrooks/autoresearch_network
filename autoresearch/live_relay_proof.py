"""Live proof against the current relay-backed AutoResearch miner."""

from __future__ import annotations

import argparse
import asyncio
import json
import textwrap
import time
import warnings
from pathlib import Path
from typing import Any

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

PLAUSIBLE_BASELINE = textwrap.dedent(
    """\
    import math

    class GPTConfig:
        n_layer: int = 12
        n_embd: int = 768
        window_pattern: str = "SSSL"

    UNEMBEDDING_LR = 0.004000
    EMBEDDING_LR = 0.600000
    SCALAR_LR = 0.500000
    MATRIX_LR = 0.020000
    TOTAL_BATCH_SIZE = 2**19

    _ = math.sqrt(16)
    print("---")
    print("val_bpb:          0.997900")
    print("training_seconds: 300.0")
    print("total_seconds:    301.2")
    print("peak_vram_mb:     24000.0")
    print("mfu_percent:      39.80")
    print("total_tokens_M:   60.0")
    print("num_steps:        953")
    print("num_params_M:     50.3")
    print("depth:            8")
    """
).strip()


async def _run_probe(
    *,
    wallet_name: str,
    wallet_hotkey: str,
    wallet_path: str,
    target_hotkey: str | None,
    network: str,
    netuid: int,
    timeout: float,
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
        task_id="live_relay_proof",
        baseline_train_py=PLAUSIBLE_BASELINE,
        global_best_val_bpb=1.1,
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
    return json.loads(state_path.read_text(encoding="utf-8"))


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


def run_live_relay_proof(
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
    from autoresearch.demo_format import CYAN, demo_pacing, emit_block, emit_loading_state, style

    is_interactive = True
    line_delay, section_delay, loading_pause = demo_pacing(is_interactive)
    started_at = time.perf_counter()
    if not as_json:
        emit_block(
            [
                "═══════════════════════════════════════════════════════",
                f"  {style('AUTORESEARCH NETWORK — Live Relay Proof', CYAN, bold=True)}",
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
                "  Probe baseline:     plausible large-tier metrics",
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
                "miner response returned: signed payload accepted",
            ],
            is_interactive=is_interactive,
        )

    payload = asyncio.run(
        _run_probe(
            wallet_name=wallet_name,
            wallet_hotkey=wallet_hotkey,
            wallet_path=wallet_path,
            target_hotkey=target_hotkey,
            network=network,
            netuid=netuid,
            timeout=timeout,
        )
    )
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
            f"  Live proof complete in {time.perf_counter() - started_at:.2f} seconds",
            "═══════════════════════════════════════════════════════",
        ],
        line_delay=line_delay,
        section_delay=0.0,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live relay proof for the current AutoResearch miner"
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
    return run_live_relay_proof(
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


if __name__ == "__main__":
    raise SystemExit(main())
