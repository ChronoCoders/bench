from __future__ import annotations

import numpy as np
import pytest

import music
import rig
import signals as sig
from bench.decode import decode
from bench.measure import tempo

BPM_TOLERANCE = 0.1
# the normalised envelope moved 0.000 BPM over 60 shelved renders up to 12 dB
SHELF_TOLERANCE_BPM = 0.03
DRIFT_SPAN_TOLERANCE = 0.15
GRID_FIT_CLEAN_MS = 6.0
SPACING_TOLERANCE_S = 0.011


def measured(tmp_path, name, x):
    return tempo.measure(decode(sig.write(tmp_path / f"{name}.wav", x)))


def test_a_click_track_reads_its_own_tempo(tmp_path):
    for bpm in (88.0, 128.0, 144.0):
        got = measured(tmp_path, f"click{bpm:.0f}", music.build("click", bpm, seconds=60.0))
        rig.control(got["bpm"], bpm, BPM_TOLERANCE, f"tempo of a {bpm} BPM click track")


def test_the_tempo_control_can_fail(tmp_path):
    got = measured(tmp_path, "click128", music.build("click", 128.0, seconds=60.0))
    rig.rejects(got["bpm"], 144.0, BPM_TOLERANCE, "a 128 BPM track read as 144")


def test_onset_spacing_matches_the_beat_period(tmp_path):
    for bpm in (88.0, 175.0):
        x = music.build("click", bpm, seconds=60.0)
        values, times, envelope_hz = tempo.envelope(x, sig.SR)
        hits = tempo.onsets(values, times, envelope_hz)
        rig.control(float(np.median(np.diff(hits))), 60.0 / bpm, SPACING_TOLERANCE_S,
                    f"median onset spacing at {bpm} BPM")


def test_onset_count_matches_the_click_count(tmp_path):
    x = music.build("click", 128.0, seconds=60.0)
    values, times, envelope_hz = tempo.envelope(x, sig.SR)
    hits = tempo.onsets(values, times, envelope_hz)
    truth = music.beat_times(music.steady(128.0), 60.0)
    assert abs(hits.size - truth.size) <= 2, f"{hits.size} onsets for {truth.size} clicks"


def test_the_onset_threshold_survives_a_sparse_envelope(tmp_path):
    x = music.build("click", 72.0, seconds=60.0)
    values, _, _ = tempo.envelope(x, sig.SR)
    assert np.median(np.abs(values - np.median(values))) == 0.0, (
        "this control only means something while the envelope is sparse enough "
        "for the median absolute deviation to be zero"
    )
    got = measured(tmp_path, "sparse", x)
    rig.control(got["bpm"], 72.0, BPM_TOLERANCE, "tempo of a sparse click track")


@pytest.mark.parametrize("kind,f0,gain", [
    ("low", 200.0, 2.0), ("low", 200.0, -2.0), ("high", 4000.0, 2.0), ("high", 4000.0, -2.0),
    ("low", 200.0, 12.0), ("low", 200.0, -12.0), ("high", 4000.0, 12.0), ("high", 4000.0, -12.0),
])
def test_tempo_does_not_move_under_a_shelf(tmp_path, kind, f0, gain):
    x = music.limit(music.build("dense", 128.0, seconds=60.0, jitter=0.004))
    before = measured(tmp_path, "flat", x)
    after = measured(tmp_path, "shelved", music.shelf(x, sig.SR, f0, gain, kind))
    rig.invariance(before["bpm"], after["bpm"], SHELF_TOLERANCE_BPM,
                   f"tempo under a {gain} dB {kind} shelf at {f0} Hz")


def test_the_shelf_invariance_can_fail(tmp_path):
    at_128 = measured(tmp_path, "a", music.build("click", 128.0, seconds=60.0))
    at_129 = measured(tmp_path, "b", music.build("click", 129.0, seconds=60.0))
    rig.rejects(at_129["bpm"], at_128["bpm"], BPM_TOLERANCE,
                "a track one BPM faster read as the same tempo")


def test_grid_fit_widens_with_jitter(tmp_path):
    tight = measured(tmp_path, "tight", music.build("click", 128.0, seconds=60.0))
    loose = measured(tmp_path, "loose", music.build("click", 128.0, seconds=60.0, jitter=0.020))
    assert tight["grid_fit_ms"] < GRID_FIT_CLEAN_MS
    assert loose["grid_fit_ms"] > tight["grid_fit_ms"]


def test_the_grid_fit_comparison_can_fail(tmp_path):
    loose = measured(tmp_path, "loose", music.build("click", 128.0, seconds=60.0, jitter=0.020))
    rig.rejects(loose["grid_fit_ms"], 0.0, GRID_FIT_CLEAN_MS,
                "a track jittered by 20 ms read as sitting on the grid")


def test_grid_fit_saturates_and_coverage_does_not(tmp_path):
    at = {}
    for jitter in (0.0, 0.020, 0.040):
        got = measured(tmp_path, f"j{jitter:.3f}",
                       music.build("click", 128.0, seconds=60.0, jitter=jitter))
        at[jitter] = got
    rig.control(at[0.040]["grid_fit_ms"], at[0.020]["grid_fit_ms"], 6.0,
                "grid fit with the scatter doubled from 20 ms to 40 ms")
    assert at[0.040]["coverage"] < at[0.020]["coverage"] < at[0.0]["coverage"]
    rig.rejects(at[0.040]["coverage"], at[0.020]["coverage"], 0.1,
                "coverage failing to separate 20 ms of scatter from 40 ms")


