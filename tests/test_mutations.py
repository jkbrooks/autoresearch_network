from __future__ import annotations

import ast
import logging
from typing import Any

import pytest

from autoresearch.mutations import LLMMutationStrategy, StructuredMutationStrategy
from tests.fixtures.reference_train import REFERENCE_TRAIN_PY


def test_depth_increase_mutation() -> None:
    strategy = StructuredMutationStrategy()
    mutated = strategy._depth_increase(REFERENCE_TRAIN_PY)
    assert "n_layer: int = 14" in mutated


def test_depth_decrease_mutation() -> None:
    strategy = StructuredMutationStrategy()
    mutated = strategy._depth_decrease(REFERENCE_TRAIN_PY)
    assert "n_layer: int = 10" in mutated


def test_lr_scale_mutations() -> None:
    strategy = StructuredMutationStrategy()
    up = strategy._lr_scale_up(REFERENCE_TRAIN_PY)
    down = strategy._lr_scale_down(REFERENCE_TRAIN_PY)
    assert "EMBEDDING_LR = 0.900000" in up
    assert "EMBEDDING_LR = 0.420000" in down


def test_window_pattern_mutation() -> None:
    strategy = StructuredMutationStrategy()
    mutated = strategy._window_to_simple(REFERENCE_TRAIN_PY)
    assert 'window_pattern: str = "L"' in mutated


def test_batch_size_mutation() -> None:
    strategy = StructuredMutationStrategy()
    doubled = strategy._batch_double(REFERENCE_TRAIN_PY)
    halved = strategy._batch_halve(REFERENCE_TRAIN_PY)
    assert "TOTAL_BATCH_SIZE = 1048576" in doubled
    assert "TOTAL_BATCH_SIZE = 262144" in halved


def test_embd_mutation() -> None:
    strategy = StructuredMutationStrategy()
    increased = strategy._embd_increase(REFERENCE_TRAIN_PY)
    decreased = strategy._embd_decrease(REFERENCE_TRAIN_PY)
    assert "n_embd: int = 896" in increased
    assert "n_embd: int = 640" in decreased


def test_all_builtin_mutations_produce_valid_python() -> None:
    strategy = StructuredMutationStrategy()
    for name in strategy.mutation_names:
        ast.parse(strategy._lookup[name](REFERENCE_TRAIN_PY))


def test_builtin_mutations_cycle_without_repeating() -> None:
    strategy = StructuredMutationStrategy(seed=1)
    for _ in range(len(strategy.mutation_names)):
        strategy.propose(REFERENCE_TRAIN_PY)
    assert len(strategy.tried) == len(strategy.mutation_names)


def test_builtin_mutations_exhausted_returns_original() -> None:
    strategy = StructuredMutationStrategy(seed=1)
    for _ in range(len(strategy.mutation_names)):
        strategy.propose(REFERENCE_TRAIN_PY)
    assert strategy.propose(REFERENCE_TRAIN_PY) == REFERENCE_TRAIN_PY


def test_builtin_mutations_are_deterministic_with_seed() -> None:
    left = StructuredMutationStrategy(seed=3)
    right = StructuredMutationStrategy(seed=3)
    left_sequence = [left.propose(REFERENCE_TRAIN_PY) for _ in range(3)]
    right_sequence = [right.propose(REFERENCE_TRAIN_PY) for _ in range(3)]
    assert left_sequence == right_sequence


def test_mutations_remaining_decrements() -> None:
    strategy = StructuredMutationStrategy(seed=1)
    before = strategy.mutations_remaining
    strategy.propose(REFERENCE_TRAIN_PY)
    assert strategy.mutations_remaining == before - 1


def _append_comment(source: str) -> str:
    return source + "\n# mutation: append_comment\n"


def _bad_mutation(_source: str) -> str:
    return "def invalid_syntax("


def _prepend_counter(source: str) -> str:
    return "# mutation: prepend_counter\n" + source


def _append_constant(source: str) -> str:
    return source + "\nMUTATION_FLAG = 42\n"


def test_structured_strategy_uses_deterministic_shuffled_order() -> None:
    mutations = [
        ("prepend_counter", _prepend_counter),
        ("append_comment", _append_comment),
        ("append_constant", _append_constant),
    ]
    first = StructuredMutationStrategy(mutations, random_seed=4)
    second = StructuredMutationStrategy(mutations, random_seed=4)

    first_mutations = [first.mutate(REFERENCE_TRAIN_PY) for _ in range(first.mutations_remaining)]
    second_mutations = [
        second.mutate(REFERENCE_TRAIN_PY) for _ in range(second.mutations_remaining)
    ]
    assert first_mutations == second_mutations


def test_structured_strategy_rejects_duplicate_names_and_tracks_remaining() -> None:
    strategy = StructuredMutationStrategy(
        [
            ("append_comment", _append_comment),
            ("append_comment", _append_constant),
            ("append_constant", _append_constant),
        ],
        random_seed=7,
    )

    assert strategy.mutations_remaining == 2
    assert "append_comment" in strategy.mutation_names
    first = strategy.mutate(REFERENCE_TRAIN_PY)
    assert strategy.mutations_remaining == 1
    second = strategy.mutate(REFERENCE_TRAIN_PY)
    assert strategy.mutations_remaining == 0
    assert first != REFERENCE_TRAIN_PY
    assert second != REFERENCE_TRAIN_PY
    assert first != second


