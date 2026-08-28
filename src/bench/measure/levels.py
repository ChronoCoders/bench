from __future__ import annotations

import numpy as np

from bench.decode import Audio
from bench.measure import bs1770

METHOD = "levels/gated-crest-dc-clipping"

CLIP_RUN_MIN_SAMPLES = 3
DC_BLOCK_S = 0.400
DECIBEL_DECIMALS = 4
UNCERTAINTY = {"crest_db": 10.0 ** -DECIBEL_DECIMALS}


def full_scale(bit_depth: int | None) -> float:
    if bit_depth is None:
        return 1.0
    return 1.0 - 2.0 ** (1 - bit_depth)


def clipped_runs(samples: np.ndarray, threshold: float,
                 min_length: int = CLIP_RUN_MIN_SAMPLES) -> int:
    total = 0
    for channel in samples:
        at_full = np.abs(channel) >= threshold
        if not at_full.any():
            continue
        edges = np.flatnonzero(np.diff(np.concatenate([[0], at_full.astype(np.int8), [0]])))
        total += int(np.sum(edges[1::2] - edges[0::2] >= min_length))
    return total


def over_full_scale(samples: np.ndarray) -> int:
    return int(np.sum(np.abs(samples) > 1.0))


def dc_offset(samples: np.ndarray, rate: int) -> tuple[list[float], list[float] | None]:
    per_channel = [float(np.mean(channel)) for channel in samples]
    block = int(round(DC_BLOCK_S * rate))
    usable = (samples.shape[1] // block) * block
    if usable == 0:
        return per_channel, None
    means = samples[:, :usable].reshape(samples.shape[0], -1, block).mean(axis=2)
    return per_channel, [float(np.max(np.abs(row))) for row in means]


def gated_rms_dbfs(samples: np.ndarray, rate: int) -> float | None:
    gate = bs1770.integrated(samples, rate)
    if gate is None:
        return None
    z = bs1770.window_mean_squares(bs1770.subblock_sums(samples, rate), rate, bs1770.BLOCK_S)
    mean_square = float(np.mean(z[:, gate.keep]))
    return None if mean_square <= 0.0 else float(10.0 * np.log10(mean_square))


def measure(audio: Audio) -> dict:
    threshold = full_scale(audio.probe.bit_depth)
    per_channel, block_max = dc_offset(audio.samples, audio.sample_rate_hz)

    out = {
        "method": METHOD,
        "uncertainty": dict(UNCERTAINTY),
        "dc_offset": [round(v, 8) for v in per_channel],
        "clipped_runs": clipped_runs(audio.samples, threshold),
        "clip_threshold": round(threshold, 8),
        "clip_run_min_samples": CLIP_RUN_MIN_SAMPLES,
        "over_full_scale_samples": over_full_scale(audio.samples),
    }
    if block_max is not None:
        out["dc_offset_block_max"] = [round(v, 8) for v in block_max]

    peak = bs1770.sample_peak_dbfs(audio.samples)
    rms = gated_rms_dbfs(audio.samples, audio.sample_rate_hz)
    if peak is None or rms is None:
        out["absent_because"] = {
            "crest_db": "no block passed the loudness gates, so there is no programme to take a crest of"
            if peak is not None else "digital silence has no peak and no crest"
        }
        return out

    out["gated_rms_dbfs"] = round(rms, 4)
    out["crest_db"] = round(peak - rms, 4)
    return out
