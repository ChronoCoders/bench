from __future__ import annotations

import re
from pathlib import Path

import pytest

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


def written_test_names() -> set[str]:
    return {m for f in TESTS.rglob("test_*.py") for m in TEST_DEF.findall(f.read_text(encoding="utf-8"))}


def test_every_method_id_used_by_the_engine_is_registered():
    missing = declared_in_src() - set(methods.METHODS)
    assert not missing, f"method ids used but not documented: {sorted(missing)}"


def test_every_registered_method_is_used_by_the_engine():
    orphans = set(methods.METHODS) - declared_in_src()
    assert not orphans, f"documented methods nothing computes: {sorted(orphans)}"


def test_every_control_named_in_the_registry_exists():
    have = written_test_names()
    named = {c for m in methods.METHODS.values() for c in m.controls}
    assert not (named - have), f"controls named but not written: {sorted(named - have)}"


def test_every_method_names_at_least_one_failure_mode_and_a_cross_check():
    for m in methods.METHODS.values():
        assert m.failure_modes, f"{m.id} claims no way to be wrong"
        assert m.cross_check.strip(), f"{m.id} has no cross check"
        assert m.controls, f"{m.id} has no controls"


def test_unregistered_id_raises():
    with pytest.raises(KeyError):
        methods.get("no/such-method")
