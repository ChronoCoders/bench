"""Which files under src/bench each test actually ran code in.

The registry names the controls standing behind every number. Until now the only thing
checking that was a search for a function of the same name, so a named test emptied out
still passed. This records what ran instead.

A test that reads a structure a shared fixture built does exercise the method: the
fixture is part of the test. So fixture setup is recorded against the fixture, and each
test is credited with its own calls plus those of every fixture it asked for. Without
that, every test using a module scoped fixture reads as touching nothing, which is the
instrument talking rather than the registry.

The limit is in that same crediting. A test emptied to `pass` is caught, because an
empty body calls nothing. A test emptied to `pass` while still asking for a fixture that
does the work is not: the fixture ran, and this cannot tell a test that read its result
from one that ignored it.

sys.setprofile fires on call and return, not per line. Measured over 43 tests it cost
16.200 s against 16.212 s without, which is inside the run to run spread of the machine.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

SRC = str((Path(__file__).resolve().parent.parent / "src" / "bench").resolve())

BY_TEST: dict[str, set[str]] = {}
_by_fixture: dict[str, set[str]] = {}
_stack: list[set[str]] = []


def _probe(frame, event, arg):
    if event == "call" and _stack:
        name = frame.f_code.co_filename
        if name.startswith(SRC):
            _stack[-1].add(name)


def start() -> None:
    """Fixtures nest, so this is a stack. Turning the profiler off at the end of an
    inner fixture would stop recording for the outer one still running."""
    _stack.append(set())
    if len(_stack) == 1:
        threading.setprofile(_probe)
        sys.setprofile(_probe)


def stop() -> set[str]:
    got = _stack.pop()
    if _stack:
        _stack[-1] |= got
    else:
        sys.setprofile(None)
        threading.setprofile(None)
    return {Path(f).name for f in got}


def credit_fixture(name: str, files: set[str]) -> None:
    _by_fixture.setdefault(name, set()).update(files)


def credit_test(name: str, files: set[str], fixtures) -> None:
    for one in fixtures:
        files |= _by_fixture.get(one, set())
    BY_TEST.setdefault(name, set()).update(files)
