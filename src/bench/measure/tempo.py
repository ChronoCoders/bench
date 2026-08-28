from __future__ import annotations

import numpy as np
from scipy.signal import stft

from bench.decode import Audio

METHOD = "tempo/flux-envelope-phase-track"

ENVELOPE_HZ = 100.0
WINDOW_S = 0.04
BAND_EDGES_HZ = tuple(np.geomspace(30.0, 16000.0, 9))

SEARCH_LOW_BPM = 55.0
SEARCH_HIGH_BPM = 200.0
SEARCH_STEP_BPM = 0.01
HARMONICS = (1, 2, 4)
SPECTRUM_PAD = 1 << 21

ONSET_ALPHA = 3.0
ONSET_MIN_GAP_S = 0.05

GRID_TOLERANCE_S = 0.030
OCTAVE_RATIOS = (0.5, 2.0 / 3.0, 1.0, 1.5, 2.0)
REFINE_SPAN_BPM = 0.6
REFINE_STEP_BPM = 0.02

DRIFT_ORDER = 3
DRIFT_FLOOR_BPM = 0.4
DRIFT_SAMPLES = 400
COARSE_WINDOW_S = 25.0
COARSE_HOP_S = 5.0
COARSE_BAND = 0.10
COARSE_PAD = 1 << 20
REFIT_LIMIT = 8
PHASE_STEPS = 128

MIN_DURATION_S = 30.0
MIN_ONSETS = 20


class Unmeasurable(ValueError):
    pass


def envelope(samples: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray, float]:
    hop = int(round(rate / ENVELOPE_HZ))
    window = 1 << int(np.ceil(np.log2(rate * WINDOW_S)))
    freqs, _, transform = stft(
        samples.mean(axis=0), fs=rate, nperseg=window, noverlap=window - hop,
        window="hann", boundary=None, padded=False,
    )
    flux = np.maximum(np.diff(np.log1p(1000.0 * np.abs(transform)), axis=1), 0.0)
    bands = []
    for lo, hi in zip(BAND_EDGES_HZ[:-1], BAND_EDGES_HZ[1:]):
        band = flux[(freqs >= lo) & (freqs < hi)].sum(axis=0)
        if band.mean() > 0.0:
            bands.append(band / band.mean())
    if not bands:
        raise Unmeasurable("no band carries any onset energy")
    values = np.sum(bands, axis=0)
    times = (np.arange(values.size) + 1.0) * hop / rate + window / (2.0 * rate)
    return values - values.mean(), times, rate / hop


def onsets(values: np.ndarray, times: np.ndarray, envelope_hz: float) -> np.ndarray:
    middle = np.median(values)
    threshold = middle + ONSET_ALPHA * np.maximum(values - middle, 0.0).mean()
    reach = max(1, int(round(ONSET_MIN_GAP_S * envelope_hz)))
    keep = []
    for i in np.flatnonzero(values > threshold):
        if values[i] == values[max(0, i - reach) : i + reach + 1].max():
            keep.append(i)
    return times[np.asarray(keep, dtype=int)] if keep else np.empty(0)


def search_grid() -> np.ndarray:
    return np.arange(SEARCH_LOW_BPM, SEARCH_HIGH_BPM, SEARCH_STEP_BPM)


def harmonic_score(values: np.ndarray, envelope_hz: float, bpm: np.ndarray) -> np.ndarray:
    centred = values - values.mean()
    magnitude = np.abs(np.fft.rfft(centred, SPECTRUM_PAD)) / np.sum(np.abs(centred))
    per_hz = SPECTRUM_PAD / envelope_hz
    return np.mean(
        [magnitude[(bpm * h / 60.0 * per_hz).round().astype(int)] for h in HARMONICS], axis=0
    )


def strongest_rate(values: np.ndarray, envelope_hz: float) -> tuple[float, bool]:
    """The strongest rate strictly inside the search range, and whether the score still
    rises at an edge, which means a stronger rate lies outside it."""
    grid = search_grid()
    score = harmonic_score(values, envelope_hz, grid)
    peak = int(np.argmax(score))
    if peak not in (0, score.size - 1):
        return float(grid[peak]), False
    turning = np.flatnonzero((score[1:-1] > score[:-2]) & (score[1:-1] >= score[2:])) + 1
    if turning.size == 0:
        return float(grid[peak]), True
    return float(grid[turning[int(np.argmax(score[turning]))]]), True


