"""Package CLI entrypoint."""

from __future__ import annotations

import sys


def _usage() -> str:
    return "\n".join(
        [
            "Usage: python -m autoresearch <command>",
            "",
            "Commands:",
            "  protocol-demo       Run the scripted protocol walkthrough",
            "  validator-showcase  Run the local validator round walkthrough",
            "  network-check       Run the live signed network check against the current miner",
            "  miner-probe         Run the live signed miner probe only",
            "  demo                Alias for protocol-demo",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(_usage())
        return 0

    command, rest = args[0], args[1:]
    if command in {"demo", "protocol-demo"}:
        from autoresearch.protocol import main as protocol_main

        return protocol_main(["demo", *rest])
    if command == "validator-showcase":
        from autoresearch.validator_round_showcase import main as showcase_main

        return showcase_main(rest)
    if command in {"network-check", "live-relay-proof"}:
        from autoresearch.live_relay_proof import main as relay_main

        return relay_main(rest)
    if command == "miner-probe":
        from autoresearch.live_relay_proof import main as relay_main

        return relay_main(["--probe-only", *rest])

    print(_usage(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
