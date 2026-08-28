"""The limiter's claims. It says it limits what the bench measures, that it does not
recover instantly, and that its last step stops smoothing from undoing its own work."""

from __future__ import annotations

import numpy as np
import pytest

import rig
import signals as sig
from bench import limiter
from bench.measure import bs1770

CEILING = -1.0
PEAK_TOLERANCE_DB = 0.02
BETWEEN_SAMPLES_DB = 3.01
BETWEEN_SAMPLES_TOLERANCE_DB = 0.15
RELEASE_TOLERANCE_FRAC = 0.15
RECOVERY = 1.0 - 1.0 / np.e
FILTER_DELAY_FRAMES = (bs1770.oversampling_filter().size - 1) // 2 // bs1770.TRUE_PEAK_OVERSAMPLE


def between_samples(seconds=2.0, sample_dbfs=-1.5, rate=sig.SR):
    """Samples land at 0.7071 of the peak, so the true peak sits 3.01 dB above the
    largest sample and 1.5 dB over the ceiling. A limiter reading samples sees nothing."""
    n = int(round(seconds * rate))
    amp = 10.0 ** (sample_dbfs / 20.0) / np.sin(np.pi / 4.0)
    x = amp * np.sin(np.pi * np.arange(n) / 2.0 + np.pi / 4.0)
    return np.vstack([x, x])


def loud_burst(seconds=2.0, rate=sig.SR, quiet=0.2, loud=0.9, at=0.5, length=0.02):
    x = quiet * np.sin(2.0 * np.pi * 220.0 * np.arange(int(seconds * rate)) / rate)
    i = int(at * rate)
    x[i : i + int(length * rate)] *= loud / quiet
    return np.vstack([x, x])


def click(seconds=1.0, rate=sig.SR, at=0.5, width=64, amp=0.99, quiet=0.05):
    """One loud, short, isolated peak at a frame this file knows the number of."""
    n = int(round(seconds * rate))
    x = quiet * np.sin(2.0 * np.pi * 220.0 * np.arange(n) / rate)
    i = int(round(at * rate))
    x[i : i + width] += amp * np.hanning(width)
    return np.vstack([x, x])


CLICK_PEAK_FRAME = int(round(0.5 * sig.SR)) + 32


def sweep(seconds=2.0, rate=sig.SR, amp=0.99):
    n = int(round(seconds * rate))
    x = amp * np.sin(2.0 * np.pi * np.cumsum(np.linspace(50.0, rate / 2.0, n)) / rate)
    return np.vstack([x, x])


def noise_over(seconds=2.0, rate=sig.SR, amp=2.0, seed=5):
    rng = np.random.default_rng(seed)
    return amp * rng.standard_normal((2, int(round(seconds * rate))))


def test_the_peak_it_limits_is_the_one_between_samples():
    x = between_samples()
    rig.control(bs1770.sample_peak_dbfs(x), -1.5, 0.01, "the largest sample before limiting")
    rig.control(bs1770.true_peak_dbtp(x) - bs1770.sample_peak_dbfs(x), BETWEEN_SAMPLES_DB,
                BETWEEN_SAMPLES_TOLERANCE_DB,
                "how far the peak between samples sits above the largest sample")
    out, _ = limiter.apply(x, sig.SR, CEILING, 1.0, 50.0)
    assert bs1770.true_peak_dbtp(out) <= CEILING + PEAK_TOLERANCE_DB, (
        "a signal whose samples are all under the ceiling still went over between them"
    )


def test_reading_samples_instead_would_fail_this():
    x = between_samples()
    rig.rejects(bs1770.true_peak_dbtp(x), CEILING, PEAK_TOLERANCE_DB,
                "the unlimited signal against the ceiling")


def test_a_signal_under_the_ceiling_is_returned_untouched():
    x = 0.1 * sig.sine(440.0, 2.0, channels=2)
    out, worked = limiter.apply(x, sig.SR, CEILING, 1.0, 50.0)
    assert np.array_equal(out, x), "a limiter with nothing to do must change nothing at all"
    rig.control(worked["share_over_the_ceiling"], 0.0, 0.0, "the share it says was over")
    rig.control(worked["constant_trim_db"], 0.0, 0.0, "the trim it says it took")


def test_that_untouched_check_can_fail():
    x = sig.sine(440.0, 2.0, channels=2, amp=0.95)
    out, _ = limiter.apply(x, sig.SR, CEILING, 1.0, 50.0)
    if np.array_equal(out, x):
        raise rig.Toothless(
            "a signal well over the ceiling came back identical, so the equality check "
            "above cannot tell a working limiter from one that does nothing"
        )


