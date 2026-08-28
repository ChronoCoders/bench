from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

import music
import signals as sig
from bench import measurement

SOURCE = Path(__file__).resolve().parent.parent / "src"
CALL = re.compile(r"subprocess\.run\((.*?)\)", re.S)


def calls():
    for path in sorted(SOURCE.rglob("*.py")):
        for arguments in CALL.findall(path.read_text(encoding="utf-8")):
            yield path.name, " ".join(arguments.split())


def test_every_external_tool_is_called_with_its_own_stdin():
    found = list(calls())
    assert found, "this control only means something while something calls out to a tool"
    for name, arguments in found:
        assert "stdin=subprocess.DEVNULL" in arguments, (
            f"{name} runs a tool with the caller's stdin. If the shell that started the bench "
            f"goes away, that handle dies and the tool fails with no message."
        )


def test_the_stdin_control_can_fail():
    assert "stdin=subprocess.DEVNULL" not in "subprocess.run(cmd, capture_output=True)", (
        "the check would pass a call that does not set stdin, so it proves nothing"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="the handle is inherited differently elsewhere")
def test_a_file_measures_with_no_usable_stdin(tmp_path):
    path = sig.write(tmp_path / "one.wav", music.build("dense", 128.0, seconds=35.0))
    script = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from bench import measurement\n"
        "one = measurement.of_file(r'%s')\n"
        "print(one['loudness']['integrated_lufs'])\n" % (SOURCE, path)
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            stdin=subprocess.DEVNULL)
    assert result.returncode == 0, result.stderr[-600:]
    assert float(result.stdout.strip()) < 0.0


def test_the_measurement_still_works_in_this_process(tmp_path):
    path = sig.write(tmp_path / "one.wav", music.build("dense", 128.0, seconds=35.0))
    one = measurement.of_file(path)
    assert one["loudness"]["integrated_lufs"] < 0.0
