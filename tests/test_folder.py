from __future__ import annotations

import numpy as np

from pathlib import Path

import music
import rig
import signals as sig
from bench import compare, folder, report

TARGETS = Path(__file__).resolve().parent.parent / "targets"

HALF_DB = 20.0 * np.log10(2.0)
LUFS = "loudness.integrated_lufs"
CORRELATION = "stereo.correlation"
BPM = "tempo.bpm"
LRA = "loudness.lra_lu"


def album(tmp_path, seconds=35.0, scales=(1.0, 0.5, 0.25)):
    out = tmp_path / "album"
    out.mkdir()
    base = music.limit(music.build("dense", 128.0, seconds=seconds, jitter=0.004))
    for i, scale in enumerate(scales):
        sig.write(out / f"{i}_track.wav", base * scale)
    return out


def test_the_loudness_spread_is_the_largest_minus_the_smallest(tmp_path):
    sheet = folder.measure(album(tmp_path))
    rig.control(sheet["spread"][LUFS]["spread"], 2.0 * HALF_DB, 0.05,
                "loudness spread over three files at full, half and quarter amplitude")


def test_the_loudness_spread_control_can_fail(tmp_path):
    sheet = folder.measure(album(tmp_path))
    rig.rejects(sheet["spread"][LUFS]["spread"], HALF_DB, 0.05,
                "a spread over three files read as the gap between two of them")


def test_the_spread_says_how_many_files_it_covers(tmp_path):
    sheet = folder.measure(album(tmp_path))
    assert sheet["spread"][LUFS]["n"] == 3
    assert sheet["spread"][LUFS]["complete"] is True


def test_a_file_missing_a_field_shrinks_that_column_and_says_so(tmp_path):
    out = album(tmp_path)
    mono = music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004))[:1]
    sig.write(out / "9_mono.wav", mono)
    sheet = folder.measure(out)
    assert sheet["spread"][CORRELATION]["n"] == 3
    assert sheet["spread"][CORRELATION]["complete"] is False
    assert "L to R" in report.folder_table(sheet)
    assert "Spread taken over fewer files" in report.folder_table(sheet)


def test_a_withheld_spread_prints_no_number_and_gives_the_reason(tmp_path):
    sheet = folder.measure(album(tmp_path))
    assert "withheld" in sheet["spread"][BPM]
    assert "spread" not in sheet["spread"][BPM]
    text = report.folder_table(sheet)
    assert "No spread for BPM" in text
    spread_line = [ln for ln in text.splitlines() if ln.startswith("spread")][0]
    bpm_values = [r["values"][BPM] for r in sheet["files"]]
    assert all(v is not None for v in bpm_values), "this control needs the tempo to be measured"
    assert f"{bpm_values[0]:.2f}" not in spread_line


def test_a_file_that_cannot_be_read_is_named_rather_than_dropped(tmp_path):
    out = album(tmp_path)
    (out / "broken.wav").write_text("this is not a wave file", encoding="utf-8")
    sheet = folder.measure(out)
    assert [s["name"] for s in sheet["skipped"]] == ["broken.wav"]
    assert len(sheet["files"]) == 3
    assert "Not read: broken.wav" in report.folder_table(sheet)


def test_a_short_file_leaves_gaps_rather_than_numbers(tmp_path):
    out = tmp_path / "short"
    out.mkdir()
    sig.write(out / "a.wav", music.build("dense", 128.0, seconds=5.0))
    sheet = folder.measure(out)
    assert sheet["files"][0]["values"][BPM] is None
    assert sheet["measurements"]["a.wav"]["tempo"]["unmeasurable"]
    label = sheet["files"][0]["label"]
    assert label == "a", "the extension should be off the track name"
    row = [ln for ln in report.folder_table(sheet).splitlines() if ln.startswith(label)][0]
    assert "None" not in row and "nan" not in row


def test_every_row_has_a_cell_for_every_column(tmp_path):
    sheet = folder.measure(album(tmp_path))
    for row in sheet["files"]:
        assert set(row["values"]) == {c.path for c in folder.COLUMNS}
    header = report.folder_table(sheet).splitlines()[0]
    for column in folder.COLUMNS:
        assert column.short in header, f"{column.label} is missing from the table header"


def test_the_measurement_is_held_once_and_the_row_points_at_it(tmp_path):
    sheet = folder.measure(album(tmp_path))
    names = [r["name"] for r in sheet["files"]]
    assert sorted(sheet["measurements"]) == sorted(names)
    for row in sheet["files"]:
        assert "measurement" not in row, "the row is carrying a measurement instead of naming one"
        assert row["name"] in sheet["measurements"]


def test_each_row_points_at_the_measurement_of_its_own_file(tmp_path):
    sheet = folder.measure(album(tmp_path))
    seen = []
    for row in sheet["files"]:
        one = folder.measurement_for(sheet, row["name"])
        assert one["file"]["name"] == row["name"]
        rig.control(row["values"][LUFS], one["loudness"]["integrated_lufs"], 1e-9,
                    f"the loudness in the row for {row['name']} against its own measurement")
        seen.append(one["loudness"]["integrated_lufs"])
    assert len(set(seen)) == len(seen), "two rows point at the same measurement"


def test_the_row_to_measurement_link_can_fail(tmp_path):
    sheet = folder.measure(album(tmp_path))
    first, second = sheet["files"][0], sheet["files"][1]
    other = folder.measurement_for(sheet, second["name"])
    rig.rejects(first["values"][LUFS], other["loudness"]["integrated_lufs"], 0.05,
                "one file's row read against another file's measurement")


def test_a_target_puts_a_verdict_on_each_cell_it_covers(tmp_path):
    target = compare.load(TARGETS / "guaracha-club.json")
    sheet = folder.against(folder.measure(album(tmp_path)), target)
    assert sorted(sheet["comparisons"]) == sorted(sheet["measurements"])
    for row in sheet["files"]:
        assert row["verdicts"], "a target was given and no cell carried a verdict"
        assert LRA not in row["verdicts"], "an advisory bound produced a verdict"
        assert set(row["verdicts"]) <= set(row["values"])


def test_no_target_means_no_verdicts(tmp_path):
    sheet = folder.measure(album(tmp_path))
    assert sheet["comparisons"] == {}
    assert all("verdicts" not in row for row in sheet["files"])


def test_the_table_columns_line_up(tmp_path):
    sheet = folder.measure(album(tmp_path))
    lines = report.folder_table(sheet).splitlines()
    rule = lines[1]
    starts = [i for i, ch in enumerate(rule) if ch == "-" and (i == 0 or rule[i - 1] == " ")]
    assert len(starts) == 1 + len(folder.COLUMNS)
    for line in lines[2:2 + len(sheet["files"])]:
        assert len(line) <= len(rule) + 1, "a data row ran past the rule above it"
