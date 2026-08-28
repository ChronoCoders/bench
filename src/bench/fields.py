"""One name, one unit and one precision per measured field, used everywhere it is shown.

Band entries are built from the band edges the spectral module actually uses, so a change
to the edges cannot leave a stale label behind.
"""

from __future__ import annotations

from dataclasses import dataclass

from bench.measure import spectral


@dataclass(frozen=True)
class Field:
    path: str
    name: str
    short: str
    decimals: int
    unit: str = ""
    spread_withheld: str | None = None


def _hz(value: float) -> str:
    return f"{value / 1000.0:.0f}k" if value >= 1000.0 else f"{value:.0f}"


def _bands() -> tuple[Field, ...]:
    out = []
    for lo, hi in zip(spectral.BAND_EDGES_HZ, spectral.BAND_EDGES_HZ[1:]):
        key = f"{lo:.0f}_{hi:.0f}"
        out.append(Field(f"spectral.band_pct.{key}", f"{_hz(lo)} to {_hz(hi)} Hz",
                         f"{_hz(lo)} to {_hz(hi)}", spectral.PERCENT_DECIMALS, "%"))
    return tuple(out)


FIELDS = (
    Field("loudness.integrated_lufs", "Integrated loudness", "LUFS", 1, "LUFS"),
    Field("loudness.lra_lu", "Loudness range", "LRA", 1, "LU"),
    Field("loudness.true_peak_dbtp", "True peak", "dBTP", 1, "dBTP"),
    Field("loudness.sample_peak_dbfs", "Sample peak", "peak", 1, "dBFS"),
    Field("levels.crest_db", "Crest", "crest", 1, "dB"),
    Field("levels.gated_rms_dbfs", "Gated level", "level", 1, "dBFS"),
    Field("levels.clipped_runs", "Clipped runs", "clips", 0),
    Field("levels.over_full_scale_samples", "Samples over full scale", "over", 0),
    Field("spectral.rollups.under_250_hz_pct", "Under 250 Hz", "under 250",
          spectral.PERCENT_DECIMALS, "%"),
    Field("spectral.rollups.band_60_250_pct", "60 to 250 Hz", "60 to 250",
          spectral.PERCENT_DECIMALS, "%"),
    *_bands(),
    Field("stereo.correlation", "Left to right", "L to R", 3),
    Field("stereo.width_side_mid_db", "Width, side over mid", "width", 1, "dB"),
    Field("tempo.bpm", "Tempo", "BPM", 2, "BPM",
          spread_withheld="tracks are meant to differ in tempo, and these sit on different "
                          "octaves, so the range across them measures nothing"),
    Field("tempo.grid_fit_ms", "Grid fit", "fit", 2, "ms"),
    Field("tempo.coverage", "Onsets on the grid", "on grid", 2),
    Field("tempo.drift.span_bpm", "Tempo movement", "drift", 2, "BPM"),
)

BY_PATH = {f.path: f for f in FIELDS}


def get(path: str) -> Field:
    found = BY_PATH.get(path)
    if found is None:
        raise KeyError(f"no field registered as {path!r}")
    return found


def name_of(path: str) -> str:
    found = BY_PATH.get(path)
    return found.name if found else path
