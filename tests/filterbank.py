from __future__ import annotations

import numpy as np
from scipy.signal import ellip, resample_poly, sosfiltfilt

ORDER = 12
PASSBAND_RIPPLE_DB = 0.05
STOPBAND_DB = 120.0


def working_rate(rate: int, cutoff: float) -> tuple[int, int]:
    d = max(1, int(rate // (4 * cutoff)))
    while d > 1 and rate % d:
        d -= 1
    return rate // d, d


def lowpass_energy(samples: np.ndarray, rate: int, cutoff: float) -> float:
    wr, d = working_rate(rate, cutoff)
    y = samples if d == 1 else resample_poly(samples, 1, d, axis=-1)
    sos = ellip(ORDER, PASSBAND_RIPPLE_DB, STOPBAND_DB, cutoff, btype="low", fs=wr, output="sos")
    return float(np.sum(np.square(sosfiltfilt(sos, y, axis=-1)))) / wr


def band_percentages(samples: np.ndarray, rate: int, edges: tuple[float, ...]) -> dict:
    energy = {c: lowpass_energy(samples, rate, c) for c in edges}
    total = energy[edges[-1]] - energy[edges[0]]
    return {(lo, hi): 100.0 * (energy[hi] - energy[lo]) / total
            for lo, hi in zip(edges, edges[1:])}
