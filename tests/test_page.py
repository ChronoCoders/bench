from __future__ import annotations

import re
from pathlib import Path

import music
import signals as sig
from bench import compare, fields, folder, measurement, page, report

CEILING = {"max": -1.0, "declared_by": "test"}


def on_the_line_result():
    one = {"loudness": {"true_peak_dbtp": -1.0, "uncertainty": {"true_peak_dbtp": 0.05}},
           "spectral": {"band_set": "bench-v1"}}
    target = {"name": "test", "band_set": "bench-v1", "evidence": {"n": 2, "all_sources_lossy": True},
              "fields": {}, "limits": {"loudness.true_peak_dbtp": CEILING}}
    return compare.against(one, target)


def test_a_value_on_the_line_is_not_shown_as_a_pass():
    html = page.comparison_view(on_the_line_result())
    assert "on the line" in html
    assert "not a pass" in html
    assert ">inside<" not in html


def test_the_line_verdict_is_marked_apart_from_inside():
    html = page.comparison_view(on_the_line_result())
    marked = re.findall(r'class="(inside|line|out)">([^<]+)<', html)
    assert marked == [("line", "on the line")]


def test_a_field_with_no_target_shows_its_value_and_its_reason():
    one = {"loudness": {"true_peak_dbtp": -1.2, "uncertainty": {"true_peak_dbtp": 0.05}},
           "spectral": {"band_set": "bench-v1"}}
    target = {"name": "t", "band_set": "bench-v1", "evidence": {"n": 2}, "fields": {},
              "withheld": {"loudness.true_peak_dbtp": "the references are lossy"}}
    html = page.comparison_view(compare.against(one, target))
    assert "The references are lossy" in html, "the reason should start a sentence"
    assert "-1.2" in html


def test_the_page_says_how_many_references_the_target_rests_on():
    html = page.comparison_view(on_the_line_result())
    assert "2 references" in html
    assert "all lossy" in html


def test_an_absent_value_never_renders_as_a_number():
    assert page.number(None, 2) == '<span class="blank">.</span>'
    assert page.number(0.0, 2) == "0.00"
    assert page.number(None, 0) != page.number(0.0, 0)


def test_a_missing_number_is_a_gap_not_a_zero(tmp_path):
    out = tmp_path / "short"
    out.mkdir()
    sig.write(out / "a.wav", music.build("dense", 128.0, seconds=5.0))
    html = page.folder_view(folder.measure(out))
    assert "None" not in html
    assert "nan" not in html
    assert 'class="blank">.</span>' in html


def test_the_folder_table_carries_a_spread_row_and_a_count(tmp_path):
    out = tmp_path / "album"
    out.mkdir()
    base = music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004))
    for i, scale in enumerate((1.0, 0.5)):
        sig.write(out / f"{i}.wav", base * scale)
    html = page.folder_view(folder.measure(out))
    assert "<td>Spread</td>" in html
    assert "<td>Files</td>" in html
    assert "has no spread" in html


def test_every_shown_field_has_a_name_that_is_not_its_path(tmp_path):
    x = music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    html = page.file_view(one, None, None)
    assert "loudness.integrated_lufs" not in html
    assert "Integrated loudness" in html
    for field in fields.FIELDS:
        assert field.path not in html, f"{field.path} leaked into the page as a raw path"


