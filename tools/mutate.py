"""Break the engine one way at a time and report which test notices.

It works on a copy of the tree, never the tree itself. Each mutant stops at the first
test that catches it, so the answer is whether a break is noticed rather than how many
tests notice it. Pass --all for every catcher, which runs the whole suite once per
mutant. Any other word selects the mutations whose name contains it.

Run it: python tools/mutate.py [--all] [word ...]
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
COPIED = ("src", "tests", "tools", "targets", "fonts", "pyproject.toml")
STAGE_PREFIX = "bench-mutate-"

LIKELY_CATCHER = {
    "decode.py": "tests/test_decode.py",
    "bs1770.py": "tests/test_loudness.py",
    "ebur128.py": "tests/test_loudness.py",
    "loudness.py": "tests/test_loudness.py",
    "spectral.py": "tests/test_spectral.py",
    "levels.py": "tests/test_levels.py",
    "stereo.py": "tests/test_stereo.py",
    "tempo.py": "tests/test_tempo.py",
    "compare.py": "tests/test_compare.py",
    "folder.py": "tests/test_folder.py",
    "page.py": "tests/test_page.py",
    "typeface.py": "tests/test_typeface.py",
    "master.py": "tests/test_master.py",
    "limiter.py": "tests/test_limiter.py",
    "serve.py": "tests/test_serve.py",
}

DECODE = Path("src/bench/decode.py")
BS1770 = Path("src/bench/measure/bs1770.py")
EBUR128 = Path("src/bench/measure/ebur128.py")
SPECTRAL = Path("src/bench/measure/spectral.py")
LEVELS = Path("src/bench/measure/levels.py")
STEREO = Path("src/bench/measure/stereo.py")
TEMPO = Path("src/bench/measure/tempo.py")
COMPARE = Path("src/bench/compare.py")
FOLDER = Path("src/bench/folder.py")
PAGE = Path("src/bench/page.py")
MASTER = Path("src/bench/master.py")
SERVE = Path("tools/serve.py")
LIMITER = Path("src/bench/limiter.py")

READ_BODY = '''    data, rate = sf.read(str(path), dtype="float64", always_2d=True)
    return np.ascontiguousarray(data.T), int(rate)'''

DURATION_CALL = "    _check_duration(samples.shape[1], rate, p.container_duration_s, path)"


@dataclass(frozen=True)
class Mutant:
    name: str
    why: str
    file: Path
    find: str
    replace: str


MUTANTS = (
    Mutant(
        "resample to 22050, report 22050",
        "what librosa.load does by default",
        DECODE, READ_BODY,
        '''    from scipy.signal import resample_poly
    data, rate = sf.read(str(path), dtype="float64", always_2d=True)
    return np.ascontiguousarray(resample_poly(data.T, 1, 2, axis=1)), int(rate) // 2''',
    ),
    Mutant(
        "resample to 22050, report the source rate",
        "a decoder that resampled and does not admit it",
        DECODE, READ_BODY,
        '''    from scipy.signal import resample_poly
    data, rate = sf.read(str(path), dtype="float64", always_2d=True)
    return np.ascontiguousarray(resample_poly(data.T, 1, 2, axis=1)), int(rate)''',
    ),
    Mutant(
        "downmix to mono",
        "correlation then reads 1.0, a legitimate value for a real mono master",
        DECODE, READ_BODY,
        '''    data, rate = sf.read(str(path), dtype="float64", always_2d=True)
    return np.ascontiguousarray(data.T.mean(axis=0, keepdims=True)), int(rate)''',
    ),
    Mutant(
        "drop the last tenth of the file",
        "a truncated decode measures a track that is not the track",
        DECODE, READ_BODY,
        '''    data, rate = sf.read(str(path), dtype="float64", always_2d=True)
    a = np.ascontiguousarray(data.T)
    return a[:, : int(a.shape[1] * 0.9)], int(rate)''',
    ),
    Mutant(
        "measure loudness without the K weighting",
        "the filter is what makes it loudness rather than power",
        BS1770,
        "    return lfilter(b2, a2, lfilter(b1, a1, np.asarray(x, dtype=np.float64), axis=1), axis=1)",
        "    return np.asarray(x, dtype=np.float64)",
    ),
    Mutant(
        "drop the relative gate",
        "quiet passages then drag the integrated figure down",
        BS1770,
        "    keep = over_absolute & (loud > relative)",
        "    keep = over_absolute",
    ),
    Mutant(
        "take true peak with scipy's default oversampling filter",
        "0.015 dB of passband ripple, which is under ffmpeg's print resolution and has to be "
        "caught by the analytic control instead",
        BS1770,
        """    h = oversampling_filter(oversample)
    peak = max(float(np.max(np.abs(upfirdn(h, ch, oversample, 1)))) for ch in x)""",
        """    from scipy.signal import resample_poly
    peak = float(np.max(np.abs(resample_poly(x, oversample, 1, axis=1))))""",
    ),
    Mutant(
        "read the metadata true peak as decibels",
        "it is linear amplitude, and the wrong answer looks entirely plausible",
        EBUR128,
        '        true_peak = _agree_peak("true peak", summary["true_peak"], metadata.get("true_peak", 0.0), path)',
        '        true_peak = metadata.get("true_peak", 0.0)',
    ),
    Mutant(
        "report momentary loudness as integrated",
        "identical on constant material, wrong on everything else",
        EBUR128,
        '        integrated = _agree("integrated loudness", metadata["I"], summary["I"], path)',
        '        integrated = metadata["M"]',
    ),
    Mutant(
        "report the -70 floor as a measurement",
        "silence would come back with a loudness rather than without one",
        EBUR128,
        '    elif metadata["I"] == ABSOLUTE_GATE_LUFS:',
        "    elif False:",
    ),
    Mutant(
        "assign whole bins to the band their centre falls in",
        "biases a narrow band by one or two percent, by an amount the window length decides",
        SPECTRAL,
        """    half = (freqs[1] - freqs[0]) / 2.0
    overlap = np.clip(np.minimum(freqs + half, hi) - np.maximum(freqs - half, lo), 0.0, None)
    return float(np.sum(spectrum * overlap))""",
        """    df = freqs[1] - freqs[0]
    return float(np.sum(spectrum[(freqs >= lo) & (freqs < hi)]) * df)""",
    ),
    Mutant(
        "run the denominator to Nyquist",
        "the same master then reports different percentages at 44.1 kHz and 48 kHz",
        SPECTRAL,
        "DENOMINATOR_HZ = (20.0, 20000.0)",
        "DENOMINATOR_HZ = (20.0, 1e9)",
    ),
    Mutant(
        "truncate to a fast length instead of padding up to one",
        "drops the last fraction of a second of every file, silently",
        SPECTRAL,
        "    return int(next_fast_len(frames, real=True))",
        """    from scipy.fft import prev_fast_len
    return int(prev_fast_len(frames, real=True))""",
    ),
    Mutant(
        "double every bin, direct current and Nyquist included",
        "inflates both ends of the spectrum and nothing about the percentages looks wrong",
        SPECTRAL,
        """    if n % 2 == 0:
        power[1:-1] *= 2.0
    else:
        power[1:] *= 2.0""",
        "    power *= 2.0",
    ),
    Mutant(
        "leave out the one sided doubling",
        "every band then carries half its energy except direct current and Nyquist",
        SPECTRAL,
        """    if n % 2 == 0:
        power[1:-1] *= 2.0
    else:
        power[1:] *= 2.0""",
        "    power[0] += 0.0",
    ),
    Mutant(
        "take crest against an ungated root mean square",
        "a track with a long silent tail then reads as the most dynamic on the record",
        LEVELS,
        """    z = bs1770.window_mean_squares(bs1770.subblock_sums(samples, rate), rate, bs1770.BLOCK_S)
    mean_square = float(np.mean(z[:, gate.keep]))""",
        """    z = bs1770.window_mean_squares(bs1770.subblock_sums(samples, rate), rate, bs1770.BLOCK_S)
    mean_square = float(np.mean(z))""",
    ),
    Mutant(
        "count samples at full scale instead of runs",
        "every peak normalised master then reads as damaged",
        LEVELS,
        "        total += int(np.sum(edges[1::2] - edges[0::2] >= min_length))",
        "        total += int(np.sum(at_full))",
    ),
    Mutant(
        "put full scale at 1.0 whatever the bit depth",
        "the largest positive code at 16 bit is 32767/32768 and never reaches it",
        LEVELS,
        """    if bit_depth is None:
        return 1.0
    return 1.0 - 2.0 ** (1 - bit_depth)""",
        "    return 1.0",
    ),
    Mutant(
        "correlate the channels without removing their means",
        "a direct current offset then reads as two channels agreeing with each other",
        STEREO,
        "    return samples - samples.mean(axis=1, keepdims=True)",
        "    return samples",
    ),
    Mutant(
        "delete the duration cross check",
        "proves the check is load bearing rather than decoration",
        DECODE, DURATION_CALL, "    pass",
    ),
    Mutant(
        "sum the bands without dividing each by its own mean",
        "a shelf then moves the tempo, which is the one thing the normalisation is for",
        TEMPO,
        "            bands.append(band / band.mean())",
        "            bands.append(band)",
    ),
    Mutant(
        "threshold onsets on the median absolute deviation",
        "it is exactly zero on a sparse envelope, so the threshold collapses to the median",
        TEMPO,
        """    middle = np.median(values)
    threshold = middle + ONSET_ALPHA * np.maximum(values - middle, 0.0).mean()""",
        """    middle = np.median(values)
    threshold = middle + ONSET_ALPHA * 1.4826 * np.median(np.abs(values - middle))""",
    ),
    Mutant(
        "report any fitted change as drift",
        "a steady track then moves, because the fit never returns exactly zero",
        TEMPO,
        '        "resolved": span > DRIFT_FLOOR_BPM,',
        '        "resolved": span > 0.0,',
    ),
    Mutant(
        "break tempo ties by the highest candidate",
        "when many candidates fit the same onsets it walks to the top of the refine window",
        TEMPO,
        """    ranked = []
    for candidate in candidates:
        fit = grid_fit(times, candidate, span_s)
        tightness = fit["median_deviation_ms"]
        ranked.append((fit["onsets_fitted"], -(tightness if tightness is not None else 1e9),
                       candidate))
    return float(max(ranked)[2])""",
        """    return float(max((grid_fit(times, b, span_s)["onsets_fitted"], b) for b in candidates)[1])""",
    ),
    Mutant(
        "start the beat model at a constant tempo",
        "lock is lost on anything that moves by more than about one beat per minute",
        TEMPO,
        """    if centres.size >= DRIFT_ORDER + 1:
        coefficients = np.polyint(np.polyfit(centres, rates, DRIFT_ORDER - 1))
    else:
        coefficients = np.array([1.0 / period, 0.0])""",
        "    coefficients = np.array([1.0 / period, 0.0])",
    ),
    Mutant(
        "count every tick as occupied",
        "the double then looks as well supported as the tempo itself",
        TEMPO,
        "    filled = len(np.unique(np.round((times[hit] - best) / period))) if hit.any() else 0",
        "    filled = ticks",
    ),
    Mutant(
        "take every sample over the threshold as an onset",
        "one hit becomes a run of them and the grid fit is measured on its own ringing",
        TEMPO,
        """        if values[i] == values[max(0, i - reach) : i + reach + 1].max():
            keep.append(i)""",
        "        keep.append(i)",
    ),
    Mutant(
        "fit the beat model as a straight line",
        "tempo is then constant by construction and no track can ever move",
        TEMPO,
        "DRIFT_ORDER = 3",
        "DRIFT_ORDER = 1",
    ),
    Mutant(
        "take the drift range at the two ends of the file",
        "any tempo that comes back to where it started then reads as perfectly steady",
        TEMPO,
        """    across = 60.0 * np.polyval(rate, np.linspace(fitted.min(), fitted.max(), DRIFT_SAMPLES))
    first, last = float(across.min()), float(across.max())
    span = last - first""",
        """    first = 60.0 * np.polyval(rate, fitted.min())
    last = 60.0 * np.polyval(rate, fitted.max())
    span = abs(last - first)""",
    ),
    Mutant(
        "take the tempo peak wherever it lands, edges included",
        "a rate at the boundary is a truncation, not a maximum, and nothing said so",
        TEMPO,
        """    peak = int(np.argmax(score))
    if peak not in (0, score.size - 1):
        return float(grid[peak]), False""",
        """    peak = int(np.argmax(score))
    if True:
        return float(grid[peak]), False""",
    ),
    Mutant(
        "place a value against a boundary without its uncertainty",
        "a file sitting inside the error bar of a ceiling then reads as passed",
        COMPARE,
        """def verdict(value: float, uncertainty: float, bound: dict) -> str:
    low, high = bound.get("low"), bound.get("high", bound.get("max"))""",
        """def verdict(value: float, uncertainty: float, bound: dict) -> str:
    uncertainty = 0.0
    low, high = bound.get("low"), bound.get("high", bound.get("max"))""",
    ),
    Mutant(
        "count a value on the line as a pass",
        "the whole point of the third verdict is that it is not one of the first",
        COMPARE,
        "VERDICTS_THAT_PASS = (INSIDE,)",
        "VERDICTS_THAT_PASS = (INSIDE, ON_THE_LINE)",
    ),
    Mutant(
        "compare percentages taken under different band edges",
        "a check that cannot fail for the right reason is worse than no check",
        COMPARE,
        '    if measured_set is not None and measured_set != target["band_set"]:',
        "    if False:",
    ),
    Mutant(
        "treat a field that reports no uncertainty as if it had none",
        "an unknown uncertainty is not a zero one",
        COMPARE,
        """        unit = uncertainty_of(measurement, field)
        if unit is None:""",
        """        unit = uncertainty_of(measurement, field)
        unit = 0.0 if unit is None else unit
        if False:""",
    ),
    Mutant(
        "claim every spread covers every file",
        "a spread over eight of nine files is not the spread of the record",
        FOLDER,
        """            "n": len(present),
            "complete": len(present) == len(rows),""",
        """            "n": len(rows),
            "complete": True,""",
    ),
    Mutant(
        "print a spread for tempo",
        "tracks are meant to differ in tempo, so the range across them measures nothing",
        FOLDER,
        "        if column.spread_withheld is not None:",
        "        if False:",
    ),
    Mutant(
        "drop a file that cannot be read",
        "a folder table that quietly holds fewer files than the folder does",
        FOLDER,
        """        except (DecodeError, OSError) as why:
            skipped.append({"name": path.name, "why": str(why)})
            continue""",
        """        except (DecodeError, OSError):
            continue""",
    ),
    Mutant(
        "print a missing number as zero",
        "an empty value has to stay empty, and zero is a measurement",
        PAGE,
        """def number(value, decimals: int) -> str:
    if value is None:""",
        """def number(value, decimals: int) -> str:
    value = 0.0 if value is None else value
    if False:""",
    ),
    Mutant(
        "carry the measurement inside every row",
        "nine rows then hold nine copies of a thing that already exists once",
        FOLDER,
        """        row = {"name": path.name, "values": {c.path: _number(one, c.path) for c in COLUMNS}}""",
        """        row = {"name": path.name, "measurement": one,
               "values": {c.path: _number(one, c.path) for c in COLUMNS}}""",
    ),
    Mutant(
        "count an advisory bound among the verdicts",
        "a bound resting on two references is information, and counting it makes it a rule",
        COMPARE,
        """        if row.get("advisory"):
            continue
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1""",
        """        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1""",
    ),
    Mutant(
        "let an advisory bound decide whether the file passed",
        "every one of these files fails a loudness range taken from two references",
        COMPARE,
        """    return [r for r in rows
            if not r.get("advisory") and r["verdict"] not in (NO_TARGET, NOT_MEASURED)]""",
        """    return [r for r in rows if r["verdict"] not in (NO_TARGET, NOT_MEASURED)]""",
    ),
    Mutant(
        "charge every peak to the sample the filter delayed it to",
        "the interpolating filter lags 16 frames, so the reduction lands after the peak",
        LIMITER,
        "    delay = (h.size - 1) // 2",
        "    delay = 0",
    ),
    Mutant(
        "look no further ahead than the smoothing averages",
        "the elementwise minimum then has to catch a curve smoothed back over the ceiling",
        LIMITER,
        "LOOKAHEAD_MULTIPLE = 2",
        "LOOKAHEAD_MULTIPLE = 1",
    ),
    Mutant(
        "count the release tail as limiting",
        "an exponential recovery never reaches one, so the whole file reads as reduced",
        LIMITER,
        '        "share_over_the_ceiling": round(float((needed < 1.0).mean()), 6),',
        '        "share_over_the_ceiling": round(float((gain < 1.0).mean()), 6),',
    ),
    Mutant(
        "recover the gain instantly",
        "a limiter with no release modulates the programme at the rate of its own peaks",
        LIMITER,
        "    if release_ms <= 0.0:",
        "    if True:",
    ),
    Mutant(
        "clear the boundary by half a reporting step",
        "entry 26, the first of the four: the aim lands on the line rather than inside it",
        MASTER,
        "    return CLEARANCE * unit + loudness.TOLERANCE[CROSSCHECK_UNIT[field]]",
        "    return unit",
    ),
    Mutant(
        "clear only this instrument's own step",
        "entry 28: the verdict is drawn by the other instrument, on the written file",
        MASTER,
        "    return CLEARANCE * unit + loudness.TOLERANCE[CROSSCHECK_UNIT[field]]",
        "    return CLEARANCE * unit",
    ),
    Mutant(
        "search against a criterion no setting can fail",
        "entry 27: with no band bounded, every setting keeps every verdict",
        MASTER,
        "    if not search.was:",
        "    if False:",
    ),
    Mutant(
        "check the prediction against the other instrument",
        "entry 26, the fourth: the gap it finds is the crosscheck the bench already reports",
        MASTER,
        '    second = predicted.get("predicted_by", "").startswith("the second instrument")',
        "    second = False",
    ),
    Mutant(
        "predict the loudness instead of measuring it",
        "entry 26, the second: limiting removes loudness the gain arithmetic cannot see",
        MASTER,
        "CORRECTION_PASSES = 4",
        "CORRECTION_PASSES = 0",
    ),
    Mutant(
        "stop the correction on the condition it was derived from",
        "entry 26, the third: the loop then lands on the boundary, decided by a float",
        MASTER,
        '            short = floor + CLEARANCE * loudness_unit - current["integrated_lufs"]',
        '            short = floor - current["integrated_lufs"]',
    ),
    Mutant(
        "measure the filtered samples with the instrument that reads the file",
        "entry 29: one number then comes from the low cut and the other from the original",
        MASTER,
        '        filtered = {"loudness": second_instrument(base, audio.sample_rate_hz),',
        '        filtered = {"loudness": loudness.measure(replace(audio, samples=base)),',
    ),
    Mutant(
        "always aim at the bottom of the range",
        "entry 30: a file above its target then gets pushed further from it",
        MASTER,
        '        aim_loud, edge = high - room, f"{high}, the top of the range, less {round(room, 4)}"',
        '        aim_loud, edge = low + room, f"{low}, the bottom of the range, plus {round(room, 4)}"',
    ),
    Mutant(
        "move a file that is already inside its target",
        "entry 30: it lands on the edge of a range it was in the middle of",
        MASTER,
        "    if placed == compare.INSIDE:",
        "    if False:",
    ),
    Mutant(
        "write into the folder the source is in",
        "the only way the destination can be the source, so this is the whole safeguard",
        MASTER,
        "    if _same(out_dir, source.parent):",
        "    if False:",
    ),
    Mutant(
        "replace a master it made before",
        "nothing here overwrites, and a second run would silently be the only one kept",
        MASTER,
        "    if destination.exists():",
        "    if False:",
    ),
    Mutant(
        "declare the cut residual instead of measuring it",
        "entry 32: 0.01 was measured on three other tracks and is five times too small",
        MASTER,
        "        moved = _cut_moved(measured, filtered)",
        "        moved = 0.01",
    ),
    Mutant(
        "reach mastering with a link instead of a post",
        "following a link would then write files, and a reload would write them again",
        PAGE,
        '        f"<button class=\\"go\\" type=\\"submit\\" formmethod=\\"post\\" "',
        '        f"<button class=\\"go\\" type=\\"submit\\" "',
    ),
    Mutant(
        "let the page that is working sit still",
        "the run finishes and the page keeps showing the file it was on when it loaded",
        PAGE,
        "    reload = \"\" if again_in is None else (",
        "    reload = \"\" if True else (",
    ),
    Mutant(
        "count every file as having arrived",
        "the summary then says a record reached its target when four tracks did not",
        PAGE,
        '    arrived = sum(1 for one in done if one["reached"]["arrived"])',
        "    arrived = len(done)",
    ),
    Mutant(
        "master into the folder the source is in",
        "the mastering layer refuses that, so the page would offer a button that cannot work",
        SERVE,
        "        return path.parent / (path.name + MASTERED_SUFFIX)",
        "        return path",
    ),
    Mutant(
        "write an empty tag rather than leaving the field out",
        "an empty tag is a claim that the field is empty, not that it was not given",
        MASTER,
        "        if value:\n            out[name] = value",
        "        out[name] = value",
    ),
    Mutant(
        "say the tags held without reading the file",
        "written is not stored, and the check is supposed to be against what came back",
        MASTER,
        "    out = {\"written\": wanted, \"held\": not wrong and not left}",
        "    out = {\"written\": wanted, \"held\": True}",
    ),
    Mutant(
        "let being inside the loudness range skip the ceiling",
        "entry 35: a file at -0.3 dBTP against a -1.0 ceiling then has nothing applied",
        MASTER,
        "    if placed == compare.INSIDE:\n        aim_loud, edge = lufs,",
        "    if placed == compare.INSIDE:\n        return _finish(steps, "
        "refused, lufs, peak, 0.0)\n        aim_loud, edge = lufs,",
    ),
    Mutant(
        "start a run with no target chosen",
        "every correction is derived from the distance to one, so there is nothing to do",
        SERVE,
        '    if not target_name or target_name == NONE:\n        return ("no target is chosen, and every correction here is derived from the "',
        '    if False:\n        return ("no target is chosen, and every correction here is derived from the "',
    ),
)

FAILED = re.compile(r"^FAILED (tests/\S+)::(\w+)", re.M)


def clear_stale() -> int:
    """A killed run cannot reach its own cleanup, so the next one does it."""
    gone = 0
    for old in Path(tempfile.gettempdir()).glob(STAGE_PREFIX + "*"):
        shutil.rmtree(old, ignore_errors=True)
        gone += 1
    return gone


def stage() -> Path:
    work = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX))
    for name in COPIED:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, work / name,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            shutil.copy2(source, work / name)
    return work


def run_suite(work: Path, stop_early: bool = False, only: str | None = None) -> tuple[list[str], str]:
    cmd = [str(PYTHON), "-m", "pytest", "-q", "--no-header", "--tb=no"]
    if stop_early:
        cmd.append("-x")
    if only is not None:
        cmd.append(only)
    r = subprocess.run(
        cmd, cwd=work, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    caught = sorted({name for _, name in FAILED.findall(r.stdout)})
    summary = next((l for l in reversed(r.stdout.splitlines()) if "passed" in l or "failed" in l), "")
    return caught, summary


def chosen(argv: list[str]) -> tuple[Mutant, ...]:
    """Everything, or the ones whose name contains a word given on the command line.
    A mutation that had to be rewritten is worth running on its own rather than running
    the other fifty six again to reach it."""
    words = [a.lower() for a in argv if not a.startswith("--")]
    if not words:
        return MUTANTS
    return tuple(m for m in MUTANTS if any(w in m.name.lower() for w in words))


def main() -> int:
    every = "--all" in sys.argv[1:]
    wanted = chosen(sys.argv[1:])
    if not wanted:
        print("no mutation matches " + " ".join(a for a in sys.argv[1:] if not a.startswith("--")))
        return 2
    stale = clear_stale()
    if stale:
        print(f"cleared {stale} staging {'directory' if stale == 1 else 'directories'} "
              "left by a run that was killed")
    work = stage()
    print(f"working on a copy at {work}, the repository is not touched")
    print("stopping each mutant at its first failing test. Pass --all to list every catcher, "
          "which runs the whole suite once per mutant." if not every else
          "listing every test that catches each mutant, which runs the whole suite once per mutant.")
    print()
    try:
        baseline, summary = run_suite(work)
        if baseline:
            print("the suite is not green before mutation, fix that first:")
            for name in baseline:
                print(f"  {name}")
            return 2
        print(f"baseline: {summary}")
        print()

        if wanted != MUTANTS:
            print(f"{len(wanted)} of {len(MUTANTS)} mutations selected by name")
            print()

        survivors = []
        for m in wanted:
            target = work / m.file
            original = target.read_text(encoding="utf-8")
            if m.find not in original:
                print(f"{m.name}: cannot apply, the code it patches has moved")
                survivors.append(m.name)
                continue
            target.write_text(original.replace(m.find, m.replace), encoding="utf-8")
            hint = None if every else LIKELY_CATCHER.get(m.file.name)
            caught, _ = run_suite(work, stop_early=not every, only=hint)
            elsewhere = False
            if not caught and hint is not None:
                caught, _ = run_suite(work, stop_early=True)
                elsewhere = bool(caught)
            target.write_text(original, encoding="utf-8")

            print(f"{m.name}  ({m.why})")
            if not caught:
                print("  SURVIVED, no test noticed")
                survivors.append(m.name)
            elif every:
                print(f"  caught by {len(caught)}: " + ", ".join(caught))
            else:
                where = " (outside its own test file)" if elsewhere else ""
                print(f"  caught by {caught[0]}{where}")
            print()

        if survivors:
            print("mutations nothing caught: " + ", ".join(survivors))
            return 1
        print(f"all {len(wanted)} mutations caught")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
