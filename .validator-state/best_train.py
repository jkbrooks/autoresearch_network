import math

BASELINE_SCALE = 4


def train_step(value: int) -> int:
    return int(math.pow(value, BASELINE_SCALE))
