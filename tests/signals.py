from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100


def integer_cycles(freq_target: float, sr: int, frames: int) -> float:
    cycles = max(1, round(freq_target * frames / sr))
    return cycles * sr / frames


def sine(freq: float, seconds: float, sr: int = SR, amp: float = 0.5, channels: int = 1) -> np.ndarray:
    n = int(round(seconds * sr))
    f = integer_cycles(freq, sr, n)
    t = np.arange(n, dtype=np.float64) / sr
    one = amp * np.sin(2 * np.pi * f * t)
    return np.tile(one, (channels, 1))


def stereo(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.vstack([np.ravel(left), np.ravel(right)])


def silence(seconds: float, sr: int = SR, channels: int = 1) -> np.ndarray:
    return np.zeros((channels, int(round(seconds * sr))), dtype=np.float64)


def dc(offset: float, seconds: float, sr: int = SR, channels: int = 1) -> np.ndarray:
    return np.full((channels, int(round(seconds * sr))), offset, dtype=np.float64)


def noise(seconds: float, sr: int = SR, channels: int = 1, seed: int = 0, amp: float = 0.2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return amp * rng.standard_normal((channels, int(round(seconds * sr))))


def pcm_ramp(bits: int, count: int) -> np.ndarray:
    scale = 1 << (bits - 1)
    k = np.linspace(-scale + 1, scale - 1, count).round()
    return (k / scale).reshape(1, -1)


def write(path: Path, samples: np.ndarray, sr: int = SR, subtype: str = "PCM_24") -> Path:
    sf.write(str(path), np.atleast_2d(samples).T, sr, subtype=subtype)
    return path


def encode(source: Path, out: Path, *args: str) -> Path:
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(source), *args, str(out)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed: {r.stderr.decode(errors='replace').strip()}")
    return out


def faded(x: np.ndarray, seconds: float = 0.25, sr: int = SR) -> np.ndarray:
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    n = x.shape[1]
    f = int(round(seconds * sr))
    w = np.ones(n)
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(f) / f)
    w[:f] = ramp
    w[-f:] = ramp[::-1]
    return x * w


def flat_spectrum(seconds: float, sr: int = SR, channels: int = 2, seed: int = 0,
                  amp: float = 0.1) -> np.ndarray:
    n = int(round(seconds * sr))
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(channels):
        bins = n // 2 + 1
        mag = np.ones(bins)
        mag[0] = 0.0
        phase = rng.uniform(0.0, 2.0 * np.pi, bins)
        phase[0] = 0.0
        if n % 2 == 0:
            phase[-1] = 0.0
        y = np.fft.irfft(mag * np.exp(1j * phase), n)
        out.append(amp * y / np.max(np.abs(y)))
    return np.vstack(out)
