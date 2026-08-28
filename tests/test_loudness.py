from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from scipy.signal import freqz

import rig
import signals as sig
from bench.decode import decode
from bench.measure import bs1770, ebur128, loudness

PUBLISHED_48K = {
    "shelf_b": [1.53512485958697, -2.69169618940638, 1.19839281085285],
    "shelf_a": [1.0, -1.69065929318241, 0.73248077421585],
    "highpass_b": [1.0, -2.0, 1.0],
    "highpass_a": [1.0, -1.99004745483398, 0.99007225036621],
}
TABLE_TOLERANCE = 1e-13


def derived_48k() -> dict[str, np.ndarray]:
    sb, sa = bs1770.shelf_coefficients(48000)
    hb, ha = bs1770.highpass_coefficients(48000)
    return {"shelf_b": sb, "shelf_a": sa, "highpass_b": hb, "highpass_a": ha}


def kweighting_gain(freq: float, rate: int) -> float:
    b1, a1 = bs1770.shelf_coefficients(rate)
    b2, a2 = bs1770.highpass_coefficients(rate)
    w = [2.0 * np.pi * freq / rate]
    return float(abs(freqz(b1, a1, worN=w)[1][0] * freqz(b2, a2, worN=w)[1][0]))


def analytic_lufs(amp: float, freq: float, rate: int, channels: int) -> float:
    z = (amp * kweighting_gain(freq, rate)) ** 2 / 2.0
    return float(-0.691 + 10.0 * np.log10(channels * z))


def test_kweighting_matches_the_published_48k_table():
    have = derived_48k()
    for name, want in PUBLISHED_48K.items():
        rig.control(float(np.max(np.abs(have[name] - np.array(want)))), 0.0,
                    TABLE_TOLERANCE, f"{name} against the published 48 kHz table")


def test_kweighting_table_check_can_fail(monkeypatch):
    monkeypatch.setattr(bs1770, "SHELF_F0_HZ", bs1770.SHELF_F0_HZ + 0.01)
    have = derived_48k()
    rig.rejects(float(np.max(np.abs(have["shelf_b"] - np.array(PUBLISHED_48K["shelf_b"])))), 0.0,
                TABLE_TOLERANCE, "a shelf at the wrong frequency")


@pytest.mark.parametrize("channels", [1, 2])
def test_loudness_of_a_tone_matches_the_filter_response(channels):
    x = sig.sine(1000, 20.0, amp=0.5, channels=channels)
    freq = sig.integer_cycles(1000, sig.SR, x.shape[1])
    got = bs1770.integrated(x, sig.SR)
    rig.control(got.lufs, analytic_lufs(0.5, freq, sig.SR, channels), 0.001,
                f"{channels} channel 1 kHz tone at 0.5")


def test_loudness_of_a_tone_can_fail():
    x = sig.sine(1000, 20.0, amp=0.5, channels=2)
    freq = sig.integer_cycles(1000, sig.SR, x.shape[1])
    unweighted = float(-0.691 + 10.0 * np.log10(2 * 0.5**2 / 2.0))
    rig.rejects(unweighted, analytic_lufs(0.5, freq, sig.SR, 2), 0.001, "unweighted loudness")


def test_gain_change_moves_both_instruments_by_the_same_decibels(tmp_path):
    x = sig.faded(sig.stereo(sig.noise(12.0, seed=1, amp=0.1)[0], sig.noise(12.0, seed=2, amp=0.1)[0]))
    before = loudness.measure(decode(sig.write(tmp_path / "a.wav", x)))
    after = loudness.measure(decode(sig.write(tmp_path / "b.wav", x * 10 ** (-3.0 / 20.0))))
    rig.covariance(before["integrated_lufs"], after["integrated_lufs"], -3.0, 0.06,
                   "ebur128 integrated under a 3 dB cut")
    rig.covariance(before["crosscheck"]["integrated_lufs"], after["crosscheck"]["integrated_lufs"],
                   -3.0, 0.001, "bs1770 integrated under a 3 dB cut")
    rig.covariance(before["true_peak_dbtp"], after["true_peak_dbtp"], -3.0, 0.11,
                   "true peak under a 3 dB cut")


