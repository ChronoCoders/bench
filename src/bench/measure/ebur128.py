from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

METHOD = "loudness/ffmpeg-ebur128"

SUMMARY_ROUNDING_LU = 0.06
SUMMARY_ROUNDING_DB = 0.06
METADATA_PEAK_QUANTUM = 0.0005
GATING_BLOCK_S = 0.400
SHORT_TERM_WINDOW_S = 3.000
ABSOLUTE_GATE_LUFS = -70.0

FILTER_CHAIN = "ebur128=metadata=1:peak=true+sample,ametadata=print:file=-"

_METADATA = re.compile(r"^lavfi\.r128\.(\S+)=(\S+)$", re.M)
_SUMMARY_FIELDS = {
    "I": r"I:\s*(\S+)\s*LUFS",
    "integrated_threshold": r"Integrated loudness:\s*\n\s*I:\s*\S+\s*LUFS\s*\n\s*Threshold:\s*(\S+)\s*LUFS",
    "LRA": r"LRA:\s*(\S+)\s*LU",
    "sample_peak": r"Sample peak:\s*\n\s*Peak:\s*(\S+)\s*dBFS",
    "true_peak": r"True peak:\s*\n\s*Peak:\s*(\S+)\s*dBFS",
}


class Ebur128Error(RuntimeError):
    pass


@dataclass(frozen=True)
class Loudness:
    integrated_lufs: float | None
    integrated_absent_because: str | None
    relative_gate_lufs: float | None
    lra_lu: float | None
    lra_absent_because: str | None
    true_peak_dbtp: float | None
    sample_peak_dbfs: float | None
    peaks_absent_because: str | None

    def to_dict(self) -> dict:
        d = {"method": METHOD}
        for key, value in (
            ("integrated_lufs", self.integrated_lufs),
            ("relative_gate_lufs", self.relative_gate_lufs),
            ("lra_lu", self.lra_lu),
            ("true_peak_dbtp", self.true_peak_dbtp),
            ("sample_peak_dbfs", self.sample_peak_dbfs),
        ):
            if value is not None:
                d[key] = value
        absent = {k: v for k, v in (
            ("integrated_lufs", self.integrated_absent_because),
            ("lra_lu", self.lra_absent_because),
            ("true_peak_dbtp", self.peaks_absent_because),
            ("sample_peak_dbfs", self.peaks_absent_because),
        ) if v is not None}
        if absent:
            d["absent_because"] = absent
        return d


def _run(path: Path) -> tuple[dict[str, float], dict[str, float]]:
    cmd = [
        "ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-map", "0:a:0",
        "-filter:a", FILTER_CHAIN, "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, text=True)
    if r.returncode != 0:
        raise Ebur128Error(f"ffmpeg failed on {path}: {r.stderr.strip()[-400:]}")

    metadata: dict[str, float] = {}
    for key, raw in _METADATA.findall(r.stdout):
        metadata[key] = float(raw)
    if "I" not in metadata:
        raise Ebur128Error(f"ebur128 published no loudness metadata for {path}")

    parts = r.stderr.split("Summary:")
    if len(parts) != 2:
        raise Ebur128Error(
            f"expected exactly one ebur128 Summary for {path}, found {len(parts) - 1}"
        )
    summary: dict[str, float] = {}
    for name, pattern in _SUMMARY_FIELDS.items():
        m = re.search(pattern, parts[1])
        if m:
            summary[name] = float(m.group(1))
    return metadata, summary


def _agree(name: str, precise: float, rounded: float, path: Path) -> float:
    if abs(precise - rounded) > SUMMARY_ROUNDING_LU:
        raise Ebur128Error(
            f"{path.name}: ebur128 {name} is {precise} in the frame metadata and {rounded} in the "
            f"Summary, further apart than the Summary's rounding of {SUMMARY_ROUNDING_LU}"
        )
    return precise


def _peak_guard_db(metadata_linear: float) -> float:
    return SUMMARY_ROUNDING_DB + float(
        20.0 * np.log10((metadata_linear + METADATA_PEAK_QUANTUM) / metadata_linear)
    )


def _agree_peak(name: str, summary_db: float, metadata_linear: float, path: Path) -> float:
    if metadata_linear <= 0.0:
        return summary_db
    guard = _peak_guard_db(metadata_linear)
    metadata_db = float(20.0 * np.log10(metadata_linear))
    if abs(summary_db - metadata_db) > guard:
        raise Ebur128Error(
            f"{path.name}: ebur128 {name} is {summary_db} dB in the Summary and {metadata_db:.4f} dB "
            f"from the metadata's linear {metadata_linear}, further apart than the {guard:.4f} dB "
            "the two printing formats account for at this level"
        )
    return summary_db


def measure(path: Path, duration_s: float) -> Loudness:
    metadata, summary = _run(Path(path))
    path = Path(path)

    integrated = None
    absent_i = None
    if duration_s < GATING_BLOCK_S:
        absent_i = f"shorter than one {GATING_BLOCK_S * 1000:.0f} ms gating block"
    elif metadata["I"] == ABSOLUTE_GATE_LUFS:
        absent_i = f"no block passed the absolute gate at {ABSOLUTE_GATE_LUFS} LUFS"
    else:
        integrated = _agree("integrated loudness", metadata["I"], summary["I"], path)

    lra = None
    absent_lra = None
    if duration_s < SHORT_TERM_WINDOW_S:
        absent_lra = f"shorter than one {SHORT_TERM_WINDOW_S:.0f} s short term window"
    elif integrated is None:
        absent_lra = absent_i
    else:
        lra = _agree("loudness range", metadata["LRA"], summary["LRA"], path)

    true_peak = sample_peak = None
    absent_peaks = None
    if not math.isfinite(summary.get("true_peak", -math.inf)):
        absent_peaks = "digital silence has no peak"
    else:
        true_peak = _agree_peak("true peak", summary["true_peak"], metadata.get("true_peak", 0.0), path)
        if math.isfinite(summary.get("sample_peak", -math.inf)):
            sample_peak = _agree_peak("sample peak", summary["sample_peak"],
                                      metadata.get("sample_peak", 0.0), path)

    return Loudness(
        integrated_lufs=integrated,
        integrated_absent_because=absent_i,
        relative_gate_lufs=summary.get("integrated_threshold") if integrated is not None else None,
        lra_lu=lra,
        lra_absent_because=absent_lra,
        true_peak_dbtp=true_peak,
        sample_peak_dbfs=sample_peak,
        peaks_absent_because=absent_peaks,
    )
