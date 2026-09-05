from __future__ import annotations

import re
import urllib.request
from pathlib import Path

import pytest

import music
import signals as sig
from bench import folder, measurement, page, typeface

import serve

FACE_URL = re.compile(r"url\('([^']+)'\)")


def test_every_face_the_page_names_is_on_disk():
    referenced = FACE_URL.findall(typeface.css())
    assert referenced, "the page names no faces at all"
    for url in referenced:
        assert url.startswith(typeface.FONT_URL + "/"), f"{url} is not served from this machine"
        assert (typeface.FONT_DIR / url.rsplit("/", 1)[-1]).is_file(), f"{url} is not on disk"
    assert typeface.missing() == []


def test_the_face_check_can_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(typeface, "FONT_DIR", tmp_path)
    assert typeface.missing() == typeface.files(), (
        "pointed at an empty folder the check still reported every face present"
    )


def test_both_families_are_named():
    css = typeface.css()
    assert "'Chakra Petch'" in css
    assert "'JetBrains Mono'" in css
    assert "font-display:block" in css


def test_numbers_are_set_in_the_mono_face():
    assert "--mono: 'JetBrains Mono'" in page.STYLE
    assert "td { text-align: right; font-family: var(--mono)" in page.STYLE
    assert "tabular-nums" in page.STYLE


def test_the_key_appears_only_when_a_target_graded_the_table(tmp_path):
    out = tmp_path / "album"
    out.mkdir()
    base = music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004))
    for i, scale in enumerate((1.0, 0.5)):
        sig.write(out / f"{i}.wav", base * scale)
    from bench import compare
    targets = Path(__file__).resolve().parent.parent / "targets"
    graded = page.folder_view(folder.against(
        folder.measure(out), compare.load(targets / "guaracha-club.json")))
    plain = page.folder_view(folder.measure(out))
    assert "class=\"key\"" in graded
    assert "class=\"key\"" not in plain


@pytest.fixture
def running(tmp_path, serving):
    sig.write(tmp_path / "one.wav",
              music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004)))
    return serving


def test_the_server_hands_over_a_real_font(running):
    name = typeface.files()[0]
    with urllib.request.urlopen(f"{running}{typeface.FONT_URL}/{name}", timeout=30) as reply:
        body = reply.read()
        assert reply.status == 200
        assert reply.headers["Content-Type"] == "font/woff2"
    assert body[:4] == b"wOF2", "what came back is not a woff2 file"
    assert body == (typeface.FONT_DIR / name).read_bytes()


def test_the_server_serves_nothing_outside_the_font_list(running):
    for name in ("../../pyproject.toml", "..%2f..%2fpyproject.toml", "nothing.woff2"):
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"{running}{typeface.FONT_URL}/{name}", timeout=30)
        assert refused.value.code == 404


def test_the_served_page_names_the_faces(running):
    with urllib.request.urlopen(f"{running}/", timeout=30) as reply:
        html = reply.read().decode("utf-8")
    assert reply.status == 200
    for url in FACE_URL.findall(html):
        with urllib.request.urlopen(f"{running}{url}", timeout=30) as face:
            assert face.status == 200


def one_second(path):
    return sig.write(path, music.build("dense", 128.0, seconds=1.0))


def test_a_file_in_a_folder_is_offered_through_the_folder_and_not_twice(tmp_path):
    inside = tmp_path / "album"
    inside.mkdir()
    one_second(inside / "track.wav")
    one_second(tmp_path / "loose.wav")
    found = serve.choices(tmp_path)
    assert "album/" in found
    assert "loose.wav" in found
    assert not any("track.wav" in name for name in found), (
        "a file inside a folder was offered on its own as well as through its folder"
    )


def test_the_same_file_at_the_top_is_offered(tmp_path):
    one_second(tmp_path / "track.wav")
    found = serve.choices(tmp_path)
    assert "track.wav" in found, (
        "the check would pass by never listing anything, so it proves nothing"
    )


def test_a_folder_with_no_audio_is_not_offered(tmp_path):
    (tmp_path / "artwork").mkdir()
    (tmp_path / "artwork" / "cover.jpg").write_bytes(b"not audio")
    one_second(tmp_path / "loose.wav")
    assert "artwork/" not in serve.choices(tmp_path)


def test_the_chooser_does_not_walk_the_whole_disk(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    one_second(deep / "buried.wav")
    one_second(tmp_path / "top.wav")
    found = serve.choices(tmp_path)
    assert "top.wav" in found
    beyond = str(Path("a") / "b" / "c")
    assert not any("buried" in name or name.startswith(beyond) for name in found), (
        "the chooser reached past its depth limit and would walk a whole home folder"
    )
