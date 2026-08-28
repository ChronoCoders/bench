from __future__ import annotations

import json
from pathlib import Path

import pytest

import music
import rig
import signals as sig
from bench import compare, measurement

TARGETS = Path(__file__).resolve().parent.parent / "targets"
CEILING = {"max": -1.0}
RANGE = {"low": 60.0, "high": 70.0}


def measured(value, uncertainty, module="loudness", field="true_peak_dbtp"):
    one = {"spectral": {"band_set": "bench-v1"}}
    block = one.setdefault(module, {})
    block[field] = value
    block.setdefault("uncertainty", {})[field] = uncertainty
    return one


def target(fields=None, limits=None, withheld=None, band_set="bench-v1"):
    out = {"name": "test", "band_set": band_set, "evidence": {"n": 1},
           "fields": fields if fields is not None else {}}
    if limits is not None:
        out["limits"] = limits
    if withheld is not None:
        out["withheld"] = withheld
    return out


def only_row(measurement_dict, target_dict):
    return compare.against(measurement_dict, target_dict)["rows"][0]


def test_a_value_clear_of_the_ceiling_is_inside():
    row = only_row(measured(-1.20, 0.05),
                   target(limits={"loudness.true_peak_dbtp": dict(CEILING, declared_by="test")}))
    assert row["verdict"] == compare.INSIDE


def test_a_value_on_the_ceiling_is_not_inside():
    row = only_row(measured(-1.00, 0.05),
                   target(limits={"loudness.true_peak_dbtp": dict(CEILING, declared_by="test")}))
    assert row["verdict"] == compare.ON_THE_LINE
    assert row["verdict"] not in compare.VERDICTS_THAT_PASS


def test_the_uncertainty_is_what_moves_the_verdict():
    bound = target(limits={"loudness.true_peak_dbtp": dict(CEILING, declared_by="test")})
    tight = only_row(measured(-1.06, 0.01), bound)
    loose = only_row(measured(-1.06, 0.10), bound)
    assert tight["verdict"] == compare.INSIDE
    assert loose["verdict"] == compare.ON_THE_LINE, (
        "the same value must stop passing once its uncertainty reaches the boundary"
    )


def test_a_value_clear_over_the_ceiling_is_above():
    row = only_row(measured(-0.50, 0.05),
                   target(limits={"loudness.true_peak_dbtp": dict(CEILING, declared_by="test")}))
    assert row["verdict"] == compare.ABOVE
    rig.control(row["deviation"], 0.5, 1e-9, "how far over the ceiling the file sits")


@pytest.mark.parametrize("value,expected", [
    (65.0, compare.INSIDE), (75.0, compare.ABOVE), (55.0, compare.BELOW),
    (70.0, compare.ON_THE_LINE), (60.0, compare.ON_THE_LINE),
])
def test_a_range_places_a_value(value, expected):
    row = only_row(measured(value, 0.5, module="spectral", field="under_250_hz_pct"),
                   target(fields={"spectral.under_250_hz_pct": RANGE}))
    assert row["verdict"] == expected


def test_the_range_placement_can_fail():
    row = only_row(measured(65.0, 0.5, module="spectral", field="under_250_hz_pct"),
                   target(fields={"spectral.under_250_hz_pct": RANGE}))
    assert row["verdict"] != compare.ABOVE, "a value in the middle of the range read as above it"


def test_a_mismatched_band_set_is_refused():
    with pytest.raises(compare.BandSetMismatch, match="different band edges"):
        compare.against(measured(65.0, 0.5), target(band_set="somebody-elses-edges"))


def test_a_matching_band_set_is_not_refused():
    result = compare.against(measured(-1.2, 0.05),
                             target(limits={"loudness.true_peak_dbtp":
                                            dict(CEILING, declared_by="test")}))
    assert result["counts"][compare.INSIDE] == 1


def test_a_field_with_no_uncertainty_is_not_placed():
    one = {"loudness": {"true_peak_dbtp": -1.2}, "spectral": {"band_set": "bench-v1"}}
    row = only_row(one, target(limits={"loudness.true_peak_dbtp":
                                       dict(CEILING, declared_by="test")}))
    assert row["verdict"] == compare.NOT_MEASURED
    assert "uncertainty" in row["why"]


