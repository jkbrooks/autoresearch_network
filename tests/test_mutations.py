from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from autoresearch.mutations import LLMMutationStrategy, StructuredMutationStrategy

REFERENCE_TRAIN = Path(__file__).with_name("fixtures").joinpath("reference_train.py").read_text(
    encoding="utf-8"
)


def test_depth_increase_mutation() -> None:
    strategy = StructuredMutationStrategy()
    mutated = strategy._depth_increase(REFERENCE_TRAIN)
    assert "n_layer: int = 14" in mutated


def test_depth_decrease_mutation() -> None:
    strategy = StructuredMutationStrategy()
    mutated = strategy._depth_decrease(REFERENCE_TRAIN)
    assert "n_layer: int = 10" in mutated


def test_lr_scale_mutations() -> None:
    strategy = StructuredMutationStrategy()
    up = strategy._lr_scale_up(REFERENCE_TRAIN)
    down = strategy._lr_scale_down(REFERENCE_TRAIN)
    assert "EMBEDDING_LR = 0.900000" in up
    assert "EMBEDDING_LR = 0.420000" in down


def test_window_pattern_mutation() -> None:
    strategy = StructuredMutationStrategy()
    mutated = strategy._window_to_simple(REFERENCE_TRAIN)
    assert 'window_pattern: str = "L"' in mutated


def test_batch_size_mutation() -> None:
    strategy = StructuredMutationStrategy()
    doubled = strategy._batch_double(REFERENCE_TRAIN)
    halved = strategy._batch_halve(REFERENCE_TRAIN)
    assert "TOTAL_BATCH_SIZE = 1048576" in doubled
    assert "TOTAL_BATCH_SIZE = 262144" in halved


def test_embd_mutation() -> None:
    strategy = StructuredMutationStrategy()
    increased = strategy._embd_increase(REFERENCE_TRAIN)
    decreased = strategy._embd_decrease(REFERENCE_TRAIN)
    assert "n_embd: int = 896" in increased
    assert "n_embd: int = 640" in decreased


def test_all_mutations_produce_valid_python() -> None:
    strategy = StructuredMutationStrategy()
    for _, mutation in strategy._mutations:
        ast.parse(mutation(REFERENCE_TRAIN))


def test_mutations_cycle_without_repeating() -> None:
    strategy = StructuredMutationStrategy(seed=1)
    for _ in range(len(strategy._order)):
        strategy.propose(REFERENCE_TRAIN)
    assert len(strategy.tried) == len(strategy._order)


def test_mutations_exhausted_returns_original() -> None:
    strategy = StructuredMutationStrategy(seed=1)
    for _ in range(len(strategy._order)):
        strategy.propose(REFERENCE_TRAIN)
    assert strategy.propose(REFERENCE_TRAIN) == REFERENCE_TRAIN


def test_deterministic_with_seed() -> None:
    left = StructuredMutationStrategy(seed=3)
    right = StructuredMutationStrategy(seed=3)
    left_sequence = [left.propose(REFERENCE_TRAIN) for _ in range(3)]
    right_sequence = [right.propose(REFERENCE_TRAIN) for _ in range(3)]
    assert left_sequence == right_sequence


def test_mutations_remaining_decrements() -> None:
    strategy = StructuredMutationStrategy(seed=1)
    before = strategy.mutations_remaining
    strategy.propose(REFERENCE_TRAIN)
    assert strategy.mutations_remaining == before - 1


def test_llm_strategy_parses_python_code_block(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(
        strategy,
        "_request_completion",
        lambda _: "```python\nprint('hello')\n```",
    )
    assert strategy.propose(REFERENCE_TRAIN) == "print('hello')"


def test_llm_strategy_parses_untagged_code_block(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(strategy, "_request_completion", lambda _: "```\nprint('x')\n```")
    assert strategy.propose(REFERENCE_TRAIN) == "print('x')"


def test_llm_strategy_no_code_block_returns_original(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(strategy, "_request_completion", lambda _: "plain text")
    assert strategy.propose(REFERENCE_TRAIN) == REFERENCE_TRAIN


def test_llm_strategy_invalid_python_returns_original(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(strategy, "_request_completion", lambda _: "```python\nif:\n```")
    assert strategy.propose(REFERENCE_TRAIN) == REFERENCE_TRAIN


def test_llm_strategy_api_timeout_returns_original(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(
        strategy,
        "_request_completion",
        lambda _: (_ for _ in ()).throw(TimeoutError()),
    )
    assert strategy.propose(REFERENCE_TRAIN) == REFERENCE_TRAIN


def test_llm_strategy_api_auth_error_returns_original(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(
        strategy,
        "_request_completion",
        lambda _: (_ for _ in ()).throw(PermissionError()),
    )
    assert strategy.propose(REFERENCE_TRAIN) == REFERENCE_TRAIN


def test_llm_strategy_api_key_not_in_logs(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="super-secret")
    monkeypatch.setattr(
        strategy,
        "_request_completion",
        lambda _: (_ for _ in ()).throw(RuntimeError()),
    )
    with caplog.at_level(logging.WARNING):
        strategy.propose(REFERENCE_TRAIN)
    assert "super-secret" not in caplog.text


def test_llm_strategy_missing_key_falls_back() -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key=None)
    assert strategy.propose(REFERENCE_TRAIN) == REFERENCE_TRAIN
