"""Decode at native rate. Sample arrays are (channels, frames), float64."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

PROBE_METHOD = "probe/ffprobe"
DECODE_METHOD = "decode/native-rate"

DURATION_TOLERANCE_S = 0.05
DURATION_TOLERANCE_FRAC = 0.005


class DecodeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Probe:
    container: str
    codec: str
    sample_rate_hz: int
    channels: int
    bit_depth: int | None
    container_duration_s: float | None


@dataclass(frozen=True)
class Audio:
    samples: np.ndarray
    sample_rate_hz: int
    path: Path
    sha1: str
    probe: Probe
    decoder: str

    @property
    def channels(self) -> int:
        return int(self.samples.shape[0])

    @property
    def frames(self) -> int:
        return int(self.samples.shape[1])

    @property
    def duration_s(self) -> float:
        return self.frames / self.sample_rate_hz

    def source_dict(self) -> dict:
        d = {
            "container": self.probe.container,
            "codec": self.probe.codec,
            "sample_rate_hz": self.probe.sample_rate_hz,
            "channels": self.channels,
            "measured_at_hz": self.sample_rate_hz,
            "decoder": self.decoder,
        }
        if self.probe.bit_depth is not None:
            d["bit_depth"] = self.probe.bit_depth
        if self.probe.container_duration_s is not None:
            d["container_duration_s"] = self.probe.container_duration_s
        return d


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: Path) -> Probe:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", "-select_streams", "a:0", str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, text=True)
    if r.returncode != 0:
        raise DecodeError(f"ffprobe failed on {path}: {r.stderr.strip()}")
    doc = json.loads(r.stdout)
    streams = doc.get("streams") or []
    if not streams:
        raise DecodeError(f"no audio stream in {path}")
    s = streams[0]

    depth = None
    for key in ("bits_per_raw_sample", "bits_per_sample"):
        raw = s.get(key)
        if raw not in (None, "0", 0):
            depth = int(raw)
            break

    duration = s.get("duration") or doc.get("format", {}).get("duration")
    return Probe(
        container=doc.get("format", {}).get("format_name", ""),
        codec=s.get("codec_name", ""),
        sample_rate_hz=int(s["sample_rate"]),
        channels=int(s["channels"]),
        bit_depth=depth,
        container_duration_s=float(duration) if duration is not None else None,
    )


def _read_soundfile(path: Path) -> tuple[np.ndarray, int]:
    data, rate = sf.read(str(path), dtype="float64", always_2d=True)
    return np.ascontiguousarray(data.T), int(rate)


def _read_ffmpeg(path: Path, rate: int, channels: int) -> tuple[np.ndarray, int]:
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0",
        "-ar", str(rate), "-ac", str(channels),
        "-acodec", "pcm_f64le", "-f", "f64le", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise DecodeError(f"ffmpeg failed on {path}: {r.stderr.decode(errors='replace').strip()}")
    flat = np.frombuffer(r.stdout, dtype="<f8")
    if channels and flat.size % channels:
        raise DecodeError(f"ffmpeg returned {flat.size} samples, not a multiple of {channels} channels")
    return np.ascontiguousarray(flat.reshape(-1, channels).T), rate


def _check_duration(frames: int, rate: int, claimed: float | None, path: Path) -> None:
    if claimed is None:
        return
    measured = frames / rate
    tolerance = max(DURATION_TOLERANCE_S, DURATION_TOLERANCE_FRAC * claimed)
    if abs(measured - claimed) > tolerance:
        raise DecodeError(
            f"{path.name}: decoded {frames} frames at {rate} Hz is {measured:.3f} s, "
            f"container claims {claimed:.3f} s, tolerance {tolerance:.3f} s"
        )


def decode(path: str | Path) -> Audio:
    path = Path(path)
    if not path.is_file():
        raise DecodeError(f"not a file: {path}")
    p = probe(path)

    try:
        samples, rate = _read_soundfile(path)
        decoder = "soundfile"
    except Exception:
        samples, rate = _read_ffmpeg(path, p.sample_rate_hz, p.channels)
        decoder = "ffmpeg"

    if rate != p.sample_rate_hz:
        raise DecodeError(
            f"{path.name}: {decoder} returned {rate} Hz for a {p.sample_rate_hz} Hz source"
        )
    if samples.shape[0] != p.channels:
        raise DecodeError(
            f"{path.name}: {decoder} returned {samples.shape[0]} channels for a {p.channels} channel source"
        )
    _check_duration(samples.shape[1], rate, p.container_duration_s, path)

    return Audio(
        samples=samples,
        sample_rate_hz=rate,
        path=path,
        sha1=sha1_of(path),
        probe=p,
        decoder=decoder,
    )
