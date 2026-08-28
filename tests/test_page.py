from __future__ import annotations

import re

import music
import signals as sig
from bench import compare, fields, folder, measurement, page

CEILING = {"max": -1.0, "declared_by": "test"}


def on_the_line_result():
    one = {"loudness": {"true_peak_dbtp": -1.0, "uncertainty": {"true_peak_dbtp": 0.05}},
           "spectral": {"band_set": "bench-v1"}}
    target = {"name": "test", "band_set": "bench-v1", "evidence": {"n": 2, "all_sources_lossy": True},
              "fields": {}, "limits": {"loudness.true_peak_dbtp": CEILING}}
    return compare.against(one, target)


def test_a_value_on_the_line_is_not_shown_as_a_pass():
    html = page.comparison_view(on_the_line_result())
    assert "on the line" in html
    assert "not a pass" in html
    assert ">inside<" not in html


def test_the_line_verdict_is_marked_apart_from_inside():
    html = page.comparison_view(on_the_line_result())
    marked = re.findall(r'class="(inside|line|out)">([^<]+)<', html)
    assert marked == [("line", "on the line")]


def test_a_field_with_no_target_shows_its_value_and_its_reason():
    one = {"loudness": {"true_peak_dbtp": -1.2, "uncertainty": {"true_peak_dbtp": 0.05}},
           "spectral": {"band_set": "bench-v1"}}
    target = {"name": "t", "band_set": "bench-v1", "evidence": {"n": 2}, "fields": {},
              "withheld": {"loudness.true_peak_dbtp": "the references are lossy"}}
    html = page.comparison_view(compare.against(one, target))
    assert "The references are lossy" in html, "the reason should start a sentence"
    assert "-1.2" in html


def test_the_page_says_how_many_references_the_target_rests_on():
    html = page.comparison_view(on_the_line_result())
    assert "2 references" in html
    assert "all lossy" in html


def test_an_absent_value_never_renders_as_a_number():
    assert page.number(None, 2) == '<span class="blank">.</span>'
    assert page.number(0.0, 2) == "0.00"
    assert page.number(None, 0) != page.number(0.0, 0)


def test_a_missing_number_is_a_gap_not_a_zero(tmp_path):
    out = tmp_path / "short"
    out.mkdir()
    sig.write(out / "a.wav", music.build("dense", 128.0, seconds=5.0))
    html = page.folder_view(folder.measure(out))
    assert "None" not in html
    assert "nan" not in html
    assert 'class="blank">.</span>' in html


def test_the_folder_table_carries_a_spread_row_and_a_count(tmp_path):
    out = tmp_path / "album"
    out.mkdir()
    base = music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004))
    for i, scale in enumerate((1.0, 0.5)):
        sig.write(out / f"{i}.wav", base * scale)
    html = page.folder_view(folder.measure(out))
    assert "<td>Spread</td>" in html
    assert "<td>Files</td>" in html
    assert "has no spread" in html


def test_every_shown_field_has_a_name_that_is_not_its_path(tmp_path):
    x = music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    html = page.file_view(one, None, None)
    assert "loudness.integrated_lufs" not in html
    assert "Integrated loudness" in html
    for field in fields.FIELDS:
        assert field.path not in html, f"{field.path} leaked into the page as a raw path"


def test_the_page_asks_for_nothing_from_outside(tmp_path):
    x = music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    html = page.document("t", page.file_view(one, None, None))
    for forbidden in ("http://", "https://", "//fonts", "<script", "@import"):
        assert forbidden not in html, f"the page reaches outside itself with {forbidden}"


def test_the_document_is_one_html_page():
    html = page.document("t", "<p>x</p>")
    assert html.startswith("<!doctype html>")
    assert html.count("<html") == 1 and html.count("</html>") == 1
    assert "<title>t</title>" in html


def test_the_octave_alternatives_are_shown_not_only_computed(tmp_path):
    x = music.limit(music.build("kick_hat_snare", 88.0, seconds=60.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    html = page.file_view(one, None, None)
    assert "Rates the signal also supports" in html
    for alternative in one["tempo"]["alternatives"]:
        assert f"{alternative['bpm']:.2f}" in html, (
            f"{alternative['bpm']} was computed and never shown"
        )
    assert html.count("<span class=\"tag\">reported</span>") == 1


def test_the_alternatives_check_can_fail(tmp_path):
    x = music.limit(music.build("kick_hat_snare", 88.0, seconds=60.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    one["tempo"] = dict(one["tempo"], alternatives=[])
    assert page.octaves(one) == "", (
        "the block would claim to show alternatives when there are none"
    )
