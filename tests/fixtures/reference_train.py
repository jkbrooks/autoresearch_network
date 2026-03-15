"""Reference train.py fixture used by mutation tests."""

from __future__ import annotations

import textwrap

REFERENCE_TRAIN_PY = textwrap.dedent(
    """\
    import math

    class GPTConfig:
        n_layer: int = 12
        n_embd: int = 768
        window_pattern: str = "SSSL"


    UNEMBEDDING_LR = 0.004000
    EMBEDDING_LR = 0.600000
    SCALAR_LR = 0.500000
    MATRIX_LR = 0.020000
    TOTAL_BATCH_SIZE = 2**19


    def train_step(value: int) -> int:
        return int(math.pow(value, 4))
    """
).strip()
