from __future__ import annotations

import numpy as np


class Toothless(AssertionError):
    """Raised when a check accepted a value it was supposed to reject."""


def within(measured: float, expected: float, tol: float) -> bool:
    return abs(float(measured) - float(expected)) <= tol


def control(measured: float, expected: float, tol: float, what: str) -> None:
    if not within(measured, expected, tol):
        raise AssertionError(f"{what}: measured {measured!r}, expected {expected!r} within {tol!r}")


def rejects(measured: float, expected: float, tol: float, what: str) -> None:
    if within(measured, expected, tol):
        raise Toothless(
            f"{what}: tolerance {tol!r} accepted {measured!r} as {expected!r}. "
            "This check cannot fail, so it proves nothing."
        )


def invariance(before: float, after: float, tol: float, what: str) -> None:
    if not within(after, before, tol):
        raise AssertionError(f"{what}: moved from {before!r} to {after!r}, allowed {tol!r}")


def covariance(before: float, after: float, expected_delta: float, tol: float, what: str) -> None:
    delta = float(after) - float(before)
    if not within(delta, expected_delta, tol):
        raise AssertionError(
            f"{what}: moved by {delta!r}, expected {expected_delta!r} within {tol!r} "
            f"({before!r} to {after!r})"
        )


def power_in_band(x: np.ndarray, sr: int, lo: float, hi: float) -> float:
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    freqs = np.fft.rfftfreq(x.shape[1], 1.0 / sr)
    sel = (freqs >= lo) & (freqs < hi)
    return float(sum(np.sum(np.abs(np.fft.rfft(ch)[sel]) ** 2) for ch in x))


def fraction_above(x: np.ndarray, sr: int, hz: float, reference_total: float | None = None) -> float:
    total = reference_total if reference_total is not None else power_in_band(x, sr, 0.0, sr / 2.0)
    return power_in_band(x, sr, hz, sr / 2.0) / max(total, 1e-30)