def test_gain_change_does_not_move_loudness_range(tmp_path):
    loud = sig.noise(8.0, seed=1, amp=0.25)[0]
    quiet = sig.noise(8.0, seed=3, amp=0.025)[0]
    x = sig.faded(np.vstack([np.concatenate([loud, quiet])] * 2))
    before = loudness.measure(decode(sig.write(tmp_path / "a.wav", x)))
    after = loudness.measure(decode(sig.write(tmp_path / "b.wav", x * 10 ** (-6.0 / 20.0))))
    rig.invariance(before["lra_lu"], after["lra_lu"], 0.06, "loudness range under a 6 dB cut")


def test_material_below_the_absolute_gate_is_excluded():
    tone = sig.sine(1000, 20.0, amp=0.5, channels=2)
    with_quiet = np.concatenate([tone, tone * 10 ** (-80.0 / 20.0)], axis=1)
    got = bs1770.integrated(with_quiet, sig.SR)
    rig.control(got.lufs, bs1770.integrated(tone, sig.SR).lufs, 0.05,
                "20 s of tone plus 20 s at 80 dB down")
    assert got.blocks_over_absolute_gate < got.blocks_total


def test_material_below_the_relative_gate_is_excluded():
    tone = sig.sine(1000, 20.0, amp=0.5, channels=2)
    with_quiet = np.concatenate([tone, tone * 10 ** (-60.0 / 20.0)], axis=1)
    got = bs1770.integrated(with_quiet, sig.SR)
    assert got.blocks_over_absolute_gate == got.blocks_total
    assert got.blocks_over_relative_gate < got.blocks_total
    rig.control(got.lufs, bs1770.integrated(tone, sig.SR).lufs, 0.05,
                "20 s of tone plus 20 s at 60 dB down")


def test_the_gates_can_fail():
    tone = sig.sine(1000, 20.0, amp=0.5, channels=2)
    with_softer = np.concatenate([tone, tone * 10 ** (-5.0 / 20.0)], axis=1)
    got = bs1770.integrated(with_softer, sig.SR)
    assert got.blocks_over_relative_gate == got.blocks_total
    rig.rejects(got.lufs, bs1770.integrated(tone, sig.SR).lufs, 0.05,
                "20 s of tone plus 20 s at 5 dB down")


def intersample_control() -> tuple[np.ndarray, float, float]:
    n = int(8.0 * sig.SR)
    t = np.arange(n) / sig.SR
    one = 0.5 * np.sin(2.0 * np.pi * (sig.SR / 4.0) * t + np.pi / 4.0)
    x = sig.faded(np.vstack([one, one]))
    return x, 20.0 * np.log10(0.5), 20.0 * np.log10(0.5 / np.sqrt(2.0))


def test_true_peak_finds_the_intersample_peak(tmp_path):
    x, true_db, _ = intersample_control()
    got = loudness.measure(decode(sig.write(tmp_path / "tp.wav", x)))
    rig.control(got["true_peak_dbtp"], true_db, 0.06, "ebur128 true peak of a quarter rate sine")
    rig.control(got["crosscheck"]["true_peak_dbtp"], true_db, 0.005,
                "bs1770 true peak of the same, held to its own precision rather than ffmpeg's")


def test_true_peak_can_fail(tmp_path):
    x, true_db, sample_db = intersample_control()
    got = loudness.measure(decode(sig.write(tmp_path / "tp.wav", x)))
    rig.control(got["sample_peak_dbfs"], sample_db, 0.06, "sample peak of a quarter rate sine")
    rig.rejects(got["sample_peak_dbfs"], true_db, 0.06, "sample peak passed off as true peak")


def test_lra_of_two_levels_is_their_separation():
    loud = sig.sine(1000, 20.0, amp=0.5, channels=2)
    x = np.concatenate([loud, loud * 10 ** (-12.0 / 20.0)], axis=1)
    rig.control(bs1770.loudness_range(x, sig.SR), 12.0, 0.3, "20 s at one level then 20 s 12 dB down")


def test_lra_of_a_constant_level_is_zero():
    rig.control(bs1770.loudness_range(sig.sine(1000, 20.0, amp=0.5, channels=2), sig.SR), 0.0,
                0.01, "loudness range of a constant tone")


def test_lra_can_fail():
    loud = sig.sine(1000, 20.0, amp=0.5, channels=2)
    x = np.concatenate([loud, loud * 10 ** (-12.0 / 20.0)], axis=1)
    rig.rejects(bs1770.loudness_range(x, sig.SR), 0.0, 0.01, "a 12 LU spread read as constant")


