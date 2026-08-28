from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import firwin, lfilter, upfirdn

METHOD = "loudness/bs1770-4-numpy"

ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = -10.0
BLOCK_S = 0.400
BLOCK_STEP_S = 0.100
SHORT_TERM_S = 3.000
LRA_RELATIVE_GATE_LU = -20.0
LRA_LOW_PERCENTILE = 10.0
LRA_HIGH_PERCENTILE = 95.0
OFFSET_DB = -0.691

TRUE_PEAK_OVERSAMPLE = 8
TRUE_PEAK_TAPS_PER_PHASE = 32
TRUE_PEAK_KAISER_BETA = 12.0

SHELF_F0_HZ = 1681.974450955533
SHELF_GAIN_DB = 3.999843853973347
SHELF_Q = 0.7071752369554196
HIGHPASS_F0_HZ = 38.13547087602444
HIGHPASS_Q = 0.5003270373238773


class Unmeasurable(ValueError):
    pass


@dataclass(frozen=True)
class Integrated:
    lufs: float
    relative_gate_lufs: float
    blocks_total: int
    blocks_over_absolute_gate: int
    blocks_over_relative_gate: int
    keep: np.ndarray


def shelf_coefficients(rate: int) -> tuple[np.ndarray, np.ndarray]:
    k = np.tan(np.pi * SHELF_F0_HZ / rate)
    vh = 10.0 ** (SHELF_GAIN_DB / 20.0)
    vb = vh**0.4996667741545416
    a0 = 1.0 + k / SHELF_Q + k * k
    b = np.array([(vh + vb * k / SHELF_Q + k * k) / a0, 2.0 * (k * k - vh) / a0,
                  (vh - vb * k / SHELF_Q + k * k) / a0])
    a = np.array([1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / SHELF_Q + k * k) / a0])
    return b, a


def highpass_coefficients(rate: int) -> tuple[np.ndarray, np.ndarray]:
    k = np.tan(np.pi * HIGHPASS_F0_HZ / rate)
    a0 = 1.0 + k / HIGHPASS_Q + k * k
    b = np.array([1.0, -2.0, 1.0])
    a = np.array([1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / HIGHPASS_Q + k * k) / a0])
    return b, a


def kweight(x: np.ndarray, rate: int) -> np.ndarray:
    b1, a1 = shelf_coefficients(rate)
    b2, a2 = highpass_coefficients(rate)
    return lfilter(b2, a2, lfilter(b1, a1, np.asarray(x, dtype=np.float64), axis=1), axis=1)


def channel_weights(channels: int) -> np.ndarray:
    if channels in (1, 2):
        return np.ones(channels, dtype=np.float64)
    raise Unmeasurable(
        f"{channels} channels: BS.1770 weights surround channels at 1.41 and the sample array "
        "does not say which channel is which"
    )


def subblock_sums(y: np.ndarray, rate: int) -> np.ndarray:
    step = int(round(BLOCK_STEP_S * rate))
    n = (y.shape[1] // step) * step
    if n == 0:
        return np.zeros((y.shape[0], 0), dtype=np.float64)
    sq = np.square(y[:, :n])
    return sq.reshape(y.shape[0], n // step, step).sum(axis=2)


def window_mean_squares(sub: np.ndarray, rate: int, window_s: float) -> np.ndarray:
    per_window = int(round(window_s / BLOCK_STEP_S))
    if sub.shape[1] < per_window:
        return np.zeros((sub.shape[0], 0), dtype=np.float64)
    cum = np.concatenate([np.zeros((sub.shape[0], 1)), np.cumsum(sub, axis=1)], axis=1)
    sums = cum[:, per_window:] - cum[:, :-per_window]
    return sums / (per_window * int(round(BLOCK_STEP_S * rate)))


def _loudness(z: np.ndarray, weights: np.ndarray) -> np.ndarray:
    total = np.tensordot(weights, z, axes=(0, 0))
    with np.errstate(divide="ignore"):
        return OFFSET_DB + 10.0 * np.log10(total)


def integrated(x: np.ndarray, rate: int) -> Integrated | None:
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    weights = channel_weights(x.shape[0])
    z = window_mean_squares(subblock_sums(kweight(x, rate), rate), rate, BLOCK_S)
    if z.shape[1] == 0:
        return None

    loud = _loudness(z, weights)
    over_absolute = loud > ABSOLUTE_GATE_LUFS
    if not over_absolute.any():
        return None

    relative = _loudness(z[:, over_absolute].mean(axis=1, keepdims=True), weights)[0] + RELATIVE_GATE_LU
    keep = over_absolute & (loud > relative)
    if not keep.any():
        return None

    return Integrated(
        lufs=float(_loudness(z[:, keep].mean(axis=1, keepdims=True), weights)[0]),
        relative_gate_lufs=float(relative),
        blocks_total=int(z.shape[1]),
        blocks_over_absolute_gate=int(over_absolute.sum()),
        blocks_over_relative_gate=int(keep.sum()),
        keep=keep,
    )


def loudness_range(x: np.ndarray, rate: int) -> float | None:
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    weights = channel_weights(x.shape[0])
    z = window_mean_squares(subblock_sums(kweight(x, rate), rate), rate, SHORT_TERM_S)
    if z.shape[1] == 0:
        return None

    short = _loudness(z, weights)
    over_absolute = short > ABSOLUTE_GATE_LUFS
    if not over_absolute.any():
        return None

    relative = _loudness(z[:, over_absolute].mean(axis=1, keepdims=True), weights)[0] + LRA_RELATIVE_GATE_LU
    kept = short[over_absolute & (short > relative)]
    if kept.size == 0:
        return None

    return float(np.percentile(kept, LRA_HIGH_PERCENTILE) - np.percentile(kept, LRA_LOW_PERCENTILE))


def oversampling_filter(oversample: int = TRUE_PEAK_OVERSAMPLE) -> np.ndarray:
    taps = oversample * TRUE_PEAK_TAPS_PER_PHASE + 1
    return firwin(taps, 1.0 / oversample, window=("kaiser", TRUE_PEAK_KAISER_BETA)) * oversample


def true_peak_dbtp(x: np.ndarray, oversample: int = TRUE_PEAK_OVERSAMPLE) -> float | None:
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    h = oversampling_filter(oversample)
    peak = max(float(np.max(np.abs(upfirdn(h, ch, oversample, 1)))) for ch in x)
    return None if peak <= 0.0 else float(20.0 * np.log10(peak))


def sample_peak_dbfs(x: np.ndarray) -> float | None:
    peak = float(np.max(np.abs(np.asarray(x, dtype=np.float64))))
    return None if peak <= 0.0 else float(20.0 * np.log10(peak))