@pytest.mark.parametrize("attack_ms", [0.5, 2.0, 5.0, 10.0])
def test_the_lookahead_is_wider_than_the_smoothing(attack_ms):
    """The elementwise minimum at the end of envelope() is a guard that the running
    minimum already makes unnecessary: it looks LOOKAHEAD_MULTIPLE times further than
    the window averaged over it, so every value averaged is already at or under what
    the sample needed. This is the control on that property, not on the guard."""
    needed = limiter.required_gain(loud_burst(), sig.SR, CEILING)
    lifted = limiter._smoothed(needed, sig.SR, attack_ms, 100.0) > needed + 1e-12
    assert not lifted.any(), (
        f"{int(lifted.sum())} samples came out of the smoothing above what the ceiling "
        "allowed them, which the running minimum is supposed to make impossible"
    )


def test_that_property_is_the_lookahead_and_not_luck(monkeypatch):
    monkeypatch.setattr(limiter, "LOOKAHEAD_MULTIPLE", 0)
    needed = limiter.required_gain(loud_burst(), sig.SR, CEILING)
    lifted = limiter._smoothed(needed, sig.SR, 5.0, 100.0) > needed + 1e-12
    if not lifted.any():
        raise rig.Toothless(
            "smoothing with no lookahead at all still lifted nothing, so the test "
            "above is not measuring the lookahead"
        )


def test_the_release_takes_the_time_it_says():
    dip = np.ones(sig.SR)
    dip[:100] = 0.5
    for release_ms in (20.0, 100.0):
        out = limiter._release(dip, sig.SR, release_ms)
        back = out[100:]
        target = out[99] + RECOVERY * (1.0 - out[99])
        took = int(np.argmax(back >= target)) / sig.SR * 1000.0
        rig.control(took, release_ms, release_ms * RELEASE_TOLERANCE_FRAC,
                    f"time to recover {round(100 * RECOVERY)} percent at {release_ms} ms")


def test_the_release_check_can_fail():
    dip = np.ones(sig.SR)
    dip[:100] = 0.5
    out = limiter._release(dip, sig.SR, 20.0)
    back = out[100:]
    target = out[99] + RECOVERY * (1.0 - out[99])
    took = int(np.argmax(back >= target)) / sig.SR * 1000.0
    rig.rejects(took, 100.0, 100.0 * RELEASE_TOLERANCE_FRAC,
                "a 20 ms release measured against a 100 ms claim")


def test_the_reduction_lands_on_the_peak_not_after_it():
    """The interpolating filter lags its input by 16 frames. Charging a peak to the
    frame 16 later puts the reduction after the thing it is for."""
    needed = limiter.required_gain(click(), sig.SR, CEILING)
    rig.control(int(np.argmin(needed)), CLICK_PEAK_FRAME, FILTER_DELAY_FRAMES / 4.0,
                "the frame the ceiling asks the most reduction at")


def test_that_alignment_check_can_fail():
    needed = limiter.required_gain(click(), sig.SR, CEILING)
    rig.rejects(int(np.argmin(needed)), CLICK_PEAK_FRAME + FILTER_DELAY_FRAMES,
                FILTER_DELAY_FRAMES / 4.0,
                "the reduction placed where an uncorrected filter delay would put it")


def test_what_it_reports_about_its_own_work():
    x = loud_burst()
    needed = limiter.required_gain(x, sig.SR, CEILING)
    gain = limiter.envelope(x, sig.SR, CEILING, 1.0, 100.0, needed)
    worked = limiter.worked(gain, needed)

    rig.control(worked["largest_db"], -20.0 * np.log10(gain.min()), 1e-3,
                "the largest reduction reported")
    rig.control(worked["share_over_the_ceiling"], float((needed < 1.0).mean()), 1e-6,
                "the share of the file reported as over the ceiling")
    assert worked["share_over_the_ceiling"] < 0.05, (
        "a 20 ms burst in a 2 second file is 1 percent of it, and anything near the "
        "whole file means the recovery tail is being counted as limiting"
    )


@pytest.mark.parametrize("name,signal", [
    ("a sine at a quarter of the rate, where every peak is between samples", between_samples),
    ("an isolated click", click),
    ("a sweep from 50 Hz to the top of the band", lambda: sweep()),
    ("noise at four times the ceiling", lambda: noise_over()),
])
@pytest.mark.parametrize("attack_ms", [0.5, 10.0])
def test_the_envelope_meets_the_ceiling_without_the_trim(name, signal, attack_ms):
    """The trim is a check on this, not a correction that carries it. If it ever has
    to act, the envelope missed, and this is the test that says so first."""
    x = signal()
    out, worked = limiter.apply(x, sig.SR, CEILING, attack_ms, 20.0)
    rig.control(bs1770.true_peak_dbtp(out), CEILING, limiter.CEILING_TOLERANCE_DB,
                f"the ceiling on {name} at {attack_ms} ms")
    rig.control(worked["constant_trim_db"], 0.0, 0.0,
                f"the trim needed on {name} at {attack_ms} ms, which should be none")


def test_the_ceiling_check_can_fail():
    rig.rejects(bs1770.true_peak_dbtp(noise_over()), CEILING, limiter.CEILING_TOLERANCE_DB,
                "unlimited noise measured against the ceiling")
