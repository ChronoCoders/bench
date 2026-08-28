"""Every file in a folder, one row each, and the spread across them per column.

The spread is the largest value minus the smallest, and it carries how many files it was
taken over. A spread over eight of nine files is not the spread of the record.
"""

from __future__ import annotations

from pathlib import Path

from bench import compare, fields, measurement
from bench.decode import DecodeError

AUDIO_SUFFIXES = (".wav", ".flac", ".aiff", ".aif", ".mp3", ".m4a", ".ogg", ".opus")


COLUMN_PATHS = (
    "loudness.integrated_lufs",
    "loudness.lra_lu",
    "loudness.true_peak_dbtp",
    "levels.crest_db",
    "spectral.rollups.under_250_hz_pct",
    "spectral.rollups.band_60_250_pct",
    "spectral.band_pct.20_60",
    "spectral.band_pct.8000_16000",
    "stereo.correlation",
    "stereo.width_side_mid_db",
    "tempo.bpm",
    "tempo.drift.span_bpm",
)

COLUMNS = tuple(fields.get(path) for path in COLUMN_PATHS)


def audio_files(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES)


def measure(folder: str | Path, target: dict | None = None) -> dict:
    rows, skipped = [], []
    measurements, comparisons = {}, {}
    for path in audio_files(folder):
        try:
            one = measurement.of_file(path)
        except (DecodeError, OSError) as why:
            skipped.append({"name": path.name, "why": str(why)})
            continue
        measurements[path.name] = one
        row = {"name": path.name, "values": {c.path: _number(one, c.path) for c in COLUMNS}}
        if target is not None:
            result = compare.against(one, target)
            comparisons[path.name] = result
            row["verdicts"] = {r["field"]: r["verdict"] for r in compare.judged(result["rows"])
                               if r["field"] in row["values"]}
        rows.append(row)

    spread = {}
    for column in COLUMNS:
        present = [r["values"][column.path] for r in rows if r["values"][column.path] is not None]
        if column.spread_withheld is not None:
            spread[column.path] = {"n": len(present), "withheld": column.spread_withheld}
            continue
        if not present:
            spread[column.path] = {"n": 0}
            continue
        spread[column.path] = {
            "low": round(min(present), column.decimals),
            "high": round(max(present), column.decimals),
            "spread": round(max(present) - min(present), column.decimals),
            "n": len(present),
            "complete": len(present) == len(rows),
        }
    return {
        "folder": str(folder),
        "columns": [{"path": c.path, "label": c.short, "name": c.name,
                     "decimals": c.decimals, "unit": c.unit,
                     "spread_withheld": c.spread_withheld} for c in COLUMNS],
        "files": rows,
        "measurements": measurements,
        "comparisons": comparisons,
        "spread": spread,
        "skipped": skipped,
    }


def measurement_for(sheet: dict, name: str) -> dict:
    return sheet["measurements"][name]


def _number(one: dict, path: str) -> float | None:
    value = compare.dig(one, path)
    return float(value) if isinstance(value, (int, float)) else None
