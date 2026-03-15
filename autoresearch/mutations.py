"""Mutation strategy helpers for generating valid Python train script variants."""

from __future__ import annotations

import ast
import os
import random
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

import anthropic
import openai

MutationFunction = Callable[[str], str]


def _validate_python_source(source: str) -> None:
    ast.parse(source)


def _extract_code_block(text: str) -> str:
    """Extract the first fenced code block from LLM text.

    If a language-tagged block exists, prefer it; otherwise return the first block.
    """

    pattern = re.compile(
        r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<body>.*?)\n```",
        flags=re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return text.strip()
    preferred = [
        match for match in matches if match.group("lang").strip().lower() in {"python", "py"}
    ]
    selected = preferred[0] if preferred else matches[0]
    return selected.group("body").strip()


@dataclass(frozen=True)
class Mutation:
    """Simple container for a named mutation function."""

    name: str
    mutate_fn: MutationFunction


class MutationStrategy(ABC):
    """Abstract base for strategies that return one mutated version at a time."""

    @property
    @abstractmethod
    def mutations_remaining(self) -> int:
        """Number of potential mutations still available."""

    @abstractmethod
    def propose(self, source_code: str) -> str:
        """Return the next mutation output."""

    def mutate(self, source_code: str) -> str:
        """Backward-compatible alias for the historical mutation API."""

        return self.propose(source_code)


class StructuredMutationStrategy(MutationStrategy):
    """Apply a deterministic, shuffled list of pure Python transformations."""

    def __init__(
        self,
        mutations: Iterable[tuple[str, MutationFunction] | MutationFunction]
        | Mapping[str, MutationFunction],
        *,
        random_seed: int = 0,
    ) -> None:
        self._mutations = self._prepare_mutations(mutations, random_seed=random_seed)
        self._index = 0

    @property
    def mutation_names(self) -> tuple[str, ...]:
        """All mutation names in this strategy after ordering and deduplication."""

        return tuple(m.name for m in self._mutations)

    @staticmethod
    def _coerce_mutations(
        mutations: Iterable[tuple[str, MutationFunction] | MutationFunction]
        | Mapping[str, MutationFunction],
    ) -> list[tuple[str, MutationFunction]]:
        if isinstance(mutations, Mapping):
            return [(name, fn) for name, fn in mutations.items()]
        normalized: list[tuple[str, MutationFunction]] = []
        for mutation in mutations:
            if isinstance(mutation, tuple):
                if len(mutation) != 2:
                    raise ValueError("Mutation tuples must be (name, fn)")
                name, fn = mutation
            else:
                name = getattr(mutation, "__name__", "mutation")
                fn = mutation
            normalized.append((str(name), fn))
        return normalized

    @staticmethod
    def _dedupe_mutations(
        mutations: list[tuple[str, MutationFunction]],
    ) -> list[tuple[str, MutationFunction]]:
        seen: set[str] = set()
        deduped: list[tuple[str, MutationFunction]] = []
        for name, fn in mutations:
            if name in seen:
                continue
            seen.add(name)
            deduped.append((name, fn))
        return deduped

    @classmethod
    def _prepare_mutations(
        cls,
        mutations: Iterable[tuple[str, MutationFunction] | MutationFunction]
        | Mapping[str, MutationFunction],
        *,
        random_seed: int,
    ) -> tuple[Mutation, ...]:
        named = cls._coerce_mutations(mutations)
        named.sort(key=lambda item: item[0])
        deduped = cls._dedupe_mutations(named)
        rng = random.Random(random_seed)
        rng.shuffle(deduped)
        return tuple(Mutation(name=name, mutate_fn=mutate_fn) for name, mutate_fn in deduped)

    @property
    def mutations_remaining(self) -> int:
        return max(0, len(self._mutations) - self._index)

    def propose(self, source_code: str) -> str:
        if not self.mutations_remaining:
            raise StopIteration("No structured mutations remaining")

        while self._index < len(self._mutations):
            mutation = self._mutations[self._index]
            self._index += 1
            candidate = mutation.mutate_fn(source_code)
            try:
                _validate_python_source(candidate)
            except SyntaxError:
                continue
            return candidate
        raise StopIteration("No structured mutations remaining")


class LLMMutationStrategy(MutationStrategy):
    """Request one mutated version from a configured LLM provider."""

    _OPENAI_RESPONSE_ENV = "OPENAI_MODEL"
    _ANTHROPIC_RESPONSE_ENV = "ANTHROPIC_MODEL"
    _OPENAI_KEY_ENV = "OPENAI_API_KEY"
    _ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"

    _OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
    _ANTHROPIC_DEFAULT_MODEL = "claude-3-5-sonnet-20240620"

    def __init__(
        self,
        *,
        provider: str = "openai",
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.provider = provider.lower()
        self.model = model or self._default_model(self.provider)
        self._api_key = api_key
        self._mutations_remaining = 1

    @property
    def mutations_remaining(self) -> int:
        return self._mutations_remaining

    @property
    def api_key(self) -> str | None:
        return self._resolve_api_key(self.provider) if self._api_key is None else self._api_key

    @staticmethod
    def _default_model(provider: str) -> str:
        if provider == "openai":
            return os.getenv(
                LLMMutationStrategy._OPENAI_RESPONSE_ENV, LLMMutationStrategy._OPENAI_DEFAULT_MODEL
            )
        if provider == "anthropic":
            return os.getenv(
                LLMMutationStrategy._ANTHROPIC_RESPONSE_ENV,
                LLMMutationStrategy._ANTHROPIC_DEFAULT_MODEL,
            )
        raise ValueError(f"Unsupported provider: {provider}")

    @classmethod
    def _resolve_api_key(cls, provider: str) -> str | None:
        if provider == "openai":
            return os.getenv(cls._OPENAI_KEY_ENV)
        if provider == "anthropic":
            return os.getenv(cls._ANTHROPIC_KEY_ENV)
        return None

    def _openai_mutation(self, source_code: str) -> str:
        if self.api_key is None or openai is None:
            return source_code
        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            max_tokens=768,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an optimizer. Return a valid, complete Python script."
                        " Use fenced code blocks."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Return a valid mutated version of this Python source."
                        " Keep behavior equivalent and wrap in a Python code block:\n\n"
                        f"{source_code}"
                    ),
                },
            ],
        )
        return response.choices[0].message.content or ""

    def _anthropic_mutation(self, source_code: str) -> str:
        if self.api_key is None or anthropic is None:
            return source_code
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=768,
            system="You are an optimizer. Return a valid Python code block.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Return a valid mutated version of this Python source."
                        " Keep behavior equivalent and wrap in a code block:\n\n"
                        f"{source_code}"
                    ),
                }
            ],
        )
        text = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text.append(getattr(block, "text", ""))
        return "".join(text)

    def _query_provider(self, source_code: str) -> str:
        if self.provider == "openai":
            return self._openai_mutation(source_code)
        if self.provider == "anthropic":
            return self._anthropic_mutation(source_code)
        raise ValueError(f"Unsupported provider: {self.provider}")

    def propose(self, source_code: str) -> str:
        try:
            response = self._query_provider(source_code)
        except Exception:
            return source_code
        if not response:
            return source_code

        candidate = _extract_code_block(response)
        if not candidate:
            return source_code
        try:
            _validate_python_source(candidate)
        except SyntaxError:
            return source_code
        return candidate
