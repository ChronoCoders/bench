from __future__ import annotations

import numpy as np
import pytest

import rig
import signals as sig
from bench.decode import decode
from bench.measure import stereo

CORRELATION_TOLERANCE = 0.01
WIDTH_TOLERANCE_DB = 0.05


def mixed_pair(common, independent, seconds=20.0):
    shared = sig.noise(seconds, seed=1, amp=1.0)[0]
    left = common * shared + independent * sig.noise(seconds, seed=2, amp=1.0)[0]
    right = common * shared + independent * sig.noise(seconds, seed=3, amp=1.0)[0]
    peak = max(np.max(np.abs(left)), np.max(np.abs(right)))
    return np.vstack([left, right]) * (0.5 / peak)


def analytic_correlation(common, independent):
    return common**2 / (common**2 + independent**2)


def analytic_width_db(common, independent):
    side = independent**2 / 2.0
    mid = common**2 + independent**2 / 2.0
    return 10.0 * np.log10(side / mid)


def test_correlation_of_identical_channels_is_one(tmp_path):
    one = sig.noise(10.0, seed=4, amp=0.3)[0]
    got = stereo.measure(decode(sig.write(tmp_path / "mono.wav", np.vstack([one, one]))))
    rig.control(got["correlation"], 1.0, 1e-9, "correlation of two identical channels")


def test_correlation_of_inverted_channels_is_minus_one(tmp_path):
    one = sig.noise(10.0, seed=4, amp=0.3)[0]
    got = stereo.measure(decode(sig.write(tmp_path / "inv.wav", np.vstack([one, -one]))))
    rig.control(got["correlation"], -1.0, 1e-9, "correlation of a channel against its inverse")


@pytest.mark.parametrize("common,independent", [(1.0, 1.0), (2.0, 1.0), (1.0, 3.0)])
def test_correlation_matches_the_mix_ratio(tmp_path, common, independent):
    x = mixed_pair(common, independent)
    got = stereo.measure(decode(sig.write(tmp_path / "mix.wav", x)))
    rig.control(got["correlation"], analytic_correlation(common, independent),
                CORRELATION_TOLERANCE, f"correlation of a {common} to {independent} mix")


def test_correlation_can_fail(tmp_path):
    x = mixed_pair(1.0, 3.0)
    got = stereo.measure(decode(sig.write(tmp_path / "mix.wav", x)))
    rig.rejects(got["correlation"], analytic_correlation(2.0, 1.0), CORRELATION_TOLERANCE,
                "a mostly independent pair read as a mostly common one")


def raw_correlation(samples):
    left, right = samples
    return float(np.dot(left, right) / np.sqrt(np.dot(left, left) * np.dot(right, right)))


def test_correlation_does_not_move_under_direct_current(tmp_path):
    x = mixed_pair(1.0, 3.0)
    before = stereo.measure(decode(sig.write(tmp_path / "a.wav", x)))["correlation"]
    after = stereo.measure(decode(sig.write(tmp_path / "b.wav", x + 0.2)))["correlation"]
    rig.invariance(before, after, 1e-4, "correlation with 0.2 of direct current added")


def test_the_direct_current_invariance_can_fail():
    x = mixed_pair(1.0, 3.0)
    rig.rejects(raw_correlation(x + 0.2), raw_correlation(x), 1e-4,
                "the same correlation taken without removing the mean")


@pytest.mark.parametrize("common,independent", [(1.0, 1.0), (2.0, 1.0), (1.0, 3.0)])
def test_width_matches_the_mix_ratio(tmp_path, common, independent):
    x = mixed_pair(common, independent)
    got = stereo.measure(decode(sig.write(tmp_path / "mix.wav", x)))
    rig.control(got["width_side_mid_db"], analytic_width_db(common, independent),
                WIDTH_TOLERANCE_DB, f"side over mid of a {common} to {independent} mix")


def test_width_can_fail(tmp_path):
    x = mixed_pair(1.0, 3.0)
    got = stereo.measure(decode(sig.write(tmp_path / "mix.wav", x)))
    rig.rejects(got["width_side_mid_db"], analytic_width_db(2.0, 1.0), WIDTH_TOLERANCE_DB,
                "a wide pair read as a narrow one")


def test_identical_channels_have_no_width(tmp_path):
    one = sig.noise(10.0, seed=4, amp=0.3)[0]
    got = stereo.measure(decode(sig.write(tmp_path / "mono.wav", np.vstack([one, one]))))
    assert "width_side_mid_db" not in got
    assert got["absent_because"]["width_side_mid_db"]


def test_a_mono_file_has_no_stereo_measurement(tmp_path):
    x = sig.noise(5.0, seed=4, amp=0.3)
    with pytest.raises(stereo.Unmeasurable, match="no left and right"):
        stereo.measure(decode(sig.write(tmp_path / "one.wav", x)))
