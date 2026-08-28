from __future__ import annotations

import numpy as np

import rig
import signals as sig
from bench.decode import decode
from bench.measure import bs1770, levels

SINE_CREST_DB = 20.0 * np.log10(np.sqrt(2.0))
CREST_TOLERANCE_DB = 0.02
CREST_SILENCE_TOLERANCE_DB = 0.1
DC_TOLERANCE = 1e-6


def ungated_crest_db(samples):
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    return 20.0 * np.log10(peak / rms)


def test_crest_of_a_sine_is_three_decibels(tmp_path):
    x = sig.sine(1000, 20.0, amp=0.5, channels=2)
    got = levels.measure(decode(sig.write(tmp_path / "sine.wav", x)))
    rig.control(got["crest_db"], SINE_CREST_DB, CREST_TOLERANCE_DB,
                "crest of a sine, peak over root mean square")


def test_crest_of_a_square_can_fail(tmp_path):
    x = np.sign(sig.sine(1000, 20.0, amp=0.5, channels=2)) * 0.5
    got = levels.measure(decode(sig.write(tmp_path / "square.wav", x)))
    rig.rejects(got["crest_db"], SINE_CREST_DB, CREST_TOLERANCE_DB,
                "a square wave, whose crest is zero, read as a sine")


def with_silence(x, seconds=30.0):
    return np.concatenate([x, sig.silence(seconds, channels=x.shape[0])], axis=1)


def test_crest_does_not_move_when_silence_is_appended(tmp_path):
    x = sig.sine(1000, 20.0, amp=0.5, channels=2)
    before = levels.measure(decode(sig.write(tmp_path / "a.wav", x)))
    after = levels.measure(decode(sig.write(tmp_path / "b.wav", with_silence(x))))
    kept = bs1770.integrated(x, sig.SR).blocks_over_relative_gate
    grew = bs1770.integrated(with_silence(x), sig.SR).blocks_over_relative_gate - kept
    assert grew <= 4, f"{grew} extra blocks kept, more than straddle one transition"
    rig.invariance(before["crest_db"], after["crest_db"], CREST_SILENCE_TOLERANCE_DB,
                   "crest with 30 s of silence appended")


def test_the_silence_invariance_can_fail():
    x = sig.sine(1000, 20.0, amp=0.5, channels=2)
    rig.rejects(ungated_crest_db(with_silence(x)), ungated_crest_db(x),
                CREST_SILENCE_TOLERANCE_DB,
                "the same crest taken against an ungated root mean square")


def test_dc_offset_reads_the_offset(tmp_path):
    x = sig.sine(1000, 10.0, amp=0.4, channels=2) + 0.05
    got = levels.measure(decode(sig.write(tmp_path / "dc.wav", x)))
    for channel in got["dc_offset"]:
        rig.control(channel, 0.05, DC_TOLERANCE, "direct current offset of 0.05")


def test_dc_offset_can_fail(tmp_path):
    x = sig.sine(1000, 10.0, amp=0.4, channels=2)
    got = levels.measure(decode(sig.write(tmp_path / "clean.wav", x)))
    rig.rejects(got["dc_offset"][0], 0.05, DC_TOLERANCE, "a clean file read as offset by 0.05")


def test_dc_offset_block_max_sees_a_step_the_mean_hides(tmp_path):
    half = sig.sine(1000, 10.0, amp=0.4, channels=2)
    x = np.concatenate([half + 0.1, half - 0.1], axis=1)
    got = levels.measure(decode(sig.write(tmp_path / "step.wav", x)))
    rig.control(got["dc_offset"][0], 0.0, 1e-4, "mean of a file that steps from plus to minus")
    rig.control(got["dc_offset_block_max"][0], 0.1, 1e-3,
                "largest block mean of the same file")


def test_clipped_runs_counts_runs_not_samples(tmp_path):
    x = sig.sine(1000, 5.0, amp=1.0, channels=2)
    got = levels.measure(decode(sig.write(tmp_path / "peaknorm.wav", x, subtype="PCM_16")))
    assert got["clipped_runs"] == 0


def test_clipped_runs_can_fail(tmp_path):
    x = np.clip(sig.sine(1000, 5.0, amp=1.6, channels=2), -1.0, 1.0)
    got = levels.measure(decode(sig.write(tmp_path / "squared.wav", x, subtype="PCM_16")))
    assert got["clipped_runs"] > 0


def test_clip_threshold_follows_bit_depth():
    assert levels.full_scale(16) == (2**15 - 1) / 2**15
    assert levels.full_scale(24) == (2**23 - 1) / 2**23
    assert levels.full_scale(None) == 1.0


def test_over_full_scale_samples_are_counted():
    x = sig.sine(1000, 1.0, amp=0.5, channels=2)
    x[0, 100] = 1.4
    x[1, 200] = -1.2
    assert levels.over_full_scale(x) == 2
    assert levels.over_full_scale(sig.sine(1000, 1.0, amp=0.9, channels=2)) == 0


def test_silence_has_no_crest(tmp_path):
    got = levels.measure(decode(sig.write(tmp_path / "silent.wav", sig.silence(5.0, channels=2))))
    assert "crest_db" not in got
    assert got["absent_because"]["crest_db"]
    assert got["clipped_runs"] == 0