def test_a_field_the_file_does_not_have_is_not_placed():
    one = {"spectral": {"band_set": "bench-v1"}}
    row = only_row(one, target(limits={"loudness.true_peak_dbtp":
                                       dict(CEILING, declared_by="test")}))
    assert row["verdict"] == compare.NOT_MEASURED


def test_a_withheld_field_shows_its_reason_and_does_not_pass():
    result = compare.against(measured(-1.2, 0.05),
                             target(withheld={"loudness.true_peak_dbtp": "the references cannot say"}))
    row = result["rows"][0]
    assert row["verdict"] == compare.NO_TARGET
    assert row["why"] == "the references cannot say"
    assert row["value"] == -1.2
    assert compare.INSIDE not in result["counts"]


def test_anything_on_the_line_stops_the_whole_comparison_passing():
    one = {"loudness": {"true_peak_dbtp": -1.0, "integrated_lufs": -9.5,
                        "uncertainty": {"true_peak_dbtp": 0.05, "integrated_lufs": 0.005}},
           "spectral": {"band_set": "bench-v1"}}
    bound = target(fields={"loudness.integrated_lufs": {"low": -10.0, "high": -9.0}},
                   limits={"loudness.true_peak_dbtp": dict(CEILING, declared_by="test")})
    result = compare.against(one, bound)
    assert result["counts"][compare.INSIDE] == 1
    assert result["counts"][compare.ON_THE_LINE] == 1
    assert result["all_inside"] is False


def test_everything_inside_passes():
    one = {"loudness": {"true_peak_dbtp": -2.0, "integrated_lufs": -9.5,
                        "uncertainty": {"true_peak_dbtp": 0.05, "integrated_lufs": 0.005}},
           "spectral": {"band_set": "bench-v1"}}
    bound = target(fields={"loudness.integrated_lufs": {"low": -10.0, "high": -9.0}},
                   limits={"loudness.true_peak_dbtp": dict(CEILING, declared_by="test")})
    assert compare.against(one, bound)["all_inside"] is True


def test_a_declared_limit_is_marked_apart_from_measured_evidence():
    bound = target(fields={"loudness.integrated_lufs": {"low": -10.0, "high": -9.0,
                                                        "from_lossy": True}},
                   limits={"loudness.true_peak_dbtp": dict(CEILING, declared_by="test")})
    one = {"loudness": {"true_peak_dbtp": -2.0, "integrated_lufs": -9.5,
                        "uncertainty": {"true_peak_dbtp": 0.05, "integrated_lufs": 0.005}},
           "spectral": {"band_set": "bench-v1"}}
    basis = {r["field"]: r["basis"] for r in compare.against(one, bound)["rows"]}
    assert basis["loudness.integrated_lufs"] == "measured references"
    assert basis["loudness.true_peak_dbtp"] == "declared"


def test_an_advisory_bound_reports_information_and_not_a_verdict():
    bound = target(fields={"loudness.integrated_lufs":
                           {"low": -10.0, "high": -9.0, "advisory": "two files is not a rule"}})
    one = {"loudness": {"integrated_lufs": -14.9, "uncertainty": {"integrated_lufs": 0.005}},
           "spectral": {"band_set": "bench-v1"}}
    result = compare.against(one, bound)
    row = result["rows"][0]
    assert row["advisory"] is True
    assert row["why"] == "two files is not a rule"
    assert result["advisory"] == 1
    assert result["counts"] == {}
    assert result["all_inside"] is True, "an advisory bound must not decide the outcome"
    assert compare.judged(result["rows"]) == []


def test_the_same_bound_without_the_advisory_note_does_decide():
    bound = target(fields={"loudness.integrated_lufs": {"low": -10.0, "high": -9.0}})
    one = {"loudness": {"integrated_lufs": -14.9, "uncertainty": {"integrated_lufs": 0.005}},
           "spectral": {"band_set": "bench-v1"}}
    result = compare.against(one, bound)
    assert result["rows"][0]["advisory"] is False
    assert result["counts"] == {compare.BELOW: 1}
    assert result["all_inside"] is False


