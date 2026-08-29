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
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from bench import compare, limiter, measurement
from bench.decode import Audio, DecodeError, decode
from bench.measure import bs1770, levels, loudness, spectral

METHOD = "master/gain-cut-and-searched-limiter"

LOUDNESS_FIELD = "loudness.integrated_lufs"
PEAK_FIELD = "loudness.true_peak_dbtp"
BELOW_FIELD = "spectral.outside_denominator_pct.below_20_hz"

CUT_HZ = spectral.DENOMINATOR_HZ[0]
# Chosen by measuring what it disturbs above itself. Across three tracks the largest
# band move is 0.16 at order 4, 0.02 at order 8, 0.01 at order 12, and order 16 buys
# nothing more. What it moves on the file in hand is measured on the file in hand: a
# residual carried over from three other tracks is a number typed in, and on a file
# with a lot under 20 Hz it is five times too small.
CUT_ORDER = 12

# The space searched, not values chosen. The result names the winner and says when it
# sits on an edge of this grid, because a peak at the edge of a search is a truncation.
#
# Widened after every winner on a nine track record came back on an edge. A grid whose
# answer is always its own boundary is reporting the boundary. Spaced by roughly three,
# because the thing being chosen is a time constant and a time constant that differs by
# a tenth of itself does not differ.
#
# The ends are where the mechanism stops meaning anything rather than round numbers.
# 0.1 ms is four samples at 44.1k, which is as short as a window can be and still be a
# window. 30 ms is longer than the gap between beats at any tempo this is for, so a
# reduction taken at one hit has not recovered before the next. 3 ms of release is
# shorter than the attack at the other end of the grid, and 1000 ms holds a reduction
# across a whole bar.
ATTACKS_MS = (0.1, 0.3, 1.0, 3.0, 10.0, 30.0)
RELEASES_MS = (3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)

# An uncertainty is half the step the value is reported in, so aiming a single
# uncertainty below a ceiling lands on a reported value that still touches it. Two
# clears the boundary by one whole reporting step, which is what "inside" needs.
CLEARANCE = 2.0
CORRECTION_PASSES = 4
# A limiter returns less loudness than the gain put into it, and near saturation it
# returns almost none. The floor stops the correction asking for a gain that no setting
# could survive; the ceiling is there because it cannot return more than it was given.
SLOPE_LIMITS = (0.05, 1.0)

# The plan is built from the second instrument, measuring in memory. The verdict is
# taken from the primary instrument, reading the written file. Those are not the same
# number, and the bench already declares how far apart the two are allowed to be. A
# plan that clears the boundary only by its own instrument's reporting step aims at a
# line a different instrument will draw somewhere else.
CROSSCHECK_UNIT = {
    "loudness.integrated_lufs": "integrated_lu",
    "loudness.true_peak_dbtp": "true_peak_db",
}


def clearance(field: str, unit: float) -> float:
    return CLEARANCE * unit + loudness.TOLERANCE[CROSSCHECK_UNIT[field]]

FULL_SCALE_DBTP = 0.0

# What goes into the file beside the audio. Three are typed once per run because
# nothing here can know them. The rest are not typed: the title is the file's own name,
# the year is the year the master was made, and the holder is declared once here rather
# than retyped into every run.
TYPED = ("artist", "album", "genre")
DERIVED = ("title", "date", "copyright", "software")
HOLDER = "Altug Tatlisu"
# Columns in the picture of the file. A drawing, not a measurement: nothing reads it
# back and no verdict rests on it.
WAVEFORM_COLUMNS = 1000
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
    # The destination can only be the source when the output folder is the source's
    # folder, which the check above has already refused. There is no second branch
    # here for that: a branch that cannot be reached cannot be a safeguard.
    destination = out_dir / source.name
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


@dataclass(frozen=True)
class _Search:
    """What every candidate is judged against, none of which changes across the grid."""

    audio: Audio
    target: dict
    before: dict
    was: dict
    ceiling_aim: float


