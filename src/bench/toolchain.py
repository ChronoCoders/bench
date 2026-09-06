"""What produced a number, as fields rather than a sentence.

The same method id can give two answers. `loudness/ffmpeg-ebur128` is an ffmpeg run,
and `loudness/bs1770-4-numpy` is scipy filters. The registry already records that the
oversampling filter decides the true peak and that two lengths of it part company by
0.029 dB on a real master, which is enough to flip a -1 dBTP ceiling. A scipy that
changes `upfirdn` moves that number the same way, and the method id does not move at
all.

Fields rather than one string, because a policy gets written against fields. A
difference here is a reason to look, not a reason to stop: it is reported beside the
number and nothing refuses on it.
"""

from __future__ import annotations

import subprocess

import numpy as np
import scipy
import soundfile as sf

# One subprocess for the life of the process. The version cannot change under a run,
# and asking per file would put an ffmpeg launch in front of every measurement.
_HERE: dict | None = None


def _ffmpeg() -> str | None:
    """The version token out of the banner, or absent. Absent is a fact about the
    record rather than a version called "unknown"."""
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL)
    except OSError:
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    words = r.stdout.splitlines()[0].split()
    return words[2] if len(words) > 2 and words[1] == "version" else None


def here() -> dict:
    """What is installed, as a fresh dict each time so a caller cannot edit the cache."""
    global _HERE
    if _HERE is None:
        _HERE = {
            "ffmpeg": _ffmpeg(),
            "libsndfile": sf.__libsndfile_version__,
            "scipy": scipy.__version__,
            "numpy": np.__version__,
        }
    return dict(_HERE)


def differences(measured: dict | None, seeded: dict | None) -> dict:
    """Which parts differ between what measured a file and what seeded a target.

    A part missing on either side is not a difference. A record that does not say and
    two records that disagree are different things, and reporting the first as the
    second would put a note on every target written before this existed.
    """
    if not measured or not seeded:
        return {}
    out = {}
    for part in sorted(set(measured) | set(seeded)):
        mine, theirs = measured.get(part), seeded.get(part)
        if mine is not None and theirs is not None and mine != theirs:
            out[part] = {"measured_with": mine, "target_seeded_with": theirs}
    return out


def sentence(differing: dict) -> str:
    """The note that goes beside the number."""
    parts = ", ".join(
        f"{name} {one['measured_with']} here against {one['target_seeded_with']} "
        "when the target was seeded"
        for name, one in differing.items()
    )
    return ("Measured on a different toolchain to the one that seeded this target: "
            f"{parts}. The figures are comparable to the extent those agree.")