def test_the_page_asks_for_nothing_from_outside(tmp_path):
    x = music.limit(music.build("dense", 128.0, seconds=35.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    html = page.document("t", page.file_view(one, None, None))
    for forbidden in ("http://", "https://", "//fonts", "<script", "@import"):
        assert forbidden not in html, f"the page reaches outside itself with {forbidden}"


def test_the_document_is_one_html_page():
    html = page.document("t", "<p>x</p>")
    assert html.startswith("<!doctype html>")
    assert html.count("<html") == 1 and html.count("</html>") == 1
    assert "<title>t</title>" in html


def test_the_octave_alternatives_are_shown_not_only_computed(tmp_path):
    x = music.limit(music.build("kick_hat_snare", 88.0, seconds=60.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    html = page.file_view(one, None, None)
    assert "Rates the signal also supports" in html
    for alternative in one["tempo"]["alternatives"]:
        assert f"{alternative['bpm']:.2f}" in html, (
            f"{alternative['bpm']} was computed and never shown"
        )
    assert html.count("<span class=\"tag\">reported</span>") == 1


def test_the_alternatives_check_can_fail(tmp_path):
    x = music.limit(music.build("kick_hat_snare", 88.0, seconds=60.0, jitter=0.004))
    one = measurement.of_file(sig.write(tmp_path / "one.wav", x))
    one["tempo"] = dict(one["tempo"], alternatives=[])
    assert page.octaves(one) == "", (
        "the block would claim to show alternatives when there are none"
    )


# The before and after views. Neither decides anything, so what these check is that
# every placed field survives the trip and that the colour rule is the same one the
# folder table uses: only what is outside is marked.

def mastered_result(after_verdicts, before_verdicts=(compare.BELOW, compare.INSIDE)):
    """A result shaped like master.run's, with the verdicts named rather than measured."""
    rows_before = [
        {"field": "loudness.integrated_lufs", "value": -14.8, "uncertainty": 0.005,
         "bound": {"low": -12.0, "high": -6.0}, "deviation": -2.8},
        {"field": "loudness.true_peak_dbtp", "value": -4.5, "uncertainty": 0.05,
         "bound": {"max": -1.0}, "deviation": 0.0},
    ]
    rows_before = [dict(row, verdict=verdict)
                   for row, verdict in zip(rows_before, before_verdicts)]
    rows_after = [dict(row, verdict=verdict) for row, verdict in zip(rows_before, after_verdicts)]
    rows_after[0]["value"], rows_after[1]["value"] = -10.5, -1.2
    graded = {"target": {"name": "test", "band_set": "bench-v1"},
              "rows": rows_after, "counts": {}, "all_inside": True}
    return {
        "method": "master/gain-cut-and-searched-limiter",
        "input": r"C:\in\one.wav", "output": r"C:\out\one.wav",
        "plan": {"method": "master/gain-cut-and-searched-limiter", "not_applied": [
                     {"correction": "low cut", "why": "there is nothing there to remove"}],
                 "steps": [{"correction": "gain", "db": 4.3, "bound_by": "the target loudness",
                            "from": "toward -12.0, the bottom of the range, plus 0.06"}]},
        "limiter_search": None,
        "before": {"measurement": {}, "comparison": {"target": {"name": "test"},
                                                     "rows": rows_before, "counts": {},
                                                     "all_inside": False}},
        "after": {"measurement": {}, "comparison": graded},
        "prediction": {"checked": True, "against": "the second instrument", "held": True,
                       "fields": {"integrated_lufs": {"predicted": -10.5, "measured": -10.5,
                                                      "gap": 0.0, "uncertainty": 0.005,
                                                      "held": True}}},
        "reached": {"arrived": True, "fields": {
            "loudness.integrated_lufs": {"value": -10.5, "uncertainty": 0.005,
                                         "verdict": compare.INSIDE, "deviation": 0.0},
            "loudness.true_peak_dbtp": {"value": -1.2, "uncertainty": 0.05,
                                        "verdict": compare.INSIDE, "deviation": 0.0}}},
    }


def marks(html):
    return re.findall(r'class="[^"]*?\b(line|out)\b[^"]*?"', html)


def test_a_run_that_was_inside_all_along_carries_no_colour():
    html = page.master_view(mastered_result([compare.INSIDE, compare.INSIDE],
                                            [compare.INSIDE, compare.INSIDE]))
    assert marks(html) == [], "nothing was outside at either end, so nothing is marked"


def test_only_the_side_that_was_outside_is_marked():
    """One field below before and inside after. The source cell carries the mark and
    nothing on the master side does."""
    assert marks(page.master_view(mastered_result([compare.INSIDE, compare.INSIDE]))) == ["out"]


def test_it_marks_a_field_that_landed_outside():
    """The control on the one above. A view that never marks the master side is not a
    view that marks what is outside."""
    marked = marks(page.master_view(mastered_result([compare.BELOW, compare.ON_THE_LINE])))
    assert marked.count("out") == 3 and marked.count("line") == 2, marked


def test_how_far_off_is_a_number_and_not_only_a_colour():
    """Inside leaves the cell empty, on the line reads zero, and outside reads how far.
    Somebody who cannot tell the two colours apart can still tell those three apart."""
    inside = page.master_view(mastered_result([compare.INSIDE, compare.INSIDE],
                                              [compare.INSIDE, compare.INSIDE]))
    assert 'class="n dev "></td>' in inside

    on_line = mastered_result([compare.ON_THE_LINE, compare.INSIDE],
                              [compare.INSIDE, compare.INSIDE])
    on_line["after"]["comparison"]["rows"][0]["deviation"] = 0.0
    assert 'class="n dev line">0.0<' in page.master_view(on_line)

    out = page.master_view(mastered_result([compare.BELOW, compare.INSIDE],
                                           [compare.INSIDE, compare.INSIDE]))
    assert 'class="n dev out">-2.8' in out


def test_the_view_says_whether_it_arrived():
    result = mastered_result([compare.INSIDE, compare.INSIDE])
    assert "It arrived." in page.master_view(result)
    result["reached"]["arrived"] = False
    assert "It did not arrive." in page.master_view(result)


def test_the_view_names_what_was_refused_and_why():
    html = page.master_view(mastered_result([compare.INSIDE, compare.INSIDE]))
    assert "not applied" in html
    assert "There is nothing there to remove" in html, "the reason should start a sentence"


def test_the_text_report_places_every_field_the_page_does():
    result = mastered_result([compare.INSIDE, compare.INSIDE])
    text = report.master_table(result)
    for field in ("Integrated loudness", "True peak"):
        assert field in text
    assert "Arrived: yes" in text
    assert "-14.8" in text and "-10.5" in text


def test_the_text_report_says_when_it_did_not_arrive():
    result = mastered_result([compare.BELOW, compare.INSIDE])
    result["reached"]["arrived"] = False
    result["reached"]["fields"]["loudness.integrated_lufs"]["deviation"] = -1.5
    text = report.master_table(result)
    assert "Arrived: no" in text
    assert "off by -1.5" in text


# Mastering from the page. The button is a second submit in the same form, so it
# carries whatever the two selects are showing, and it posts rather than gets because
# it writes files.

def form():
    return page.controls(["a.wav", "album/"], ["boom-bap"], "a.wav", "boom-bap")


def test_the_bar_holds_nothing_the_picker_cannot_move():
    """A field the server filled in stays on the last selection that was submitted.
    Beside a picker that has already moved on, it reads as the answer for the new one.
    Everything in the bar is a control, so there is nothing to go stale."""
    html = form()
    assert "<span" not in html


def test_the_page_offers_mastering_beside_measuring():
    html = form()
    assert ">MEASURE<" in html and ">MASTER<" in html


def test_mastering_is_a_post_and_measuring_is_not():
    html = form()
    assert 'formmethod="post"' in html, "mastering writes files, so it must not be a get"
    assert html.count('formmethod="post"') == 1, "only the mastering button posts"
    assert 'method="get"' in html


def test_both_buttons_carry_the_same_selection():
    """One form, two submits. A separate form would need its own copy of the two
    selects, and two lists of the same thing go out of step."""
    html = form()
    assert html.count("<form") == 1
    assert html.count("<select") == 2


def working(**over):
    job = {"what": "album/", "target": "boom-bap", "running": True, "finished": 2,
           "total": 9, "at": "Ledger.wav", "done": [], "failed": [], "failure": None,
           "refused": None, "out_dir": r"C:\music\album (Mastered)"}
    job.update(over)
    return job


def test_a_run_in_progress_says_where_it_is():
    html = page.mastering_view(working())
    assert "2 of 9 finished" in html
    assert "Ledger.wav" in html
    assert "album (Mastered)" in html


def test_a_run_in_progress_reloads_itself_without_a_script():
    html = page.document("Mastering", page.mastering_view(working()),
                         again_in=page.WORKING_AGAIN_IN_S)
    assert f'content="{page.WORKING_AGAIN_IN_S}"' in html
    for forbidden in ("http://", "https://", "<script", "@import"):
        assert forbidden not in html


def test_a_finished_run_does_not_reload_itself():
    html = page.document("Mastered", page.mastering_view(working(running=False)))
    assert "http-equiv" not in html, "a finished page that reloads never stops working"


def test_it_refuses_without_a_target_and_says_why():
    html = page.mastering_view(working(running=False, refused="no target is chosen"))
    assert "Not started" in html
    assert "No target is chosen" in html, "the reason should start a sentence"


def test_a_finished_run_counts_what_arrived():
    done = [mastered_result([compare.INSIDE, compare.INSIDE]),
            mastered_result([compare.BELOW, compare.INSIDE])]
    done[1]["reached"]["arrived"] = False
    html = page.mastering_view(working(running=False, done=done))
    assert "2 files written, 1 of them inside the target" in html
    assert html.count("<h3>PLAN</h3>") == 2, "one block per file"
    assert html.count("<h3>SPECTRAL BALANCE</h3>") == 2


# A folder run is one block per file. Nine of them open is a page that has to be
# scrolled past to be read, so each arrives closed with enough on the row to decide.

def run_of(n, arrived=()):
    done = []
    for i in range(n):
        one = mastered_result([compare.INSIDE, compare.INSIDE])
        one["input"] = f"C:/in/track{i}.wav"
        if i in arrived:
            one["reached"]["arrived"] = False
        done.append(one)
    return page.mastering_view(working(running=False, done=done, total=n))


def test_a_folder_run_comes_back_closed():
    html = run_of(9)
    assert html.count("<details class=\"one\">") == 9
    assert "<details class=\"one\" open" not in html and "<details open" not in html


def test_the_whole_run_is_on_the_page():
    """Closed is not left out. Every block is there to open, and nothing sends the
    reader to a second page for the rest of it."""
    html = run_of(9)
    assert html.count("<h3>PLAN</h3>") == 9
    assert html.count("<h3>SPECTRAL BALANCE</h3>") == 9
    for i in range(9):
        assert f"track{i}.wav" in html


def test_a_closed_row_says_the_name_and_where_it_landed():
    html = run_of(1 + 1)
    row = html[html.index("<summary>"):html.index("</summary>")]
    assert "track0.wav" in row
    assert "ARRIVED" in row
    assert ">-10.5</b> LUFS" in row
    assert ">-1.2</b> dBTP" in row


def test_the_row_reads_the_output_rather_than_naming_the_numbers_again():
    """It shows what reached measured. A row that carried its own copy would go on
    saying the old number after the measurement changed."""
    done = [mastered_result([compare.INSIDE, compare.INSIDE])]
    done[0]["reached"]["fields"]["loudness.integrated_lufs"]["value"] = -8.4
    html = page.mastering_view(working(running=False, done=done, total=2))
    assert ">-8.4</b> LUFS" in html[:html.index("</summary>")]


def test_only_a_row_that_did_not_arrive_is_coloured():
    html = run_of(2, arrived=(1,))
    rows = re.findall(r"<summary>.*?</summary>", html, re.S)
    assert len(rows) == 2
    assert "ARRIVED" in rows[0] and "lands out" not in rows[0]
    assert "NOT ARRIVED" in rows[1] and "lands out" in rows[1]


def test_a_single_file_run_is_not_collapsed():
    """There is nothing to scroll past, and a lone closed row hides the whole result."""
    html = page.mastering_view(working(
        running=False, total=1, done=[mastered_result([compare.INSIDE, compare.INSIDE])]))
    assert "<details" not in html
    assert "<h3>PLAN</h3>" in html


def test_a_file_it_would_not_master_is_named_with_the_reason():
    html = page.mastering_view(working(
        running=False, done=[mastered_result([compare.INSIDE, compare.INSIDE])],
        failed=[{"name": "Skip.wav", "why": "that file already exists"}]))
    assert "Not mastered" in html
    assert "Skip.wav" in html and "That file already exists" in html


def test_the_instrument_is_named_once():
    """Two places print this phrase and one of them used to add the noun back, which
    read as the second instrument instrument."""
    for named in ("the second instrument", "the primary instrument"):
        result = mastered_result([compare.INSIDE, compare.INSIDE])
        result["prediction"]["against"] = named
        html, text = page.master_view(result), report.master_table(result)
        assert "instrument instrument" not in html
        assert "instrument instrument" not in text
        assert named in html and named in text


# One frame, every view. Measure and master should not look like two different
# programs, and that is countable rather than a matter of taste.

def panels(html):
    return re.findall(r'<div class="card[^"]*"><div class="ch"><h3>([^<]*)</h3>', html)


def three_views(tmp_path):
    from bench import folder
    out = tmp_path / "album"
    out.mkdir()
    base = music.limit(music.build("dense", 128.0, seconds=6.0))
    for i, scale in enumerate((1.0, 0.5)):
        sig.write(out / f"{i}.wav", base * scale)
    targets = Path(__file__).resolve().parent.parent / "targets"
    target = compare.load(targets / "boom-bap.json")
    one = measurement.of_file(out / "0.wav")
    return {
        "folder": page.folder_view(folder.against(folder.measure(out), target)),
        "file": page.file_view(one, compare.against(one, target), target),
        "master": page.master_view(mastered_result([compare.INSIDE, compare.INSIDE])),
    }


def test_every_panel_on_every_view_is_the_same_card(tmp_path):
    """Nothing sits outside the frame on any of them. The one card with no header is
    the pair of waveforms, where the rows carry their own labels."""
    for name, html in three_views(tmp_path).items():
        assert html.startswith(('<div class="card', '<div class="mv"><div class="card')), (
            f"{name} opens outside a card")
        assert panels(html), f"{name} has no panels at all"
        assert html.count('<div class="card') - html.count('<div class="ch">') <= 1, name


def test_no_view_keeps_a_heading_of_its_own(tmp_path):
    """The control on the one above. Two of these used to open with their own title
    outside any card, which is what made them look like a different program."""
    for name, html in three_views(tmp_path).items():
        assert "<h1" not in html, name
        assert 'class="head"' not in html, name
        assert "<h1" not in html, f"{name} keeps a heading of its own"

def test_the_dropdown_list_is_drawn_from_the_palette():
    """The list a select drops down is the browser's, not this page's. Left alone it
    comes back with a bright blue selected row that appears nowhere else here. This
    checks the declarations exist and names the tokens; it cannot check appearance, and
    the picture for that has to be taken with the list open."""
    css = page.STYLE
    assert "color-scheme: dark" in css
    assert "option { background: var(--panel); color: var(--bone); }" in css
    assert "option:checked, option:hover" in css
    assert "var(--panel-hi)" in css.split("option:checked, option:hover {")[1].split("}")[0]


def test_the_focus_ring_is_the_accent_in_the_tokens():
    ring = page.STYLE.split("select:focus,")[1].split("}")[0]
    assert "var(--acc)" in ring
    assert "outline" in ring and "border-color" in ring


def test_no_colour_on_the_page_is_written_out_by_hand():
    """The control on both of those. A hex that is not in the reference palette is a
    colour somebody typed rather than a token, which is how a page grows a second
    palette."""
    import re
    known = {m.lower() for m in re.findall(r"#[0-9A-Fa-f]{6}", page.DESIGN)}
    known |= {"#2a2e36", "#6a7280", "#0a0c10"}
    theirs = {m.lower() for m in re.findall(r"#[0-9A-Fa-f]{6}", page.STYLE)}
    assert theirs <= known, sorted(theirs - known)
