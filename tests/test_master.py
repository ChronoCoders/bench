"""The mastering layer's claims.

Four of these are the faults found while building it, each with a control that fails
if the fix is undone: aiming at a boundary by half a step, the limiter taking loudness
the gain arithmetic cannot see, a stop condition decided by the last bit of a float,
and a prediction checked against the instrument that did not make it.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import music
import rig
import signals as sig
from bench import compare, master, measurement
from bench.decode import decode
from bench.measure import bs1770, loudness, spectral

BAND_ALLOWANCE_PCT = 8.0
RANGE_WIDTH_LU = 6.0
PUSH_LU = 1.0
CEILING = -1.0
INPUT_PEAK_DBTP = -1.5
OVER_THE_CEILING = -0.3
SECONDS = 6.0
SUB_HZ = 8.0
SUB_AMP = 0.03
HEAVY_SUB = 0.25
FOLDER_REFUSAL = "the folder the source is in"
EXISTS_REFUSAL = "already exists"


def _folder(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir(exist_ok=True)
    return folder


def at_true_peak(x, dbtp):
    return x * 10.0 ** ((dbtp - bs1770.true_peak_dbtp(x)) / 20.0)


def source(tmp_path, name="track.wav", sub=SUB_AMP, peak=INPUT_PEAK_DBTP, clean=False):
    """A master shaped like one: crest near 12 dB, a peak just under full scale, and
    content under 20 Hz. Short of the target loudness by more than its own headroom,
    so the gain alone cannot get there and the limiter has to be asked."""
    if clean:
        # Two tones and nothing else. A high passed piece of music still measures 0.01
        # under 20 Hz, which is above the 0.005 a percentage is reported to, so it is
        # not a file with nothing there.
        x = (sig.sine(1000.0, SECONDS, channels=2, amp=0.4)
             + sig.sine(5000.0, SECONDS, channels=2, amp=0.4))
        return sig.write(_folder(tmp_path) / name, at_true_peak(x, peak))
    x = music.limit(music.build("with_bass", 120.0, seconds=SECONDS), drive=4.0)
    if sub:
        t = np.arange(x.shape[1]) / sig.SR
        x = x + sub * np.sin(2.0 * np.pi * SUB_HZ * t)
    return sig.write(_folder(tmp_path) / name, at_true_peak(x, peak))


def target_around(measured, bands=True, low=None, ceiling=CEILING):
    """A target the input already sits inside on every band, so the limiter search has
    a criterion that can fail rather than one that cannot."""
    if low is None:
        low = round(compare.dig(measured, master.LOUDNESS_FIELD) + PUSH_LU, 3)
    fields = {"loudness.integrated_lufs": {"low": low, "high": low + RANGE_WIDTH_LU}}
    if bands:
        for band in measured["spectral"]["bands"]:
            key = measurement.band_key(band["lo_hz"], band["hi_hz"])
            fields[f"spectral.band_pct.{key}"] = {
                "low": round(band["pct"] - BAND_ALLOWANCE_PCT, 4),
                "high": round(band["pct"] + BAND_ALLOWANCE_PCT, 4),
            }
    out = {"name": "test", "band_set": measured["spectral"]["band_set"],
           "evidence": {"n": 1}, "fields": fields}
    if ceiling is not None:
        out["limits"] = {"loudness.true_peak_dbtp": {"max": ceiling, "declared_by": "test"}}
    return out


def sha1(path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def row(comparison, field):
    return next(r for r in comparison["rows"] if r["field"] == field)


def refusal(built, correction):
    return next(r for r in built["not_applied"] if r["correction"] == correction)["why"]


@pytest.fixture(scope="module")
def mastered(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mastered")
    path = source(tmp)
    before = measurement.of_file(path)
    return master.run(path, target_around(before), tmp / "out")


# It never writes over an input.

def test_it_refuses_to_write_into_the_folder_the_source_is_in(tmp_path):
    """It has to refuse for that reason. With this check gone the destination is the
    source, the source exists, and the check below it refuses for a different reason
    and looks the same from outside."""
    path = source(tmp_path)
    with pytest.raises(master.Unsafe) as why:
        master.refuse_unsafe(path, path.parent)
    assert FOLDER_REFUSAL in str(why.value)
    assert str(path.parent.resolve()) in str(why.value)


def test_it_refuses_the_folder_however_the_path_is_spelled(tmp_path):
    """The destination can only be the source if the output folder is the source's
    folder, so this is the check that carries the whole claim."""
    path = source(tmp_path)
    for spelling in (path.parent, path.parent / ".", path.parent / "in" / "..",
                     Path(str(path.parent).upper())):
        with pytest.raises(master.Unsafe) as why:
            master.refuse_unsafe(path, spelling)
        assert FOLDER_REFUSAL in str(why.value), spelling


def test_it_refuses_to_replace_a_master_it_made_before(tmp_path):
    path = source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / path.name).write_bytes(b"an earlier master")
    with pytest.raises(master.Unsafe) as why:
        master.refuse_unsafe(path, out)
    assert EXISTS_REFUSAL in str(why.value)
    assert FOLDER_REFUSAL not in str(why.value), (
        "two refusals that read the same cannot tell you which one fired"
    )


def test_the_refusal_is_not_blanket(tmp_path):
    """A check that refuses everything says nothing about what it refuses."""
    path = source(tmp_path)
    assert master.refuse_unsafe(path, tmp_path / "out") == (tmp_path / "out" / path.name).resolve()


def test_the_input_is_the_same_file_afterwards(tmp_path):
    path = source(tmp_path)
    before = sha1(path)
    result = master.run(path, target_around(measurement.of_file(path), bands=False),
                        tmp_path / "out")
    assert sha1(path) == before, "the mastering layer changed the file it read"
    assert Path(result["output"]).exists()
    assert Path(result["output"]).resolve() != path.resolve()


def test_that_byte_check_can_fail(tmp_path):
    path = source(tmp_path)
    before = sha1(path)
    path.write_bytes(path.read_bytes() + b"\0")
    if sha1(path) == before:
        raise rig.Toothless(
            "a file that was appended to hashed the same, so the check above cannot "
            "see a file being written over"
        )


# Fault one. Aiming at a boundary by half a step lands on the boundary.

def daylight(aim, unit):
    """How far the top of the measurement's interval sits under the ceiling. Zero is
    not inside: it is a comparison decided by the last bit of a float."""
    return CEILING - (aim + unit)


def test_the_aim_leaves_a_whole_step_of_daylight():
    unit = 0.05
    aim = CEILING - master.clearance(master.PEAK_FIELD, unit)
    assert compare.verdict(aim, unit, {"max": CEILING}) == compare.INSIDE
    assert daylight(aim, unit) >= unit, (
        f"the plan aims {round(daylight(aim, unit), 6)} under the ceiling, which is less "
        "than the step the value is reported in"
    )


def test_aiming_by_one_uncertainty_leaves_none():
    """Fault three. One uncertainty puts the top of the interval exactly on the
    ceiling, where whether it reads as inside is decided by float rounding rather than
    by the measurement."""
    unit = 0.05
    if daylight(CEILING - unit, unit) >= unit:
        raise rig.Toothless(
            "aiming one uncertainty under the ceiling left a whole step of daylight, "
            "so the test above is not measuring the clearance"
        )
    assert abs(daylight(CEILING - unit, unit)) < 1e-9


def test_the_clearance_covers_the_gap_between_the_two_instruments():
    """The plan is built in memory by the second instrument and judged on the file by
    the primary. Clearing only the reporting step aims at a line the other instrument
    draws somewhere else."""
    for field, unit_name in master.CROSSCHECK_UNIT.items():
        rig.control(master.clearance(field, 0.05),
                    master.CLEARANCE * 0.05 + loudness.TOLERANCE[unit_name], 1e-12,
                    f"the clearance on {field}")


# The corrections are derived from the measurement, or they are not applied.

def test_a_low_cut_is_applied_when_there_is_something_under_20_hz(tmp_path):
    measured = measurement.of_file(source(tmp_path))
    cut = master.step(master.plan(measured, target_around(measured, bands=False)), "low cut")
    assert cut is not None and cut["hz"] == spectral.DENOMINATOR_HZ[0]


def test_a_low_cut_is_refused_when_there_is_not(tmp_path):
    measured = measurement.of_file(source(tmp_path, name="clean.wav", clean=True))
    built = master.plan(measured, target_around(measured, bands=False))
    assert master.step(built, "low cut") is None
    assert "nothing there to remove" in refusal(built, "low cut")


def moved_by_a_cut_at(audio, hz):
    before = spectral.measure(audio)
    after = spectral.measure(
        replace(audio, samples=master.low_cut(audio.samples, audio.sample_rate_hz, hz=hz)))
    return max(abs(a["pct"] - b["pct"]) for a, b in zip(after["bands"], before["bands"]))


def test_the_plan_reports_what_the_cut_actually_moved(mastered):
    """Not a residual carried over from other tracks. The number in the plan has to be
    the number this file measures."""
    cut = master.step(mastered["plan"], "low cut")
    assert cut is not None
    rig.control(cut["moved_bands_by_pct"],
                moved_by_a_cut_at(decode(Path(mastered["input"])), master.CUT_HZ), 1e-9,
                "the band movement the plan reports for the low cut")


def test_that_reported_movement_is_not_the_same_for_any_filter(tmp_path):
    """The control on the one above: if a cut at 300 Hz measured the same, the number
    would not be telling us anything about the filter that ran."""
    audio = decode(source(tmp_path))
    rig.rejects(moved_by_a_cut_at(audio, 300.0), moved_by_a_cut_at(audio, master.CUT_HZ),
                0.05, "a cut at 300 Hz against a cut at 20 Hz")


def test_the_gain_is_derived_from_the_signal_the_cut_left(tmp_path):
    """Entry 29. loudness.measure runs the primary instrument over audio.path and the
    second over audio.samples, so handing it an Audio whose samples have been replaced
    measures the filtered signal with one and the file on disk with the other."""
    path = source(tmp_path, sub=HEAVY_SUB)
    audio = decode(path)
    filtered = master.low_cut(audio.samples, audio.sample_rate_hz)
    result = master.run(path, target_around(measurement.of_file(path), bands=False),
                        tmp_path / "out")
    gain = master.step(result["plan"], "gain")
    assert master.step(result["plan"], "low cut") is not None, "this file needs the cut"
    rig.control(gain["measured_dbtp"], bs1770.true_peak_dbtp(filtered), 0.001,
                "the peak the gain was derived from")


def test_that_check_can_tell_the_two_signals_apart(tmp_path):
    """The control on the one above. If the cut moved the peak by less than the check
    allows, the check could not see which signal was measured."""
    audio = decode(source(tmp_path, sub=HEAVY_SUB))
    filtered = master.low_cut(audio.samples, audio.sample_rate_hz)
    rig.rejects(bs1770.true_peak_dbtp(audio.samples), bs1770.true_peak_dbtp(filtered), 0.001,
                "the unfiltered peak against the filtered one")


def test_no_gain_when_the_target_says_nothing_about_loudness(tmp_path):
    measured = measurement.of_file(source(tmp_path))
    target = target_around(measured, bands=False)
    del target["fields"]["loudness.integrated_lufs"]
    built = master.plan(measured, target)
    assert master.step(built, "gain") is None
    assert "nothing to raise the file to" in refusal(built, "gain")


def test_no_gain_when_the_file_is_already_inside_the_range(tmp_path):
    """A file inside its target does not get moved to the edge of it."""
    measured = measurement.of_file(source(tmp_path))
    here = compare.dig(measured, master.LOUDNESS_FIELD)
    built = master.plan(measured, target_around(measured, bands=False,
                                                low=round(here - RANGE_WIDTH_LU / 2.0, 3)))
    assert master.step(built, "gain") is None
    assert "neither the target nor the ceiling asks for anything" in refusal(built, "gain")


def test_a_file_over_the_ceiling_comes_under_it_with_the_loudness_already_inside(tmp_path):
    """The ceiling is not conditional on the gain. Being inside the loudness range says
    nothing about the peak, and a file over the ceiling comes under it either way."""
    measured = measurement.of_file(source(tmp_path, peak=OVER_THE_CEILING))
    here = compare.dig(measured, master.LOUDNESS_FIELD)
    target = target_around(measured, bands=False,
                           low=round(here - RANGE_WIDTH_LU / 2.0, 3))
    built = master.plan(measured, target)
    gain = master.step(built, "gain")
    assert gain is not None, "nothing was applied to a file over the ceiling"
    assert gain["bound_by"] == "the ceiling"
    assert gain["db"] < 0.0, "it has to come down"


def test_that_file_really_is_inside_its_loudness_range(tmp_path):
    """The control on the one above. If it were outside on loudness too, the gain would
    have been asked for by the loudness and the ceiling would prove nothing."""
    measured = measurement.of_file(source(tmp_path, peak=OVER_THE_CEILING))
    here = compare.dig(measured, master.LOUDNESS_FIELD)
    target = target_around(measured, bands=False,
                           low=round(here - RANGE_WIDTH_LU / 2.0, 3))
    row = next(r for r in compare.against(measured, target)["rows"]
               if r["field"] == master.LOUDNESS_FIELD)
    assert row["verdict"] == compare.INSIDE
    assert compare.dig(measured, master.PEAK_FIELD) > CEILING


def test_it_writes_a_file_that_is_under_the_ceiling(tmp_path):
    measured = measurement.of_file(source(tmp_path, peak=OVER_THE_CEILING))
    here = compare.dig(measured, master.LOUDNESS_FIELD)
    result = master.run(source(tmp_path, name="over.wav", peak=OVER_THE_CEILING),
                        target_around(measured, low=round(here - RANGE_WIDTH_LU / 2.0, 3)),
                        tmp_path / "out")
    landed = result["reached"]["fields"][master.PEAK_FIELD]
    assert landed["verdict"] == compare.INSIDE, landed


def test_a_file_above_its_range_is_brought_to_the_top_and_not_the_bottom(tmp_path):
    """Aiming always at the bottom would take a file that is a little too loud and
    turn it down by the whole width of the range."""
    measured = measurement.of_file(source(tmp_path))
    here = compare.dig(measured, master.LOUDNESS_FIELD)
    unit = compare.dig(measured, "loudness.uncertainty.integrated_lufs")
    room = master.clearance(master.LOUDNESS_FIELD, unit)

    target = target_around(measured, bands=False,
                           low=round(here - RANGE_WIDTH_LU - PUSH_LU, 3))
    bound = target["fields"][master.LOUDNESS_FIELD]
    down = master.plan(measured, target)
    rig.control(master.step(down, "gain")["db"], bound["high"] - room - here, 0.002,
                "the gain onto a file that is louder than its target")
    assert master.step(down, "gain")["db"] < 0.0


def test_a_file_below_its_range_is_raised(tmp_path):
    measured = measurement.of_file(source(tmp_path))
    here = compare.dig(measured, master.LOUDNESS_FIELD)
    up = master.plan(measured, target_around(measured, bands=False,
                                             low=round(here + PUSH_LU, 3)))
    assert master.step(up, "gain")["db"] > 0.0


def test_render_does_only_what_the_plan_says(tmp_path):
    audio = decode(source(tmp_path))
    rig.control(float(np.max(np.abs(master.render(audio, {"steps": [
                    {"correction": "gain", "db": -6.0}]})))),
                float(np.max(np.abs(audio.samples))) * 10.0 ** (-6.0 / 20.0), 1e-12,
                "a plan with one gain step and nothing else")
    assert np.array_equal(master.render(audio, {"steps": []}), audio.samples), (
        "a plan with no steps changed the audio"
    )


# The limiter is chosen by a criterion that can fail, or it is not chosen.

def test_a_target_that_bounds_no_band_refuses_to_limit(tmp_path):
    path = source(tmp_path)
    before = measurement.of_file(path)
    audio = decode(path)
    target = target_around(before, bands=False)
    found = master.search_limiter(audio, audio.samples * 4.0,
                                  master.step_ceiling(target, before), target, before)
    assert found["chosen"] is None
    assert "no setting can fail" in found["no_criterion"]


def test_a_target_that_bounds_bands_does_search(tmp_path):
    """The control on the one above: the refusal is about the criterion being empty,
    not about the search never running at all."""
    path = source(tmp_path)
    before = measurement.of_file(path)
    audio = decode(path)
    target = target_around(before)
    found = master.search_limiter(audio, audio.samples * 4.0,
                                  master.step_ceiling(target, before), target, before)
    assert "no_criterion" not in found
    assert len(found["tried"]) == len(master.ATTACKS_MS) * len(master.RELEASES_MS)


def test_it_says_when_the_winner_sits_on_the_edge_of_the_grid(mastered):
    """A winner on the boundary of the grid was chosen by the grid rather than by the
    material, so the result says so. It also has to not say so otherwise."""
    found = mastered["limiter_search"]
    chosen = found["chosen"]
    on_edge = (chosen["attack_ms"] in (min(master.ATTACKS_MS), max(master.ATTACKS_MS))
               or chosen["release_ms"] in (min(master.RELEASES_MS), max(master.RELEASES_MS)))
    assert ("at_search_edge" in found) == on_edge, (
        f"{chosen['attack_ms']} ms and {chosen['release_ms']} ms against "
        f"{master.ATTACKS_MS} and {master.RELEASES_MS}"
    )


def test_a_grid_of_one_setting_is_all_edge(tmp_path, monkeypatch):
    """The control on the one above, which on a given file exercises whichever branch
    that file happens to land in."""
    monkeypatch.setattr(master, "ATTACKS_MS", (2.0,))
    monkeypatch.setattr(master, "RELEASES_MS", (60.0,))
    path = source(tmp_path)
    before = measurement.of_file(path)
    audio = decode(path)
    target = target_around(before)
    found = master.search_limiter(audio, audio.samples * 4.0,
                                  master.step_ceiling(target, before), target, before)
    assert len(found["tried"]) == 1
    assert "attack at 2.0 ms" in found["at_search_edge"]
    assert "release at 60.0 ms" in found["at_search_edge"]


# Fault four. A prediction checked against the instrument that did not make it.

def _after(primary, crosscheck, unit=0.05):
    return {"loudness": {"true_peak_dbtp": primary,
                         "crosscheck": {"true_peak_dbtp": crosscheck},
                         "uncertainty": {"true_peak_dbtp": unit}}}


def _predicting(by):
    return {"predicted": {"integrated_lufs": None, "true_peak_dbtp": -1.25, "predicted_by": by}}


def test_a_prediction_is_checked_against_the_instrument_that_made_it():
    held = master._held(_predicting("the second instrument, measured in memory"),
                        _after(primary=-1.0, crosscheck=-1.25))
    assert held["against"] == "the second instrument"
    assert held["fields"]["true_peak_dbtp"]["held"]


def test_checking_it_against_the_other_one_would_not_hold():
    held = master._held(_predicting("arithmetic on the primary instrument"),
                        _after(primary=-1.0, crosscheck=-1.25))
    assert held["against"] == "the primary instrument"
    assert not held["fields"]["true_peak_dbtp"]["held"], (
        "the same prediction has to fail against the other instrument, or this pair "
        "is not measuring which instrument gets read"
    )


# End to end.

def test_the_file_started_outside_the_target(mastered):
    """The control on everything below: a file already inside says nothing about a
    layer that is supposed to put it there."""
    assert row(mastered["before"]["comparison"], master.LOUDNESS_FIELD)["verdict"] != compare.INSIDE


def test_the_output_is_measured_and_the_prediction_holds(mastered):
    assert mastered["prediction"]["checked"]
    assert mastered["prediction"]["held"], mastered["prediction"]["fields"]


def test_the_peak_lands_inside_the_ceiling_not_on_it(mastered):
    got = row(mastered["after"]["comparison"], master.PEAK_FIELD)
    assert got["verdict"] == compare.INSIDE, f"{got['value']} with {got['uncertainty']}"


def test_the_loudness_lands_inside_the_target(mastered):
    got = row(mastered["after"]["comparison"], master.LOUDNESS_FIELD)
    assert got["verdict"] == compare.INSIDE, (
        f"{got['value']} against {got['bound']} with {got['uncertainty']} uncertainty, "
        f"and the plan says {mastered['plan'].get('shortfall_lu')} unreachable"
    )


def test_the_correction_stops_with_room_and_not_on_the_condition(mastered):
    """Fault three. The loop stops when the measurement clears its aim, and it has to
    clear it by a whole reporting step or the stop rests on the last bit of a float."""
    search = mastered["limiter_search"]
    assert search is not None and search.get("chosen"), "this file was meant to need one"
    assert search["cleared_the_floor"], (
        "this file is built so the correction can reach its aim. Not reaching it means "
        "the loop stopped early, which is the fault this test is here for"
    )
    unit = compare.dig(mastered["before"]["measurement"],
                       "loudness.uncertainty.integrated_lufs")
    low = row(mastered["after"]["comparison"], master.LOUDNESS_FIELD)["bound"]["low"]
    room = search["chosen"]["integrated_lufs"] - master.CLEARANCE * unit - low
    assert room >= unit, (
        f"the correction stopped {round(room, 6)} above its own stop condition, which "
        f"is less than the {unit} the measurement resolves"
    )


def test_it_says_where_it_landed(mastered):
    assert mastered["reached"]["arrived"], mastered["reached"]["fields"]


def test_a_target_it_cannot_reach_is_reported_as_not_reached(tmp_path):
    """A run that cannot get there says so from the output rather than reporting the
    plan it carried out."""
    path = source(tmp_path)
    before = measurement.of_file(path)
    here = compare.dig(before, master.LOUDNESS_FIELD)
    target = target_around(before, bands=False, low=round(here + 20.0, 3))
    result = master.run(path, target, tmp_path / "out")
    assert not result["reached"]["arrived"]
    landed = result["reached"]["fields"][master.LOUDNESS_FIELD]
    assert landed["verdict"] == compare.BELOW and landed["deviation"] < 0.0


def test_it_says_what_the_limiter_took(mastered):
    squash = master.step(mastered["plan"], "limiter")
    assert squash is not None, "this file was supposed to need the limiter"
    assert squash["gain_reduction"]["largest_db"] >= 0.0
    assert 0.0 <= squash["gain_reduction"]["share_over_the_ceiling"] <= 1.0
