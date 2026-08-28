"""Gain, a low cut, and a limiter whose attack and release are chosen by measuring.

A fourth layer. It reads the same Measurement and Target the rest of the bench
produces and changes neither. Every correction is a number the measurement implies.
The limiter's two parameters are not implied by anything, so they are searched for
and the winner is the one whose output keeps every band's verdict against the target,
which is a criterion the bench already computes.

It never writes over an input, and it measures what it wrote.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from bench import compare, limiter, measurement
from bench.decode import Audio, decode
from bench.measure import bs1770, levels, loudness, spectral

METHOD = "master/gain-cut-and-searched-limiter"

LOUDNESS_FIELD = "loudness.integrated_lufs"
PEAK_FIELD = "loudness.true_peak_dbtp"
BELOW_FIELD = "spectral.outside_denominator_pct.below_20_hz"

CUT_HZ = spectral.DENOMINATOR_HZ[0]
# Chosen by measuring what it disturbs above itself. Across three tracks the largest
# band move is 0.16 at order 4, 0.02 at order 8, 0.01 at order 12, and order 16 buys
# nothing more. 0.01 is twice the 0.005 a percentage is reported to, so the residual
# is declared rather than claimed away.
CUT_ORDER = 12
CUT_RESIDUAL_PCT = 0.01

# The space searched, not values chosen. The result names the winner and says when it
# sits on an edge of this grid, because a peak at the edge of a search is a truncation.
ATTACKS_MS = (0.5, 2.0, 5.0, 10.0)
RELEASES_MS = (20.0, 60.0, 150.0)

# An uncertainty is half the step the value is reported in, so aiming a single
# uncertainty below a ceiling lands on a reported value that still touches it. Two
# clears the boundary by one whole reporting step, which is what "inside" needs.
CLEARANCE = 2.0
CORRECTION_PASSES = 4

FULL_SCALE_DBTP = 0.0
SUBTYPE = "PCM_24"


class Unsafe(ValueError):
    pass


class Unmasterable(ValueError):
    pass


def _same(a: Path, b: Path) -> bool:
    if a.exists() and b.exists():
        return a.samefile(b)
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def refuse_unsafe(source: Path, out_dir: Path) -> Path:
    """Where the output will go, or an error naming what it would have destroyed."""
    source, out_dir = Path(source).resolve(), Path(out_dir).resolve()
    if _same(out_dir, source.parent):
        raise Unsafe(
            f"the output folder is the folder the source is in, {out_dir}. Mastering "
            "writes beside its inputs only by overwriting one of them."
        )
    destination = out_dir / source.name
    if _same(destination, source):
        raise Unsafe(f"the output path is the source itself, {source}")
    if destination.exists():
        raise Unsafe(
            f"{destination} already exists. Nothing here overwrites, so the previous "
            "master has to be moved or removed first."
        )
    return destination


def low_cut(samples: np.ndarray, rate: int, hz: float = CUT_HZ,
            order: int = CUT_ORDER) -> np.ndarray:
    sos = butter(order, hz / (rate / 2.0), btype="highpass", output="sos")
    return np.ascontiguousarray(sosfiltfilt(sos, samples, axis=1))


def _bound(target: dict, field: str, side: str):
    for section in ("fields", "limits"):
        found = target.get(section, {}).get(field)
        if found is not None and side in found:
            return found[side], section
    return None, None


def band_verdicts(block: dict, target: dict) -> dict:
    """Where every band the target bounds sits, in the same words the folder table uses."""
    unit = spectral.PERCENT_UNCERTAINTY
    out = {}
    for band in block["bands"]:
        key = measurement.band_key(band["lo_hz"], band["hi_hz"])
        out.update(_one(f"spectral.band_pct.{key}", band["pct"], unit, target))
    for name, pct in block["rollups"].items():
        out.update(_one(f"spectral.rollups.{name}", pct, unit, target))
    return out


def _one(field: str, value: float, unit: float, target: dict) -> dict:
    bound = target.get("fields", {}).get(field)
    if bound is None or bound.get("advisory"):
        return {}
    return {field: compare.verdict(value, unit, bound)}


def _candidate(audio: Audio, pushed: np.ndarray, ceiling_aim: float, attack: float,
               release: float, was: dict, before: dict, needed: np.ndarray) -> dict:
    rate = audio.sample_rate_hz
    gain = limiter.envelope(pushed, rate, ceiling_aim, attack, release, needed)
    made = replace(audio, samples=pushed * gain)
    block = spectral.measure(made)
    reached = bs1770.integrated(made.samples, rate)
    now = band_verdicts(block, target=None) if False else band_verdicts(block, _candidate.target)
    changed = sorted(f for f in was if was[f] != now.get(f))
    over = levels.over_full_scale(made.samples)
    moved = max(abs(new["pct"] - old["pct"])
                for new, old in zip(block["bands"], before["spectral"]["bands"]))
    return {
        "attack_ms": attack,
        "release_ms": release,
        "largest_band_move_pct": round(moved, 4),
        "verdicts_changed": changed,
        "over_full_scale": over,
        "gain_reduction": limiter.worked(gain),
        "integrated_lufs": round(reached.lufs, 3) if reached else None,
        "accepted": not changed and over == 0,
    }


def search_limiter(audio: Audio, pushed: np.ndarray, ceiling_aim: float,
                   target: dict, before: dict, loudness_aim: float | None = None,
                   loudness_unit: float = 0.0) -> dict:
    """Try every attack and release, keep the ones that change no verdict.

    The ceiling is met by construction, so it is not what the search is for. What it
    is for is finding the setting that moves the balance least while getting there.
    """
    rate = audio.sample_rate_hz
    _candidate.target = target
    needed = limiter.required_gain(pushed, rate, ceiling_aim)
    was = band_verdicts(before["spectral"], target)
    tried = [_candidate(audio, pushed, ceiling_aim, attack, release, was, before, needed)
             for attack in ATTACKS_MS for release in RELEASES_MS]
    accepted = [one for one in tried if one["accepted"]]
    best = min(accepted, key=lambda one: one["largest_band_move_pct"]) if accepted else None
    out = {"tried": tried, "accepted": len(accepted), "chosen": best, "correction_db": 0.0}

    # The limiter takes loudness the gain arithmetic could not see, and lifting the gain
    # makes it take a little more. Correct by measuring, and stop when the measurement
    # says the value is inside rather than when a formula says it should be.
    if best is not None and loudness_aim is not None and best["integrated_lufs"] is not None:
        # The search reads the numpy instrument in memory and the verdict is taken from
        # ffmpeg reading the written file. They disagree by about the size of the margin
        # being cleared, so the stop condition clears the edge by the whole uncertainty
        # twice over: once for the reporting step, once for that disagreement.
        floor = loudness_aim
        total, current = 0.0, best
        for _ in range(CORRECTION_PASSES):
            if current["integrated_lufs"] - CLEARANCE * loudness_unit >= floor:
                break
            # Aim one uncertainty above the condition rather than at it. Landing on
            # the stop condition means landing on the boundary it was derived from,
            # where the comparison is decided by the last bit of a float.
            total += (loudness_aim + (CLEARANCE + 1.0) * loudness_unit
                      - current["integrated_lufs"])
            lifted = pushed * (10.0 ** (total / 20.0))
            again = limiter.required_gain(lifted, rate, ceiling_aim)
            tryout = _candidate(audio, lifted, ceiling_aim, best["attack_ms"],
                                best["release_ms"], was, before, again)
            if not tryout["accepted"]:
                total -= loudness_aim - current["integrated_lufs"]
                break
            current = tryout
        if total:
            out["correction_db"] = round(total, 3)
            out["corrected_from"] = (
                f"the chosen setting reached {best['integrated_lufs']} LUFS against a floor "
                f"of {round(floor, 3)}, so the gain was lifted {round(total, 3)} dB across "
                "measured passes until it cleared it"
            )
            out["chosen"] = current
        out["cleared_the_floor"] = (
            current["integrated_lufs"] - CLEARANCE * loudness_unit >= floor)
    if best is not None:
        edges = []
        if best["attack_ms"] in (min(ATTACKS_MS), max(ATTACKS_MS)):
            edges.append(f"attack at {best['attack_ms']} ms")
        if best["release_ms"] in (min(RELEASES_MS), max(RELEASES_MS)):
            edges.append(f"release at {best['release_ms']} ms")
        if edges:
            out["at_search_edge"] = (
                "the winner sits on the edge of the grid searched (" + ", ".join(edges)
                + "), so a better setting may lie outside it"
            )
    return out


def plan(measured: dict, target: dict, filtered: dict | None = None,
         limiting: dict | None = None) -> dict:
    steps, refused = [], []

    below = compare.dig(measured, BELOW_FIELD)
    resolution = compare.dig(measured, "spectral.uncertainty.every_percentage")
    if isinstance(below, (int, float)) and resolution is not None and below > resolution:
        steps.append({
            "correction": "low cut",
            "hz": CUT_HZ,
            "order": CUT_ORDER,
            "from": f"{BELOW_FIELD} is {below}, above the {resolution} it is reported at",
            "disturbs_bands_by_up_to_pct": CUT_RESIDUAL_PCT,
        })
    elif isinstance(below, (int, float)):
        refused.append({
            "correction": "low cut",
            "why": f"{BELOW_FIELD} is {below}, at or under the {resolution} it is "
                   "reported at, so there is nothing there to remove",
        })
    else:
        refused.append({"correction": "low cut",
                        "why": "the file has no spectral measurement to derive it from"})

    source = filtered if filtered is not None else measured
    lufs = compare.dig(source, LOUDNESS_FIELD)
    peak = compare.dig(source, PEAK_FIELD)
    lufs_unit = compare.dig(measured, "loudness.uncertainty.integrated_lufs")
    peak_unit = compare.dig(measured, "loudness.uncertainty.true_peak_dbtp")

    if None in (lufs, peak, lufs_unit, peak_unit):
        refused.append({"correction": "gain",
                        "why": "loudness or true peak is absent, so no gain follows from it"})
        return _finish(steps, refused, None, None, 0.0)

    low, _ = _bound(target, LOUDNESS_FIELD, "low")
    if low is None:
        refused.append({"correction": "gain",
                        "why": f"the target sets no {LOUDNESS_FIELD}, so there is nothing "
                               "to raise the file to"})
        return _finish(steps, refused, None, None, 0.0)

    ceiling, section = _bound(target, PEAK_FIELD, "max")
    if ceiling is None:
        ceiling, section = FULL_SCALE_DBTP, "full scale, because the target declares no ceiling"
    aim = ceiling - CLEARANCE * peak_unit
    aim_loud = low + CLEARANCE * lufs_unit

    want_loud = aim_loud - lufs
    want_room = aim - peak
    shortfall = 0.0

    if want_room >= want_loud:
        gain, bound_by = want_loud, "the target loudness"
    elif limiting is not None and limiting.get("chosen"):
        gain, bound_by = want_loud, "the target loudness, with the limiter finding the rest"
    else:
        gain, bound_by = want_room, "the ceiling"
        shortfall = round(want_loud - want_room, 3)

    if abs(gain) <= lufs_unit and limiting is None:
        refused.append({
            "correction": "gain",
            "why": f"the file is already within {lufs_unit} LU of the target, which is "
                   "what this measurement can resolve",
        })
        return _finish(steps, refused, lufs, peak, 0.0)

    steps.append({
        "correction": "gain",
        "db": round(gain, 3),
        "bound_by": bound_by,
        "from": f"{low} plus {round(CLEARANCE * lufs_unit, 4)} to clear the boundary, "
                f"against {lufs} measured",
        "ceiling_from": section,
    })

    if limiting is not None and limiting.get("correction_db"):
        steps[-1]["db"] = round(gain + limiting["correction_db"], 3)
        steps[-1]["corrected_by_db"] = limiting["correction_db"]
        steps[-1]["correction_from"] = limiting["corrected_from"]

    if limiting is not None:
        chosen = limiting.get("chosen")
        if chosen is None:
            refused.append({
                "correction": "limiter",
                "why": f"none of the {len(limiting['tried'])} settings tried kept every "
                       "band's verdict against the target, so the gain was held at the "
                       "ceiling instead",
                "loudness_unreachable_lu": shortfall,
            })
        else:
            steps.append({
                "correction": "limiter",
                "ceiling_dbtp": round(aim, 3),
                "attack_ms": chosen["attack_ms"],
                "release_ms": chosen["release_ms"],
                "chosen_from": f"{limiting['accepted']} of {len(limiting['tried'])} settings "
                               "kept every band's verdict, and this one moved the balance least",
                "largest_band_move_pct": chosen["largest_band_move_pct"],
                "gain_reduction": chosen["gain_reduction"],
                "balance_moved_more_than_measurement_resolution":
                    chosen["largest_band_move_pct"] > spectral.PERCENT_UNCERTAINTY,
            })
            if "at_search_edge" in limiting:
                steps[-1]["at_search_edge"] = limiting["at_search_edge"]

    predicted_peak = min(round(peak + gain, 3), round(aim, 3))
    predicted_lufs = round(lufs + gain, 3)
    by = "arithmetic on the primary instrument"
    if limiting is not None and limiting.get("chosen"):
        measured_lufs = limiting["chosen"].get("integrated_lufs")
        if measured_lufs is not None:
            predicted_lufs, by = measured_lufs, "the second instrument, measured in memory"
    return _finish(steps, refused, predicted_lufs, predicted_peak, shortfall, by)


def _finish(steps, refused, lufs, peak, shortfall,
            by: str = "arithmetic on the primary instrument") -> dict:
    out = {"method": METHOD, "steps": steps, "not_applied": refused}
    if lufs is not None:
        out["predicted"] = {"integrated_lufs": lufs, "true_peak_dbtp": peak,
                            "predicted_by": by}
    if shortfall:
        out["shortfall_lu"] = shortfall
    return out


def step(built: dict, correction: str) -> dict | None:
    for one in built["steps"]:
        if one["correction"] == correction:
            return one
    return None


def render(audio: Audio, built: dict) -> np.ndarray:
    """Exactly what the plan says, and nothing the plan does not say."""
    samples = audio.samples
    if step(built, "low cut"):
        samples = low_cut(samples, audio.sample_rate_hz)
    gain = step(built, "gain")
    if gain:
        samples = samples * (10.0 ** (gain["db"] / 20.0))
    squash = step(built, "limiter")
    if squash:
        samples = limiter.apply(samples, audio.sample_rate_hz, squash["ceiling_dbtp"],
                                squash["attack_ms"], squash["release_ms"])
    return samples


def run(path: str | Path, target: dict, out_dir: str | Path) -> dict:
    source = Path(path).resolve()
    destination = refuse_unsafe(source, Path(out_dir))

    audio = decode(source)
    before = measurement.of_audio(audio)
    if "unmeasurable" in before.get("loudness", {}):
        raise Unmasterable(f"{source.name} has no loudness measurement to work from")

    first = plan(before, target)
    filtered = None
    base = audio.samples
    if step(first, "low cut"):
        base = low_cut(audio.samples, audio.sample_rate_hz)
        filtered = {"loudness": loudness.measure(replace(audio, samples=base))}

    without = plan(before, target, filtered)
    limiting = None
    if without.get("shortfall_lu"):
        gain = step(without, "gain")
        wanted = without["shortfall_lu"] + gain["db"]
        low, _ = _bound(target, LOUDNESS_FIELD, "low")
        unit = compare.dig(before, "loudness.uncertainty.integrated_lufs")
        limiting = search_limiter(
            audio, base * (10.0 ** (wanted / 20.0)),
            step_ceiling(target, before), target, before,
            loudness_aim=low, loudness_unit=unit)
    built = plan(before, target, filtered, limiting)

    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(destination), render(audio, built).T, audio.sample_rate_hz, subtype=SUBTYPE)

    after = measurement.of_file(destination)
    return {
        "method": METHOD,
        "input": str(source),
        "output": str(destination),
        "plan": built,
        "limiter_search": limiting,
        "before": {"measurement": before, "comparison": compare.against(before, target)},
        "after": {"measurement": after, "comparison": compare.against(after, target)},
        "prediction": _held(built, after),
    }


def step_ceiling(target: dict, measured: dict) -> float:
    ceiling, _ = _bound(target, PEAK_FIELD, "max")
    if ceiling is None:
        ceiling = FULL_SCALE_DBTP
    return ceiling - CLEARANCE * compare.dig(measured, "loudness.uncertainty.true_peak_dbtp")


def _held(built: dict, after: dict) -> dict:
    predicted = built.get("predicted")
    if predicted is None:
        return {"checked": False, "why": "the plan predicted nothing to check"}
    # A prediction made by one instrument has to be checked against that instrument.
    # Checking a numpy figure against ffmpeg measures the gap between the two, which
    # the bench already reports, and calls it a failed plan.
    second = predicted.get("predicted_by", "").startswith("the second instrument")
    out = {"checked": True, "against": "the second instrument" if second else "the primary",
           "fields": {}}
    for field, name in ((LOUDNESS_FIELD, "integrated_lufs"), (PEAK_FIELD, "true_peak_dbtp")):
        got = compare.dig(after, f"loudness.crosscheck.{name}") if second else None
        if got is None:
            got = compare.dig(after, field)
        unit = compare.dig(after, f"loudness.uncertainty.{name}")
        if got is None or unit is None:
            out["fields"][name] = {"held": False, "why": "the output has no such measurement"}
            continue
        gap = round(got - predicted[name], 4)
        out["fields"][name] = {
            "predicted": predicted[name], "measured": got,
            "gap": gap, "uncertainty": unit, "held": abs(gap) <= unit,
        }
    out["held"] = all(f.get("held") for f in out["fields"].values())
    return out
