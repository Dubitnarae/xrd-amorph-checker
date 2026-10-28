"""배경: 저각 지수 감쇠 + 1차 다항식."""

from __future__ import annotations

import numpy as np

PARAM_NAMES = ["b0", "b1", "B", "t"]


def background(x, b0, b1, B, t, x_start, x_mid):
    """b0 + b1·(2θ − 중앙) + B·exp(−(2θ − 시작)/t)."""
    return b0 + b1 * (x - x_mid) + B * np.exp(-(x - x_start) / t)
