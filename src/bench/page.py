"""HTML output. Formats what it is given and decides nothing.

No request leaves the page. Fonts are the ones already on the machine.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from bench import compare, fields, measurement, typeface

DESIGN = (Path(__file__).resolve().parent / "design.css").read_text(encoding="utf-8")

STYLE = DESIGN + """
/* Everything below is the folder table and the single file view, which keep the
   redesign they already had. They are held off the reference stylesheet by a class
   so that taking it wholesale could not change a table nobody asked to change. */
:root { --edge-hi: #2a2e36; --unclaimed: #6a7280;
        --mono: 'JetBrains Mono', ui-monospace, monospace; }
main { max-width: none; margin: 0; padding: 0; }
h1, h2, h3 { font-weight: 500; }
p { margin-bottom: 10px; color: var(--dim); max-width: 62em; }
.fld input { appearance: none; width: 100%; background: #0a0c10;
             border: 1px solid var(--line); border-radius: 6px; color: var(--bone);
             font: inherit; font-size: 13px; padding: 8px 11px; }
.fld input::placeholder { color: var(--dimmer); }
.fld.typed { flex: 0 1 190px; }
.fld .said { display: block; background: #0a0c10; border: 1px solid var(--line);
             border-radius: 6px; color: var(--text); font: inherit; font-size: 13px;
             padding: 8px 11px; white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis; max-width: 320px; }
/* The list a select drops down is drawn by the browser, not by this page, and left
   alone it comes back with a bright blue selected row and a white ground that appear
   nowhere else here. color-scheme tells the browser which end of the palette this page
   is at; the rest names the colours it should use. The inset shadow is how a checked
   row is coloured at all: background on option:checked is overridden by the system
   highlight, and a shadow spread across the row is not. */
:root { color-scheme: dark; }
option { background: var(--panel); color: var(--bone); }
option:checked, option:hover { box-shadow: 0 0 10px 100px var(--panel-hi) inset; }
select:focus, select:focus-visible, .fld input:focus, .fld input:focus-visible {
    outline: 2px solid var(--acc); outline-offset: 2px; border-color: var(--acc); }
:focus-visible { outline: 2px solid var(--acc); outline-offset: 2px; }
.wrap { overflow-x: auto; overflow-y: hidden; }
.card .wrap, .card .inset { padding: 6px 15px 13px; }
.card .inset p:last-child, .card .inset ul:last-child { margin-bottom: 0; }
.card .inset .key { margin: 2px 0 0; }
.card .plot { padding: 6px 15px 8px; }
.ch .where { margin-left: auto; font-family: var(--mono); font-size: 11px;
             color: var(--dimmer); text-align: right; }

