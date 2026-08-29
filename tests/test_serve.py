"""Mastering from the page, over the wire.

The button posts because it writes files. What these hold it to is that a get never
writes anything, that a reload of the result does not run it again, and that what the
page shows afterwards is what is on disk.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

import music
import serve
import signals as sig
from bench import compare, master, measurement

SHORT_S = 4.0
WAIT_S = 180.0
TARGET = "_serving-test"
TARGETS = Path(__file__).resolve().parent.parent / "targets"


@pytest.fixture
def album(tmp_path):
    """Two short tracks in a folder, and a target they are outside on loudness."""
    where = tmp_path / "album"
    where.mkdir()
    x = music.limit(music.build("with_bass", 120.0, seconds=SHORT_S), drive=4.0)
    for name, level in (("one.wav", 0.5), ("two.wav", 0.35)):
        sig.write(where / name, x * level)

    measured = measurement.of_file(where / "one.wav")
    here = compare.dig(measured, master.LOUDNESS_FIELD)
    written = TARGETS / f"{TARGET}.json"
    written.write_text(json.dumps({
        "name": "serving test", "band_set": measured["spectral"]["band_set"],
        "evidence": {"n": 1},
        "fields": {master.LOUDNESS_FIELD: {"low": round(here + 1.0, 3),
                                           "high": round(here + 7.0, 3)}},
        "limits": {master.PEAK_FIELD: {"max": -1.0, "declared_by": "test"}},
    }), encoding="utf-8")
    yield where
    written.unlink()


def get(url):
    with urllib.request.urlopen(url, timeout=30) as reply:
        return reply.status, reply.read().decode("utf-8")


def headers(url):
    with urllib.request.urlopen(url, timeout=30) as reply:
        return dict(reply.headers)


def post(base, what, target):
    body = urllib.parse.urlencode({"what": what, "target": target}).encode("utf-8")
    with urllib.request.urlopen(f"{base}{serve.page.MASTER_URL}", body, timeout=30) as reply:
        return reply.status, reply.geturl(), reply.read().decode("utf-8")


def until_finished(base, url):
    """The page reloads itself while it works, so this does what a browser does."""
    ran_out = time.monotonic() + WAIT_S
    while time.monotonic() < ran_out:
        status, html = get(url)
        if "http-equiv" not in html:
            return status, html
        time.sleep(1.0)
    raise AssertionError(f"still working after {WAIT_S} seconds")


def test_no_page_is_held_by_the_browser(album, serving):
    """Every page here is built from files that change under it, and a run in progress
    asks for itself again every few seconds. A held copy is showing yesterday."""
    _, where, _ = post(serving, "album/", serve.NONE)
    for url in (f"{serving}/", f"{serving}/?what=album/&target={TARGET}", where):
        sent = headers(url)
        assert sent.get("Cache-Control") == serve.NO_CACHE, url
        assert sent.get("Pragma") == "no-cache", url


def test_the_replies_say_http_1_1(serving):
    """Cache-Control arrived with 1.1. A cache reading a 1.0 reply may ignore it and
    guess a freshness lifetime, which is a stale page nobody asked for."""
    with urllib.request.urlopen(f"{serving}/", timeout=30) as reply:
        assert reply.version == 11, reply.version


def test_the_faces_are_still_allowed_to_be_held(serving):
    """The control on the one above. A woff2 that is never cached is fetched on every
    page load, and those are the only bytes here that do not change."""
    from bench import typeface
    name = typeface.files()[0]
    held = headers(f"{serving}{typeface.FONT_URL}/{name}").get("Cache-Control")
    assert held and held != serve.NO_CACHE, held


def test_mastering_is_offered_on_the_page(serving):
    status, html = get(f"{serving}/")
    assert status == 200
    assert ">Master<" in html and ">Measure<" in html


def test_the_page_says_where_mastering_would_write(album, serving):
    """Before the button is pressed, not after. A run that writes somewhere unexpected
    is one that had nowhere to say so."""
    _, html = get(f"{serving}/?what=album/&target={TARGET}")
    assert "album" + serve.MASTERED_SUFFIX in html


def test_it_says_nothing_when_there_is_nothing_chosen(serving):
    _, html = get(f"{serving}/")
    assert "Output" not in html


def test_a_get_never_masters_anything(album, serving, tmp_path):
    """The button posts. Nothing that writes a file can be reachable by following a
    link, which is what a get is."""
    get(f"{serving}/?what=album/&target={TARGET}")
    assert not (tmp_path / ("album" + serve.MASTERED_SUFFIX)).exists()


def test_it_masters_a_folder_and_shows_the_before_and_after(album, serving, tmp_path):
    status, where, _ = post(serving, "album/", TARGET)
    assert status == 200
    assert serve.page.MASTER_URL in where, "the post should send us to the run"

    status, html = until_finished(serving, where)
    assert status == 200
    assert "2 files written" in html
    assert html.count("<h2>Plan</h2>") == 2, "one block per file"

    out = tmp_path / ("album" + serve.MASTERED_SUFFIX)
    assert sorted(p.name for p in out.iterdir()) == ["one.wav", "two.wav"]
    for name in ("one.wav", "two.wav"):
        assert (album / name).exists(), "the source has to still be there"
        assert (out / name).read_bytes() != (album / name).read_bytes()


def test_running_it_twice_over_refuses_rather_than_replacing(album, serving, tmp_path):
    _, where, _ = post(serving, "album/", TARGET)
    until_finished(serving, where)
    out = tmp_path / ("album" + serve.MASTERED_SUFFIX)
    was = {p.name: p.read_bytes() for p in out.iterdir()}

    _, again, _ = post(serving, "album/", TARGET)
    _, html = until_finished(serving, again)
    assert "Not mastered" in html and "already exists" in html
    assert {p.name: p.read_bytes() for p in out.iterdir()} == was


def test_it_refuses_without_a_target_and_writes_nothing(album, serving, tmp_path):
    _, where, _ = post(serving, "album/", serve.NONE)
    status, html = get(where)
    assert status == 200
    assert "Not started" in html and "no target is chosen" in html.lower()
    assert not (tmp_path / ("album" + serve.MASTERED_SUFFIX)).exists()


def test_it_refuses_a_path_outside_the_folder_being_served(album, serving):
    _, where, _ = post(serving, "../..", TARGET)
    _, html = get(where)
    assert "Not started" in html and "outside the folder being served" in html


def test_a_single_file_goes_into_a_folder_beside_it(album, serving):
    _, where, _ = post(serving, "album/one.wav", TARGET)
    _, html = until_finished(serving, where)
    assert "1 file written" in html
    out = album / serve.MASTERED_FOLDER
    assert (out / "one.wav").exists()
    assert out.parent == album, "the output folder sits beside the file, not around it"


def test_an_unknown_run_is_not_a_crash(serving):
    with pytest.raises(urllib.error.HTTPError) as refused:
        get(f"{serving}{serve.page.MASTER_URL}?job=nothing")
    assert refused.value.code == 404

def test_every_page_the_server_hands_over_is_framed(album, serving):
    """The complaint that started this: the page you land on has to be the new one.
    Every state, not only the one with a table in it."""
    _, refused, _ = post(serving, "album/", serve.NONE)
    for name, url in (("landing", f"{serving}/"),
                      ("outside the root", f"{serving}/?what=../..&target={TARGET}"),
                      ("no such run", f"{serving}{serve.page.MASTER_URL}?job=nothing"),
                      ("refused to start", refused)):
        try:
            _, html = get(url)
        except urllib.error.HTTPError as sent:
            html = sent.read().decode("utf-8")
        body = html[html.index("<main>"):]
        assert '<div class="card' in body, f"{name} has no card"
        assert "<h1" not in body and "class=\"head\"" not in body, name
        assert body.index('<div class="card') < body.index("</main>"), name
