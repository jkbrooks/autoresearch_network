"""Validator-side forward loop and demo helpers."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray

from autoresearch.constants import HardwareTier
from autoresearch.mock import MockSubmissionFactory
from autoresearch.protocol import ExperimentSubmission
from autoresearch.validator.guards import check_guards
from autoresearch.validator.replay import maybe_replay_submission, update_replay_stats
from autoresearch.validator.reward import get_rewards
from autoresearch.validator.stats import format_leaderboard, update_miner_stats

LOGGER = logging.getLogger(__name__)
DEFAULT_BASELINE_VAL_BPB = 1.1


def build_demo_submission() -> ExperimentSubmission:
    """Create the canonical demo submission used by the package CLI."""

    factory = MockSubmissionFactory(seed=42)
    return factory.make_submission(
        baseline_val_bpb=0.9979,
        tier=HardwareTier.LARGE,
        improvement=0.0037,
        task_id="round_20260315_001",
    )


def _append_log(validator: Any, message: str, *, level: int = logging.INFO) -> None:
    messages = getattr(validator, "log_messages", None)
    if messages is None:
        messages = []
        validator.log_messages = messages
    messages.append(message)
    LOGGER.log(level, message)


async def forward(self: Any) -> NDArray[np.float64]:
    """Run one validator tempo using the local mockable runtime surfaces."""

    self.log_messages = []
    baseline_best = (
        float(self.tracker.val_bpb)
        if np.isfinite(self.tracker.val_bpb)
        else DEFAULT_BASELINE_VAL_BPB
    )
    challenge = ExperimentSubmission(
        task_id=f"round_{self.step:06d}_{uuid4().hex[:8]}",
        baseline_train_py=self.tracker.train_py,
        global_best_val_bpb=baseline_best,
    )

    metagraph_uids = (
        self.metagraph.uids.tolist()
        if hasattr(self.metagraph.uids, "tolist")
        else list(self.metagraph.uids)
    )
    miner_uids = [int(uid) for uid in metagraph_uids if self.metagraph.axons[int(uid)].is_serving]
    if not miner_uids:
        LOGGER.warning("No active miners found this step.")
        _append_log(
            self,
            f"[VALIDATOR] Step {self.step} | Queried 0 miners | 0 responded",
            level=logging.WARNING,
        )
        self.last_round = {
            "challenge": challenge,
            "responses": [],
            "miner_uids": [],
            "stage1_scores": np.asarray([], dtype=float),
            "final_scores": np.asarray([], dtype=float),
        }
        self.step += 1
        if self.step % 10 == 0:
            self.save_state()
        return np.asarray([], dtype=float)

    responses = await self.dendrite(
        axons=[self.metagraph.axons[uid] for uid in miner_uids],
        synapse=challenge,
        deserialize=False,
        timeout=660,
    )

    stage1_scores = get_rewards(list(responses), baseline_best)
    final_scores: list[float] = []
    recent_submissions: list[str] = []
    replay_results: dict[str, object] = {}
    for uid, response, stage1_score in zip(miner_uids, responses, stage1_scores, strict=True):
        hotkey = str(self.metagraph.hotkeys[uid])
        multiplier = check_guards(
            response,
            self.submission_hashes,
            recent_submissions,
            submitter_hotkey=hotkey,
        )
        if self.replay_enabled and self.replay_mode == "shadow" and self.replay_runner is not None:
            replay_result = maybe_replay_submission(
                submission=response,
                miner_uid=uid,
                step=self.step,
                sampler=self.replay_sampler,
                runner=self.replay_runner,
                tolerance=self.replay_tolerance,
            )
            replay_results[hotkey] = replay_result
            update_replay_stats(self.replay_stats, hotkey=hotkey, replay_result=replay_result)
            if replay_result.selected and replay_result.executed:
                LOGGER.info(
                    "[REPLAY SHADOW] uid=%s hotkey=%s passed=%s reason=%s diff=%s",
                    uid,
                    hotkey,
                    replay_result.passed,
                    replay_result.reason,
                    replay_result.relative_diff,
                )
        final_scores.append(float(stage1_score) * float(multiplier))
        train_py = getattr(response, "train_py", None)
        if train_py and train_py not in recent_submissions:
            recent_submissions.append(train_py)

    final_scores_array = np.asarray(final_scores, dtype=float)
    for uid, response in zip(miner_uids, responses, strict=True):
        val_bpb = getattr(response, "val_bpb", None)
        train_py = getattr(response, "train_py", None)
        if val_bpb is None or not train_py:
            continue
        if float(val_bpb) < self.tracker.val_bpb:
            self.tracker.update(float(val_bpb), train_py, str(self.metagraph.hotkeys[uid]))

    self.update_scores(final_scores_array, miner_uids)
    update_miner_stats(
        self.miner_stats,
        responses=list(responses),
        miner_uids=list(miner_uids),
        metagraph=self.metagraph,
        current_best_bpb=baseline_best,
    )
    self.set_weights()

    responding = sum(1 for response in responses if getattr(response, "val_bpb", None) is not None)
    best_this_round = min(
        (
            float(response.val_bpb)
            for response in responses
            if getattr(response, "val_bpb", None) is not None
        ),
        default=None,
    )
    _append_log(
        self,
        f"[VALIDATOR] Step {self.step} | Queried {len(miner_uids)} miners | "
        f"{responding} responded | Best this round: {best_this_round} | "
        f"Global best: {self.tracker.val_bpb} (by {self.tracker.achieved_by})",
    )
    _append_log(self, f"[VALIDATOR] Scores: {np.round(final_scores_array, 3).tolist()}")

    self.last_round = {
        "challenge": challenge,
        "responses": list(responses),
        "miner_uids": list(miner_uids),
        "stage1_scores": np.asarray(stage1_scores, dtype=float),
        "final_scores": final_scores_array,
        "replay_results": replay_results,
    }
    self.step += 1
    if self.step % 10 == 0:
        self.save_state()
        for line in format_leaderboard(self.miner_stats, top_n=5):
            _append_log(self, f"[LEADERBOARD] {line}")
    return final_scores_array