table.rows { border-collapse: collapse; width: 100%; }
table.rows th, table.rows td { padding: 8px 0 8px 18px;
    border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
table.rows th:first-child, table.rows td:first-child { width: 1%; padding-left: 0;
    padding-right: 26px; }
table.rows th.grp, table.rows td.grp { padding-left: 34px; position: relative; }
table.rows th.grp::before, table.rows td.grp::before { content: ""; position: absolute;
    left: 16px; top: -1px; bottom: -1px; border-left: 1px solid var(--line-soft); }
table.rows th.grp::before { top: auto; height: 11px; bottom: 9px; }
table.rows th.quiet { color: var(--dimmer); }
table.rows th { text-align: right; font-size: 10px; font-weight: 600; color: var(--dim);
    text-transform: uppercase; letter-spacing: 0.09em; }
table.rows th:first-child, table.rows td:first-child { text-align: left; }
table.rows td { text-align: right; font-family: var(--mono); font-weight: 400;
    font-size: 12px; font-variant-numeric: tabular-nums; color: var(--bone); }
table.rows td.name { font-family: 'Chakra Petch', system-ui, sans-serif; font-size: 13px;
    color: var(--bone); padding-right: 28px; }
table.rows tbody tr:hover td { background: var(--panel-hi); }
table.rows tr.pause td { border-bottom: none; padding: 0; height: 22px; }
table.rows tr.pause td:hover { background: none; }
table.rows tr.spread td { border-top: 1px solid var(--edge-hi); border-bottom: none;
    color: var(--bone); }
table.rows tr.spread td:first-child, table.rows tr.over td:first-child { color: var(--dim);
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.09em; }
table.rows tr.over td { color: var(--dimmer); font-size: 11px; border-bottom: none;
    padding-top: 0; }
table.rows tr.spread td:hover, table.rows tr.over td:hover { background: none; }
.blank { color: var(--dimmer); }
.line { color: var(--cue); background: rgba(255, 176, 32, 0.12);
        box-shadow: inset 0 -2px 0 var(--cue); }
.out { color: var(--kill); }
.none { color: var(--unclaimed); }
.gap { color: var(--dimmer); }
.note { font-size: 12px; color: var(--dim); margin-top: 8px; }
.reasons { list-style: none; }
.reasons li { padding: 7px 0; border-bottom: 1px solid var(--line); color: var(--dim);
              font-size: 12px; max-width: 74em; }
.reasons li:last-child { border-bottom: none; padding-bottom: 0; }
.reasons b { color: var(--bone); font-weight: 600; }
.tag { display: inline-block; font-size: 9px; letter-spacing: 0.09em;
       text-transform: uppercase; color: var(--dimmer); border: 1px solid var(--line);
       border-radius: 2px; padding: 1px 5px; margin-left: 6px; vertical-align: 1px; }
.key { display: flex; gap: 16px; flex-wrap: wrap; font-size: 11px; color: var(--dim); }
.key .unmarked { color: var(--dimmer); }
.key span { display: inline-flex; align-items: center; gap: 5px; }
.key i { width: 9px; height: 9px; border-radius: 1px; display: inline-block;
         font-style: normal; }
.plot svg { display: block; width: 100%; height: auto; }
.hold, .hold b, .hold .bv, .hold .bd { color: var(--dimmer); }
/* A folder run is one block per file, and nine of them is a page nobody reads. Each
   arrives closed, saying the name, whether it arrived, and the two numbers the plan
   aims at. Details is the browser's own, so opening one needs no script. */
details.one { margin-bottom: 10px; }
details.one > summary { display: flex; align-items: baseline; gap: 16px;
    background: var(--panel); border: 1px solid var(--line); border-radius: 9px;
    padding: 12px 15px 11px; cursor: pointer; list-style: none; }
details.one > summary::-webkit-details-marker { display: none; }
details.one > summary::before { content: "+"; font-family: var(--mono); font-size: 12px;
    color: var(--dim); width: 8px; }
details.one[open] > summary::before { content: "-"; }
details.one[open] > summary { margin-bottom: 12px; }
details.one > summary:hover { border-color: var(--dimmer); }
details.one > summary h3 { font-size: 12px; letter-spacing: 0.02em; color: var(--bone);
    font-weight: 500; }
details.one .lands { font-size: 9px; letter-spacing: 0.2em; color: var(--dim); }
details.one .lands.out { color: var(--kill); }
details.one .figs { margin-left: auto; font-family: var(--mono); font-size: 11px;
    color: var(--dimmer); white-space: nowrap; }
details.one .figs b { font-weight: 400; color: var(--bone); }
details.one .figs span { margin-left: 16px; }
"""

VERDICT_CLASS = {
    compare.INSIDE: "",
    compare.ON_THE_LINE: "line",
    compare.ABOVE: "out",
    compare.BELOW: "out",
    compare.NO_TARGET: "gap",
    compare.NOT_MEASURED: "gap",
}


def document(title: str, body: str, again_in: int | None = None) -> str:
    """`again_in` reloads the page after that many seconds. It is how a run in
    progress shows what it has finished without a line of script on the page."""
    reload = "" if again_in is None else (
        f"<meta http-equiv=\"refresh\" content=\"{int(again_in)}\">")
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"{reload}<title>{escape(title)}</title>"
        f"<style>{typeface.css()}</style><style>{STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>\n"
    )


def said(title: str, text: str, where: str = "") -> str:
    """A card with a sentence in it. Every state this app can be in is framed, including
    the ones that are only a sentence: nothing here is bare text on an empty page."""
    return card(title, f"<div class=\"inset\"><p>{escape(text)}</p></div>", where)


def card(title: str, body: str, where: str = "") -> str:
    """The frame every panel on every view sits in. It holds nothing of its own: what
    goes inside it is the same table, with the same numbers and the same verdicts, as
    before there was a frame."""
    aside = f"<span class=\"where\">{escape(where)}</span>" if where else ""
    return (f"<div class=\"card\"><div class=\"ch\"><h3>{escape(title)}</h3>{aside}</div>"
            f"{body}</div>")


def sentence(text: str) -> str:
    """A reason written to follow a colon, made to follow a full stop."""
    return text[:1].upper() + text[1:] if text else text


def number(value, decimals: int) -> str:
    if value is None:
        return "<span class=\"blank\">.</span>"
    return f"{value:.{decimals}f}"


MASTER_URL = "/master"


TYPED = ("artist", "album", "genre")


def controls(files: list[str], targets: list[str], chosen_file: str, chosen_target: str,
             said: dict | None = None) -> str:
    """Every field here is one the browser keeps in step with what is chosen. A value
    the server worked out sits still while the picker moves, and reads as though it had
    followed."""
    def options(values, chosen):
        out = []
        for value in values:
            mark = " selected" if value == chosen else ""
            out.append(f"<option value=\"{escape(value)}\"{mark}>{escape(value)}</option>")
        return "".join(out)

    typed = "".join(
        f"<div class=\"fld typed\"><label for=\"{name}\">{name.upper()}</label>"
        f"<input id=\"{name}\" name=\"{name}\" type=\"text\" autocomplete=\"off\" "
        f"value=\"{escape(str((said or {}).get(name, '')))}\"></div>" for name in TYPED)
    return (
        "<form class=\"bar\" method=\"get\" action=\"/\">"
        "<div class=\"fld grow\"><label for=\"what\">FILE OR FOLDER</label>"
        f"<select id=\"what\" name=\"what\">{options(files, chosen_file)}</select></div>"
        "<div class=\"fld\"><label for=\"target\">TARGET</label>"
        f"<select id=\"target\" name=\"target\">{options(['none'] + targets, chosen_target)}"
        "</select></div>" + typed +
        "<button class=\"go ghost\" type=\"submit\">MEASURE</button>"
        f"<button class=\"go\" type=\"submit\" formmethod=\"post\" "
        f"formaction=\"{MASTER_URL}\">MASTER</button>"
        "</form>"
    )


def spectrum(measurement: dict, target: dict | None) -> str:
    bands = measurement.get("spectral", {}).get("bands")
    if not bands:
        return ""
    width, height, pad = 1100, 210, 26
    top = max(b["pct"] for b in bands) * 1.12 or 1.0
    step = (width - 2 * pad) / len(bands)
    parts = []
    for i, band in enumerate(bands):
        key = "spectral.band_pct.{:.0f}_{:.0f}".format(band["lo_hz"], band["hi_hz"])
        label = fields.BY_PATH[key].short if key in fields.BY_PATH else key
        x = pad + i * step
        bar = step * 0.62
        tall = (band["pct"] / top) * (height - 46)
        parts.append(
            f"<rect x=\"{x:.1f}\" y=\"{height - 26 - tall:.1f}\" width=\"{bar:.1f}\" "
            f"height=\"{tall:.1f}\" fill=\"#34e7de\" />"
        )
        if target is not None:
            bound = target.get("fields", {}).get(key)
            if bound:
                low = (bound["low"] / top) * (height - 46)
                high = (bound["high"] / top) * (height - 46)
                parts.append(
                    f"<rect x=\"{x - step * 0.08:.1f}\" y=\"{height - 26 - high:.1f}\" "
                    f"width=\"{bar + step * 0.16:.1f}\" height=\"{max(high - low, 1.5):.1f}\" "
                    f"fill=\"none\" stroke=\"#ffb020\" stroke-width=\"1.2\" />"
                )
        parts.append(
            f"<text x=\"{x + bar / 2:.1f}\" y=\"{height - 10}\" fill=\"#6b7280\" "
            f"font-size=\"10\" text-anchor=\"middle\">{escape(label)}</text>"
        )
    return card(
        "Spectrum",
        f"<div class=\"plot\"><svg viewBox=\"0 0 {width} {height}\" role=\"img\">"
        f"{''.join(parts)}</svg></div>"
        + ("<div class=\"inset\"><p class=\"note\">Outlined boxes are the target range "
           "for that band.</p></div>" if target is not None else "")
    )


KEY = (
    ("var(--kill)", "outside the target"),
    ("var(--cue)", "on the line"),
    ("var(--unclaimed)", "no verdict claimed"),
)


def key() -> str:
    marks = "".join(f"<span><i style=\"background:{colour}\"></i>{escape(text)}</span>"
                    for colour, text in KEY)
    return (f"<div class=\"key\">{marks}"
            "<span class=\"unmarked\">unmarked is inside the target</span></div>")


def _why_no_verdict(sheet: dict, path: str) -> str:
    """The target's own words for why it claims nothing here."""
    for result in sheet.get("comparisons", {}).values():
        for row in result["rows"]:
            if row["field"] == path and row.get("why"):
                return row["why"]
    return "this target sets no bound for it."


def folder_view(sheet: dict) -> str:
    columns = sheet["columns"]
    graded = any(row.get("verdicts") for row in sheet["files"])
    claimed = {c["path"] for c in columns
               if any(c["path"] in row.get("verdicts", {}) for row in sheet["files"])}

    def group(c, extra=""):
        classes = [k for k in ("grp" if c["starts_group"] else "", extra) if k]
        return f' class="{" ".join(classes)}"' if classes else ""

    head = "".join(
        f"<th{group(c, 'quiet' if graded and c['path'] not in claimed else '')}>"
        f"{escape(c['label'])}</th>" for c in columns)

    rows = []
    for row in sheet["files"]:
        verdicts = row.get("verdicts", {})
        cells = []
        for c in columns:
            if not graded:
                klass = ""
            elif c["path"] in verdicts:
                klass = VERDICT_CLASS.get(verdicts[c["path"]], "")
            else:
                klass = "none"
            cells.append(f"<td{group(c, klass)}>"
                         f"{number(row['values'][c['path']], c['decimals'])}</td>")
        rows.append(f"<tr><td class=\"name\">{escape(row.get('label', row['name']))}</td>"
                    f"{''.join(cells)}</tr>")

    spread, over = [], []
    for c in columns:
        found = sheet["spread"][c["path"]]
        spread.append(f"<td{group(c)}>" + ("<span class=\"blank\">.</span>"
                      if "withheld" in found
                      else number(found.get("spread"), c["decimals"])) + "</td>")
        over.append(f"<td{group(c)}>" + ("" if found["n"] == 0 else str(found["n"])) + "</td>")

    notes = []
    for c in columns:
        if graded and c["path"] not in claimed:
            why = _why_no_verdict(sheet, c["path"])
            notes.append(f"<li><b>{escape(c['name'])}</b> carries no verdict. "
                         f"{escape(sentence(why))}</li>")
    for c in columns:
        found = sheet["spread"][c["path"]]
        if "withheld" in found:
            notes.append(f"<li><b>{escape(c['label'])}</b> has no spread. "
                         f"{escape(sentence(found['withheld']))}.</li>")
    partial = [c["label"] for c in columns if "withheld" not in sheet["spread"][c["path"]]
               and 0 < sheet["spread"][c["path"]]["n"] < len(sheet["files"])]
    if partial:
        notes.append("<li><b>" + escape(", ".join(partial)) +
                     "</b> covers fewer files than the folder holds. The row below the spread "
                     "says how many.</li>")
    for skip in sheet["skipped"]:
        notes.append(f"<li><b>{escape(skip['name'])}</b> could not be read. "
                     f"{escape(sentence(skip['why']))}</li>")

    where = Path(sheet["folder"])
    counted = f"{len(sheet['files'])} file" + ("" if len(sheet["files"]) == 1 else "s")
    table = (
        (f"<div class=\"inset\">{key()}</div>" if graded else "")
        + "<div class=\"wrap\">"
        + f"<table class=\"rows\"><thead><tr><th>Track</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody>"
        + f"<tfoot><tr class=\"pause\"><td colspan=\"{len(columns) + 1}\"></td></tr>"
        f"<tr class=\"spread\"><td>Spread</td>{''.join(spread)}</tr>"
        f"<tr class=\"over\"><td>Files</td>{''.join(over)}</tr></tfoot></table></div>"
    )
    return (
        card("Tracks", table, f"{where}, {counted}")
        + (card("Reasons", f"<div class=\"inset\"><ul class=\"reasons\">"
                           f"{''.join(notes)}</ul></div>") if notes else "")
    )


def _bound_text(bound: dict) -> str:
    if "max" in bound:
        return f"at most {bound['max']}"
    return f"{bound['low']} to {bound['high']}"


def comparison_view(result: dict) -> str:
    evidence = result["target"]["evidence"]
    rows = []
    for row in result["rows"]:
        if row["verdict"] == compare.NO_TARGET or row.get("advisory"):
            continue
        field = fields.BY_PATH.get(row["field"])
        decimals = field.decimals if field else 3
        tags = ""
        if row.get("basis") == "declared":
            tags += "<span class=\"tag\">rule</span>"
        if row.get("from_lossy"):
            tags += "<span class=\"tag\">lossy source</span>"
        rows.append(
            f"<tr><td class=\"name\">{escape(fields.name_of(row['field']))}{tags}</td>"
            f"<td>{number(row.get('value'), decimals)}</td>"
            f"<td class=\"blank\">{number(row.get('uncertainty'), 3)}</td>"
            f"<td class=\"blank\">{escape(_bound_text(row['bound']) if row.get('bound') else '')}</td>"
            f"<td>{number(row.get('deviation'), decimals)}</td>"
            f"<td class=\"{VERDICT_CLASS.get(row['verdict'], 'gap')}\">"
            f"{escape(row['verdict'])}</td></tr>"
        )

    gaps = []
    for row in result["rows"]:
        if not row.get("advisory"):
            continue
        field = fields.BY_PATH.get(row["field"])
        shown = number(row.get("value"), field.decimals if field else 3)
        bound = row["bound"]
        against = f"{bound['low']} to {bound['high']}" if "low" in bound else ""
        gaps.append(f"<li><b>{escape(fields.name_of(row['field']))}</b> measures {shown} "
                    f"against {escape(against)}, reported as information rather than a verdict. "
                    f"{escape(sentence(row.get('why', '')))}</li>")
    for row in result["rows"]:
        if row["verdict"] != compare.NO_TARGET:
            continue
        field = fields.BY_PATH.get(row["field"])
        shown = number(row.get("value"), field.decimals if field else 3)
        gaps.append(f"<li><b>{escape(fields.name_of(row['field']))}</b> measures {shown}, "
                    f"and has no target. {escape(sentence(row['why']))}</li>")
    for row in result["rows"]:
        if row["verdict"] == compare.NOT_MEASURED:
            gaps.append(f"<li><b>{escape(fields.name_of(row['field']))}</b> could not be "
                        f"placed. {escape(sentence(row['why']))}</li>")

    on_line = result["counts"].get(compare.ON_THE_LINE, 0)
    verdict = ("Every field sits inside its target." if result["all_inside"]
               else "Not every field sits inside its target.")
    if on_line:
        verdict += (f" {on_line} reach" + ("es" if on_line == 1 else "") +
                    " a boundary once the measurement's own uncertainty is counted, "
                    "which is not a pass.")

    return card(
        f"Against {result['target']['name']}",
        f"<div class=\"inset\"><p>Built from {evidence['n']} reference"
        + ("s" if evidence["n"] != 1 else "") +
        (", all lossy." if evidence.get("all_sources_lossy") else ".") +
        f" {escape(verdict)}</p></div>"
        "<div class=\"wrap\"><table class=\"rows\"><thead><tr><th>Field</th><th>Value</th>"
        "<th>Plus minus</th><th>Target</th><th>Deviation</th><th>Verdict</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        + (f"<div class=\"inset\"><ul class=\"reasons\">{''.join(gaps)}</ul></div>"
           if gaps else "")
    )