def test_structured_strategy_skips_invalid_ast_mutation_and_raises_on_exhaustion() -> None:
    strategy = StructuredMutationStrategy(
        [
            ("bad", _bad_mutation),
            ("append", _append_constant),
            ("comment", _append_comment),
        ],
        random_seed=19,
    )

    generated = []
    while strategy.mutations_remaining:
        try:
            generated.append(strategy.mutate(REFERENCE_TRAIN_PY))
        except StopIteration:
            break

    assert len(generated) == 2
    assert strategy.mutations_remaining == 0
    with pytest.raises(StopIteration):
        strategy.mutate(REFERENCE_TRAIN_PY)


def test_mutate_alias_delegates_to_propose_for_llm_style_usage() -> None:
    alias_strategy = StructuredMutationStrategy(
        [("append_comment", _append_comment)], random_seed=0
    )
    direct_strategy = StructuredMutationStrategy(
        [("append_comment", _append_comment)], random_seed=0
    )
    assert alias_strategy.mutate(REFERENCE_TRAIN_PY) == direct_strategy.propose(REFERENCE_TRAIN_PY)


def test_llm_strategy_parses_python_code_block(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(
        strategy,
        "_request_completion",
        lambda *_: "```python\nprint('hello')\n```",
    )
    assert strategy.propose(REFERENCE_TRAIN_PY) == "print('hello')"


def test_llm_strategy_parses_untagged_code_block(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(strategy, "_request_completion", lambda *_: "```\nprint('x')\n```")
    assert strategy.propose(REFERENCE_TRAIN_PY) == "print('x')"


def test_llm_strategy_no_code_block_returns_original(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(strategy, "_request_completion", lambda *_: "plain text")
    assert strategy.propose(REFERENCE_TRAIN_PY) == REFERENCE_TRAIN_PY


def test_llm_strategy_invalid_python_returns_original(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(strategy, "_request_completion", lambda *_: "```python\nif:\n```")
    assert strategy.propose(REFERENCE_TRAIN_PY) == REFERENCE_TRAIN_PY


def test_llm_strategy_api_timeout_returns_original(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(
        strategy,
        "_request_completion",
        lambda *_: (_ for _ in ()).throw(TimeoutError()),
    )
    assert strategy.propose(REFERENCE_TRAIN_PY) == REFERENCE_TRAIN_PY


def test_llm_strategy_api_auth_error_returns_original(monkeypatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="secret")
    monkeypatch.setattr(
        strategy,
        "_request_completion",
        lambda *_: (_ for _ in ()).throw(PermissionError()),
    )
    assert strategy.propose(REFERENCE_TRAIN_PY) == REFERENCE_TRAIN_PY


def test_llm_strategy_api_key_not_in_logs(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="super-secret")
    monkeypatch.setattr(
        strategy,
        "_request_completion",
        lambda *_: (_ for _ in ()).throw(RuntimeError()),
    )
    with caplog.at_level(logging.WARNING):
        strategy.propose(REFERENCE_TRAIN_PY)
    assert "super-secret" not in caplog.text


def test_llm_strategy_missing_key_falls_back() -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key=None)
    assert strategy.propose(REFERENCE_TRAIN_PY) == REFERENCE_TRAIN_PY


def test_llm_strategy_extracts_python_code_block_via_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = REFERENCE_TRAIN_PY
    strategy = LLMMutationStrategy(provider="openai")

    class _OpenAIStub:
        class chat:
            class completions:
                @staticmethod
                def create(*_args: Any, **_kwargs: Any) -> Any:
                    return type(
                        "Resp",
                        (),
                        {
                            "choices": [
                                type(
                                    "Choice",
                                    (),
                                    {
                                        "message": type(
                                            "Message", (), {"content": "```python\nX=1\n```"}
                                        )
                                    },
                                )
                            ],
                        },
                    )()

    monkeypatch.setattr(
        "autoresearch.mutations.openai",
        type("openai", (), {"OpenAI": lambda api_key: _OpenAIStub()}),
    )
    monkeypatch.setattr(
        "autoresearch.mutations.os.getenv",
        lambda key: "test-key" if key == "OPENAI_API_KEY" else None,
    )
    assert strategy.mutate(source) == "X=1"


def test_llm_strategy_fallback_on_invalid_python_from_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = REFERENCE_TRAIN_PY
    strategy = LLMMutationStrategy(provider="openai")

    class _OpenAIStub:
        class chat:
            class completions:
                @staticmethod
                def create(*_args: Any, **_kwargs: Any) -> Any:
                    return type(
                        "Resp",
                        (),
                        {
                            "choices": [
                                type(
                                    "Choice",
                                    (),
                                    {
                                        "message": type(
                                            "Message", (), {"content": "```python\ndef invalid("}
                                        )
                                    },
                                )
                            ],
                        },
                    )()

    monkeypatch.setattr(
        "autoresearch.mutations.openai",
        type("openai", (), {"OpenAI": lambda api_key: _OpenAIStub()}),
    )
    monkeypatch.setattr(
        "autoresearch.mutations.os.getenv",
        lambda key: "test-key" if key == "OPENAI_API_KEY" else None,
    )
    assert strategy.mutate(source) == source


def test_llm_strategy_fallback_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    source = REFERENCE_TRAIN_PY
    strategy = LLMMutationStrategy(provider="openai")
    monkeypatch.setattr("autoresearch.mutations.os.getenv", lambda key: None)
    assert strategy.mutate(source) == source


def test_llm_strategy_repr_does_not_expose_api_key() -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="super-secret-key")
    assert "super-secret-key" not in repr(strategy)
