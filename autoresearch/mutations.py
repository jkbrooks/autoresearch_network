"""Mutation strategies for miner train.py proposals."""

from __future__ import annotations

import ast
import logging
import os
import random
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import cast

LOGGER = logging.getLogger(__name__)


class MutationStrategy(ABC):
    @abstractmethod
    def propose(self, baseline_train_py: str) -> str:
        ...


class StructuredMutationStrategy(MutationStrategy):
    def __init__(self, seed: int = 42) -> None:
        self.tried: set[str] = set()
        self.rng = random.Random(seed)
        self._mutations: list[tuple[str, Callable[[str], str]]] = [
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
        self._order = [name for name, _ in self._mutations]
        self.rng.shuffle(self._order)
        self._lookup = dict(self._mutations)

    @property
    def mutations_remaining(self) -> int:
        return len(self._order) - len(self.tried)

    def propose(self, baseline_train_py: str) -> str:
        for name in self._order:
            if name in self.tried:
                continue
            self.tried.add(name)
            candidate = self._lookup[name](baseline_train_py)
            if candidate == baseline_train_py:
                continue
            try:
                ast.parse(candidate)
            except SyntaxError:
                continue
            return candidate
        return baseline_train_py

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
            r"((?:UNEMBEDDING_LR|EMBEDDING_LR|SCALAR_LR|MATRIX_LR)\s*=\s*)([\d.]+)",
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
            value = int(eval(expr, {"__builtins__": {}}, {}))
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
    def __init__(
        self,
        provider: str,
        api_key: str | None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider = provider
        self.api_key = api_key
        self.model = model or ("claude-opus-4-5" if provider == "anthropic" else "gpt-4o")
        self.base_url = base_url
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        self.system_prompt = open(os.path.join(data_dir, "program.md"), encoding="utf-8").read()

    def propose(self, baseline_train_py: str) -> str:
        if self.provider == "none" or not self.api_key:
            LOGGER.warning("LLM mutation unavailable; falling back to original source.")
            return baseline_train_py
        try:
            response = self._request_completion(baseline_train_py)
        except Exception as exc:
            LOGGER.warning("LLM mutation failed with %s: %s", exc.__class__.__name__, exc)
            return baseline_train_py

        code = self._extract_code_block(response)
        if code is None:
            LOGGER.warning("Could not extract code block from LLM response")
            return baseline_train_py
        try:
            ast.parse(code)
        except SyntaxError:
            LOGGER.warning("LLM produced invalid Python, falling back")
            return baseline_train_py
        return code

    def _request_completion(self, baseline_train_py: str) -> str:
        user_prompt = (
            "Here is the current train.py:\n\n```python\n"
            f"{baseline_train_py}\n```\n\n"
            "Propose ONE modification to improve val_bpb. Return ONLY the complete "
            "modified train.py inside a ```python code block."
        )
        if self.provider == "anthropic":
            from anthropic import Anthropic

            client = Anthropic(api_key=self.api_key, timeout=60)
            response = client.messages.create(
                model=self.model,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=24_000,
            )
            content_block = response.content[0]
            return cast(str, getattr(content_block, "text", ""))

        from openai import OpenAI

        openai_client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=60)
        openai_response = openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return openai_response.choices[0].message.content or ""

    @staticmethod
    def _extract_code_block(response: str) -> str | None:
        tagged = re.search(r"```python\n(.*?)```", response, re.DOTALL)
        if tagged:
            return tagged.group(1).strip()
        untagged = re.search(r"```\n(.*?)```", response, re.DOTALL)
        if untagged:
            return untagged.group(1).strip()
        return None