def grid_fit(times: np.ndarray, bpm: float, span_s: float) -> dict:
    period = 60.0 / bpm
    phase = times % period
    offsets = np.linspace(0.0, period, PHASE_STEPS, endpoint=False)
    best = max(offsets, key=lambda c: np.sum(
        np.abs((phase - c + period / 2.0) % period - period / 2.0) <= GRID_TOLERANCE_S))
    deviation = np.abs((phase - best + period / 2.0) % period - period / 2.0)
    hit = deviation <= GRID_TOLERANCE_S
    ticks = int(np.floor(span_s / period)) + 1
    filled = len(np.unique(np.round((times[hit] - best) / period))) if hit.any() else 0
    return {
        "occupancy": filled / max(ticks, 1),
        "coverage": float(hit.mean()) if times.size else 0.0,
        "median_deviation_ms": float(np.median(deviation[hit]) * 1000.0) if hit.any() else None,
        "onsets_fitted": int(hit.sum()),
    }


def refine(times: np.ndarray, bpm: float, span_s: float) -> float:
    candidates = np.arange(bpm - REFINE_SPAN_BPM, bpm + REFINE_SPAN_BPM, REFINE_STEP_BPM)
    ranked = []
    for candidate in candidates:
        fit = grid_fit(times, candidate, span_s)
        tightness = fit["median_deviation_ms"]
        ranked.append((fit["onsets_fitted"], -(tightness if tightness is not None else 1e9),
                       candidate))
    return float(max(ranked)[2])


def coarse_rate(values: np.ndarray, envelope_hz: float, bpm: float) -> tuple[np.ndarray, np.ndarray]:
    length = int(COARSE_WINDOW_S * envelope_hz)
    step = int(COARSE_HOP_S * envelope_hz)
    grid = np.arange(bpm * (1.0 - COARSE_BAND), bpm * (1.0 + COARSE_BAND), SEARCH_STEP_BPM)
    per_hz = COARSE_PAD / envelope_hz
    centres, rates = [], []
    for start in range(0, max(1, values.size - length + 1), step):
        segment = values[start : start + length]
        if segment.size < length:
            break
        segment = segment - segment.mean()
        magnitude = np.abs(np.fft.rfft(segment, COARSE_PAD)) / np.sum(np.abs(segment))
        score = np.mean(
            [magnitude[(grid * h / 60.0 * per_hz).round().astype(int)] for h in HARMONICS], axis=0
        )
        centres.append((start + length / 2.0) / envelope_hz)
        rates.append(grid[int(np.argmax(score))])
    return np.asarray(centres), np.asarray(rates) / 60.0


def beat_model(times: np.ndarray, values: np.ndarray, envelope_hz: float, bpm: float):
    period = 60.0 / bpm
    centres, rates = coarse_rate(values, envelope_hz, bpm)
    if centres.size >= DRIFT_ORDER + 1:
        coefficients = np.polyint(np.polyfit(centres, rates, DRIFT_ORDER - 1))
    else:
        coefficients = np.array([1.0 / period, 0.0])
    coefficients = np.asarray(coefficients, dtype=np.float64).copy()
    index = np.polyval(coefficients, times)
    shifts = np.linspace(0.0, 1.0, PHASE_STEPS, endpoint=False)
    best = max(shifts, key=lambda c: np.sum(
        np.abs(((index + c) % 1.0) - 0.5) >= 0.5 - GRID_TOLERANCE_S / period))
    coefficients[-1] += best
    matched = None
    for _ in range(REFIT_LIMIT):
        index = np.polyval(coefficients, times)
        hit = np.abs(index - np.round(index)) * period <= GRID_TOLERANCE_S
        if hit.sum() < MIN_ONSETS:
            return None
        if matched is not None and np.array_equal(hit, matched):
            break
        matched = hit
        coefficients = np.polyfit(times[hit], np.round(index[hit]), DRIFT_ORDER)
    index = np.polyval(coefficients, times)
    hit = np.abs(index - np.round(index)) * period <= GRID_TOLERANCE_S
    if hit.sum() < MIN_ONSETS:
        return None
    coefficients, covariance = np.polyfit(times[hit], np.round(index[hit]), DRIFT_ORDER, cov=True)
    return coefficients, covariance, times[hit]