def _slope(first: dict, current: dict, lifted_db: float) -> float:
    """Loudness out per dB of gain in, measured across the correction so far.

    One before any correction has been made, because there is nothing to measure it
    from yet. Held inside SLOPE_LIMITS: a limiter near saturation returns almost
    nothing, and dividing by that would ask for a gain no setting could survive.
    """
    if lifted_db <= 0.0 or current is first:
        return 1.0
    got = (current["integrated_lufs"] - first["integrated_lufs"]) / lifted_db
    return min(max(got, SLOPE_LIMITS[0]), SLOPE_LIMITS[1])


def _candidate(search: _Search, pushed: np.ndarray, attack: float, release: float,
               needed: np.ndarray) -> dict:
    rate = search.audio.sample_rate_hz
    limited, gain, _ = limiter.shaped(pushed, rate, search.ceiling_aim, attack, release, needed)
    made = replace(search.audio, samples=limited)
    block = spectral.measure(made)
    reached = bs1770.integrated(made.samples, rate)
    now = band_verdicts(block, search.target)
    changed = sorted(f for f in search.was if search.was[f] != now.get(f))
    over = levels.over_full_scale(made.samples)
    moved = max(abs(new["pct"] - old["pct"])
                for new, old in zip(block["bands"], search.before["spectral"]["bands"]))
    return {
        "attack_ms": attack,
        "release_ms": release,
        "largest_band_move_pct": round(moved, 4),
        "verdicts_changed": changed,
        "over_full_scale": over,
        "gain_reduction": limiter.worked(gain, needed),
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
    search = _Search(audio=audio, target=target, before=before, ceiling_aim=ceiling_aim,
                     was=band_verdicts(before["spectral"], target))
    if not search.was:
        return {
            "tried": [], "accepted": 0, "chosen": None, "correction_db": 0.0,
            "no_criterion":
                "the target bounds no band and no rollup, so keeping every band's verdict "
                "is a condition no setting can fail. There is nothing here to choose a "
                "limiter setting by, so none was chosen.",
        }
    needed = limiter.required_gain(pushed, rate, ceiling_aim)
    tried = [_candidate(search, pushed, attack, release, needed)
             for attack in ATTACKS_MS for release in RELEASES_MS]
    accepted = [one for one in tried if one["accepted"]]
    best = min(accepted, key=lambda one: one["largest_band_move_pct"]) if accepted else None
    out = {"tried": tried, "accepted": len(accepted), "chosen": best, "correction_db": 0.0}
    if accepted:
        # The spread the winner was picked out of. A choice made across 0.04 points is
        # a choice the instrument can barely see, and the reader should be able to tell
        # that from a choice made across half a point.
        moved = [one["largest_band_move_pct"] for one in accepted]
        out["moved_least"], out["moved_most"] = round(min(moved), 4), round(max(moved), 4)

    # The limiter takes loudness the gain arithmetic could not see, and lifting the gain
    # makes it take a little more. Correct by measuring, and stop when the measurement
    # says the value is inside rather than when a formula says it should be.
    if best is not None and loudness_aim is not None and best["integrated_lufs"] is not None:
        # The search reads the numpy instrument in memory and the verdict is taken from
        # ffmpeg reading the written file. They disagree by about the size of the margin
        # being cleared, so the stop condition clears the edge by the whole uncertainty
        # twice over: once for the reporting step, once for that disagreement.
        # Stop with a whole reporting step of room, not on the condition itself. The
        # aim below is one uncertainty above it for the same reason: stopping the
        # moment the condition is met leaves the verdict resting on the last bit.
        floor = loudness_aim + loudness_unit
        total, current = 0.0, best
        for _ in range(CORRECTION_PASSES):
            if current["integrated_lufs"] - CLEARANCE * loudness_unit >= floor:
                break
            # Aim one uncertainty above the condition rather than at it. Landing on
            # the stop condition means landing on the boundary it was derived from,
            # where the comparison is decided by the last bit of a float.
            short = floor + CLEARANCE * loudness_unit - current["integrated_lufs"]
            # A dB of gain into a limiter is not a dB of loudness out of it. How much
            # it is worth is measured from the passes already taken rather than assumed
            # to be one, which is what left this loop stopping short of its own aim.
            lift = short / _slope(best, current, total)
            total += lift
            lifted = pushed * (10.0 ** (total / 20.0))
            again = limiter.required_gain(lifted, rate, ceiling_aim)
            tryout = _candidate(search, lifted, best["attack_ms"], best["release_ms"], again)
            if not tryout["accepted"]:
                total -= lift
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


def _cut_moved(measured: dict, filtered: dict | None) -> float | None:
    """The largest band the cut actually moved on this file, once it has been made.
    Absent on the first plan, which is built before anything has been filtered."""
    after = compare.dig(filtered or {}, "spectral.bands")
    before = compare.dig(measured, "spectral.bands")
    if not after or not before:
        return None
    return round(max(abs(a["pct"] - b["pct"]) for a, b in zip(after, before)), 4)


def plan(measured: dict, target: dict, filtered: dict | None = None,
         limiting: dict | None = None) -> dict:
    steps, refused = [], []

    below = compare.dig(measured, BELOW_FIELD)
    resolution = compare.dig(measured, "spectral.uncertainty.every_percentage")
    if isinstance(below, (int, float)) and resolution is not None and below > resolution:
        cut = {
            "correction": "low cut",
            "hz": CUT_HZ,
            "order": CUT_ORDER,
            "from": f"{BELOW_FIELD} is {below}, above the {resolution} it is reported at",
        }
        moved = _cut_moved(measured, filtered)
        if moved is not None:
            cut["moved_bands_by_pct"] = moved
        steps.append(cut)
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

    bound = target["fields"][LOUDNESS_FIELD]
    high = bound.get("high")
    placed = compare.verdict(lufs, lufs_unit, bound)

    ceiling, section = _bound(target, PEAK_FIELD, "max")
    if ceiling is None:
        ceiling, section = FULL_SCALE_DBTP, "full scale, because the target declares no ceiling"
    aim = ceiling - clearance(PEAK_FIELD, peak_unit)

    # Where the loudness should end up. A file already inside the range ends up where it
    # is: it is not moved to the edge of a target it is in the middle of. That is a
    # statement about loudness and about nothing else. The ceiling is not conditional on
    # it, and a file over the ceiling comes under it whether or not it wants loudness.
    room = clearance(LOUDNESS_FIELD, lufs_unit)
    if placed == compare.INSIDE:
        aim_loud, edge = lufs, f"{lufs}, where it already is, inside {low} to {high}"
    elif high is not None and lufs > (low + high) / 2.0:
        aim_loud, edge = high - room, f"{high}, the top of the range, less {round(room, 4)}"
    else:
        aim_loud, edge = low + room, f"{low}, the bottom of the range, plus {round(room, 4)}"

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
            "why": f"{lufs} LUFS is inside {low} to {high} and {peak} dBTP is already "
                   f"under {ceiling}, so neither the target nor the ceiling asks for "
                   "anything",
        })
        return _finish(steps, refused, lufs, peak, 0.0)

    steps.append({
        "correction": "gain",
        "db": round(gain, 3),
        "bound_by": bound_by,
        "from": f"toward {edge}, against {lufs} measured",
        "ceiling_from": section,
        # The two numbers the gain was actually derived from. After a low cut these
        # describe the filtered signal, not the file on disk, and the difference
        # between those is what entry 29 was.
        "measured_lufs": lufs,
        "measured_dbtp": peak,
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
                "why": limiting.get("no_criterion") or
                       f"none of the {len(limiting['tried'])} settings tried kept every "
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
                               "kept every band's verdict, the balance moved between "
                               f"{limiting['moved_least']} and {limiting['moved_most']} "
                               "points across them, and this one moved it least",
                "largest_band_move_pct": chosen["largest_band_move_pct"],
                "gain_reduction": chosen["gain_reduction"],
                "balance_moved_more_than_measurement_resolution":
                    chosen["largest_band_move_pct"] > spectral.PERCENT_UNCERTAINTY,
            })
            if "at_search_edge" in limiting:
                steps[-1]["at_search_edge"] = limiting["at_search_edge"]
            if not limiting.get("cleared_the_floor", True):
                steps[-1]["stopped_at_lufs"] = chosen["integrated_lufs"]
                steps[-1]["why_it_stopped"] = (
                    f"{CORRECTION_PASSES} measured passes lifted the gain as far as this "
                    f"setting would carry it, and it reached {chosen['integrated_lufs']} "
                    f"LUFS against {round(aim_loud, 3)} aimed at. Whether that is inside "
                    "the target is decided by the output, not here."
                )

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
        samples, _ = limiter.apply(samples, audio.sample_rate_hz, squash["ceiling_dbtp"],
                                   squash["attack_ms"], squash["release_ms"])
    return samples


