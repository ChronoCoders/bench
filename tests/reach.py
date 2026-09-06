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

A complete run leaves what it saw in a record beside these tests, so the check can be
made again without running everything again. That is what makes a mutation of the
registry affordable: mutate.py has to run the whole suite for any break it cannot aim a
single test file at, and three registry mutants at a whole suite each were half an hour
of every sweep.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = str((ROOT / "src" / "bench").resolve())
RECORD = Path(__file__).resolve().parent / ".reached.json"

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


def fingerprint() -> str:
    """What the record describes: every source file, every test and every tool, because
    all of them decide which files a test runs code in.

    `methods.py` is the single exclusion and it is the whole point. The registry is data
    that nothing running reads, so changing it cannot move one touch, which is what lets
    a record taken before a registry mutation still describe the tree after it. A test
    holds that claim, because the day something under src imports the registry this
    exclusion becomes a way for a stale record to answer for a tree it does not
    describe.
    """
    parts = []
    for folder, pattern in ((ROOT / "src", "**/*.py"), (ROOT / "tests", "**/*.py"),
                            (ROOT / "tools", "*.py")):
        for one in sorted(folder.glob(pattern)):
            if one.name == "methods.py":
                continue
            parts.append(f"{one.relative_to(ROOT).as_posix()}:"
                         f"{hashlib.sha256(one.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def recorded() -> dict[str, set[str]]:
    """What a previous complete run saw, if it saw the tree that is here now."""
    try:
        held = json.loads(RECORD.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if held.get("fingerprint") != fingerprint():
        return {}
    return {name: set(files) for name, files in held.get("touched", {}).items()}


def available() -> dict[str, set[str]]:
    """This session's touches, and a matching record for the tests it did not run."""
    got = {name: set(files) for name, files in BY_TEST.items()}
    for name, files in recorded().items():
        got.setdefault(name, set()).update(files)
    return got


def save_if_complete(wanted: set[str]) -> bool:
    """Only a run that saw everything writes the record.

    A partial run is a true observation and still the wrong thing to keep, because
    writing it would replace a complete record with a smaller one and leave the next
    reader with a gap it cannot tell from a test that touches nothing. It matters most
    under mutation, where every run but the baseline is a single test file: one of those
    overwriting the baseline's record would put the whole suite back into the sweep.
    """
    if not wanted or not wanted <= set(BY_TEST):
        return False
    RECORD.write_text(json.dumps(
        {"fingerprint": fingerprint(),
         "touched": {name: sorted(files) for name, files in sorted(BY_TEST.items())}},
        indent=1), encoding="utf-8")
    return True