def drift(model) -> dict:
    coefficients, covariance, fitted = model
    rate = np.polyder(coefficients)
    across = 60.0 * np.polyval(rate, np.linspace(fitted.min(), fitted.max(), DRIFT_SAMPLES))
    first, last = float(across.min()), float(across.max())
    span = last - first
    uncertainty = 120.0 * (fitted.max() - fitted.min()) * float(np.sqrt(covariance[0, 0]))
    return {
        "low_bpm": round(first, 3),
        "high_bpm": round(last, 3),
        "span_bpm": round(span, 3),
        "uncertainty_bpm": round(uncertainty, 3),
        "floor_bpm": DRIFT_FLOOR_BPM,
        "resolved": span > DRIFT_FLOOR_BPM,
    }


def measure(audio: Audio) -> dict:
    seconds = audio.samples.shape[1] / audio.sample_rate_hz
    if seconds < MIN_DURATION_S:
        raise Unmeasurable(f"{seconds:.1f} s of audio: too few beats to fit a grid to")

    values, times, envelope_hz = envelope(audio.samples, audio.sample_rate_hz)
    hits = onsets(values, times, envelope_hz)
    if hits.size < MIN_ONSETS:
        raise Unmeasurable(f"{hits.size} onsets found, fewer than {MIN_ONSETS}")

    top, at_edge = strongest_rate(values, envelope_hz)
    span_s = float(times[-1])

    alternatives = []
    for ratio in OCTAVE_RATIOS:
        tuned = refine(hits, top * ratio, span_s)
        fit = grid_fit(hits, tuned, span_s)
        alternatives.append({
            "bpm": round(tuned, 3),
            "ratio": round(ratio, 4),
            "occupancy": round(fit["occupancy"], 4),
            "coverage": round(fit["coverage"], 4),
            "onsets_fitted": fit["onsets_fitted"],
        })

    chosen = refine(hits, top, span_s)
    fit = grid_fit(hits, chosen, span_s)

    out = {
        "method": METHOD,
        "bpm": round(chosen, 3),
        "alternatives": alternatives,
        "onsets_detected": int(hits.size),
        "onsets_fitted": fit["onsets_fitted"],
        "occupancy": round(fit["occupancy"], 4),
        "coverage": round(fit["coverage"], 4),
        "search_range_bpm": [SEARCH_LOW_BPM, SEARCH_HIGH_BPM],
        "uncertainty": {"bpm": REFINE_STEP_BPM / 2.0, "drift_span_bpm": DRIFT_FLOOR_BPM},
    }
    if at_edge:
        out["caveats"] = [
            f"the score is still rising at the edge of the {SEARCH_LOW_BPM:.0f} to "
            f"{SEARCH_HIGH_BPM:.0f} BPM search range, so a stronger rate lies outside it "
            f"and the range, not the signal, chose this octave"
        ]
    absent = {}
    if fit["median_deviation_ms"] is None:
        absent["grid_fit_ms"] = "no onset fell on the grid, so there is no deviation to report"
    else:
        out["grid_fit_ms"] = round(fit["median_deviation_ms"], 2)

    model = beat_model(times, values, envelope_hz, chosen)
    if model is None:
        absent["drift"] = "the beat could not be tracked across the whole file"
    else:
        moved = drift(model)
        if moved["resolved"]:
            out["drift"] = moved
        else:
            absent["drift"] = (
                f"the fitted change of {moved['span_bpm']} BPM is under the "
                f"{DRIFT_FLOOR_BPM} BPM this method can resolve"
            )

    if absent:
        out["absent_because"] = absent
    return out