def test_the_double_leaves_half_its_ticks_empty(tmp_path):
    got = measured(tmp_path, "click88", music.build("click", 88.0, seconds=60.0))
    doubled = [a for a in got["alternatives"] if a["ratio"] == 2.0]
    assert doubled, "the double was not offered as an alternative"
    rig.control(doubled[0]["occupancy"], 0.5, 0.05,
                "occupancy of a grid at twice the click rate")


def test_the_alternatives_carry_the_octave_relations(tmp_path):
    got = measured(tmp_path, "click88", music.build("click", 88.0, seconds=60.0))
    ratios = sorted(a["ratio"] for a in got["alternatives"])
    assert ratios == [0.5, 0.6667, 1.0, 1.5, 2.0]


@pytest.mark.parametrize("start,end", [(88.0, 89.0), (88.0, 91.0), (128.0, 124.0)])
def test_drift_reads_a_known_ramp(tmp_path, start, end):
    x = music.limit(music.build("dense", start, seconds=90.0, jitter=0.004,
                                beats=music.ramp(start, end, 90.0)))
    got = measured(tmp_path, "ramp", x)
    scale = round(got["bpm"] / start)
    rig.control(got["drift"]["span_bpm"] / scale, abs(end - start), DRIFT_SPAN_TOLERANCE,
                f"drift span of a {start} to {end} ramp")


def test_the_drift_control_can_fail(tmp_path):
    x = music.limit(music.build("dense", 88.0, seconds=90.0, jitter=0.004,
                                beats=music.ramp(88.0, 89.0, 90.0)))
    got = measured(tmp_path, "ramp", x)
    scale = round(got["bpm"] / 88.0)
    rig.rejects(got["drift"]["span_bpm"] / scale, 3.0, DRIFT_SPAN_TOLERANCE,
                "a one BPM ramp read as a three BPM ramp")


def test_drift_sees_a_tempo_that_comes_back(tmp_path):
    seconds = 120.0
    x = music.limit(music.build("dense", 120.0, seconds=seconds, jitter=0.004,
                                beats=music.arch(120.0, 126.0, seconds)))
    got = measured(tmp_path, "arch", x)
    scale = round(got["bpm"] / 120.0)
    assert "drift" in got, got.get("absent_because")
    rig.control(got["drift"]["span_bpm"] / scale, 6.0, 0.6,
                "drift span of a tempo that rises to 126 and returns to 120")


def test_the_returning_tempo_is_not_read_as_steady(tmp_path):
    seconds = 120.0
    x = music.limit(music.build("dense", 120.0, seconds=seconds, jitter=0.004,
                                beats=music.arch(120.0, 126.0, seconds)))
    got = measured(tmp_path, "arch", x)
    scale = round(got["bpm"] / 120.0)
    rig.rejects(got["drift"]["span_bpm"] / scale, 0.0, tempo.DRIFT_FLOOR_BPM,
                "a tempo that rises six and returns read as steady")


def test_a_steady_track_reports_no_drift(tmp_path):
    x = music.limit(music.build("dense", 128.0, seconds=90.0, jitter=0.004))
    got = measured(tmp_path, "steady", x)
    assert "drift" not in got
    assert "this method can resolve" in got["absent_because"]["drift"]


@pytest.mark.parametrize("pattern", ["click", "dense", "with_bass", "syncopated"])
@pytest.mark.parametrize("bpm", [88.0, 128.0])
def test_a_steady_track_stays_under_the_declared_horizon(pattern, bpm):
    x = music.limit(music.build(pattern, bpm, seconds=90.0, jitter=0.004))
    values, times, envelope_hz = tempo.envelope(x, sig.SR)
    model = tempo.beat_model(times, values, envelope_hz, tempo.strongest_rate(values, envelope_hz)[0])
    moved = tempo.drift(model)
    assert not moved["resolved"], moved
    assert moved["span_bpm"] <= tempo.DRIFT_FLOOR_BPM, moved


def test_tempo_does_not_depend_on_the_sample_rate(tmp_path):
    at_44100 = measured(tmp_path, "a", music.build("click", 128.0, seconds=60.0, rate=44100))
    x = music.build("click", 128.0, seconds=60.0, rate=48000)
    at_48000 = tempo.measure(decode(sig.write(tmp_path / "b.wav", x, sr=48000)))
    rig.invariance(at_44100["bpm"], at_48000["bpm"], BPM_TOLERANCE,
                   "the same click track written at 44100 and 48000")


def test_a_rate_at_the_search_boundary_is_declared(tmp_path):
    got = measured(tmp_path, "edge", music.build("click", tempo.SEARCH_HIGH_BPM, seconds=60.0))
    assert "caveats" in got, got
    assert "search range" in got["caveats"][0]
    rig.control(got["bpm"], tempo.SEARCH_HIGH_BPM / 2.0, BPM_TOLERANCE,
                "the interior rate reported when the peak sits on the boundary")


def test_a_rate_inside_the_range_carries_no_caveat(tmp_path):
    got = measured(tmp_path, "mid", music.build("click", 128.0, seconds=60.0))
    assert "caveats" not in got, got["caveats"]
    assert got["search_range_bpm"] == [tempo.SEARCH_LOW_BPM, tempo.SEARCH_HIGH_BPM]


def test_a_short_file_has_no_tempo(tmp_path):
    x = music.build("click", 128.0, seconds=10.0)
    with pytest.raises(tempo.Unmeasurable, match="too few beats"):
        measured(tmp_path, "short", x)


def test_silence_has_no_tempo(tmp_path):
    with pytest.raises(tempo.Unmeasurable):
        measured(tmp_path, "silent", sig.silence(60.0, channels=2))