def test_the_shipped_target_marks_loudness_range_as_information():
    loaded = compare.load(TARGETS / "guaracha-club.json")
    assert loaded["fields"]["loudness.lra_lu"].get("advisory")
    assert loaded["evidence"]["n"] == 2
    others = [f for name, f in loaded["fields"].items() if name != "loudness.lra_lu"]
    assert not any(f.get("advisory") for f in others), (
        "only loudness range is marked advisory, and the reason names the evidence count"
    )


def write_target(tmp_path, body):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_a_target_without_an_evidence_count_is_refused(tmp_path):
    body = {"name": "t", "band_set": "bench-v1", "evidence": {}, "fields": {}}
    with pytest.raises(compare.TargetError, match="how many references"):
        compare.load(write_target(tmp_path, body))


def test_a_target_with_a_bound_that_says_nothing_is_refused(tmp_path):
    body = {"name": "t", "band_set": "bench-v1", "evidence": {"n": 1},
            "fields": {"loudness.lra_lu": {"about": 7}}}
    with pytest.raises(compare.TargetError, match="max, or both low and high"):
        compare.load(write_target(tmp_path, body))


def test_a_limit_that_does_not_say_who_declared_it_is_refused(tmp_path):
    body = {"name": "t", "band_set": "bench-v1", "evidence": {"n": 1}, "fields": {},
            "limits": {"loudness.true_peak_dbtp": {"max": -1.0}}}
    with pytest.raises(compare.TargetError, match="who declared it"):
        compare.load(write_target(tmp_path, body))


def test_a_well_formed_target_loads(tmp_path):
    body = {"name": "t", "band_set": "bench-v1", "evidence": {"n": 2}, "fields": {},
            "limits": {"loudness.true_peak_dbtp": {"max": -1.0, "declared_by": "test"}}}
    assert compare.load(write_target(tmp_path, body))["evidence"]["n"] == 2


def shipped():
    return sorted(TARGETS.glob("*.json"))


@pytest.mark.parametrize("path", shipped(), ids=lambda p: p.stem)
def test_every_shipped_target_says_what_it_rests_on(path):
    loaded = compare.load(path)
    evidence = loaded["evidence"]
    assert evidence["n"] == len(evidence["sources"]), (
        "the evidence count does not match the number of sources listed"
    )
    assert evidence["n"] >= 1
    if evidence.get("all_sources_lossy"):
        assert all(source["lossy"] for source in evidence["sources"])
        assert all(f["from_lossy"] for f in loaded["fields"].values())
        assert "loudness.true_peak_dbtp" not in loaded["fields"], (
            "a lossy reference cannot say where a true peak sits"
        )
        assert "loudness.true_peak_dbtp" in loaded["limits"]
    for name, bound in loaded["fields"].items():
        assert len(bound["values"]) == evidence["n"], (
            f"{name} was seeded from a different number of files than the evidence count"
        )
        assert bound["low"] == min(bound["values"])
        assert bound["high"] == max(bound["values"])


@pytest.mark.parametrize("path", shipped(), ids=lambda p: p.stem)
def test_a_dropped_reference_is_named_with_its_reason(path):
    evidence = compare.load(path)["evidence"]
    for dropped in evidence.get("excluded", []):
        assert dropped["file"] and dropped["why"], (
            "a reference was removed from a profile without saying which or why"
        )
        assert dropped["file"] not in [s["file"] for s in evidence["sources"]]


def test_the_shipped_target_check_can_fail(tmp_path):
    body = {"name": "t", "band_set": "bench-v1",
            "evidence": {"n": 3, "sources": [{"file": "a", "lossy": True}]},
            "fields": {}}
    loaded = compare.load(write_target(tmp_path, body))
    assert loaded["evidence"]["n"] != len(loaded["evidence"]["sources"]), (
        "the count check would accept a profile claiming more sources than it lists"
    )


def test_a_real_file_compares_against_the_shipped_target(tmp_path):
    x = music.limit(music.build("dense", 128.0, seconds=40.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    result = compare.against(one, compare.load(TARGETS / "guaracha-club.json"))
    assert result["rows"]
    assert result["target"]["evidence"]["n"] == 2
    placed = [r for r in result["rows"] if "verdict" in r and r["verdict"] not in
              (compare.NO_TARGET, compare.NOT_MEASURED)]
    assert placed, "nothing in the shipped target could be placed against a real measurement"
