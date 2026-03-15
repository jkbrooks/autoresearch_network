"""Vendored experiment preparation helper."""

from __future__ import annotations

import argparse
import random
import time


def main(argv: list[str] | None = None) -> int:
    """Run a tiny deterministic training simulation and emit metrics."""

    parser = argparse.ArgumentParser(description="Run vendored AutoResearch preparation task.")
    parser.add_argument("--seed", type=int, default=17, help="Deterministic random seed.")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.01,
        help="Artificial duration to emulate training.",
    )
    parser.add_argument(
        "--val-bpb",
        type=float,
        default=1.01,
        help="Validation BPE value to emit.",
    )
    args = parser.parse_args(argv)

    random.seed(args.seed)
    time.sleep(max(0.0, args.sleep))

    val_bpb = args.val_bpb
    training_seconds = round(max(0.5, args.sleep * 10), 3)
    peak_vram_mb = random.uniform(2_000.0, 10_000.0)
    total_tokens_m = random.uniform(12.0, 64.0)
    num_steps = random.randint(500, 1_200)
    throughput_toks_per_sec = total_tokens_m / max(1e-3, training_seconds)
    print(f"val_bpb: {val_bpb:.6f}")
    print(f"training_seconds: {training_seconds:.3f}")
    print(f"peak_vram_mb: {peak_vram_mb:.3f}")
    print(f"total_tokens_M: {total_tokens_m:.3f}")
    print(f"num_steps: {num_steps}")
    print(f"throughput_toks_per_sec: {throughput_toks_per_sec:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