def run(path: str | Path, target: dict, out_dir: str | Path,
        said: dict | None = None) -> dict:
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
        # spectral.measure reads samples and nothing else, so a replaced Audio is safe
        # here in a way it is not for loudness. second_instrument says why.
        filtered = {"loudness": second_instrument(base, audio.sample_rate_hz),
                    "spectral": spectral.measure(replace(audio, samples=base))}

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
    made = render(audio, built)
    wanted = tags_for(source, said)
    write_master(destination, made, audio.sample_rate_hz, wanted)

    after = measurement.of_file(destination)
    graded = compare.against(after, target)
    return {
        "method": METHOD,
        "input": str(source),
        "output": str(destination),
        "plan": built,
        "limiter_search": limiting,
        "before": {"measurement": before, "comparison": compare.against(before, target),
                   "waveform": waveform(audio.samples)},
        "after": {"measurement": after, "comparison": graded, "waveform": waveform(made)},
        "prediction": _held(built, after),
        "reached": reached(after, graded),
        "tags": tags_held(wanted, tags_of(destination)),
    }


def second_instrument(samples: np.ndarray, rate: int) -> dict:
    """Loudness and peak of samples that are not on disk.

    loudness.measure runs the primary instrument over audio.path and the second over
    audio.samples. Handing it an Audio whose samples have been replaced measures the
    file for one number and the replacement for the other, and calls the difference
    between them instrument disagreement. Nothing in this module does that.
    """
    reached = bs1770.integrated(samples, rate)
    return {
        "method": bs1770.METHOD,
        "measured_from": "samples in memory, by the second instrument only",
        "integrated_lufs": None if reached is None else round(reached.lufs, 4),
        "true_peak_dbtp": bs1770.true_peak_dbtp(samples),
    }


