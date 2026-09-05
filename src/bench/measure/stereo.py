from __future__ import annotations

import numpy as np

from bench.decode import Audio
from bench.measure import Unmeasurable

METHOD = "stereo/energy-weighted-correlation"

CORRELATION_DECIMALS = 6
WIDTH_DECIMALS = 4
UNCERTAINTY = {
    "correlation": 0.5 * 10.0 ** -CORRELATION_DECIMALS,
    "width_side_mid_db": 0.5 * 10.0 ** -WIDTH_DECIMALS,
}


def centred(samples: np.ndarray) -> np.ndarray:
    return samples - samples.mean(axis=1, keepdims=True)


def correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    left_energy = float(np.dot(left, left))
    right_energy = float(np.dot(right, right))
    if left_energy <= 0.0 or right_energy <= 0.0:
        return None
    return float(np.dot(left, right) / np.sqrt(left_energy * right_energy))


def width_db(left: np.ndarray, right: np.ndarray) -> float | None:
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_energy = float(np.dot(mid, mid))
    side_energy = float(np.dot(side, side))
    if mid_energy <= 0.0 or side_energy <= 0.0:
        return None
    return float(10.0 * np.log10(side_energy / mid_energy))


def measure(audio: Audio) -> dict:
    if audio.channels != 2:
        raise Unmeasurable(
            f"{audio.channels} channel file: there is no left and right to compare"
        )

    left, right = centred(audio.samples)
    out = {"method": METHOD, "uncertainty": dict(UNCERTAINTY)}
    absent = {}

    value = correlation(left, right)
    if value is None:
        absent["correlation"] = "a channel with no signal has no correlation with the other"
    else:
        out["correlation"] = round(value, 6)

    value = width_db(left, right)
    if value is None:
        absent["width_side_mid_db"] = (
            "identical channels have no side energy, and channels that cancel have no mid energy"
        )
    else:
        out["width_side_mid_db"] = round(value, 4)

    if absent:
        out["absent_because"] = absent
    return out
