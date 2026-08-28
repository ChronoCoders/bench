from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import resample_poly

import rig
import signals as sig
from bench import decode as dec


def test_probe_reads_wav_pcm_fields(tmp_path):
    p = sig.write(tmp_path / "a.wav", sig.sine(1000, 1.0, channels=2), subtype="PCM_24")
    pr = dec.probe(p)
    assert pr.codec == "pcm_s24le"
    assert pr.sample_rate_hz == sig.SR
    assert pr.channels == 2
    assert pr.bit_depth == 24


def test_probe_omits_bit_depth_for_lossy(tmp_path):
    src = sig.write(tmp_path / "a.wav", sig.sine(1000, 2.0, channels=2))
    mp3 = sig.encode(src, tmp_path / "a.mp3", "-b:a", "192k")
    pr = dec.probe(mp3)
    assert pr.codec == "mp3"
    assert pr.bit_depth is None


def test_decode_keeps_content_above_11k(tmp_path):
    p = sig.write(tmp_path / "hi.wav", sig.sine(15000, 2.0))
    a = dec.decode(p)
    assert a.sample_rate_hz == sig.SR
    rig.control(rig.fraction_above(a.samples, a.sample_rate_hz, 11025), 1.0, 0.01,
                "energy above 11 kHz in a 15 kHz tone")


def test_decode_keeps_content_above_11k_can_fail(tmp_path):
    p = sig.write(tmp_path / "hi.wav", sig.sine(15000, 2.0))
    a = dec.decode(p)
    total = rig.power_in_band(a.samples, a.sample_rate_hz, 0.0, a.sample_rate_hz / 2)
    halved = resample_poly(a.samples, 1, 2, axis=1)
    kept = rig.power_in_band(halved, sig.SR // 2, 0.0, sig.SR / 4) / total
    rig.rejects(kept, 1.0, 0.01, "a loader resampling to 22050 keeps none of a 15 kHz tone")


def test_decode_keeps_both_channels(tmp_path):
    p = sig.write(tmp_path / "st.wav", sig.stereo(sig.sine(200, 2.0), sig.sine(300, 2.0)))
    a = dec.decode(p)
    assert a.channels == 2
    r = float(np.corrcoef(a.samples[0], a.samples[1])[0, 1])
    rig.control(r, 0.0, 0.02, "correlation of two independent tones")


def test_decode_keeps_both_channels_can_fail(tmp_path):
    p = sig.write(tmp_path / "st.wav", sig.stereo(sig.sine(200, 2.0), sig.sine(300, 2.0)))
    a = dec.decode(p)
    mono = a.samples.mean(axis=0)
    r = float(np.corrcoef(mono, mono)[0, 1])
    rig.rejects(r, 0.0, 0.02, "a downmix read as stereo")


def test_decode_refuses_a_rate_that_is_not_the_source_rate(tmp_path, monkeypatch):
    p = sig.write(tmp_path / "a.wav", sig.sine(1000, 1.0))
    monkeypatch.setattr(dec, "_read_soundfile", lambda path: (sig.sine(1000, 1.0, sr=22050), 22050))
    with pytest.raises(dec.DecodeError, match="22050"):
        dec.decode(p)


def test_container_duration_disagreeing_with_frames_is_caught(tmp_path, monkeypatch):
    p = sig.write(tmp_path / "a.wav", sig.sine(1000, 2.0))
    real = dec.probe(p)
    doubled = dec.Probe(real.container, real.codec, real.sample_rate_hz, real.channels,
                        real.bit_depth, real.container_duration_s * 2)
    monkeypatch.setattr(dec, "probe", lambda path: doubled)
    with pytest.raises(dec.DecodeError, match="container claims"):
        dec.decode(p)


def test_container_duration_check_can_fail(tmp_path, monkeypatch):
    p = sig.write(tmp_path / "a.wav", sig.sine(1000, 2.0))
    real = dec.probe(p)
    nudged = dec.Probe(real.container, real.codec, real.sample_rate_hz, real.channels,
                       real.bit_depth, real.container_duration_s + 0.4 * dec.DURATION_TOLERANCE_S)
    monkeypatch.setattr(dec, "probe", lambda path: nudged)
    dec.decode(p)


def test_decode_pcm16_round_trips_exactly(tmp_path):
    want = sig.pcm_ramp(16, 4096)
    p = sig.write(tmp_path / "r16.wav", want, subtype="PCM_16")
    got = dec.decode(p).samples
    assert np.array_equal(got, want)


def test_decode_pcm24_round_trips_exactly(tmp_path):
    want = sig.pcm_ramp(24, 4096)
    p = sig.write(tmp_path / "r24.wav", want, subtype="PCM_24")
    got = dec.decode(p).samples
    assert np.array_equal(got, want)


def test_ffmpeg_and_soundfile_decode_the_same_samples(tmp_path):
    src = sig.write(tmp_path / "a.wav", sig.stereo(sig.noise(2.0, seed=1), sig.noise(2.0, seed=2)))
    flac = sig.encode(src, tmp_path / "a.flac", "-c:a", "flac")
    a = dec.decode(flac)
    other, rate = dec._read_ffmpeg(flac, a.sample_rate_hz, a.channels)
    assert rate == a.sample_rate_hz
    assert np.array_equal(other, a.samples)


def test_source_dict_omits_what_the_container_did_not_say(tmp_path):
    src = sig.write(tmp_path / "a.wav", sig.sine(1000, 2.0, channels=2))
    mp3 = sig.encode(src, tmp_path / "a.mp3", "-b:a", "192k")
    d = dec.decode(mp3).source_dict()
    assert "bit_depth" not in d
    assert d["measured_at_hz"] == sig.SR