def tags_for(source, said: dict | None = None) -> dict:
    """What is written into the master beside the audio.

    An empty field is left out rather than written empty. An empty tag is a claim that
    the field is empty, and this bench does not make claims it was not given.
    """
    year = str(date.today().year)
    out = {"title": Path(source).stem, "date": year,
           "copyright": f"{year} {HOLDER}", "software": METHOD}
    for name in TYPED:
        value = str((said or {}).get(name, "")).strip()
        if value:
            out[name] = value
    return out


def tags_of(path) -> dict:
    """What the file says about itself, read back off the file."""
    with sf.SoundFile(str(path)) as f:
        return {name: getattr(f, name) or ""
                for name in DERIVED + TYPED}


def tags_held(wanted: dict, got: dict) -> dict:
    """Whether the file came back saying what it was told to say.

    libsndfile appends its own name to the software field, so that one is checked by
    what it starts with. Everything else has to match exactly.
    """
    wrong = {}
    for name, value in wanted.items():
        found = got.get(name, "")
        if name == "software":
            if not found.startswith(value):
                wrong[name] = found
        elif found != value:
            wrong[name] = found
    left = {name: got[name] for name in got if got[name] and name not in wanted}
    out = {"written": wanted, "held": not wrong and not left}
    if wrong:
        out["came_back_different"] = wrong
    if left:
        out["not_asked_for"] = left
    return out


