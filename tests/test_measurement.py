"""What measurement.py does to what the measure modules hand it.

The spectral block is expanded on the way out, and what the expansion drops is not
recoverable downstream. A refusal is carried through with its reason, including when
the module that refused borrowed the class from another module.
"""

from __future__ import annotations

import rig
import signals as sig
from bench import compare, measurement
from bench.decode import decode
from bench.measure import spectral

RESOLUTION_FIELD = "spectral.uncertainty.every_percentage"


def two_tones(tmp_path, seconds=6.0):
    x = (sig.sine(100, seconds, channels=2, amp=0.4)
         + sig.sine(5000, seconds, channels=2, amp=0.4))
    return decode(sig.write(tmp_path / "two-tones.wav", x))


def surround(tmp_path, channels=5, seconds=2.0):
    """More channels than either instrument will weight. EBU Tech 3341 case 6 is the
    published version of this file, and the tone there is 1 kHz as well."""
    return sig.write(tmp_path / "surround.wav", sig.sine(1000, seconds, channels=channels))


def dropped_resolution(block):
    """The expansion as it was before this was fixed: one entry per reported percentage
    and nothing left saying what a percentage is reported to."""
    out = dict(block)
    every = block["uncertainty"]["every_percentage"]
    out["band_pct"] = {measurement.band_key(b["lo_hz"], b["hi_hz"]): b["pct"]
                       for b in block["bands"]}
    out["uncertainty"] = {name: every for name in block["rollups"]}
    out["uncertainty"].update({key: every for key in out["band_pct"]})
    return out


def test_every_reported_percentage_carries_an_uncertainty(tmp_path):
    block = measurement._expand_spectral(spectral.measure(two_tones(tmp_path)))
    reported = (list(block["band_pct"]) + list(block["rollups"])
                + list(block["outside_denominator_pct"]))
    missing = [name for name in reported if name not in block["uncertainty"]]
    assert not missing, f"reported with no uncertainty: {missing}"
    for name in reported:
        rig.control(block["uncertainty"][name], spectral.PERCENT_UNCERTAINTY, 0.0,
                    f"the uncertainty on {name}")


def test_the_resolution_itself_survives_the_expansion(tmp_path):
    one = {"spectral": measurement._expand_spectral(spectral.measure(two_tones(tmp_path)))}
    rig.control(compare.dig(one, RESOLUTION_FIELD), spectral.PERCENT_UNCERTAINTY, 0.0,
                "what a percentage is reported to, read back off the measurement")


def test_that_check_can_fail(tmp_path):
    one = {"spectral": dropped_resolution(spectral.measure(two_tones(tmp_path)))}
    if compare.dig(one, RESOLUTION_FIELD) is not None:
        raise rig.Toothless(
            f"{RESOLUTION_FIELD} was still readable after an expansion that drops it, "
            "so the check above cannot fail"
        )


def test_a_borrowed_refusal_is_carried_rather_than_crashed(tmp_path):
    """loudness and levels both reach bs1770 and neither declares a refusal class of
    its own. Naming the module in the handler looked for an attribute that was never
    there, so a refusal arrived as an AttributeError with the reason destroyed."""
    one = measurement.of_file(surround(tmp_path))
    assert "1.41" in one["loudness"]["unmeasurable"]
    assert "1.41" in one["levels"]["unmeasurable"]
    assert "no left and right" in one["stereo"]["unmeasurable"]


def test_the_rest_of_the_measurement_survives_a_refusal(tmp_path):
    """The control. If one refusal stopped the whole measurement, the test above would
    pass on a structure that had simply given up."""
    one = measurement.of_file(surround(tmp_path))
    assert one["spectral"]["bands"], "the spectrum does not care how many channels there are"


def test_a_measured_file_carries_the_resolution(tmp_path):
    one = measurement.of_file(sig.write(tmp_path / "one.wav",
                                        sig.sine(1000, 4.0, channels=2, amp=0.3)))
    rig.control(compare.dig(one, RESOLUTION_FIELD), spectral.PERCENT_UNCERTAINTY, 0.0,
                "the resolution on a file measured end to end")
