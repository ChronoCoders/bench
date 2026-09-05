"""Every file in a folder, one row each, and the spread across them per column.

The spread is the largest value minus the smallest, and it carries how many files it was
taken over. A spread over eight of nine files is not the spread of the record.

Measuring and comparing are separate calls. A measurement is a fact about the files and
can be held; a comparison is a fact about the files and a target, and holding one means
serving the verdicts of a target that may since have been edited.
"""

from __future__ import annotations

import os
from pathlib import Path

from bench import compare, fields, measurement
from bench.decode import DecodeError

AUDIO_SUFFIXES = (".wav", ".flac", ".aiff", ".aif", ".mp3", ".m4a", ".ogg", ".opus")


# Grouped so the table can rule between them. The grouping is what the columns
# measure, not how they are laid out, so it lives with the list rather than in the
# thing that draws it.
COLUMN_GROUPS = (
    ("loudness.integrated_lufs", "loudness.lra_lu", "loudness.true_peak_dbtp",
     "levels.crest_db"),
    ("spectral.rollups.under_250_hz_pct", "spectral.rollups.band_60_250_pct",
     "spectral.band_pct.20_60", "spectral.band_pct.8000_16000"),
    ("stereo.correlation", "stereo.width_side_mid_db"),
    ("tempo.bpm", "tempo.drift.span_bpm"),
)

COLUMN_PATHS = tuple(path for group in COLUMN_GROUPS for path in group)
COLUMNS = tuple(fields.get(path) for path in COLUMN_PATHS)
GROUP_STARTS = frozenset(group[0] for group in COLUMN_GROUPS[1:])


def labels(names: list[str]) -> dict[str, str]:
    """Track names with the extension and any shared prefix taken off.

    Six files called "Pull me under (Arabic) Bahrein.wav" and so on differ in one
    word, and the column is easier to read when only that word is in it. A prefix
    is only removed when every name carries it and none is left empty.
    """
    stems = {name: Path(name).stem for name in names}
    if len(stems) < 2:
        return stems
    shared = os.path.commonprefix(list(stems.values()))
    if not shared:
        return stems
    trimmed = {name: stem[len(shared):].lstrip(" _-") for name, stem in stems.items()}
    if any(not short for short in trimmed.values()):
        return stems
    return trimmed


def audio_files(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES)


def measure(folder: str | Path) -> dict:
    rows, skipped = [], []
    measurements = {}
    for path in audio_files(folder):
        try:
            one = measurement.of_file(path)
        except (DecodeError, OSError) as why:
            skipped.append({"name": path.name, "why": str(why)})
            continue
        measurements[path.name] = one
        rows.append({"name": path.name,
                     "values": {c.path: _number(one, c.path) for c in COLUMNS}})

    short = labels([row["name"] for row in rows])
    for row in rows:
        row["label"] = short[row["name"]]

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
                     "starts_group": c.path in GROUP_STARTS,
                     "spread_withheld": c.spread_withheld} for c in COLUMNS],
        "files": rows,
        "measurements": measurements,
        "comparisons": {},
        "spread": spread,
        "skipped": skipped,
    }


def against(sheet: dict, target: dict | None) -> dict:
    """The same sheet with a target applied, as a new sheet.

    New rather than in place because the sheet handed in may be a held measurement, and
    a verdict written into it would outlive the target it came from.
    """
    if target is None:
        return sheet
    comparisons, rows = {}, []
    for row in sheet["files"]:
        result = compare.against(sheet["measurements"][row["name"]], target)
        comparisons[row["name"]] = result
        rows.append(dict(row, verdicts={
            r["field"]: r["verdict"] for r in compare.judged(result["rows"])
            if r["field"] in row["values"]}))
    return dict(sheet, files=rows, comparisons=comparisons)


def measurement_for(sheet: dict, name: str) -> dict:
    return sheet["measurements"][name]


def _number(one: dict, path: str) -> float | None:
    value = compare.dig(one, path)
    return float(value) if isinstance(value, (int, float)) else None
