"""Minimal reader for the General MIDI sample set that ships with Windows.

Enough of the DLS structure to find which recorded sample a note should play.
Used to render known answer material, never by the bench itself.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GM_DLS = Path("C:/Windows/System32/drivers/gm.dls")
DRUM_BANK_FLAG = 0x80000000


@dataclass(frozen=True)
class Region:
    low_key: int
    high_key: int
    wave_index: int
    unity_note: int
    fine_tune: int
    gain_db: float


@dataclass(frozen=True)
class Instrument:
    bank: int
    program: int
    drums: bool
    regions: tuple[Region, ...]

    def region_for(self, note: int) -> Region | None:
        for r in self.regions:
            if r.low_key <= note <= r.high_key:
                return r
        return None


@dataclass(frozen=True)
class Wave:
    rate: int
    samples: np.ndarray


def _chunks(buf: bytes, start: int, end: int):
    off = start
    while off + 8 <= end:
        cid = buf[off : off + 4]
        size = struct.unpack_from("<I", buf, off + 4)[0]
        yield cid, off + 8, size
        off += 8 + size + (size & 1)


def _lists(buf: bytes, start: int, end: int, want: bytes):
    for cid, body, size in _chunks(buf, start, end):
        if cid in (b"LIST", b"RIFF") and buf[body : body + 4] == want:
            yield body + 4, body + size


def _find(buf: bytes, start: int, end: int, want: bytes):
    for cid, body, size in _chunks(buf, start, end):
        if cid == want:
            return body, size
    return None


def _region(buf: bytes, start: int, end: int) -> Region | None:
    header = _find(buf, start, end, b"rgnh")
    link = _find(buf, start, end, b"wlnk")
    sample = _find(buf, start, end, b"wsmp")
    if header is None or link is None:
        return None
    low, high = struct.unpack_from("<HH", buf, header[0])
    table_index = struct.unpack_from("<I", buf, link[0] + 8)[0]
    unity, fine, gain = 60, 0, 0
    if sample is not None:
        unity, fine, gain = struct.unpack_from("<Hhi", buf, sample[0] + 4)
    return Region(low, high, table_index, unity, fine, gain / 655360.0)


def _instrument(buf: bytes, start: int, end: int) -> Instrument | None:
    header = _find(buf, start, end, b"insh")
    if header is None:
        return None
    _, bank, program = struct.unpack_from("<III", buf, header[0])
    regions = []
    for rgn_start, rgn_end in _lists(buf, start, end, b"lrgn"):
        for cid, body, size in _chunks(buf, rgn_start, rgn_end):
            if cid == b"LIST" and buf[body : body + 4] in (b"rgn ", b"rgn2"):
                r = _region(buf, body + 4, body + size)
                if r is not None:
                    regions.append(r)
    return Instrument(bank & ~DRUM_BANK_FLAG, program & 0x7F,
                      bool(bank & DRUM_BANK_FLAG), tuple(regions))


def _wave(buf: bytes, start: int, end: int) -> Wave | None:
    fmt = _find(buf, start, end, b"fmt ")
    data = _find(buf, start, end, b"data")
    if fmt is None or data is None:
        return None
    tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", buf, fmt[0])
    if tag != 1 or bits != 16:
        return None
    pcm = np.frombuffer(buf, dtype="<i2", count=data[1] // 2, offset=data[0])
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)
    return Wave(rate, pcm.astype(np.float64) / 32768.0)


def load(path: Path = GM_DLS) -> tuple[dict[tuple[int, bool], Instrument], list[Wave]]:
    buf = path.read_bytes()
    top = next(_lists(buf, 0, len(buf), b"DLS "))
    instruments = {}
    for lins_start, lins_end in _lists(buf, *top, b"lins"):
        for ins_start, ins_end in _lists(buf, lins_start, lins_end, b"ins "):
            ins = _instrument(buf, ins_start, ins_end)
            if ins is not None and ins.bank == 0:
                instruments[(ins.program, ins.drums)] = ins
    waves = []
    for wvpl_start, wvpl_end in _lists(buf, *top, b"wvpl"):
        for wave_start, wave_end in _lists(buf, wvpl_start, wvpl_end, b"wave"):
            waves.append(_wave(buf, wave_start, wave_end))
    return instruments, waves


def voice(instruments, waves, program: int, drums: bool, note: int,
          rate: int, seconds: float) -> np.ndarray | None:
    ins = instruments.get((0 if drums else program, drums))
    if ins is None:
        return None
    region = ins.region_for(note)
    if region is None or region.wave_index >= len(waves):
        return None
    wave = waves[region.wave_index]
    if wave is None:
        return None
    semitones = note - region.unity_note + region.fine_tune / 100.0
    step = (2.0 ** (semitones / 12.0)) * wave.rate / rate
    wanted = int(seconds * rate)
    index = np.arange(wanted) * step
    inside = index < wave.samples.size - 1
    out = np.zeros(wanted)
    i = index[inside]
    base = i.astype(int)
    frac = i - base
    out[inside] = wave.samples[base] * (1.0 - frac) + wave.samples[base + 1] * frac
    return out * (10.0 ** (region.gain_db / 20.0))
