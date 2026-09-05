"""A true peak limiter whose attack and release are chosen by search, not by taste.

The gain envelope is built from the same oversampled peak the bench measures with, so
what it limits is what the bench reports. Nothing here picks an attack or a release:
that is master.py's job, and it picks them by measuring the result.

The output is measured before it is returned. On everything this repo has measured,
the envelope meets the ceiling on its own to four decimal places, so the constant trim
that follows it has never had to act. It stays because the alternative is assuming a
property of the method rather than checking it, and it reports what it took, so a trim
that is not zero is a report that the envelope missed. A constant moves no band and no
crest, so if it ever acts it costs only loudness.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import minimum_filter1d
from scipy.signal import upfirdn

from bench.measure import bs1770

LOOKAHEAD_MULTIPLE = 2

# A constant scales the interpolated signal by exactly the same constant, so one pass
# reaches the ceiling and the rest are there to catch the arithmetic being wrong.
CEILING_PASSES = 3
CEILING_TOLERANCE_DB = 0.0001


def required_gain(samples: np.ndarray, rate: int, ceiling_dbtp: float,
                  oversample: int = bs1770.TRUE_PEAK_OVERSAMPLE) -> np.ndarray:
    """The most gain each input sample may keep without any channel going over.

    The peak is taken between samples, not at them, so a signal that only exceeds the
    ceiling on reconstruction is still caught.
    """
    x = np.atleast_2d(np.asarray(samples, dtype=np.float64))
    h = bs1770.oversampling_filter(oversample)
    frames = x.shape[1]
    # The interpolating filter is linear phase, so its output lags its input by half
    # its length. Without removing that lag every peak is charged to a sample 16 frames
    # later than the one it came from, and the gain arrives after the peak it is for.
    delay = (h.size - 1) // 2
    usable = frames * oversample
    peak = np.zeros(frames)
    for channel in x:
        up = np.abs(upfirdn(h, channel, oversample, 1))
        if up.size < delay + usable:
            up = np.pad(up, (0, delay + usable - up.size))
        peak = np.maximum(peak, up[delay:delay + usable].reshape(frames, oversample).max(axis=1))
    ceiling = 10.0 ** (ceiling_dbtp / 20.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        gain = np.where(peak > ceiling, ceiling / peak, 1.0)
    return np.clip(np.nan_to_num(gain, nan=1.0), 0.0, 1.0)


def _running_min(values: np.ndarray, window: int) -> np.ndarray:
    """Every sample's own reduction, held over the whole window around it. Linear in
    the file rather than in the file times the window, which on a three minute track
    at a 10 ms attack is the difference between a tenth of a second and two seconds."""
    if window <= 1:
        return values
    return minimum_filter1d(values, size=window, mode="nearest")


def _release(values: np.ndarray, rate: int, release_ms: float) -> np.ndarray:
    """Fall at once, come back over the release. A limiter that recovers instantly
    modulates the programme at the rate of its own peaks."""
    if release_ms <= 0.0:
        return values
    alpha = float(1.0 - np.exp(-1.0 / max(release_ms * 1e-3 * rate, 1.0)))
    # Over plain floats rather than over the array. The recursion cannot be vectorised,
    # and indexing a numpy array a sample at a time costs four times as much.
    out, running = [], float(values[0])
    for wanted in values.tolist():
        running = wanted if wanted < running else running + alpha * (wanted - running)
        out.append(running)
    return np.asarray(out)


def _smoothed(needed: np.ndarray, rate: int, attack_ms: float,
              release_ms: float) -> np.ndarray:
    """The shaped curve, before it is held back to what the ceiling allows. The
    convolution here is the step that can lift the curve above that."""
    attack = max(1, int(round(attack_ms * 1e-3 * rate)))
    out = _running_min(needed, attack * LOOKAHEAD_MULTIPLE)
    if attack > 1:
        window = np.hanning(attack + 2)[1:-1]
        window = window / window.sum()
        out = np.convolve(np.pad(out, (attack, attack), mode="edge"),
                          window, mode="same")[attack:-attack]
    return _release(out, rate, release_ms)


def envelope(samples: np.ndarray, rate: int, ceiling_dbtp: float,
             attack_ms: float, release_ms: float,
             needed: np.ndarray | None = None) -> np.ndarray:
    """`needed` is the required gain, which does not depend on attack or release. A
    search over those two recomputes everything else and should not recompute it."""
    if needed is None:
        needed = required_gain(samples, rate, ceiling_dbtp)
    return np.minimum(_smoothed(needed, rate, attack_ms, release_ms), needed)


def shaped(samples: np.ndarray, rate: int, ceiling_dbtp: float, attack_ms: float,
           release_ms: float, needed: np.ndarray | None = None
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The output, the envelope that made it, and the gain the ceiling required.

    The one place the audio is touched, so what a search measures and what is written
    to disk cannot be two different signals. What the search does not do is measure the
    true peak of every candidate, because that is a check on the file that gets written
    and it costs as much as everything else in the loop put together.
    """
    x = np.asarray(samples, dtype=np.float64)
    if needed is None:
        needed = required_gain(x, rate, ceiling_dbtp)
    gain = envelope(x, rate, ceiling_dbtp, attack_ms, release_ms, needed)
    return x * gain, gain, needed


def apply(samples: np.ndarray, rate: int, ceiling_dbtp: float,
          attack_ms: float, release_ms: float,
          needed: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """Shaped, then measured. A trim that is not zero is a report that the envelope
    missed the ceiling, which has not happened on anything measured here."""
    out, gain, needed = shaped(samples, rate, ceiling_dbtp, attack_ms, release_ms, needed)
    trim = 0.0
    for _ in range(CEILING_PASSES):
        peak = bs1770.true_peak_dbtp(out * (10.0 ** (trim / 20.0)))
        if peak is None or peak <= ceiling_dbtp + CEILING_TOLERANCE_DB:
            break
        trim += ceiling_dbtp - peak
    return out * (10.0 ** (trim / 20.0)), worked(gain, needed, trim)


def worked(gain: np.ndarray, needed: np.ndarray, trim_db: float | None = None) -> dict:
    """How much it took off, and how much of the file was over the ceiling to begin
    with. The second is read off the required gain rather than off the envelope: a
    release that recovers exponentially never returns to exactly one, so counting the
    envelope would report every sample after the first reduction as reduced.

    The trim is absent unless one was measured. A search over settings never measures
    it, and a default zero sitting where a measurement belongs reads as a file that was
    checked and found to need nothing.
    """
    out = {
        "largest_db": round(float(-20.0 * np.log10(max(gain.min(), 1e-12))), 3),
        "share_over_the_ceiling": round(float((needed < 1.0).mean()), 6),
    }
    if trim_db is not None:
        out["constant_trim_db"] = round(float(trim_db), 3)
    return out
