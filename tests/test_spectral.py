from __future__ import annotations

import numpy as np
import pytest

import filterbank
import rig
import signals as sig
from bench.decode import decode
from bench.measure import spectral

SPLIT_TOLERANCE_PCT = 0.05
FLAT_TOLERANCE_PCT = 0.02
PARSEVAL_TOLERANCE = 0.0001
INVARIANCE_TOLERANCE_PCT = 0.02
RATE_TOLERANCE_PCT = 0.05
FILTERBANK_TOLERANCE_PCT = 0.1


def band_pct(samples, rate, lo, hi):
    freqs, power = spectral.spectrum(samples, rate)
    total = spectral.band_power(freqs, power, *spectral.DENOMINATOR_HZ)
    return 100.0 * spectral.band_power(freqs, power, lo, hi) / total


def two_tones(a1, a2, seconds=20.0, rate=sig.SR):
    return (sig.sine(100, seconds, sr=rate, amp=a1, channels=2)
            + sig.sine(5000, seconds, sr=rate, amp=a2, channels=2))


def analytic_low_pct(a1, a2):
    return 100.0 * a1**2 / (a1**2 + a2**2)


@pytest.mark.parametrize("a1,a2", [(0.5, 0.5), (0.8, 0.2), (0.1, 0.9)])
def test_two_tone_split_matches_the_amplitudes(a1, a2):
    x = two_tones(a1, a2)
    rig.control(band_pct(x, sig.SR, 60.0, 120.0), analytic_low_pct(a1, a2), SPLIT_TOLERANCE_PCT,
                f"60 to 120 Hz share of two tones at {a1} and {a2}")
    rig.control(band_pct(x, sig.SR, 4000.0, 8000.0), 100.0 - analytic_low_pct(a1, a2),
                SPLIT_TOLERANCE_PCT, "4 to 8 kHz share of the same")


def test_two_tone_split_can_fail():
    x = two_tones(0.8, 0.2)
    rig.rejects(band_pct(x, sig.SR, 4000.0, 8000.0), analytic_low_pct(0.8, 0.2),
                SPLIT_TOLERANCE_PCT, "the high band's share read as the low band's")


def test_flat_spectrum_fills_bands_in_proportion_to_width(tmp_path):
    got = spectral.measure(decode(sig.write(tmp_path / "flat.wav", sig.flat_spectrum(20.0, seed=11))))
    span = spectral.DENOMINATOR_HZ[1] - spectral.DENOMINATOR_HZ[0]
    for band in got["bands"]:
        rig.control(band["pct"], 100.0 * (band["hi_hz"] - band["lo_hz"]) / span, FLAT_TOLERANCE_PCT,
                    f"{band['lo_hz']:.0f} to {band['hi_hz']:.0f} Hz on a flat spectrum")
    for name, (lo, hi) in spectral.ROLLUPS.items():
        rig.control(got["rollups"][name], 100.0 * (hi - lo) / span, FLAT_TOLERANCE_PCT, name)


def test_percentages_sum_to_one_hundred(tmp_path):
    got = spectral.measure(decode(sig.write(tmp_path / "flat.wav", sig.flat_spectrum(20.0, seed=3))))
    rig.control(sum(b["pct"] for b in got["bands"]), 100.0, 0.05, "the band set summed")


def test_summing_to_one_hundred_proves_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(spectral, "BAND_EDGES_HZ", (20.0, 21.0, 22.0, 23.0, 19000.0, 20000.0))
    got = spectral.measure(decode(sig.write(tmp_path / "flat.wav", sig.flat_spectrum(20.0, seed=3))))
    rig.control(sum(b["pct"] for b in got["bands"]), 100.0, 0.05,
                "a band set of nonsense edges, summed")
    band = next(b for b in got["bands"] if b["lo_hz"] == 20.0)
    span = spectral.DENOMINATOR_HZ[1] - spectral.DENOMINATOR_HZ[0]
    rig.rejects(band["pct"], 100.0 * (60.0 - 20.0) / span, FLAT_TOLERANCE_PCT,
                "a 1 Hz band carrying the share of a 40 Hz band")


def test_the_spectrum_integrates_to_the_time_domain_energy():
    x = sig.flat_spectrum(20.0, seed=5)
    _, power = spectral.spectrum(x, sig.SR)
    got = spectral.total_energy(power, spectral.transform_length(x.shape[1]))
    rig.control(got / float(np.sum(np.square(x))), 1.0, PARSEVAL_TOLERANCE,
                "energy from the spectrum over energy from the samples")