def test_silence_has_no_loudness_and_no_peak(tmp_path):
    got = loudness.measure(decode(sig.write(tmp_path / "s.wav", sig.silence(8.0, channels=2))))
    assert "integrated_lufs" not in got
    assert "true_peak_dbtp" not in got
    assert "sample_peak_dbfs" not in got
    assert got["absent_because"]["integrated_lufs"]
    assert got["absent_because"]["true_peak_dbtp"] == "digital silence has no peak"


def test_shorter_than_a_gating_block_has_no_integrated_loudness(tmp_path):
    x = sig.faded(sig.sine(1000, 0.30, amp=0.5, channels=2), seconds=0.05)
    got = loudness.measure(decode(sig.write(tmp_path / "short.wav", x)))
    assert "integrated_lufs" not in got
    assert "gating block" in got["absent_because"]["integrated_lufs"]
    assert got["true_peak_dbtp"] is not None


def test_shorter_than_a_short_term_window_has_no_loudness_range(tmp_path):
    x = sig.faded(sig.sine(1000, 2.0, amp=0.5, channels=2), seconds=0.1)
    got = loudness.measure(decode(sig.write(tmp_path / "brief.wav", x)))
    assert "lra_lu" not in got
    assert "short term window" in got["absent_because"]["lra_lu"]
    assert got["integrated_lufs"] is not None


def test_metadata_peaks_are_linear_not_decibels(tmp_path):
    x, true_db, _ = intersample_control()
    path = sig.write(tmp_path / "tp.wav", x * 1.98)
    metadata, summary = ebur128._run(path)
    linear = metadata["true_peak"]
    assert linear > 0.9
    rig.control(float(20.0 * np.log10(linear)), summary["true_peak"], 0.06,
                "the linear metadata peak converted to decibels")
    rig.rejects(linear, summary["true_peak"], 0.06, "the linear metadata peak read as decibels")


def test_a_second_summary_block_is_refused(monkeypatch, tmp_path):
    doubled = SimpleNamespace(
        returncode=0,
        stdout="lavfi.r128.I=-14.000\nlavfi.r128.LRA=1.000\nlavfi.r128.true_peak=0.500\n",
        stderr="Summary:\n  I: -14.0 LUFS\nSummary:\n  I: -9.0 LUFS\n",
    )
    monkeypatch.setattr(ebur128.subprocess, "run", lambda *a, **k: doubled)
    with pytest.raises(ebur128.Ebur128Error, match="exactly one"):
        ebur128.measure(tmp_path / "whatever.wav", 30.0)


@pytest.mark.parametrize("name", ["stereo noise", "mono noise", "tone", "quarter rate sine", "two level"])
def test_the_two_instruments_agree_within_the_stated_tolerances(tmp_path, name):
    material = {
        "stereo noise": lambda: sig.stereo(sig.noise(10.0, seed=1, amp=0.1)[0],
                                           sig.noise(10.0, seed=2, amp=0.1)[0]),
        "mono noise": lambda: sig.noise(10.0, seed=5, amp=0.1),
        "tone": lambda: sig.sine(1000, 10.0, amp=0.5, channels=2),
        "quarter rate sine": lambda: intersample_control()[0],
        "two level": lambda: np.concatenate([sig.sine(1000, 8.0, amp=0.5, channels=2),
                                             sig.sine(1000, 8.0, amp=0.125, channels=2)], axis=1),
    }[name]()
    got = loudness.measure(decode(sig.write(tmp_path / "m.wav", sig.faded(material))))
    cross = got["crosscheck"]
    assert "beyond_tolerance" not in cross, (name, cross["delta"])
    assert "only_one_instrument_reported" not in cross, (name, cross)


def test_a_discontinuity_makes_them_disagree_about_true_peak(tmp_path):
    n = int(8.0 * sig.SR)
    t = np.arange(n) / sig.SR
    one = 0.5 * np.sin(2.0 * np.pi * (sig.SR / 4.0) * t + np.pi / 4.0)
    got = loudness.measure(decode(sig.write(tmp_path / "abrupt.wav", np.vstack([one, one]))))
    assert got["crosscheck"]["beyond_tolerance"] == ["true_peak_db"]
    assert abs(got["crosscheck"]["delta"]["true_peak_db"]) > 0.3
