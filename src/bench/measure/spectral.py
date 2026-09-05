from __future__ import annotations

import numpy as np
from scipy.fft import next_fast_len

from bench.decode import Audio
from bench.measure import Unmeasurable

METHOD = "spectral/periodogram-band-energy"

BAND_SET = "bench-v1"
BAND_EDGES_HZ = (20.0, 60.0, 120.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0, 20000.0)
DENOMINATOR_HZ = (20.0, 20000.0)
ROLLUPS = {"under_250_hz_pct": (20.0, 250.0), "band_60_250_pct": (60.0, 250.0)}

MIN_DURATION_S = 1.0
PERCENT_DECIMALS = 2
PERCENT_UNCERTAINTY = 0.5 * 10.0 ** -PERCENT_DECIMALS


def band_power(freqs: np.ndarray, spectrum: np.ndarray, lo: float, hi: float) -> float:
    half = (freqs[1] - freqs[0]) / 2.0
    overlap = np.clip(np.minimum(freqs + half, hi) - np.maximum(freqs - half, lo), 0.0, None)
    return float(np.sum(spectrum * overlap))


def transform_length(frames: int) -> int:
    return int(next_fast_len(frames, real=True))


def spectrum(samples: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    n = transform_length(samples.shape[1])
    padded = np.zeros((samples.shape[0], n), dtype=np.float64)
    padded[:, : samples.shape[1]] = samples
    power = np.zeros(n // 2 + 1, dtype=np.float64)
    for channel in padded:
        power += np.abs(np.fft.rfft(channel)) ** 2
    if n % 2 == 0:
        power[1:-1] *= 2.0
    else:
        power[1:] *= 2.0
    return np.fft.rfftfreq(n, 1.0 / rate), power


def total_energy(power: np.ndarray, frames_transformed: int) -> float:
    return float(np.sum(power)) / frames_transformed


def _round(value: float) -> float:
    return round(value, PERCENT_DECIMALS)


def measure(audio: Audio) -> dict:
    if audio.duration_s < MIN_DURATION_S:
        raise Unmeasurable(
            f"{audio.duration_s:.3f} s is shorter than {MIN_DURATION_S:.0f} s, below which the "
            "transform cannot place the 20 Hz band edge to better than a hertz"
        )

    nyquist = audio.sample_rate_hz / 2.0
    freqs, power = spectrum(audio.samples, audio.sample_rate_hz)
    hi_limit = min(DENOMINATOR_HZ[1], nyquist)
    total = band_power(freqs, power, DENOMINATOR_HZ[0], hi_limit)
    if total <= 0.0:
        raise Unmeasurable(
            f"no energy between {DENOMINATOR_HZ[0]:.0f} Hz and {hi_limit:.0f} Hz to take a percentage of"
        )

    bands = [
        {"lo_hz": lo, "hi_hz": hi, "pct": _round(100.0 * band_power(freqs, power, lo, hi) / total)}
        for lo, hi in zip(BAND_EDGES_HZ, BAND_EDGES_HZ[1:])
        if hi <= nyquist
    ]
    return {
        "method": METHOD,
        "band_set": BAND_SET,
        "denominator_hz": [DENOMINATOR_HZ[0], hi_limit],
        "complete": hi_limit >= DENOMINATOR_HZ[1],
        "bin_width_hz": round(float(freqs[1] - freqs[0]), 6),
        "frames": audio.frames,
        "frames_transformed": transform_length(audio.frames),
        "bands": bands,
        "rollups": {name: _round(100.0 * band_power(freqs, power, lo, hi) / total)
                    for name, (lo, hi) in ROLLUPS.items()},
        "uncertainty": {"every_percentage": PERCENT_UNCERTAINTY},
        "outside_denominator_pct": {
            "below_20_hz": _round(100.0 * band_power(freqs, power, 0.0, DENOMINATOR_HZ[0]) / total),
            f"above_{hi_limit:.0f}_hz": _round(
                100.0 * band_power(freqs, power, hi_limit, nyquist) / total),
        },
    }
