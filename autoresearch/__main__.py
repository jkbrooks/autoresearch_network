"""Package CLI entrypoint."""

from __future__ import annotations

import sys

from autoresearch.protocol import main as protocol_main


def main() -> int:
    return protocol_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
