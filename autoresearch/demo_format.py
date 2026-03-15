"""Shared terminal presentation helpers for AutoResearch demos and showcases."""

from __future__ import annotations

import sys
import time
from collections.abc import Sequence

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"


def style(text: str, color: str = "", *, bold: bool = False) -> str:
    prefix = f"{BOLD if bold else ''}{color}"
    return f"{prefix}{text}{RESET}" if prefix else text


def format_elapsed(elapsed_seconds: float) -> str:
    if elapsed_seconds < 1:
        return f"{elapsed_seconds:.3f} seconds"
    return f"{elapsed_seconds:.2f} seconds"


def demo_pacing(is_interactive: bool | None = None) -> tuple[float, float, float]:
    active = sys.stdout.isatty() if is_interactive is None else is_interactive
    if active:
        return 0.2, 0.5, 10.0
    return 0.0, 0.0, 0.0


def emit_block(lines: Sequence[str], *, line_delay: float, section_delay: float) -> None:
    for line in lines:
        print(line, flush=True)
        time.sleep(line_delay)
    time.sleep(section_delay)


def progress_bar(progress: float, *, width: int = 20) -> str:
    filled = round(progress * width)
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def emit_loading_state(
    *,
    total_duration: float,
    phases: Sequence[str],
    is_interactive: bool | None = None,
) -> None:
    active = sys.stdout.isatty() if is_interactive is None else is_interactive
    if not active or not phases:
        return

    step_duration = max(0.0, total_duration / len(phases))
    for index, phase in enumerate(phases, start=1):
        progress = index / len(phases)
        print(
            "  Progress:         "
            f"{style(progress_bar(progress), CYAN, bold=True)} "
            f"{int(progress * 100):>3}%  {phase}",
            flush=True,
        )
        time.sleep(step_duration)
