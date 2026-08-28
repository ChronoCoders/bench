from __future__ import annotations

from bench.decode import Audio
from bench.measure import bs1770, ebur128

METHOD = "loudness/two-instruments"

ROUNDING_HALF_STEP = {
    "integrated_lufs": 0.0005,
    "lra_lu": 0.005,
    "true_peak_dbtp": 0.05,
    "sample_peak_dbfs": 0.05,
}
TRUE_PEAK_METHOD_UNCERTAINTY_DB = 0.03

TOLERANCE = {
    "integrated_lu": 0.05,
    "lra_lu": 0.1,
    "true_peak_db": 0.15,
    "sample_peak_db": 0.06,
}


def measure(audio: Audio) -> dict:
    primary = ebur128.measure(audio.path, audio.duration_s)
    out = primary.to_dict()

    second = bs1770.integrated(audio.samples, audio.sample_rate_hz)
    cross = {
        "method": bs1770.METHOD,
        "integrated_lufs": None if second is None else second.lufs,
        "lra_lu": bs1770.loudness_range(audio.samples, audio.sample_rate_hz),
        "true_peak_dbtp": bs1770.true_peak_dbtp(audio.samples),
        "sample_peak_dbfs": bs1770.sample_peak_dbfs(audio.samples),
    }
    if second is not None:
        cross["gating_blocks"] = {
            "total": second.blocks_total,
            "over_absolute_gate": second.blocks_over_absolute_gate,
            "over_relative_gate": second.blocks_over_relative_gate,
        }

    delta = {}
    disagree_on_existence = []
    beyond = []
    for field, unit in (("integrated_lufs", "integrated_lu"), ("lra_lu", "lra_lu"),
                        ("true_peak_dbtp", "true_peak_db"), ("sample_peak_dbfs", "sample_peak_db")):
        a, b = out.get(field), cross.get(field)
        if a is None and b is None:
            continue
        if a is None or b is None:
            disagree_on_existence.append(field)
            continue
        delta[unit] = round(b - a, 4)
        if abs(delta[unit]) > TOLERANCE[unit]:
            beyond.append(unit)

    cross = {k: v for k, v in cross.items() if v is not None}
    cross["delta"] = delta
    cross["tolerance"] = TOLERANCE
    if beyond:
        cross["beyond_tolerance"] = beyond
    if disagree_on_existence:
        cross["only_one_instrument_reported"] = disagree_on_existence

    uncertainty = {}
    for field, unit in (("integrated_lufs", "integrated_lu"), ("lra_lu", "lra_lu"),
                        ("true_peak_dbtp", "true_peak_db"), ("sample_peak_dbfs", "sample_peak_db")):
        if out.get(field) is None:
            continue
        floor = ROUNDING_HALF_STEP[field]
        if field == "true_peak_dbtp":
            floor = max(floor, TRUE_PEAK_METHOD_UNCERTAINTY_DB)
        uncertainty[field] = round(max(floor, abs(delta.get(unit, 0.0))), 4)
    out["uncertainty"] = uncertainty
    out["crosscheck"] = cross
    return out
