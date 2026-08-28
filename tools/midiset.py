"""Known answer material for tempo, built from a MIDI file and real recorded samples.

The tempo map is written into the file and read back out of it, so the answer the
bench is checked against comes from the artifact rather than from the generator.
Run it: python tools/midiset.py
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import mido
import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import dls
from bench.decode import decode
from bench.measure import tempo

RATE = 44100
TICKS_PER_BEAT = 480
DRUM_CHANNEL = 9
PERCUSSION_S = 1.2
SUSTAINED_S = 1.6
TAIL_S = 2.0
SPAN_TOLERANCE_BPM = 0.25
SPAN_TOLERANCE_FRACTION = 0.10

KICK, SNARE, HAT, OPEN_HAT, CRASH = 36, 38, 42, 46, 49
TOMS = (45, 47, 50)
BASS_PROGRAM = 33
CHORD_PROGRAM = 48
BREAKDOWN_BARS = range(16, 24)

PROGRESSION = ((45, (57, 60, 64)), (41, (53, 57, 60)), (36, (48, 52, 55)), (43, (55, 59, 62)))


@dataclass(frozen=True)
class Case:
    name: str
    bars: int
    curve: Callable[[float, int], float]
    representable: bool
    breakdown: bool = False


def steady(bpm):
    return lambda beat, beats: bpm


def linear(start, end):
    return lambda beat, beats: start + (end - start) * beat / beats


def ritardando(start, end):
    return lambda beat, beats: end + (start - end) * np.exp(-3.0 * beat / beats)


def step(first, second):
    return lambda beat, beats: first if beat < beats / 2 else second


def arch(low, high):
    return lambda beat, beats: low + (high - low) * np.sin(np.pi * beat / beats)


CASES = (
    Case("steady 128", 64, steady(128.0), True),
    Case("linear 88 to 91", 48, linear(88.0, 91.0), True),
    Case("linear 132 to 129", 56, linear(132.0, 129.0), True),
    Case("steady 88, drums out 8 bars", 48, steady(88.0), True, breakdown=True),
    Case("ritardando 140 to 120", 56, ritardando(140.0, 120.0), False),
    Case("step 128 to 132", 64, step(128.0, 132.0), False),
    Case("arch 120 to 126 to 120", 64, arch(120.0, 126.0), True),
)


def drum_bar(bar: int, breakdown: bool) -> list[tuple[float, int, int]]:
    if breakdown and bar in BREAKDOWN_BARS:
        return []
    hits = [(eighth * 0.5, OPEN_HAT if eighth == 6 else HAT, 70) for eighth in range(8)]
    hits += [(beat, KICK, 110) for beat in (0.0, 1.5, 2.5)]
    hits += [(beat, SNARE, 100) for beat in (1.0, 3.0)]
    if bar % 8 == 7:
        hits = [h for h in hits if h[0] < 2.0]
        hits += [(2.0 + i * 0.25, TOMS[i % 3], 90 + i) for i in range(8)]
    if bar % 8 == 0:
        hits.append((0.0, CRASH, 100))
    return hits


def arrangement(bars: int, breakdown: bool) -> list[tuple[float, int, int, int, float]]:
    events = []
    for bar in range(bars):
        base = bar * 4.0
        root, triad = PROGRESSION[bar % len(PROGRESSION)]
        for offset, note, velocity in drum_bar(bar, breakdown):
            events.append((base + offset, DRUM_CHANNEL, note, velocity, 0.25))
        for eighth in (0, 1, 3, 4, 6):
            events.append((base + eighth * 0.5, 0, root + (12 if eighth == 6 else 0), 96, 0.45))
        for note in triad:
            events.append((base, 1, note, 70, 3.8))
    return sorted(events)


def write_midi(path: Path, case: Case) -> Path:
    beats = case.bars * 4
    midi = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)

    tempo_track = mido.MidiTrack()
    midi.tracks.append(tempo_track)
    previous = 0
    for beat in range(beats):
        tick = beat * TICKS_PER_BEAT
        value = int(round(mido.bpm2tempo(float(case.curve(beat, beats)))))
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=value, time=tick - previous))
        previous = tick

    notes = mido.MidiTrack()
    midi.tracks.append(notes)
    notes.append(mido.Message("program_change", channel=0, program=BASS_PROGRAM, time=0))
    notes.append(mido.Message("program_change", channel=1, program=CHORD_PROGRAM, time=0))
    queue = []
    for start, channel, note, velocity, length in arrangement(case.bars, case.breakdown):
        queue.append((start, "note_on", channel, note, velocity))
        queue.append((start + length, "note_off", channel, note, 0))
    previous = 0
    for beat, kind, channel, note, velocity in sorted(queue, key=lambda q: (q[0], q[1] == "note_on")):
        tick = int(round(beat * TICKS_PER_BEAT))
        notes.append(mido.Message(kind, channel=channel, note=note, velocity=velocity,
                                  time=tick - previous))
        previous = tick
    midi.save(str(path))
    return path


def tempo_map(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Absolute seconds and beats per minute at every tempo change, read back from the file."""
    midi = mido.MidiFile(str(path))
    events = []
    for track in midi.tracks:
        tick = 0
        for message in track:
            tick += message.time
            if message.type == "set_tempo":
                events.append((tick, message.tempo))
    events.sort()
    seconds, previous_tick, previous_value = 0.0, 0, events[0][1]
    times, rates = [], []
    for tick, value in events:
        seconds += (tick - previous_tick) / midi.ticks_per_beat * previous_value / 1e6
        times.append(seconds)
        rates.append(mido.tempo2bpm(value))
        previous_tick, previous_value = tick, value
    return np.asarray(times), np.asarray(rates)


