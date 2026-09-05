"""The published compliance cases, from the documents rather than from another tool.

Every expected value and tolerance here is quoted from a table in an EBU document, and
every signal is built from the description in the same table. Nothing in this file is
derived from what the bench reports.

  EBU Tech 3341, November 2023, Table 1, cases 1 to 5 and 15 to 19
  EBU Tech 3342, August 2011, Table 1, cases 1 to 4

The cases left out are left out for a reason. Cases 9 to 14 of 3341 assert momentary
and short term loudness and the maximum of each over time, none of which this bench
reports. Case 6 is 5.0 channel and the second instrument refuses surround, which
test_measurement.py covers. Cases 7 and 8 of 3341 and 5 and 6 of 3342 are authentic
programme segments that ship only in the EBU test set. Cases 20 to 23 are built at four
times the rate and downsampled through an anti-aliasing filter the document does not
specify, so a disagreement would be about the filter chosen here rather than about the
bench.

The signals are synthesised at 48 kHz in float, which is the rate the EBU set is
synthesised at and the format that keeps quantisation out of a comparison against a
stated number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pytest
import soundfile as sf

import rig
from bench.decode import decode
from bench.measure import bs1770, ebur128

SR = 48000
INTEGRATED, TRUE_PEAK, RANGE = "integrated loudness", "maximum true peak", "loudness range"


def tone(seconds: float, peak_dbfs: float | None = None, hz: float = 1000.0,
         phase_deg: float = 0.0, amplitude: float | None = None) -> np.ndarray:
    """One tone, applied in phase to both channels, as every case in both tables asks."""
    n = int(round(seconds * SR))
    t = np.arange(n) / SR
    a = amplitude if amplitude is not None else 10.0 ** (peak_dbfs / 20.0)
    x = a * np.sin(2.0 * np.pi * hz * t + math.radians(phase_deg))
    return np.stack([x, x])


def tapered(x: np.ndarray, ms: float = 10.0) -> np.ndarray:
    """The 10 ms fade case 15 asks for. It touches neither the loudness nor the peak of
    what lies between the fades."""
    k = int(round(ms * 1e-3 * SR))
    window = 0.5 * (1.0 - np.cos(np.pi * np.arange(k) / k))
    out = x.copy()
    out[:, :k] *= window
    out[:, -k:] *= window[::-1]
    return out


def run(*parts: np.ndarray) -> np.ndarray:
    return np.concatenate(parts, axis=1)


@dataclass(frozen=True)
class Case:
    document: str
    number: int
    field: str
    stated: float
    low: float
    high: float
    signal: object

    @property
    def name(self) -> str:
        return f"{self.document}-{self.number}"

    def holds(self, measured: float) -> bool:
        return self.low <= round(measured - self.stated, 6) <= self.high


CASES = (
    Case("3341", 1, INTEGRATED, -23.0, -0.1, 0.1, lambda: tone(20.0, -23.0)),
    Case("3341", 2, INTEGRATED, -33.0, -0.1, 0.1, lambda: tone(20.0, -33.0)),
    Case("3341", 3, INTEGRATED, -23.0, -0.1, 0.1,
         lambda: run(tone(10.0, -36.0), tone(60.0, -23.0), tone(10.0, -36.0))),
    Case("3341", 4, INTEGRATED, -23.0, -0.1, 0.1,
         lambda: run(tone(10.0, -72.0), tone(10.0, -36.0), tone(60.0, -23.0),
                     tone(10.0, -36.0), tone(10.0, -72.0))),
    Case("3341", 5, INTEGRATED, -23.0, -0.1, 0.1,
         lambda: run(tone(20.0, -26.0), tone(20.1, -20.0), tone(20.0, -26.0))),
    Case("3341", 15, TRUE_PEAK, -6.0, -0.4, 0.2,
         lambda: tapered(tone(5.0, hz=SR / 4.0, phase_deg=0.0, amplitude=0.50))),
    Case("3341", 16, TRUE_PEAK, -6.0, -0.4, 0.2,
         lambda: tapered(tone(5.0, hz=SR / 4.0, phase_deg=45.0, amplitude=0.50))),
    Case("3341", 17, TRUE_PEAK, -6.0, -0.4, 0.2,
         lambda: tapered(tone(5.0, hz=SR / 6.0, phase_deg=60.0, amplitude=0.50))),
    Case("3341", 18, TRUE_PEAK, -6.0, -0.4, 0.2,
         lambda: tapered(tone(5.0, hz=SR / 8.0, phase_deg=67.5, amplitude=0.50))),
    Case("3341", 19, TRUE_PEAK, 3.0, -0.4, 0.2,
         lambda: tapered(tone(5.0, hz=SR / 4.0, phase_deg=45.0, amplitude=1.41))),
    Case("3342", 1, RANGE, 10.0, -1.0, 1.0,
         lambda: run(tone(20.0, -20.0), tone(20.0, -30.0))),
    Case("3342", 2, RANGE, 5.0, -1.0, 1.0,
         lambda: run(tone(20.0, -20.0), tone(20.0, -15.0))),
    Case("3342", 3, RANGE, 20.0, -1.0, 1.0,
         lambda: run(tone(20.0, -40.0), tone(20.0, -20.0))),
    Case("3342", 4, RANGE, 15.0, -1.0, 1.0,
         lambda: run(tone(20.0, -50.0), tone(20.0, -35.0), tone(20.0, -20.0),
                     tone(20.0, -35.0), tone(20.0, -50.0))),
)

BY_NAME = {c.name: c for c in CASES}
IDS = [c.name for c in CASES]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    where = tmp_path_factory.mktemp("ebu")
    out = {}
    for case in CASES:
        path = where / f"{case.name}.wav"
        sf.write(str(path), case.signal().T, SR, subtype="FLOAT")
        out[case.name] = path
    return out


def primary(case: Case, path):
    got = ebur128.measure(path, decode(path).duration_s)
    return {INTEGRATED: got.integrated_lufs, TRUE_PEAK: got.true_peak_dbtp,
            RANGE: got.lra_lu}[case.field]


def second(case: Case, path):
    audio = decode(path)
    if case.field == TRUE_PEAK:
        return bs1770.true_peak_dbtp(audio.samples)
    if case.field == RANGE:
        return bs1770.loudness_range(audio.samples, audio.sample_rate_hz)
    got = bs1770.integrated(audio.samples, audio.sample_rate_hz)
    return None if got is None else got.lufs


def _check(case: Case, measured, instrument: str):
    assert measured is not None, f"{instrument} reported no {case.field} for {case.name}"
    assert case.holds(measured), (
        f"{case.name} {case.field}: {instrument} reads {measured:.3f} against the "
        f"{case.stated} the document states, which is {measured - case.stated:+.3f} "
        f"against an allowed {case.low:+.1f} to {case.high:+.1f}"
    )


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_primary_instrument_meets_the_published_value(case, rendered):
    _check(case, primary(case, rendered[case.name]), "ffmpeg ebur128")


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_second_instrument_meets_the_published_value(case, rendered):
    _check(case, second(case, rendered[case.name]), "bs1770 in numpy")


def test_the_primary_tolerance_can_reject(rendered):
    """The two below read the second instrument, so neither of them says anything about
    whether the primary readings are being judged at all. Case 2 is case 1 ten decibels
    down, and ffmpeg reading it against the value stated for case 1 has to be refused."""
    quiet = primary(BY_NAME["3341-2"], rendered["3341-2"])
    rig.rejects(quiet, BY_NAME["3341-1"].stated, 0.1,
                "a tone 10 dB down, read by ffmpeg against the value stated for case 1")


def test_the_loudness_tolerance_can_reject(rendered):
    """Case 2 is case 1 ten decibels down. Read against the value stated for case 1 it
    has to be refused, or the tenth of a decibel these cases are judged on proves
    nothing."""
    quiet = second(BY_NAME["3341-2"], rendered["3341-2"])
    rig.rejects(quiet, BY_NAME["3341-1"].stated, 0.1,
                "a tone 10 dB down read against the value stated for case 1")


def test_the_true_peak_tolerance_can_reject(rendered):
    """Case 16 puts its peak between samples. The largest sample is 3 dB below the true
    peak the document states, so a meter reading samples fails this at the same
    tolerance the case is judged on."""
    audio = decode(rendered["3341-16"])
    rig.rejects(bs1770.sample_peak_dbfs(audio.samples), BY_NAME["3341-16"].stated, 0.4,
                "the largest sample of case 16 read as its true peak")
