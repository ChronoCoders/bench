"""A true peak limiter whose attack and release are chosen by search, not by taste.

The gain envelope is built from the same oversampled peak the bench measures with, so
what it limits is what the bench reports. Nothing here picks an attack or a release:
that is master.py's job, and it picks them by measuring the result.

The last step takes the elementwise minimum of the smoothed envelope and the envelope
the ceiling actually requires. Smoothing a gain curve can lift it back above what a
sample needed, and one sample over is still over.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import upfirdn

from bench.measure import bs1770

LOOKAHEAD_MULTIPLE = 2


def required_gain(samples: np.ndarray, rate: int, ceiling_dbtp: float,
                  oversample: int = bs1770.TRUE_PEAK_OVERSAMPLE) -> np.ndarray:
    """The most gain each input sample may keep without any channel going over.

    The peak is taken between samples, not at them, so a signal that only exceeds the
    ceiling on reconstruction is still caught.
    """
    x = np.atleast_2d(np.asarray(samples, dtype=np.float64))
    h = bs1770.oversampling_filter(oversample)
    frames = x.shape[1]
    peak = np.zeros(frames)
    for channel in x:
        up = np.abs(upfirdn(h, channel, oversample, 1))
        usable = frames * oversample
        if up.size < usable:
            up = np.pad(up, (0, usable - up.size))
        peak = np.maximum(peak, up[:usable].reshape(frames, oversample).max(axis=1))
    ceiling = 10.0 ** (ceiling_dbtp / 20.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        gain = np.where(peak > ceiling, ceiling / peak, 1.0)
    return np.clip(np.nan_to_num(gain, nan=1.0), 0.0, 1.0)


def _running_min(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    strides = np.lib.stride_tricks.sliding_window_view(padded, window)
    return strides.min(axis=1)[: values.size]


def _release(values: np.ndarray, rate: int, release_ms: float) -> np.ndarray:
    """Fall at once, come back over the release. A limiter that recovers instantly
    modulates the programme at the rate of its own peaks."""
    if release_ms <= 0.0:
        return values
    alpha = 1.0 - np.exp(-1.0 / max(release_ms * 1e-3 * rate, 1.0))
    out = np.empty_like(values)
    running = values[0]
    for i, wanted in enumerate(values):
        running = wanted if wanted < running else running + alpha * (wanted - running)
        out[i] = running
    return out


def envelope(samples: np.ndarray, rate: int, ceiling_dbtp: float,
             attack_ms: float, release_ms: float,
             needed: np.ndarray | None = None) -> np.ndarray:
    """`needed` is the required gain, which does not depend on attack or release. A
    search over those two recomputes everything else and should not recompute it."""
    if needed is None:
        needed = required_gain(samples, rate, ceiling_dbtp)
    attack = max(1, int(round(attack_ms * 1e-3 * rate)))
    smoothed = _running_min(needed, attack * LOOKAHEAD_MULTIPLE)
    if attack > 1:
        window = np.hanning(attack + 2)[1:-1]
        window = window / window.sum()
        smoothed = np.convolve(np.pad(smoothed, (attack, attack), mode="edge"),
                               window, mode="same")[attack:-attack]
    smoothed = _release(smoothed, rate, release_ms)
    return np.minimum(smoothed, needed)


def apply(samples: np.ndarray, rate: int, ceiling_dbtp: float,
          attack_ms: float, release_ms: float,
          needed: np.ndarray | None = None) -> np.ndarray:
    gain = envelope(samples, rate, ceiling_dbtp, attack_ms, release_ms, needed)
    return np.asarray(samples, dtype=np.float64) * gain


def worked(gain: np.ndarray) -> dict:
    return {
        "largest_db": round(float(-20.0 * np.log10(max(gain.min(), 1e-12))), 3),
        "share_of_file": round(float((gain < 1.0).mean()), 6),
    }