def test_parseval_check_can_fail():
    x = sig.flat_spectrum(20.0, seed=5)
    _, power = spectral.spectrum(x, sig.SR)
    n = spectral.transform_length(x.shape[1])
    undoubled = float(np.sum(power) - np.sum(power[1:-1]) / 2.0) / n
    rig.rejects(undoubled / float(np.sum(np.square(x))), 1.0, PARSEVAL_TOLERANCE,
                "a one sided spectrum without the doubling")


def band_energy_two_ways(x, rate, lo, hi):
    n = spectral.transform_length(x.shape[1])
    padded = np.zeros((x.shape[0], n))
    padded[:, : x.shape[1]] = x
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    mask = (freqs >= lo) & (freqs < hi)
    time_domain = 0.0
    frequency_domain = 0.0
    for channel in padded:
        transform = np.fft.rfft(channel)
        time_domain += float(np.sum(np.square(np.fft.irfft(transform * mask, n))))
        one_sided = np.abs(transform) ** 2
        if n % 2 == 0:
            one_sided[1:-1] *= 2.0
        else:
            one_sided[1:] *= 2.0
        frequency_domain += float(np.sum(one_sided[mask])) / n
    return time_domain, frequency_domain


@pytest.mark.parametrize("lo,hi", [(60.0, 120.0), (250.0, 500.0), (4000.0, 8000.0)])
def test_each_band_energy_survives_the_round_trip(lo, hi):
    x = sig.flat_spectrum(4.0, seed=9)
    time_domain, frequency_domain = band_energy_two_ways(x, sig.SR, lo, hi)
    rig.control(frequency_domain / time_domain, 1.0, PARSEVAL_TOLERANCE,
                f"{lo:.0f} to {hi:.0f} Hz energy in the frequency domain over the time domain")


def test_the_round_trip_check_can_fail():
    x = sig.flat_spectrum(4.0, seed=9)
    time_domain, frequency_domain = band_energy_two_ways(x, sig.SR, 60.0, 120.0)
    rig.rejects(frequency_domain / (2.0 * time_domain), 1.0, PARSEVAL_TOLERANCE,
                "the same energy with the one sided doubling applied twice")


def test_percentages_do_not_move_under_a_gain_change():
    x = sig.flat_spectrum(20.0, seed=7)
    before = band_pct(x, sig.SR, 20.0, 250.0)
    after = band_pct(x * 10 ** (-6.0 / 20.0), sig.SR, 20.0, 250.0)
    rig.invariance(before, after, 0.001, "under 250 Hz share under a 6 dB cut")


def test_percentages_move_when_the_balance_moves():
    before = band_pct(two_tones(0.5, 0.5), sig.SR, 60.0, 120.0)
    after = band_pct(two_tones(0.8, 0.2), sig.SR, 60.0, 120.0)
    rig.covariance(before, after, analytic_low_pct(0.8, 0.2) - analytic_low_pct(0.5, 0.5),
                   SPLIT_TOLERANCE_PCT, "low band share when the tone balance changes")


def test_sample_rate_does_not_change_the_percentages(tmp_path):
    values = []
    for rate in (44100, 48000):
        x = sig.flat_spectrum(20.0, sr=rate, seed=13)
        got = spectral.measure(decode(sig.write(tmp_path / f"f{rate}.wav", x, sr=rate)))
        values.append(got["rollups"]["under_250_hz_pct"])
    rig.invariance(values[0], values[1], RATE_TOLERANCE_PCT,
                   "under 250 Hz share at 44.1 kHz against 48 kHz")


def test_sample_rate_invariance_can_fail():
    values = []
    for rate in (44100, 48000):
        x = sig.flat_spectrum(20.0, sr=rate, seed=13)
        freqs, power = spectral.spectrum(x, rate)
        to_nyquist = spectral.band_power(freqs, power, spectral.DENOMINATOR_HZ[0], rate / 2.0)
        values.append(100.0 * spectral.band_power(freqs, power, 20.0, 250.0) / to_nyquist)
    rig.rejects(values[0], values[1], RATE_TOLERANCE_PCT,
                "a denominator running to Nyquist instead of 20 kHz")


def rumble(seconds, seed=19):
    x = sig.flat_spectrum(seconds, seed=seed)
    return sig.faded(x), sig.faded(x + sig.sine(15, seconds, amp=0.3, channels=2))


def test_content_below_20_hz_stays_out_of_the_bands():
    plain, loud = rumble(20.0)
    rig.invariance(band_pct(plain, sig.SR, 20.0, 250.0), band_pct(loud, sig.SR, 20.0, 250.0),
                   INVARIANCE_TOLERANCE_PCT, "under 250 Hz share with a 15 Hz tone at 0.3 added")


