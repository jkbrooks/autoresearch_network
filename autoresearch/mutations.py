"""Mutation strategies for miner train.py proposals."""

from __future__ import annotations

import ast
import logging
import operator
import os
import random
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

LOGGER = logging.getLogger(__name__)

MutationFunction = Callable[[str], str]

try:
    import anthropic
except ImportError:  # pragma: no cover - optional dependency in some local environments
    anthropic = None  # type: ignore[assignment]

try:
    import openai
except ImportError:  # pragma: no cover - optional dependency in some local environments
    openai = None  # type: ignore[assignment]


def _validate_python_source(source: str) -> None:
    ast.parse(source)


def _extract_code_block(text: str) -> str | None:
    pattern = re.compile(
        r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<body>.*?)\n```",
        flags=re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    preferred = [
        match for match in matches if match.group("lang").strip().lower() in {"python", "py"}
    ]
    selected = preferred[0] if preferred else matches[0]
    return selected.group("body").strip()


@dataclass(frozen=True)
class Mutation:
    name: str
    mutate_fn: MutationFunction


class MutationStrategy(ABC):
    @property
    @abstractmethod
    def mutations_remaining(self) -> int:
        ...

    @abstractmethod
    def propose(self, source_code: str) -> str:
        ...

    def mutate(self, source_code: str) -> str:
        return self.propose(source_code)


class StructuredMutationStrategy(MutationStrategy):
    """Default deterministic train.py mutation strategy with optional custom mutations."""

    def __init__(
        self,
        mutations: Iterable[tuple[str, MutationFunction] | MutationFunction]
        | Mapping[str, MutationFunction]
        | None = None,
        *,
        seed: int = 42,
        random_seed: int | None = None,
    ) -> None:
        normalized = self._prepare_mutations(
            self._default_mutations() if mutations is None else mutations,
            random_seed=seed if random_seed is None else random_seed,
        )
        self._mutations = list(normalized)
        self._order = [mutation.name for mutation in normalized]
        self._lookup = {mutation.name: mutation.mutate_fn for mutation in normalized}
        self.tried: set[str] = set()

    @property
    def mutation_names(self) -> tuple[str, ...]:
        return tuple(self._order)

    @property
    def mutations_remaining(self) -> int:
        return max(0, len(self._order) - len(self.tried))

    def propose(self, source_code: str) -> str:
        candidate = self._next_candidate(source_code)
        return source_code if candidate is None else candidate

    def mutate(self, source_code: str) -> str:
        candidate = self._next_candidate(source_code)
        if candidate is None:
            raise StopIteration("No structured mutations remaining")
        return candidate

    def _next_candidate(self, source_code: str) -> str | None:
        for name in self._order:
            if name in self.tried:
                continue
            self.tried.add(name)
            candidate = self._lookup[name](source_code)
            if candidate == source_code:
                continue
            try:
                _validate_python_source(candidate)
            except SyntaxError:
                continue
            return candidate
        return None

    @staticmethod
    def _coerce_mutations(
        mutations: Iterable[tuple[str, MutationFunction] | MutationFunction]
        | Mapping[str, MutationFunction],
    ) -> list[tuple[str, MutationFunction]]:
        if isinstance(mutations, Mapping):
            return [(str(name), fn) for name, fn in mutations.items()]
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

    def _default_mutations(self) -> list[tuple[str, MutationFunction]]:
        return [
            ("depth_increase", self._depth_increase),
            ("depth_decrease", self._depth_decrease),
            ("lr_scale_up", self._lr_scale_up),
            ("lr_scale_down", self._lr_scale_down),
            ("window_to_simple", self._window_to_simple),
            ("window_to_sssl", self._window_to_sssl),
            ("batch_double", self._batch_double),
            ("batch_halve", self._batch_halve),
            ("embd_increase", self._embd_increase),
            ("embd_decrease", self._embd_decrease),
        ]

    def _replace_pattern(
        self,
        source: str,
        pattern: str,
        transform: Callable[[re.Match[str]], str],
    ) -> str:
        return re.sub(pattern, transform, source, count=1, flags=re.MULTILINE)

    def _depth_increase(self, source: str) -> str:
        return self._replace_pattern(
            source,
            r"(n_layer:\s*int\s*=\s*)(\d+)",
            lambda m: f"{m.group(1)}{int(m.group(2)) + 2}",
        )

    def _depth_decrease(self, source: str) -> str:
        return self._replace_pattern(
            source,
            r"(n_layer:\s*int\s*=\s*)(\d+)",
            lambda m: f"{m.group(1)}{max(4, int(m.group(2)) - 2)}",
        )

    def _lr_scale_up(self, source: str) -> str:
        return self._scale_lr(source, 1.5)

    def _lr_scale_down(self, source: str) -> str:
        return self._scale_lr(source, 0.7)

    def _scale_lr(self, source: str, factor: float) -> str:
        return self._replace_pattern(
            source,
            r"(^\s*EMBEDDING_LR\s*=\s*)([\d.]+)",
            lambda m: f"{m.group(1)}{float(m.group(2)) * factor:.6f}",
        )

    def _window_to_simple(self, source: str) -> str:
        return source.replace('window_pattern: str = "SSSL"', 'window_pattern: str = "L"', 1)

    def _window_to_sssl(self, source: str) -> str:
        return source.replace('window_pattern: str = "L"', 'window_pattern: str = "SSSL"', 1)

    def _batch_double(self, source: str) -> str:
        return self._replace_batch(source, 2.0)

    def _batch_halve(self, source: str) -> str:
        return self._replace_batch(source, 0.5)

    def _replace_batch(self, source: str, factor: float) -> str:
        def transform(match: re.Match[str]) -> str:
            expr = match.group(2).strip()
            value = _safe_eval_int(expr)
            updated = max(1, int(value * factor))
            return f"{match.group(1)}{updated}"

        return self._replace_pattern(source, r"(TOTAL_BATCH_SIZE\s*=\s*)([^\n#]+)", transform)

    def _embd_increase(self, source: str) -> str:
        return self._replace_pattern(
            source,
            r"(n_embd:\s*int\s*=\s*)(\d+)",
            lambda m: f"{m.group(1)}{int(m.group(2)) + 128}",
        )

    def _embd_decrease(self, source: str) -> str:
        return self._replace_pattern(
            source,
            r"(n_embd:\s*int\s*=\s*)(\d+)",
            lambda m: f"{m.group(1)}{max(256, int(m.group(2)) - 128)}",
        )


class LLMMutationStrategy(MutationStrategy):
    _OPENAI_KEY_ENV = "OPENAI_API_KEY"
    _ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"
    _OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
    _ANTHROPIC_DEFAULT_MODEL = "claude-3-5-sonnet-20240620"

    def __init__(
        self,
        *,
        provider: str = "openai",
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model or self._default_model(self.provider)
        self.base_url = base_url
        self._mutations_remaining = 1
        program_path = Path(__file__).with_name("data") / "program.md"
        self.system_prompt = (
            program_path.read_text(encoding="utf-8") if program_path.exists() else ""
        )

    @property
    def mutations_remaining(self) -> int:
        return self._mutations_remaining

    def propose(self, source_code: str) -> str:
        if self.provider == "none":
            LOGGER.warning("LLM mutation unavailable; falling back to structured behavior.")
            return source_code

        resolved_key = self.api_key or self._resolve_api_key(self.provider)
        if not resolved_key:
            LOGGER.warning("Missing API key for mutation provider '%s'.", self.provider)
            return source_code

        try:
            response = self._request_completion(source_code, resolved_key)
        except Exception as exc:
            LOGGER.warning("LLM mutation failed with %s: %s", exc.__class__.__name__, exc)
            return source_code

        code = _extract_code_block(response)
        if code is None:
            LOGGER.warning("Could not extract a fenced code block from LLM response.")
            return source_code

        try:
            _validate_python_source(code)
        except SyntaxError:
            LOGGER.warning("LLM produced invalid Python, falling back to baseline source.")
            return source_code
        return code

    def _request_completion(self, baseline_train_py: str, api_key: str) -> str:
        user_prompt = (
            "Here is the current train.py:\n\n```python\n"
            f"{baseline_train_py}\n```\n\n"
            "Propose ONE modification to improve val_bpb. Return ONLY the complete "
            "modified train.py inside a code block."
        )
        if self.provider == "anthropic":
            if anthropic is None:
                raise RuntimeError("anthropic SDK is not installed")
            anthropic_client = anthropic.Anthropic(api_key=api_key)
            response = anthropic_client.messages.create(
                model=self.model,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=24_000,
            )
            parts: list[str] = []
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    parts.append(cast(str, getattr(block, "text", "")))
            return "".join(parts)

        if self.provider not in {"openai", "openai-compatible"}:
            raise ValueError(f"Unsupported provider: {self.provider}")
        if openai is None:
            raise RuntimeError("openai SDK is not installed")

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if self.base_url is not None:
            client_kwargs["base_url"] = self.base_url
        openai_client = openai.OpenAI(**client_kwargs)
        openai_response = openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return openai_response.choices[0].message.content or ""

    @classmethod
    def _resolve_api_key(cls, provider: str) -> str | None:
        if provider == "anthropic":
            return os.getenv(cls._ANTHROPIC_KEY_ENV)
        if provider in {"openai", "openai-compatible"}:
            return os.getenv(cls._OPENAI_KEY_ENV)
        return None

    @classmethod
    def _default_model(cls, provider: str) -> str:
        if provider == "anthropic":
            return cls._ANTHROPIC_DEFAULT_MODEL
        return cls._OPENAI_DEFAULT_MODEL


_ALLOWED_AST_BINOPS: dict[type[ast.operator], Callable[[int, int], int]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_AST_UNARYOPS: dict[type[ast.unaryop], Callable[[int], int]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval_int(expression: str) -> int:
    tree = ast.parse(expression, mode="eval")
    return _eval_int_node(tree.body)


def _eval_int_node(node: ast.AST) -> int:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return int(node.value)
    if isinstance(node, ast.BinOp):
        binop_type = type(node.op)
        if binop_type not in _ALLOWED_AST_BINOPS:
            raise ValueError(
                f"Unsupported operator in batch expression: {binop_type.__name__}"
            )
        left = _eval_int_node(node.left)
        right = _eval_int_node(node.right)
        return _ALLOWED_AST_BINOPS[binop_type](left, right)
    if isinstance(node, ast.UnaryOp):
        unaryop_type = type(node.op)
        if unaryop_type not in _ALLOWED_AST_UNARYOPS:
            raise ValueError(f"Unsupported unary operator: {unaryop_type.__name__}")
        operand = _eval_int_node(node.operand)
        return _ALLOWED_AST_UNARYOPS[unaryop_type](operand)
    raise ValueError(f"Unsupported expression node: {node.__class__.__name__}")
