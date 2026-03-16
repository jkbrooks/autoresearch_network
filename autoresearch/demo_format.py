"""Shared terminal presentation helpers for AutoResearch demos and showcases."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Sequence
from threading import Event, Thread
from typing import TypeVar

T = TypeVar("T")

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


def run_with_spinner(
    fn: Callable[[], T],
    *,
    label: str,
    interval: float = 0.12,
    enabled: bool = True,
    show_elapsed: bool = True,
) -> T:
    if not enabled:
        return fn()

    stop_event = Event()
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    started_at = time.perf_counter()
    last_render_width = 0

    def _spin() -> None:
        nonlocal last_render_width
        index = 0
        while not stop_event.is_set():
            frame = frames[index % len(frames)]
            elapsed_suffix = ""
            if show_elapsed:
                elapsed_seconds = int(time.perf_counter() - started_at)
                elapsed_suffix = f" ({elapsed_seconds}s elapsed)"
            rendered = f"  Waiting:          {frame} {label}{elapsed_suffix}"
            last_render_width = max(last_render_width, len(rendered))
            print(f"\r{rendered.ljust(last_render_width)}", end="", flush=True)
            index += 1
            time.sleep(interval)
        print("\r" + " " * last_render_width + "\r", end="", flush=True)

    spinner = Thread(target=_spin, daemon=True)
    spinner.start()
    try:
        return fn()
    finally:
        stop_event.set()
        spinner.join(timeout=1)
