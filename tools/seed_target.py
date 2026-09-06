"""Build target profiles from reference files by measuring them.

Nothing here accepts a quoted figure. Every bound is the smallest and largest value
measured across the references, and every field records that its sources were lossy.
Run it: python tools/seed_target.py [slug ...]
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bench import compare, measurement, toolchain

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "targets"

# One list, used by every profile. A field seeded for one style and not another would
# make two profiles incomparable for a reason nobody wrote down.
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

# A delivery rule held for this bench's own output, whatever the style. It is not
# evidence and it is not seeded, so it lives apart from the measured fields.
LIMITS = {
    "loudness.true_peak_dbtp": {
        "max": -1.0,
        "declared_by": "the person this bench is for, as a delivery ceiling",
        "why_not_seeded":
            "the references are lossy. Decoding overshoots the encoder's peak and every one "
            "of them reads over full scale, so a ceiling cannot be measured from them. This "
            "bound is a rule, not evidence.",
    },
}

# What no lossy reference can support, whatever the style.
LOSSY_WITHHELD = {
    "loudness.sample_peak_dbfs":
        "the references are lossy and all of them decode above full scale, so they cannot "
        "say where a peak sits.",
    "spectral.band_pct.16000_20000":
        "the references are lowpassed by the encoder near 16 kHz, so this band holds the "
        "encoder's setting rather than the music.",
    "stereo.correlation":
        "joint stereo coding rebuilds the side signal, so correlation from an mp3 is the "
        "codec's, not the master's.",
    "stereo.width_side_mid_db":
        "same reason as correlation.",
}


@dataclass(frozen=True)
class Profile:
    name: str
    slug: str
    references: tuple[tuple[str, str], ...]
    advisory: dict
    withheld: dict
    note: str
    observed: tuple[str, ...] = ()
    excluded: tuple[dict, ...] = ()
    limits: dict = field(default_factory=lambda: LIMITS)


GUARACHA = Profile(
    name="guaracha club",
    slug="guaracha-club",
    references=(
        ("Hugel and Solto, Jamaican Bam Bam",
         "C:/Users/altug/Downloads/13_DJ_M.A.G._MUSIC_-_Jamaican_Bam_Bam_-_HUGEL_SOLTO_FR_(mp3.pm).mp3"),
        ("Alan Gomez, Matias Mareco and DJ Lucas remix, Raka Taka Taka",
         "C:/Users/altug/Downloads/Dj_Alan_Gomez_Matias_Mareco_DJ_Lucas_Rmx_-_Raka_Taka_Taka_(mp3.pm).mp3"),
    ),
    advisory={
        "loudness.lra_lu":
            "two references are not a rule. Loudness range follows the arrangement and the "
            "section structure more than the style, so with an evidence count of 2 this is "
            "reported as information and no verdict is claimed from it.",
    },
    withheld=dict(LOSSY_WITHHELD, **{
        "tempo.bpm":
            "the two references measure 122.00 and 100.00 BPM. Two numbers an octave and a "
            "fifth apart do not describe a tempo any track could be checked against.",
    }),
    note="Bounds are the smallest and largest of two measurements, not a distribution. "
         "Two references cannot show how wide the style is.",
)

BOOM_BAP = Profile(
    name="boom bap",
    slug="boom-bap",
    references=(
        ("Kendrick Lamar, DNA.",
         "C:/Users/altug/Downloads/boom-bap-refs/Kendrick_Lamar_-_DNA._Prod._by_Mike_Will_Made-It_(mp3.pm).mp3"),
        ("Kendrick Lamar, HUMBLE.",
         "C:/Users/altug/Downloads/boom-bap-refs/Kendrick_Lamar_-_HUMBLE._K-Dot-esquirrrre_(mp3.pm).mp3"),
        ("Denzel Curry, RICKY",
         "C:/Users/altug/Downloads/boom-bap-refs/Denzel_Curry_-_RICKY_(mp3.pm).mp3"),
    ),
    advisory={
        "loudness.lra_lu":
            "loudness range follows the arrangement and the section structure more than the "
            "style. Across these three it runs 3.3 to 5.7 LU, which is too wide to check a "
            "master against, so it is reported as information and no verdict is claimed.",
    },
    withheld=dict(LOSSY_WITHHELD, **{
        "tempo.bpm":
            "the three references measure 139.98, 150.02 and 168.98 BPM. Tracks are meant "
            "to differ in tempo, so the range across them is not something a master can be "
            "checked against. This is the same reason folder mode prints no tempo spread.",
        "tempo.drift.span_bpm":
            "only one of the three moves enough to measure, and that one moves 16.41 BPM "
            "because it changes beat partway through. One value is not a bound.",
    }),
    note="Bounds are the smallest and largest of three measurements, not a distribution.",
    observed=(
        "This profile was asked for on the understanding that boom bap carries a much "
        "heavier 60 to 250 band than guaracha. It does not, in these references. The band "
        "runs 18.37 to 36.22 percent here against 23.64 to 35.93 for guaracha, and the "
        "lightest of the two sets is one of these. The heavier figure was quoted, not "
        "measured, and this file records the measurement instead.",
    ),
    excluded=(
        {
            "title": "Travis Scott featuring Drake, SICKO MODE, Upgrade Bootleg",
            "file": "Travis_Scott_-_SICKO_MODE_Ft._Drake_Upgrade_Bootleg_(mp3.pm).mp3",
            "why":
                "a bootleg re-edit rather than a released master, and an outlier on every "
                "loudness field: minus 4.8 LUFS against minus 8.4 to minus 9.7 for the "
                "other three, plus 3.2 dBTP, 63732 clipped runs and 627823 samples over "
                "full scale. Keeping it would have widened every bound with damage that is "
                "not the style's.",
        },
    ),
)

PROFILES = (GUARACHA, BOOM_BAP)


def _number(measured: dict, path: str) -> float | None:
    value = compare.dig(measured, path)
    return float(value) if isinstance(value, (int, float)) else None


def build(profile: Profile) -> bool:
    """True if the profile was written. A profile whose references are gone is skipped,
    not fatal: the file it already produced stays as the record of what was measured."""
    missing = [path for _, path in profile.references if not Path(path).exists()]
    if missing:
        print(f"{profile.slug}: skipped, {len(missing)} reference"
              f"{'' if len(missing) == 1 else 's'} not on this machine")
        for path in missing:
            print(f"    {path}")
        print(f"  targets/{profile.slug}.json is unchanged and remains the record of what "
              "was measured when they were here.")
        return False

    sources, measured = [], []
    for title, path in profile.references:
        p = Path(path)
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
    for name in SEEDED:
        values = [_number(one, name) for one in measured]
        if any(v is None for v in values):
            print(f"  {name}: not measured on every reference, left out")
            continue
        fields[name] = {
            "low": round(min(values), 4),
            "high": round(max(values), 4),
            "from_lossy": True,
            "values": [round(v, 4) for v in values],
        }
        if name in profile.advisory:
            fields[name]["advisory"] = profile.advisory[name]

    evidence = {
        "n": len(profile.references),
        "all_sources_lossy": True,
        "sources": sources,
        "note": profile.note,
        # What measured the references. A target is a set of numbers, and the tools that
        # produced them are part of what those numbers mean.
        "toolchain": toolchain.here(),
    }
    if profile.observed:
        evidence["observed"] = list(profile.observed)
    if profile.excluded:
        evidence["excluded"] = list(profile.excluded)

    target = {
        "name": profile.name,
        "band_set": measured[0]["spectral"]["band_set"],
        "evidence": evidence,
        "fields": fields,
        "limits": profile.limits,
        "withheld": profile.withheld,
    }
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{profile.slug}.json"
    path.write_text(json.dumps(target, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    print(f"  {len(fields)} fields seeded, {len(profile.advisory)} advisory, "
          f"{len(profile.limits)} declared limits, {len(profile.withheld)} withheld, "
          f"evidence n = {len(profile.references)}")
    for name, bound in fields.items():
        mark = "  advisory" if "advisory" in bound else ""
        print(f"    {name:38} {bound['low']:9.3f} .. {bound['high']:<9.3f}{mark}")
    return True


def main() -> int:
    wanted = sys.argv[1:] or [p.slug for p in PROFILES]
    written = 0
    for profile in PROFILES:
        if profile.slug not in wanted:
            continue
        written += build(profile)
        print()
    print(f"{written} of {len(wanted)} written")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
