from __future__ import annotations

import re
from pathlib import Path

import pytest

import reach
from bench import methods

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "bench"
TESTS = ROOT / "tests"

METHOD_CONST = re.compile(r'^([A-Z][A-Z0-9_]*)\s*=\s*"([^"]+)"', re.M)
TEST_DEF = re.compile(r"^def (test_\w+)", re.M)


def declared_in_src() -> set[str]:
    found = set()
    for f in SRC.rglob("*.py"):
        for name, value in METHOD_CONST.findall(f.read_text(encoding="utf-8")):
            if "METHOD" in name:
                found.add(value)
    return found


def defined_in_tests() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for f in TESTS.rglob("test_*.py"):
        for name in TEST_DEF.findall(f.read_text(encoding="utf-8")):
            found.setdefault(name, set()).add(f.name)
    return found


def test_every_method_id_used_by_the_engine_is_registered():
    missing = declared_in_src() - set(methods.METHODS)
    assert not missing, f"method ids used but not documented: {sorted(missing)}"


def test_every_registered_method_is_used_by_the_engine():
    orphans = set(methods.METHODS) - declared_in_src()
    assert not orphans, f"documented methods nothing computes: {sorted(orphans)}"


def named_controls() -> set[str]:
    return {c for m in methods.METHODS.values() for c in m.controls}


def test_every_control_named_in_the_registry_exists():
    missing = named_controls() - set(defined_in_tests())
    assert not missing, f"controls named but not written: {sorted(missing)}"


def test_every_control_written_where_the_registry_draws_from_is_registered():
    """The other direction. A test file the registry already takes controls from is a
    file whose tests stand behind a number, so one written there that nothing names is a
    control the registry does not know it has.

    Which files those are is read off the registry rather than listed here. Files for
    layers with no method id, the page and the server and the comparison, stay outside
    by construction, and naming one control in a file brings the whole file in.
    """
    where = defined_in_tests()
    named = named_controls()
    drawn = {f for c in named for f in where.get(c, ())}
    loose = sorted(n for n, files in where.items() if n not in named and files & drawn)
    assert not loose, f"controls written but not registered: {loose}"


def test_every_name_marked_inline_is_a_control_of_that_method():
    for m in methods.METHODS.values():
        stray = sorted(set(m.inline) - set(m.controls))
        assert not stray, f"{m.id} marks names that are not its controls: {stray}"


def test_every_control_reaches_the_method_it_stands_behind():
    """A name is not a control. This is what ran.

    Both directions of the inline marker are checked here, and that is the point of it.
    A control marked as running none of the method's files, which then runs one, is
    marked wrong, so the marker cannot be used to take a control out of the check.

    What it cannot see: a test emptied to `pass` that still asks for a fixture doing the
    work reads as reached, because the fixture ran and this cannot tell a test that read
    its result from one that ignored it. An empty test with no fixtures is caught.
    """
    ran = reach.BY_TEST
    absent = sorted(named_controls() - set(ran))
    if absent:
        pytest.skip(f"{len(absent)} controls did not run in this session, "
                    f"starting with {absent[0]}. This holds over a whole run.")
    wrong = []
    for m in methods.METHODS.values():
        for c in m.controls:
            hit = sorted(ran[c] & set(m.files))
            if c in m.inline:
                if hit:
                    wrong.append(f"{c} is marked as running none of {m.id}, and it ran {hit}")
            elif not hit:
                wrong.append(f"{c} stands behind {m.id} and ran none of {list(m.files)}. "
                             f"It ran {sorted(ran[c]) or 'nothing'}")
    assert not wrong, "\n" + "\n".join(wrong)


def test_every_method_names_at_least_one_failure_mode_and_a_cross_check():
    for m in methods.METHODS.values():
        assert m.failure_modes, f"{m.id} claims no way to be wrong"
        assert m.cross_check.strip(), f"{m.id} has no cross check"
        assert m.controls, f"{m.id} has no controls"
        assert m.files, f"{m.id} names no file it runs in"
        for name in m.files:
            assert list(SRC.rglob(name)), f"{m.id} runs in {name}, which is not in src"


def test_unregistered_id_raises():
    with pytest.raises(KeyError):
        methods.get("no/such-method")