def octaves(measurement: dict) -> str:
    """The rates the signal also supports, with how well each fits.

    The chosen one is a judgement the registry admits it gets wrong on 8 of 35 known
    answers, so the runners up are shown rather than left in the structured output.
    """
    found = measurement.get("tempo", {})
    alternatives = found.get("alternatives")
    if not alternatives:
        return ""
    chosen = found.get("bpm")
    rows = []
    for one in alternatives:
        here = abs(one["bpm"] - chosen) < 1e-6 if chosen is not None else False
        mark = "<span class=\"tag\">reported</span>" if here else ""
        rows.append(
            f"<tr><td class=\"name\">{number(one['bpm'], 2)} BPM{mark}</td>"
            f"<td class=\"blank\">{escape(_ratio(one['ratio']))}</td>"
            f"<td>{number(one['occupancy'], 3)}</td>"
            f"<td>{number(one['coverage'], 3)}</td>"
            f"<td>{one['onsets_fitted']}</td></tr>")
    return card(
        "Rates the signal also supports",
        "<div class=\"inset\"><p>Which of these is the beat is a musical judgement, not a "
        "property of the signal. Occupancy is the share of grid ticks that carry an onset, "
        "coverage the share of onsets that sit on a tick.</p></div>"
        "<div class=\"wrap\"><table class=\"rows\"><thead><tr><th>Rate</th><th>Against the reported one</th>"
        "<th>Occupancy</th><th>Coverage</th><th>Onsets fitted</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _ratio(value: float) -> str:
    for text, number_ in (("half", 0.5), ("two thirds", 2.0 / 3.0), ("the same", 1.0),
                          ("one and a half", 1.5), ("double", 2.0)):
        if abs(value - number_) < 0.01:
            return text
    return f"{value:g}"


def file_view(measurement: dict, result: dict | None, target: dict | None) -> str:
    source = measurement.get("source", {})
    meta = ", ".join(str(v) for v in (
        source.get("container"), source.get("codec"),
        f"{source.get('measured_at_hz')} Hz", f"{source.get('channels')} channels",
        f"{measurement.get('duration_s')} s") if v)
    rows = []
    for field in fields.FIELDS:
        value = compare.dig(measurement, field.path)
        if not isinstance(value, (int, float)):
            continue
        rows.append(f"<tr><td class=\"name\">{escape(field.name)}</td>"
                    f"<td>{number(value, field.decimals)}</td>"
                    f"<td class=\"blank\">{escape(field.unit)}</td></tr>")

    missing = []
    for block in ("loudness", "spectral", "levels", "stereo", "tempo"):
        found = measurement.get(block, {})
        if "unmeasurable" in found:
            missing.append(f"<li><b>{escape(block.title())}</b> was not measured. "
                           f"{escape(sentence(found['unmeasurable']))}</li>")
        for name, why in (found.get("absent_because") or {}).items():
            missing.append(f"<li><b>{escape(fields.name_of(f'{block}.{name}'))}</b> is not "
                           f"reported. {escape(sentence(why))}</li>")
        for caveat in found.get("caveats", []):
            missing.append(f"<li><b>{escape(block.title())}</b>: {escape(caveat)}.</li>")

    body = (
        card("Measured",
             f"<div class=\"wrap\"><table class=\"rows\"><tbody>{''.join(rows)}"
             "</tbody></table></div>",
             meta)
        + (card("Reasons", f"<div class=\"inset\"><ul class=\"reasons\">"
                           f"{''.join(missing)}</ul></div>") if missing else "")
        + octaves(measurement)
        + spectrum(measurement, target)
    )
    if result is not None:
        body += comparison_view(result)
    return body


def _plan_items(plan: dict) -> str:
    items = []
    for one in plan["steps"]:
        if one["correction"] == "low cut":
            said = f"At {one['hz']:.0f} Hz, order {one['order']}. {sentence(one['from'])}."
            if "moved_bands_by_pct" in one:
                said += (f" Moved the bands above it by at most "
                         f"{one['moved_bands_by_pct']} points.")
        elif one["correction"] == "gain":
            said = f"{one['db']:+.3f} dB, set by {one['bound_by']}. Aimed {one['from']}."
            if "corrected_by_db" in one:
                said += (f" Of that, {one['corrected_by_db']:+.3f} dB is a correction: "
                         f"{one['correction_from']}.")
        else:
            worked = one["gain_reduction"]
            said = (f"To {one['ceiling_dbtp']} dBTP, attack {one['attack_ms']} ms, release "
                    f"{one['release_ms']} ms. {sentence(one['chosen_from'])}. Took at most "
                    f"{worked['largest_db']} dB off, and moved the widest band by "
                    f"{one['largest_band_move_pct']} points.")
            if one.get("at_search_edge"):
                said += f" {sentence(one['at_search_edge'])}."
            if "why_it_stopped" in one:
                said += f" {one['why_it_stopped']}"
        items.append(f"<li><b>{escape(one['correction'].capitalize())}</b> {escape(said)}</li>")
    for one in plan["not_applied"]:
        items.append(f"<li><b>{escape(one['correction'].capitalize())}</b> not applied. "
                     f"{escape(sentence(one['why']))}.</li>")
    return f"<ul class=\"reasons\">{''.join(items)}</ul>"

WORKING_AGAIN_IN_S = 3
PEAK_FIELD = "loudness.true_peak_dbtp"
WAVE_HEIGHT = 56
WAVE_WIDTH = 1000
FIGURES = (("LUFS", "loudness.integrated_lufs"), ("DBTP", "loudness.true_peak_dbtp"),
           ("CREST", "levels.crest_db"))
PLAN_CELLS = ("GAIN", "LOW CUT", "CEILING", "LIMITER", "REDUCTION", "PREDICTED", "MEASURED")
QUIET_CELLS = ("PREDICTED", "MEASURED")


def _wave(shape: list, master_side: bool) -> str:
    """A picture of the file, drawn from the samples that were written. Nothing reads it
    back and no verdict rests on it, which is why it is the only thing on this page
    allowed to be a shape rather than a number."""
    middle = WAVE_HEIGHT / 2.0
    fill = "var(--mst)" if master_side else "var(--src)"
    if not shape:
        return (f"<svg viewBox=\"0 0 {WAVE_WIDTH} {WAVE_HEIGHT}\" "
                "preserveAspectRatio=\"none\"></svg>")
    step = WAVE_WIDTH / len(shape)
    top = " ".join(f"{i * step:.1f},{middle - v * middle:.1f}" for i, v in enumerate(shape))
    bottom = " ".join(f"{i * step:.1f},{middle + v * middle:.1f}"
                      for i, v in reversed(list(enumerate(shape))))
    return (f"<svg viewBox=\"0 0 {WAVE_WIDTH} {WAVE_HEIGHT}\" preserveAspectRatio=\"none\">"
            f"<path d=\"M{top} L{bottom} Z\" fill=\"{fill}\"></path></svg>")


def _figures(measured: dict) -> str:
    out = []
    for unit, path in FIGURES:
        field = fields.BY_PATH.get(path)
        out.append(f"<span><i>{escape(unit)}</i>"
                   f"{number(compare.dig(measured, path), field.decimals if field else 1)}"
                   "</span>")
    return "".join(out)


def _side(name: str, side: dict, master_side: bool) -> str:
    figures = _figures(side.get("measurement", {})) if side else ""
    return (f"<div class=\"wv\"><div class=\"wh\">"
            f"<b class=\"{'m' if master_side else 's'}\">{escape(name)}</b>"
            f"<span class=\"figs\">{figures}</span></div>"
            + _wave(side.get("waveform") or [], master_side) + "</div>")


def _signed(value, decimals: int) -> str:
    return number(None, decimals) if value is None else f"{value:+.{decimals}f}"


def _step(built: dict, correction: str):
    for one in built.get("steps", []):
        if one["correction"] == correction:
            return one
    return None


def plan_strip(result: dict) -> str:
    """Seven numbers across the top, in the order the layer decides them."""
    built = result.get("plan") or {"steps": []}
    gain, cut, squash = _step(built, "gain"), _step(built, "low cut"), _step(built, "limiter")
    after = (result.get("after") or {}).get("measurement", {})
    predicted = built.get("predicted") or {}
    ceiling = None
    for row in ((result.get("after") or {}).get("comparison") or {}).get("rows", []):
        if row["field"] == PEAK_FIELD and row.get("bound"):
            ceiling = row["bound"].get("max")

    values = {
        "GAIN": _signed(gain["db"] if gain else None, 2),
        "LOW CUT": f"{cut['hz']:.0f}" if cut else number(None, 0),
        "CEILING": number(ceiling, 2),
        "LIMITER": (f"{squash['attack_ms']:g} / {squash['release_ms']:g}"
                    if squash else number(None, 1)),
        "REDUCTION": number(squash["gain_reduction"]["largest_db"] if squash else None, 2),
        "PREDICTED": number(predicted.get("integrated_lufs"), 2),
        "MEASURED": number(compare.dig(after, "loudness.integrated_lufs"), 2),
    }
    cells = "".join(
        f"<div class=\"pc{' q' if name in QUIET_CELLS else ''}\"><span>{name}</span>"
        f"<b>{values[name]}</b></div>" for name in PLAN_CELLS)
    return f"<div class=\"plan\">{cells}</div>"


def _ab_row(field: str, was: dict, now: dict) -> str:
    one = fields.BY_PATH.get(field)
    decimals = one.decimals if one else 3
    bound = now.get("bound") or {}
    delta = None
    if was.get("value") is not None and now.get("value") is not None:
        delta = round(now["value"] - was["value"], decimals)
    quiet = now.get("advisory") or now["verdict"] in (compare.NO_TARGET, compare.NOT_MEASURED)
    was_mark = "none" if quiet else VERDICT_CLASS.get(was.get("verdict"), "")
    now_mark = "none" if quiet else VERDICT_CLASS.get(now.get("verdict"), "")
    off = "" if quiet or now["verdict"] == compare.INSIDE else number(now.get("deviation"),
                                                                     decimals)
    return (
        f"<tr><td class=\"fld{' adv' if quiet else ''}\">"
        f"{escape(fields.name_of(field))}</td>"
        f"<td class=\"n {was_mark}\">{number(was.get('value'), decimals)}</td>"
        f"<td class=\"n {now_mark}\">{number(now.get('value'), decimals)}</td>"
        f"<td class=\"n d\">{_signed(delta, decimals)}</td>"
        f"<td class=\"u\">{escape(one.unit if one else '')}</td>"
        f"<td class=\"t\">{escape(_bound_text(bound) if bound else '')}</td>"
        f"<td class=\"n dev {now_mark}\">{off}</td></tr>"
    )


AB_HEAD = ("<thead><tr><th class=\"l\">FIELD</th><th>SOURCE</th><th>MASTER</th>"
           "<th>DELTA</th><th style=\"text-align:left;padding-left:7px\"></th>"
           "<th>TARGET</th><th style=\"padding-right:15px\">DEV</th></tr></thead>")
BANDS_HEAD = ("<div class=\"bhead\"><span>BAND</span><span></span><span>SOURCE</span>"
              "<span>MASTER</span><span>DELTA</span></div>")


def against_panel(result: dict) -> str:
    was = {r["field"]: r for r in result["before"]["comparison"].get("rows", [])}
    rows = "".join(_ab_row(row["field"], was.get(row["field"], {}), row)
                   for row in result["after"]["comparison"].get("rows", []))
    return ("<div class=\"card\"><div class=\"ch\"><h3>SOURCE AGAINST MASTER</h3></div>"
            f"<table>{AB_HEAD}<tbody>{rows}</tbody></table></div>")


def bands_panel(result: dict) -> str:
    """Every band as a share of the whole, source above master. The bars are scaled to
    the largest band on either side, so the shape is comparable and the number is what
    the value is."""
    was = result["before"]["measurement"].get("spectral", {}).get("bands", [])
    now = result["after"]["measurement"].get("spectral", {}).get("bands", [])
    top = max([b["pct"] for b in was] + [b["pct"] for b in now] + [1e-9])
    rows = []
    for source, made in zip(was, now):
        key = f"spectral.band_pct.{measurement.band_key(source['lo_hz'], source['hi_hz'])}"
        one = fields.BY_PATH.get(key)
        decimals = one.decimals if one else 2
        rows.append(
            "<div class=\"bnd\">"
            f"<span class=\"bl\">{escape(one.short if one else key)}</span>"
            "<span class=\"bar2\">"
            f"<i class=\"sb\" style=\"width:{100.0 * source['pct'] / top:.1f}%\"></i>"
            f"<i class=\"mb\" style=\"width:{100.0 * made['pct'] / top:.1f}%\"></i></span>"
            f"<span class=\"n bv\">{number(source['pct'], decimals)}</span>"
            f"<span class=\"n bv\">{number(made['pct'], decimals)}</span>"
            f"<span class=\"n bd\">"
            f"{_signed(round(made['pct'] - source['pct'], decimals), decimals)}</span></div>")
    return ("<div class=\"card\"><div class=\"ch\"><h3>SPECTRAL BALANCE</h3></div>"
            f"<div class=\"bands\">{BANDS_HEAD}{''.join(rows)}</div></div>")


def _notes(result: dict) -> str:
    landed = result["reached"]
    where = []
    for field, one in landed["fields"].items():
        if "value" not in one:
            where.append(f"{fields.name_of(field)} was not measured on the output")
            continue
        where.append(f"{fields.name_of(field)} landed at {one['value']} plus or minus "
                     f"{one['uncertainty']}, {one['verdict']}")
    said = [f"<li>{escape('; '.join(where))}. "
            + ("It arrived." if landed["arrived"] else "It did not arrive.") + "</li>"]

    for row in result["after"]["comparison"].get("rows", []):
        if not (row.get("advisory") or row["verdict"] in (compare.NO_TARGET,
                                                          compare.NOT_MEASURED)):
            continue
        if row.get("why"):
            said.append(f"<li><b>{escape(fields.name_of(row['field']))}</b> carries no "
                        f"verdict. {escape(sentence(row['why']))}.</li>")

    tags = result.get("tags")
    if tags:
        wrote = ", ".join(f"{name} {value}" for name, value in tags["written"].items())
        said.append("<li>The file says " + escape(wrote) + ". "
                    + ("Read back off it and it holds." if tags["held"]
                       else "Read back off it, that is not what it says.") + "</li>")

    held = result["prediction"]
    if held.get("checked"):
        parts = []
        for name, one in held["fields"].items():
            if "predicted" not in one:
                continue
            parts.append(f"{fields.name_of('loudness.' + name)} was predicted "
                         f"{one['predicted']} and measured {one['measured']}, apart by "
                         f"{one['gap']} against {one['uncertainty']} allowed")
        said.append(f"<li>Checked against {escape(held['against'])}: "
                    + escape("; ".join(parts)) + ". "
                    + ("Every prediction held." if held.get("held")
                       else "Not every prediction held.") + "</li>")
    return ("<div class=\"card\"><div class=\"ch\"><h3>WHAT IT DID</h3></div>"
            f"<div class=\"inset\">{_plan_items(result['plan'])}"
            f"<ul class=\"reasons\">{''.join(said)}</ul></div></div>")


def master_view(result: dict) -> str:
    """One file: the plan across the top, the two waveforms stacked under it, and the
    field table beside the spectral balance. The frame is docs/master-view.html."""
    name = Path(result["input"]).name
    return (
        "<div class=\"mv\">"
        "<div class=\"card\"><div class=\"ch\"><h3>PLAN</h3>"
        f"<span class=\"where\">{escape(name)}</span></div>{plan_strip(result)}</div>"
        "<div class=\"card\">"
        + _side("SOURCE", result["before"], False)
        + _side("MASTER", result["after"], True)
        + "</div>"
        f"<div class=\"split\">{against_panel(result)}{bands_panel(result)}</div>"
        + _notes(result) + "</div>"
    )


def closed_view(result: dict) -> str:
    """The same block, behind a row that says enough to decide whether to open it.

    The name, whether it arrived, and the two fields the plan aims at, read off the
    output the way reached does rather than named again here.
    """
    name = Path(result["input"]).name
    got = result.get("reached", {})
    lands = "ARRIVED" if got.get("arrived") else "NOT ARRIVED"
    klass = "lands" if got.get("arrived") else "lands out"
    figs = "".join(
        f"<span><b>{number(found.get('value'), fields.get(path).decimals)}</b> "
        f"{escape(fields.get(path).unit)}</span>"
        for path, found in got.get("fields", {}).items())
    return (
        "<details class=\"one\"><summary>"
        f"<h3>{escape(name)}</h3><span class=\"{klass}\">{lands}</span>"
        f"<span class=\"figs\">{figs}</span></summary>"
        + master_view(result) + "</details>"
    )


def waiting_view(name: str) -> str:
    """The same shape with nothing in it yet, so the page does not jump when the run
    lands. Every card here is the size of the card that replaces it."""
    cells = "".join(
        f"<div class=\"pc{' q' if one in QUIET_CELLS else ''}\"><span>{one}</span>"
        f"<b>{number(None, 2)}</b></div>" for one in PLAN_CELLS)
    rows = "".join("<tr><td class=\"fld\">&nbsp;</td><td class=\"n\"></td>"
                   "<td class=\"n\"></td><td class=\"n d\"></td><td class=\"u\"></td>"
                   "<td class=\"t\"></td><td class=\"n dev\"></td></tr>"
                   for _ in range(9))
    bands = "".join("<div class=\"bnd\"><span class=\"bl\">&nbsp;</span>"
                    "<span class=\"bar2\"></span><span class=\"n bv\"></span>"
                    "<span class=\"n bv\"></span><span class=\"n bd\"></span></div>"
                    for _ in range(10))
    return (
        "<div class=\"mv hold\">"
        "<div class=\"card\"><div class=\"ch\"><h3>PLAN</h3>"
        f"<span class=\"where\">{escape(name)}</span></div><div class=\"plan\">{cells}"
        "</div></div>"
        "<div class=\"card\">"
        "<div class=\"wv\"><div class=\"wh\"><b class=\"s\">SOURCE</b></div>"
        + _wave([], False) + "</div>"
        "<div class=\"wv\"><div class=\"wh\"><b class=\"m\">MASTER</b></div>"
        + _wave([], True) + "</div></div>"
        "<div class=\"split\">"
        "<div class=\"card\"><div class=\"ch\"><h3>SOURCE AGAINST MASTER</h3></div>"
        f"<table>{AB_HEAD}<tbody>{rows}</tbody></table></div>"
        "<div class=\"card\"><div class=\"ch\"><h3>SPECTRAL BALANCE</h3></div>"
        f"<div class=\"bands\">{BANDS_HEAD}{bands}</div></div></div></div>"
    )


def mastering_view(job: dict) -> str:
    """A run in progress or a run that finished, in one view. While it works the page
    reloads itself, so what is on screen is what has actually been written."""
    if job.get("refused"):
        return said("Not started", sentence(job["refused"]) + ".")
    if job.get("failure"):
        return card("Stopped", "<div class=\"inset\"><p>The run stopped on an error.</p>"
                    f"<pre>{escape(job['failure'])}</pre></div>")

    done, failed = job["done"], job["failed"]
    arrived = sum(1 for one in done if one["reached"]["arrived"])
    if job["running"]:
        at = job.get("at") or ""
        of = f" of {job['total']}" if job["total"] else ""
        told = (f"{job['finished']}{of} finished, {arrived} inside the target. "
                + (f"Working on {escape(at)}. " if at else "")
                + "This page keeps itself up to date.")
    else:
        told = (f"{len(done)} file" + ("" if len(done) == 1 else "s") +
                f" written, {arrived} of them inside the target on loudness and true peak.")

    head = card("Mastering" if job["running"] else "Mastered",
                f"<div class=\"inset\"><p>{told}</p>{key()}</div>",
                str(job["out_dir"]))
    refused = ""
    if failed:
        items = "".join(f"<li><b>{escape(one['name'])}</b> {escape(sentence(one['why']))}.</li>"
                        for one in failed)
        refused = card("Not mastered",
                       f"<div class=\"inset\"><ul class=\"reasons\">{items}</ul></div>")

    one_file = job["total"] == 1
    blocks = "".join((master_view if one_file else closed_view)(one) for one in done)
    if job["running"]:
        blocks += waiting_view(job.get("at") or str(job["what"]))
    return head + refused + blocks