def render(path: Path, instruments, waves, rate: int = RATE) -> np.ndarray:
    midi = mido.MidiFile(str(path))
    programs = {DRUM_CHANNEL: 0}
    length = int((midi.length + TAIL_S) * rate)
    out = np.zeros(length)
    now = 0.0
    for message in midi:
        now += message.time
        if message.type == "program_change":
            programs[message.channel] = message.program
        elif message.type == "note_on" and message.velocity > 0:
            drums = message.channel == DRUM_CHANNEL
            voice = dls.voice(instruments, waves, programs.get(message.channel, 0), drums,
                              message.note, rate, PERCUSSION_S if drums else SUSTAINED_S)
            if voice is None:
                continue
            start = int(now * rate)
            end = min(length, start + voice.size)
            if end > start:
                out[start:end] += voice[: end - start] * (message.velocity / 127.0)
    peak = np.max(np.abs(out))
    return np.vstack([out, out]) / peak * 0.7 if peak > 0 else np.vstack([out, out])


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="bench-midiset-"))
    instruments, waves = dls.load()
    print(f"rendering into {work}")
    print()
    print(f"{'case':30} {'written map':>16} {'bench bpm':>10} {'true':>7} {'bench':>7} "
          f"{'error':>7} {'fit ms':>7} {'cov':>5}")
    missed = []
    for case in CASES:
        path = write_midi(work / f"{case.name.replace(' ', '_').replace(',', '')}.mid", case)
        audio = render(path, instruments, waves)
        wav = path.with_suffix(".wav")
        sf.write(str(wav), audio.T, RATE, subtype="PCM_24")

        _, rates = tempo_map(path)
        got = tempo.measure(decode(wav))
        scale = max(1, round(got["bpm"] / float(np.median(rates))))
        true_span = float(rates.max() - rates.min())
        bench_span = got["drift"]["span_bpm"] / scale if "drift" in got else 0.0
        error = abs(bench_span - true_span)
        allowed = max(SPAN_TOLERANCE_BPM, SPAN_TOLERANCE_FRACTION * true_span)
        if case.representable and error > allowed:
            missed.append(case.name)
        mark = "" if case.representable else "  not representable"
        print(f"{case.name:30} {rates.min():7.2f}..{rates.max():<7.2f} {got['bpm'] / scale:10.2f} "
              f"{true_span:7.2f} {bench_span:7.2f} {error:7.2f} {got['grid_fit_ms']:7.2f} "
              f"{got['coverage']:5.2f}{mark}")
    print()
    claimed = [c for c in CASES if c.representable]
    print(f"{len(claimed) - len(missed)} of {len(claimed)} shapes the model claims to hold "
          f"are within {SPAN_TOLERANCE_BPM} BPM or {SPAN_TOLERANCE_FRACTION:.0%} of the "
          f"written map")
    if missed:
        print("missed: " + ", ".join(missed))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
