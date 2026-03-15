"""Tests for mutation strategy implementations."""

from __future__ import annotations

from typing import Any

import pytest

from autoresearch.mutations import LLMMutationStrategy, StructuredMutationStrategy
from tests.fixtures.reference_train import REFERENCE_TRAIN_PY


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
    assert strategy.mutations_remaining == 2
    first = strategy.mutate(REFERENCE_TRAIN_PY)
    assert strategy.mutations_remaining == 1
    assert first != REFERENCE_TRAIN_PY
    second = strategy.mutate(REFERENCE_TRAIN_PY)
    assert strategy.mutations_remaining == 0
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


class _TrackingLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.called = False
        self.received_prompt = None

    def chat(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("unexpected chat path")

    def __call__(self, *args: Any, **_kwargs: Any) -> None:
        raise AssertionError("unexpected direct invocation")

    def completions(self) -> None:
        raise AssertionError("unexpected path")

    def create(self, *, model: str, **_: Any) -> Any:  # pragma: no cover
        raise AssertionError("unexpected path")

    class _Response:
        def __init__(self, content: str) -> None:
            self.choices = [
                type("Choice", (), {"message": type("Message", (), {"content": content})})
            ]

    def __init_response(self, *args: Any, **kwargs: Any) -> _TrackingLLMClient._Response:
        self.called = True
        self.received_prompt = args[0] if args else kwargs.get("prompt")
        return self._Response(self.response)


def test_llm_strategy_extracts_python_code_block(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_mutate_alias_delegates_to_propose() -> None:
    alias_strategy = StructuredMutationStrategy(
        [("append_comment", _append_comment)], random_seed=0
    )
    direct_strategy = StructuredMutationStrategy(
        [("append_comment", _append_comment)], random_seed=0
    )

    assert alias_strategy.mutate(REFERENCE_TRAIN_PY) == direct_strategy.propose(REFERENCE_TRAIN_PY)


def test_llm_strategy_fallback_on_invalid_python(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_llm_strategy_does_not_log_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    strategy = LLMMutationStrategy(provider="openai", api_key="super-secret-key")

    monkeypatch.setattr(
        "autoresearch.mutations.os.getenv",
        lambda key: "super-secret-key" if key == "OPENAI_API_KEY" else None,
    )

    assert "super-secret-key" not in repr(strategy)
