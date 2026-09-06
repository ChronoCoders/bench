"""What produced a number, recorded beside it.

A difference here is reported and never acted on. The tests that matter most are the
ones holding that line: a comparison against a target seeded on another ffmpeg has to
come back with exactly the verdicts it would have come back with anyway.
"""

from __future__ import annotations

import numpy as np

import signals as sig
from bench import compare, measurement, page, report, toolchain
from bench.decode import decode

PARTS = ("ffmpeg", "libsndfile", "scipy", "numpy")
CEILING = {"max": -1.0, "declared_by": "test"}


def measured(seeded=None):
    one = {"spectral": {"band_set": "bench-v1"},
           "loudness": {"true_peak_dbtp": -3.0, "uncertainty": {"true_peak_dbtp": 0.05}},
           "toolchain": {"ffmpeg": "9.0", "scipy": "1.15.3"}}
    return one


def against(seeded, mine=None):
    """One comparison, with whatever the target says it was seeded on."""
    one = measured()
    if mine is not None:
        one["toolchain"] = mine
    aim = {"name": "test", "band_set": "bench-v1", "evidence": {"n": 1},
           "fields": {}, "limits": {"loudness.true_peak_dbtp": dict(CEILING)}}
    if seeded is not None:
        aim["evidence"]["toolchain"] = seeded
    return compare.against(one, aim)


def test_a_measurement_says_what_produced_it(tmp_path):
    path = sig.write(tmp_path / "tone.wav", sig.sine(1000, 3.0, amp=0.4, channels=2))
    got = measurement.of_audio(decode(path))["toolchain"]
    assert set(got) == set(PARTS), f"the record names {sorted(got)}"
    for part in PARTS:
        assert got[part] is None or isinstance(got[part], str), f"{part} is not a version"
    assert got["numpy"] == np.__version__, "the recorded numpy is not the one running"


def test_a_toolchain_that_differs_is_reported():
    got = against({"ffmpeg": "7.1", "scipy": "1.15.3"})["toolchain_differs"]
    assert got == {"ffmpeg": {"measured_with": "9.0", "target_seeded_with": "7.1"}}


def test_a_toolchain_that_matches_reports_nothing():
    """The control. A report that named a difference every time would be no report."""
    assert against({"ffmpeg": "9.0", "scipy": "1.15.3"})["toolchain_differs"] == {}


def test_a_target_that_does_not_say_is_not_a_disagreement():
    """Every target written before this existed says nothing, and silence is not a
    difference. Reporting it as one would put a note on every comparison there is."""
    assert against(None)["toolchain_differs"] == {}
    assert against({"ffmpeg": "9.0"}, mine=None)["toolchain_differs"] == {}


def test_a_part_only_one_side_names_is_not_a_disagreement():
    assert toolchain.differences({"ffmpeg": "9.0", "numpy": "2.2.6"},
                                 {"ffmpeg": "9.0"}) == {}


def test_a_difference_changes_no_verdict():
    """The policy, held by a test. It is a reason to look, not a reason to stop, so
    everything the comparison decides has to be identical either way."""
    same = against({"ffmpeg": "9.0", "scipy": "1.15.3"})
    other = against({"ffmpeg": "7.1", "scipy": "1.15.3"})
    assert other["toolchain_differs"], "this comparison was supposed to differ"
    for key in ("rows", "counts", "all_inside", "advisory"):
        assert other[key] == same[key], f"a toolchain difference moved {key}"


def test_the_note_reaches_the_page_and_the_report():
    other = against({"ffmpeg": "7.1", "scipy": "1.15.3"})
    assert "7.1" in page.comparison_view(other), "the page does not say the toolchain differed"
    assert "7.1" in report.comparison_table(other), "the report does not say it either"


def test_neither_carries_a_note_when_they_agree():
    """The control on the one above, which would pass on a page that always says it."""
    same = against({"ffmpeg": "9.0", "scipy": "1.15.3"})
    assert "different toolchain" not in page.comparison_view(same)
    assert "different toolchain" not in report.comparison_table(same)