def test_content_below_20_hz_staying_out_can_fail():
    plain, loud = rumble(1.2)
    rig.rejects(band_pct(loud, sig.SR, 20.0, 250.0), band_pct(plain, sig.SR, 20.0, 250.0),
                INVARIANCE_TOLERANCE_PCT,
                "the same tone in a 1.2 s file, where a bin is nearly a hertz wide")


@pytest.mark.parametrize("frames", [11395200, 9955200, 10000019, 100003])
def test_the_transform_keeps_every_frame(frames):
    n = spectral.transform_length(frames)
    assert n >= frames
    assert (n - frames) / frames < 0.02


def test_zero_padding_does_not_move_the_answer():
    x = sig.flat_spectrum(20.0, seed=21)
    n = x.shape[1]
    freqs = np.fft.rfftfreq(n, 1.0 / sig.SR)
    power = np.zeros(n // 2 + 1)
    for channel in x:
        power += np.abs(np.fft.rfft(channel)) ** 2
    power[1:-1] *= 2.0
    unpadded = (100.0 * spectral.band_power(freqs, power, 20.0, 250.0)
                / spectral.band_power(freqs, power, *spectral.DENOMINATOR_HZ))
    rig.invariance(unpadded, band_pct(x, sig.SR, 20.0, 250.0), 0.02,
                   "under 250 Hz share with and without padding to a fast length")


def test_a_file_shorter_than_the_minimum_has_no_spectral_measurement(tmp_path):
    x = sig.sine(1000, 0.5, amp=0.5, channels=2)
    with pytest.raises(spectral.Unmeasurable, match="shorter than"):
        spectral.measure(decode(sig.write(tmp_path / "short.wav", x)))


def test_an_independent_filterbank_agrees_on_a_controlled_signal():
    x = two_tones(0.8, 0.2)
    got = filterbank.band_percentages(x, sig.SR, spectral.BAND_EDGES_HZ)
    rig.control(got[(60.0, 120.0)], band_pct(x, sig.SR, 60.0, 120.0), FILTERBANK_TOLERANCE_PCT,
                "elliptic filterbank against the transform, tones clear of every band edge")


def test_the_filterbank_check_can_fail():
    x = two_tones(0.8, 0.2)
    got = filterbank.band_percentages(x, sig.SR, spectral.BAND_EDGES_HZ)
    rig.rejects(got[(4000.0, 8000.0)], band_pct(x, sig.SR, 60.0, 120.0),
                FILTERBANK_TOLERANCE_PCT, "the filterbank's high band read as its low band")


def uniform_spectrum(spacing=7.0, bins=100):
    return np.arange(bins) * spacing, np.ones(bins)


def whole_bin_power(freqs, power, lo, hi):
    df = freqs[1] - freqs[0]
    return float(np.sum(power[(freqs >= lo) & (freqs < hi)]) * df)


def test_band_power_weights_partial_bins():
    freqs, power = uniform_spectrum()
    rig.control(spectral.band_power(freqs, power, 20.0, 60.0), 40.0, 1e-9,
                "a 40 Hz band of unit density, edges falling inside bins 7 Hz wide")


def test_partial_bin_weighting_can_fail():
    freqs, power = uniform_spectrum()
    rig.rejects(whole_bin_power(freqs, power, 20.0, 60.0), 40.0, 1e-9,
                "the same band with whole bins assigned by their centre")


def direct_current_and_nyquist(rate=sig.SR):
    n = spectral.transform_length(rate)
    index = np.arange(n)
    tone = 0.5 * np.sin(2.0 * np.pi * round(1000 * n / rate) * index / n)
    one = 0.3 + 0.3 * (-1.0) ** index + tone
    return np.vstack([one, one]), n


def test_parseval_holds_with_direct_current_and_nyquist_content():
    x, n = direct_current_and_nyquist()
    _, power = spectral.spectrum(x, sig.SR)
    rig.control(spectral.total_energy(power, n) / float(np.sum(np.square(x))), 1.0,
                PARSEVAL_TOLERANCE, "energy of a signal that is mostly direct current and Nyquist")


def test_doubling_direct_current_and_nyquist_can_fail():
    x, n = direct_current_and_nyquist()
    undoubled = np.zeros(n // 2 + 1)
    for channel in x:
        undoubled += np.abs(np.fft.rfft(channel)) ** 2
    doubled_everywhere = float(np.sum(2.0 * undoubled)) / n
    rig.rejects(doubled_everywhere / float(np.sum(np.square(x))), 1.0, PARSEVAL_TOLERANCE,
                "every bin doubled, direct current and Nyquist included")
