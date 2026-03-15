"""Reference train.py fixture used by mutation tests."""

from __future__ import annotations

import textwrap

REFERENCE_TRAIN_PY = textwrap.dedent(
    """\
    import math

    BASELINE_SCALE = 4


    def train_step(value: int) -> int:
        return int(math.pow(value, BASELINE_SCALE))
    """
).strip()
