"""Validator EMA/stat helpers for per-miner tracking and leaderboard output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class MinerStats:
    """Per-miner leaderboard and participation counters."""

    hotkey: str
    uid: int
    total_experiments: int = 0
    total_improvements: int = 0
    best_val_bpb: float = float("inf")
    last_seen: str = ""


def ensure_miner_stats_entry(
    miner_stats: dict[str, MinerStats],
    *,
    hotkey: str,
    uid: int,
) -> MinerStats:
    """Get or create a stable stats entry for a miner hotkey."""

    stats = miner_stats.get(hotkey)
    if stats is None:
        stats = MinerStats(hotkey=hotkey, uid=uid)
        miner_stats[hotkey] = stats
    else:
        stats.uid = uid
    return stats


def update_miner_stats(
    miner_stats: dict[str, MinerStats],
    *,
    responses: list[Any],
    miner_uids: list[int],
    metagraph: Any,
    current_best_bpb: float,
    observed_at: str | None = None,
) -> dict[str, MinerStats]:
    """Update per-miner counters from a batch of validator responses."""

    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    for index, response in enumerate(responses):
        uid = int(miner_uids[index])
        hotkey = str(metagraph.hotkeys[uid])
        val_bpb = getattr(response, "val_bpb", None)
        if val_bpb is None:
            continue

        stats = ensure_miner_stats_entry(miner_stats, hotkey=hotkey, uid=uid)
        stats.total_experiments += 1
        if float(val_bpb) < current_best_bpb:
            stats.total_improvements += 1
        if float(val_bpb) < stats.best_val_bpb:
            stats.best_val_bpb = float(val_bpb)
        stats.last_seen = timestamp
    return miner_stats


def format_leaderboard(
    miner_stats: dict[str, MinerStats],
    *,
    top_n: int = 5,
) -> list[str]:
    """Render leaderboard lines ordered by improvements, then experiments, then hotkey."""

    ranked = sorted(
        miner_stats.values(),
        key=lambda item: (-item.total_improvements, -item.total_experiments, item.hotkey),
    )
    lines: list[str] = []
    for index, stats in enumerate(ranked[:top_n], start=1):
        lines.append(
            f"{index}. {stats.hotkey} | improvements: {stats.total_improvements} | "
            f"experiments: {stats.total_experiments} | best_bpb: {stats.best_val_bpb:.4f}"
        )
    return lines
