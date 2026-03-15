"""Wrapper entrypoint for the vendored AutoResearch prepare script."""

from __future__ import annotations

from pathlib import Path
from runpy import run_path

if __name__ == "__main__":
    run_path(
        str(Path(__file__).parent / "autoresearch" / "data" / "prepare.py"),
        run_name="__main__",
    )
