"""Configuration helpers for the miner CLI."""

from __future__ import annotations

import argparse
import os
from types import SimpleNamespace
from typing import Any, cast

import torch


def _default_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netuid", type=int, default=1)
    parser.add_argument("--mock", action="store_true", default=False)
    parser.add_argument("--skip-health-check", action="store_true", default=False)

    parser.add_argument("--wallet.name", dest="wallet_name", default="default")
    parser.add_argument("--wallet.hotkey", dest="wallet_hotkey", default="default")
    parser.add_argument(
        "--wallet.path",
        dest="wallet_path",
        default=os.path.expanduser("~/.bittensor/wallets"),
    )

    parser.add_argument(
        "--subtensor.network",
        "--network",
        dest="subtensor_network",
        default="finney",
    )
    parser.add_argument("--subtensor.chain-endpoint", dest="subtensor_chain_endpoint", default=None)

    parser.add_argument("--logging.debug", dest="logging_debug", action="store_true", default=False)
    parser.add_argument("--logging.trace", dest="logging_trace", action="store_true", default=False)
    parser.add_argument("--logging.info", dest="logging_info", action="store_true", default=False)
    parser.add_argument(
        "--logging.logging-dir",
        dest="logging_dir",
        default=os.path.expanduser("~/.bittensor/miners"),
    )

    parser.add_argument("--axon.port", dest="axon_port", type=int, default=8091)
    parser.add_argument("--axon.ip", dest="axon_ip", default="[::]")
    parser.add_argument("--axon.external-ip", dest="axon_external_ip", default=None)
    parser.add_argument("--axon.external-port", dest="axon_external_port", type=int, default=None)
    parser.add_argument("--axon.max-workers", dest="axon_max_workers", type=int, default=10)

    parser.add_argument("--neuron.name", dest="neuron_name", default="miner")
    parser.add_argument("--neuron.device", dest="neuron_device", default=_default_device())
    parser.add_argument("--neuron.epoch-length", dest="neuron_epoch_length", type=int, default=100)

    parser.add_argument(
        "--blacklist.allow-non-registered",
        dest="blacklist_allow_non_registered",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--blacklist.force-validator-permit",
        dest="blacklist_force_validator_permit",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--blacklist.min-stake",
        dest="blacklist_min_stake",
        type=float,
        default=1000.0,
    )

    parser.add_argument("--mutation-provider", dest="mutation_provider", default="none")
    parser.add_argument("--mutation-model", dest="mutation_model", default=None)
    parser.add_argument("--mutation-base-url", dest="mutation_base_url", default=None)
    parser.add_argument("--hardware-tier", dest="hardware_tier", default=None)

    return parser


def build_config(args: list[str] | None = None) -> SimpleNamespace:
    namespace = build_parser().parse_args(args=args)
    config = SimpleNamespace(
        netuid=namespace.netuid,
        mock=namespace.mock,
        skip_health_check=namespace.skip_health_check,
        wallet=SimpleNamespace(
            name=namespace.wallet_name,
            hotkey=namespace.wallet_hotkey,
            path=namespace.wallet_path,
        ),
        subtensor=SimpleNamespace(
            network=namespace.subtensor_network,
            chain_endpoint=namespace.subtensor_chain_endpoint or namespace.subtensor_network,
        ),
        logging=SimpleNamespace(
            debug=namespace.logging_debug,
            trace=namespace.logging_trace,
            info=namespace.logging_info,
            logging_dir=namespace.logging_dir,
        ),
        axon=SimpleNamespace(
            port=namespace.axon_port,
            ip=namespace.axon_ip,
            external_ip=namespace.axon_external_ip,
            external_port=namespace.axon_external_port,
            max_workers=namespace.axon_max_workers,
        ),
        neuron=SimpleNamespace(
            name=namespace.neuron_name,
            device=namespace.neuron_device,
            epoch_length=namespace.neuron_epoch_length,
            full_path="",
        ),
        blacklist=SimpleNamespace(
            allow_non_registered=namespace.blacklist_allow_non_registered,
            force_validator_permit=namespace.blacklist_force_validator_permit,
            min_stake=namespace.blacklist_min_stake,
        ),
        mutation_provider=namespace.mutation_provider,
        mutation_model=namespace.mutation_model,
        mutation_base_url=namespace.mutation_base_url,
        hardware_tier=namespace.hardware_tier,
    )
    return cast(SimpleNamespace, check_config(config))


def check_config(config: Any) -> Any:
    full_path = os.path.expanduser(
        os.path.join(
            config.logging.logging_dir,
            config.wallet.name,
            config.wallet.hotkey,
            f"netuid{config.netuid}",
            config.neuron.name,
        )
    )
    os.makedirs(full_path, exist_ok=True)
    config.neuron.full_path = full_path
    return config
