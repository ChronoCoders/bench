"""One file, every measurement, in one structure. Knows nothing about display."""

from __future__ import annotations

from pathlib import Path

from bench import toolchain
from bench.decode import Audio, decode
from bench.measure import Unmeasurable, levels, loudness, spectral, stereo, tempo

MODULES = (
    ("loudness", loudness),
    ("spectral", spectral),
    ("levels", levels),
    ("stereo", stereo),
    ("tempo", tempo),
)


def band_key(lo_hz: float, hi_hz: float) -> str:
    return f"{lo_hz:.0f}_{hi_hz:.0f}"


def _expand_spectral(block: dict) -> dict:
    block = dict(block)
    block["band_pct"] = {band_key(b["lo_hz"], b["hi_hz"]): b["pct"] for b in block["bands"]}
    every = block.get("uncertainty", {}).get("every_percentage")
    if every is not None:
        spread = {"every_percentage": every}
        spread.update({name: every for name in block["rollups"]})
        spread.update({key: every for key in block["band_pct"]})
        spread.update({key: every for key in block["outside_denominator_pct"]})
        block["uncertainty"] = spread
    return block


def of_audio(audio: Audio) -> dict:
    # What produced these numbers, beside the numbers. Same method id, different
    # ffmpeg or scipy, different answer, and until this nothing recorded which.
    out = {"source": audio.source_dict(), "duration_s": round(audio.duration_s, 3),
           "toolchain": toolchain.here()}
    for name, module in MODULES:
        try:
            block = module.measure(audio)
        # One class for every module, because a module can raise the one belonging
        # to another. levels and loudness both reach bs1770 and neither declares its
        # own, so naming the module here looked for an attribute that was never there.
        except Unmeasurable as why:
            out[name] = {"unmeasurable": str(why)}
            continue
        out[name] = _expand_spectral(block) if name == "spectral" else block
    return out


def of_file(path: str | Path) -> dict:
    path = Path(path)
    out = {"file": {"name": path.name, "path": str(path)}}
    out.update(of_audio(decode(path)))
    return out