def write_master(destination, samples: np.ndarray, rate: int, tags: dict) -> None:
    """The audio and what it says about itself, in one file."""
    with sf.SoundFile(str(destination), "w", samplerate=rate,
                      channels=int(np.atleast_2d(samples).shape[0]), subtype=SUBTYPE) as f:
        for name, value in tags.items():
            setattr(f, name, value)
        f.write(np.atleast_2d(samples).T)


def waveform(samples: np.ndarray, columns: int = WAVEFORM_COLUMNS) -> list[float]:
    """The largest magnitude in each column, as a fraction of full scale."""
    loud = np.max(np.abs(np.atleast_2d(np.asarray(samples, dtype=np.float64))), axis=0)
    if loud.size == 0:
        return []
    edges = np.linspace(0, loud.size, min(columns, loud.size) + 1).astype(int)
    return [round(float(loud[a:b].max()), 4)
            for a, b in zip(edges[:-1], edges[1:]) if b > a]


def run_each(paths, target: dict, out_dir, watching=None,
             said: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Master a list of files into one folder, and say which ones it could not.

    A file it refuses does not stop the rest. It comes back with the reason, because a
    run that quietly did eight of nine is a run that has to be counted by hand.

    `watching` is called with the name, how many are finished and how many there are,
    before each file. It is how a caller that is not a terminal shows progress.
    """
    paths = list(paths)
    done, failed = [], []
    for path in paths:
        if watching is not None:
            watching(Path(path).name, len(done) + len(failed), len(paths))
        try:
            done.append(run(path, target, out_dir, said))
        except (Unsafe, Unmasterable, DecodeError, compare.BandSetMismatch) as why:
            failed.append({"name": Path(path).name, "why": str(why)})
    return done, failed


def step_ceiling(target: dict, measured: dict) -> float:
    ceiling, _ = _bound(target, PEAK_FIELD, "max")
    if ceiling is None:
        ceiling = FULL_SCALE_DBTP
    return ceiling - clearance(
        PEAK_FIELD, compare.dig(measured, "loudness.uncertainty.true_peak_dbtp"))


def reached(after: dict, comparison: dict) -> dict:
    """Where the output landed on the two fields the plan aims at.

    A plan that ran is not a plan that arrived. The plan is built from the input and
    cannot know what the output will measure, so this is read off the output.
    """
    out = {"arrived": True, "fields": {}}
    for field in (LOUDNESS_FIELD, PEAK_FIELD):
        row = next((r for r in comparison["rows"] if r["field"] == field), None)
        if row is None or "value" not in row:
            out["fields"][field] = {"verdict": compare.NOT_MEASURED}
            out["arrived"] = False
            continue
        out["fields"][field] = {"value": row["value"], "uncertainty": row.get("uncertainty"),
                                "verdict": row["verdict"], "deviation": row.get("deviation")}
        if row["verdict"] != compare.INSIDE:
            out["arrived"] = False
    return out


def _held(built: dict, after: dict) -> dict:
    predicted = built.get("predicted")
    if predicted is None:
        return {"checked": False, "why": "the plan predicted nothing to check"}
    # A prediction made by one instrument has to be checked against that instrument.
    # Checking a numpy figure against ffmpeg measures the gap between the two, which
    # the bench already reports, and calls it a failed plan.
    second = predicted.get("predicted_by", "").startswith("the second instrument")
    # A whole phrase, not half of one. Two places print this and one of them was
    # adding the noun back, which read as the second instrument instrument.
    out = {"checked": True,
           "against": "the second instrument" if second else "the primary instrument",
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
