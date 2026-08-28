"""Build a target profile from reference files by measuring them.

Nothing here accepts a quoted figure. Every bound is the smallest and largest value
measured across the references, and every field records that its references are lossy.
Run it: python tools/seed_target.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bench import compare, measurement

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "targets" / "guaracha-club.json"

REFERENCES = (
    ("Hugel and Solto, Jamaican Bam Bam",
     "C:/Users/altug/Downloads/13_DJ_M.A.G._MUSIC_-_Jamaican_Bam_Bam_-_HUGEL_SOLTO_FR_(mp3.pm).mp3"),
    ("Alan Gomez, Matias Mareco and DJ Lucas remix, Raka Taka Taka",
     "C:/Users/altug/Downloads/Dj_Alan_Gomez_Matias_Mareco_DJ_Lucas_Rmx_-_Raka_Taka_Taka_(mp3.pm).mp3"),
)

ADVISORY = {
    "loudness.lra_lu":
        "two references are not a rule. Loudness range follows the arrangement and the section "
        "structure more than the style, so with an evidence count of 2 this is reported as "
        "information and no verdict is claimed from it.",
}

SEEDED = (
    "loudness.integrated_lufs",
    "loudness.lra_lu",
    "levels.crest_db",
    "spectral.rollups.under_250_hz_pct",
    "spectral.rollups.band_60_250_pct",
    "spectral.band_pct.20_60",
    "spectral.band_pct.60_120",
    "spectral.band_pct.120_250",
    "spectral.band_pct.250_500",
    "spectral.band_pct.500_1000",
    "spectral.band_pct.1000_2000",
    "spectral.band_pct.2000_4000",
    "spectral.band_pct.4000_8000",
    "spectral.band_pct.8000_16000",
)

LIMITS = {
    "loudness.true_peak_dbtp": {
        "max": -1.0,
        "declared_by": "the person this bench is for, as a delivery ceiling",
        "why_not_seeded":
            "both references are mp3. Decoding overshoots the encoder's peak and both read over "
            "full scale, at plus 1.1 and plus 1.4 dBTP, so a ceiling cannot be measured from "
            "them. This bound is a rule, not evidence.",
    },
}

WITHHELD = {
    "loudness.sample_peak_dbfs":
        "same reason as true peak. Both references decode above full scale.",
    "spectral.band_pct.16000_20000":
        "both references are lowpassed by the encoder near 16 kHz, so this band holds the "
        "encoder's setting rather than the music.",
    "stereo.correlation":
        "joint stereo coding rebuilds the side signal, so correlation from an mp3 is the "
        "codec's, not the master's.",
    "stereo.width_side_mid_db":
        "same reason as correlation.",
    "tempo.bpm":
        "the two references measure 122.00 and 100.00 BPM. Two numbers an octave and a fifth "
        "apart do not describe a tempo any track could be checked against.",
}


def _number(measured: dict, path: str) -> float | None:
    value = compare.dig(measured, path)
    return float(value) if isinstance(value, (int, float)) else None


def main() -> int:
    sources, measured = [], []
    for title, path in REFERENCES:
        p = Path(path)
        if not p.exists():
            print(f"missing reference: {p}")
            return 2
        one = measurement.of_file(p)
        measured.append(one)
        source = one["source"]
        sources.append({
            "title": title,
            "file": p.name,
            "container": source.get("container"),
            "codec": source.get("codec"),
            "measured_at_hz": source.get("measured_at_hz"),
            "lossy": True,
        })

    fields = {}
    for field in SEEDED:
        values = [_number(one, field) for one in measured]
        if any(v is None for v in values):
            print(f"{field}: not measured on every reference, left out")
            continue
        fields[field] = {
            "low": round(min(values), 4),
            "high": round(max(values), 4),
            "from_lossy": True,
            "values": [round(v, 4) for v in values],
        }
        if field in ADVISORY:
            fields[field]["advisory"] = ADVISORY[field]

    target = {
        "name": "guaracha club",
        "band_set": measured[0]["spectral"]["band_set"],
        "evidence": {
            "n": len(REFERENCES),
            "all_sources_lossy": True,
            "sources": sources,
            "note": "Bounds are the smallest and largest of two measurements, not a "
                    "distribution. Two references cannot show how wide the style is.",
        },
        "fields": fields,
        "limits": LIMITS,
        "withheld": WITHHELD,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(target, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  {len(fields)} fields seeded, {len(ADVISORY)} of them advisory, "
          f"{len(LIMITS)} declared limits, {len(WITHHELD)} withheld, "
          f"evidence n = {len(REFERENCES)}")
    for field, bound in fields.items():
        print(f"    {field:38} {bound['low']:9.3f} .. {bound['high']:<9.3f} from {bound['values']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
