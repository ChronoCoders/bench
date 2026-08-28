from __future__ import annotations

import numpy as np

import signals as sig

FADE_FRACTION = 0.25
DECAY_LENGTHS = 9


def _hit(tau: float, body, rate: int = sig.SR) -> np.ndarray:
    n = int(rate * tau * DECAY_LENGTHS)
    t = np.arange(n) / rate
    x = body(t) * np.exp(-t / tau)
    k = int(n * FADE_FRACTION)
    x[n - k :] *= 0.5 * (1.0 + np.cos(np.pi * np.arange(k) / k))
    return x


def kick(rate: int = sig.SR, tau: float = 0.045, top: float = 110.0, bottom: float = 45.0):
    def body(t):
        f = bottom + (top - bottom) * np.exp(-t / 0.02)
        return np.sin(2.0 * np.pi * np.cumsum(f) / rate)
    return _hit(tau, body, rate)


def snare(rate: int = sig.SR, tau: float = 0.03, seed: int = 7):
    n = int(rate * tau * DECAY_LENGTHS)
    g = np.random.default_rng(seed).standard_normal(n)
    return _hit(tau, lambda t: 0.7 * g + 0.3 * np.sin(2.0 * np.pi * 190.0 * t), rate)


def hat(rate: int = sig.SR, tau: float = 0.008, seed: int = 11):
    n = int(rate * tau * DECAY_LENGTHS)
    g = np.random.default_rng(seed).standard_normal(n)
    return _hit(tau, lambda t: np.diff(np.concatenate([[0.0], g])), rate)


def bass(f: float, rate: int = sig.SR, tau: float = 0.25):
    return _hit(tau, lambda t: 2.0 * ((t * f) % 1.0) - 1.0, rate)


def pad(f: float, seconds: float = 2.0, rate: int = sig.SR):
    t = np.arange(int(rate * seconds)) / rate
    x = sum(np.sin(2.0 * np.pi * f * m * t) / m for m in (1, 2, 3))
    return x * np.sin(np.pi * np.arange(x.size) / x.size) ** 2


KICK, SNARE, HAT = kick(), snare(), hat()
BASS = [bass(f) for f in (55.0, 65.4, 73.4)]
PADS = [pad(f) for f in (110.0, 130.8)]

PATTERNS = {
    "click": [(0.0, 1.0, KICK, 1.0)],
    "kick_hat_snare": [(0.0, 1.0, KICK, 1.0), (0.0, 0.5, HAT, 0.35), (1.0, 2.0, SNARE, 0.8)],
    "half_time": [(0.0, 4.0, KICK, 1.0), (2.0, 4.0, SNARE, 0.9), (0.0, 1.0, HAT, 0.3)],
    "fast_hats": [(0.0, 1.0, KICK, 1.0), (0.0, 0.25, HAT, 0.3), (2.0, 4.0, SNARE, 0.8)],
    "syncopated": [(0.0, 4.0, KICK, 1.0), (1.75, 4.0, KICK, 0.9), (2.5, 4.0, KICK, 0.9),
                   (1.0, 2.0, SNARE, 0.8), (0.0, 0.5, HAT, 0.3)],
    "with_bass": [(0.0, 1.0, KICK, 1.0), (1.0, 2.0, SNARE, 0.8), (0.0, 0.5, HAT, 0.3),
                  (0.0, 2.0, BASS[0], 0.6), (1.0, 2.0, BASS[1], 0.6)],
    "dense": [(0.0, 1.0, KICK, 1.0), (1.0, 2.0, SNARE, 0.8), (0.0, 0.25, HAT, 0.25),
              (0.0, 2.0, BASS[0], 0.6), (1.0, 2.0, BASS[2], 0.6),
              (0.0, 8.0, PADS[0], 0.4), (4.0, 8.0, PADS[1], 0.4)],
}


def steady(bpm: float):
    return lambda k: k * 60.0 / bpm


def ramp(start_bpm: float, end_bpm: float, seconds: float):
    a = start_bpm / 60.0
    b = (end_bpm - start_bpm) / 60.0 / seconds
    if abs(b) < 1e-12:
        return lambda k: k / a
    return lambda k: (np.sqrt(a * a + 2.0 * b * k) - a) / b


def schedule(bpm_of_time, seconds: float, resolution: float = 0.001):
    t = np.arange(0.0, seconds, resolution)
    beats = np.cumsum(np.asarray(bpm_of_time(t), dtype=np.float64) / 60.0) * resolution
    return lambda k: float(np.interp(k, beats, t)) if k <= beats[-1] else seconds + 1.0


def arch(low: float, high: float, seconds: float):
    return schedule(lambda t: low + (high - low) * np.sin(np.pi * t / seconds), seconds)


def beat_times(beats, seconds: float, step: float = 1.0, offset: float = 0.0) -> np.ndarray:
    out, k = [], offset
    while True:
        t = beats(k)
        if t > seconds:
            return np.asarray(out)
        out.append(t)
        k += step


def build(pattern: str, bpm: float, seconds: float = 120.0, beats=None,
          jitter: float = 0.0, seed: int = 3, rate: int = sig.SR) -> np.ndarray:
    beats_at = beats or steady(bpm)
    out = np.zeros(int(seconds * rate) + rate)
    rng = np.random.default_rng(seed)
    for offset, period, hit, gain in PATTERNS[pattern]:
        for t in beat_times(beats_at, seconds, period, offset):
            shift = rng.normal(0.0, jitter) if jitter else 0.0
            i = int(round((t + shift) * rate))
            if 0 <= i < out.size - hit.size:
                out[i : i + hit.size] += gain * hit
    x = out[: int(seconds * rate)]
    x = x / (np.max(np.abs(x)) + 1e-12) * 0.7
    return np.vstack([x, x])


def limit(x: np.ndarray, drive: float = 6.0) -> np.ndarray:
    return np.tanh(drive * x) / np.tanh(drive)


def shelf(x: np.ndarray, rate: int, f0: float, gain_db: float, kind: str) -> np.ndarray:
    from scipy.signal import sosfilt
    A = 10.0 ** (gain_db / 40.0)
    w = 2.0 * np.pi * f0 / rate
    alpha = np.sin(w) / 2.0 * np.sqrt(2.0)
    c, s = np.cos(w), 2.0 * np.sqrt(A) * alpha
    if kind == "low":
        b = [A * ((A + 1) - (A - 1) * c + s), 2 * A * ((A - 1) - (A + 1) * c),
             A * ((A + 1) - (A - 1) * c - s)]
        a = [(A + 1) + (A - 1) * c + s, -2 * ((A - 1) + (A + 1) * c),
             (A + 1) + (A - 1) * c - s]
    else:
        b = [A * ((A + 1) + (A - 1) * c + s), -2 * A * ((A - 1) + (A + 1) * c),
             A * ((A + 1) + (A - 1) * c - s)]
        a = [(A + 1) - (A - 1) * c + s, 2 * ((A - 1) - (A + 1) * c),
             (A + 1) - (A - 1) * c - s]
    return sosfilt(np.array([b + a]) / a[0], x, axis=1)
