"""HTML output. Formats what it is given and decides nothing.

No request leaves the page. Fonts are the ones already on the machine.
"""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

from bench import compare, fields, typeface

STYLE = """
:root {
  --bg: #08090b; --panel: #0d0f13; --panel-hi: #12151a;
  --edge: #1a1d23; --edge-soft: #141720; --edge-hi: #2a2f3a;
  --text: #efe9de; --dim: #5f6672; --faint: #3d434d; --unclaimed: #6a7280;
  --accent: #34e7de; --cue: #ffb020; --kill: #ff4d5e;
  --mono: 'JetBrains Mono', ui-monospace, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  min-height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: 'Chakra Petch', system-ui, sans-serif;
  font-size: 14px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
main { max-width: 1240px; margin: 0 auto; padding: 26px 22px 80px; }
h1 { font-size: 20px; font-weight: 600; letter-spacing: 0.01em; }
h2 { font-size: 11px; font-weight: 600; margin: 30px 0 10px;
     text-transform: uppercase; letter-spacing: 0.11em; color: var(--dim); }
p { margin-bottom: 10px; color: var(--dim); max-width: 62em; }
.controls { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end;
            padding: 13px 15px; background: var(--panel); border: 1px solid var(--edge);
            border-radius: 3px; margin-bottom: 20px; }
.control { display: flex; flex-direction: column; gap: 5px; }
label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.11em; color: var(--dim); }
select, button {
  background: var(--bg); color: var(--text); border: 1px solid var(--edge);
  border-radius: 2px; padding: 7px 9px; font: inherit; font-size: 13px; min-width: 230px;
}
button { min-width: 0; cursor: pointer; border-color: var(--edge-hi); letter-spacing: 0.06em;
         text-transform: uppercase; font-size: 11px; padding: 9px 16px; }
button:hover { border-color: var(--accent); color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.wrap { overflow-x: auto; overflow-y: hidden; }
table { border-collapse: collapse; width: 100%; }
th, td { padding: 8px 0 8px 18px; border-bottom: 1px solid var(--edge-soft);
         white-space: nowrap; }
th:first-child, td:first-child { width: 1%; padding-left: 0; padding-right: 26px; }
th.grp, td.grp { padding-left: 34px; position: relative; }
th.grp::before, td.grp::before { content: ""; position: absolute; left: 16px;
  top: -1px; bottom: -1px; border-left: 1px solid var(--edge-soft); }
th.grp::before { top: auto; height: 11px; bottom: 9px; }
th.quiet { color: var(--faint); }
th { text-align: right; font-size: 10px; font-weight: 600; color: var(--dim);
     text-transform: uppercase; letter-spacing: 0.09em; }
th:first-child, td:first-child { text-align: left; }
td { text-align: right; font-family: var(--mono); font-weight: 400; font-size: 12px;
     font-variant-numeric: tabular-nums; color: var(--text); }
td.name { font-family: 'Chakra Petch', system-ui, sans-serif; font-size: 13px;
          color: var(--text); padding-right: 28px; }
tbody tr:hover td { background: var(--panel-hi); }
tr.pause td { border-bottom: none; padding: 0; height: 22px; }
tr.pause td:hover { background: none; }
tr.spread td { border-top: 1px solid var(--edge-hi); border-bottom: none; color: var(--text); }
tr.spread td:first-child, tr.over td:first-child {
  color: var(--dim); font-size: 10px; text-transform: uppercase; letter-spacing: 0.09em; }
tr.over td { color: var(--faint); font-size: 11px; border-bottom: none; padding-top: 0; }
tr.spread td:hover, tr.over td:hover { background: none; }
.blank { color: var(--faint); }
.line { color: var(--cue); background: rgba(255, 176, 32, 0.12);
        box-shadow: inset 0 -2px 0 var(--cue); }
.out { color: var(--kill); }
.none { color: var(--unclaimed); }
.gap { color: var(--faint); }
.note { font-size: 12px; color: var(--dim); margin-top: 8px; }
.reasons { margin-top: 12px; list-style: none; }
.reasons li { padding: 7px 0; border-bottom: 1px solid var(--edge); color: var(--dim);
              font-size: 12px; max-width: 74em; }
.reasons b { color: var(--text); font-weight: 600; }
.tag { display: inline-block; font-size: 9px; letter-spacing: 0.09em; text-transform: uppercase;
       color: var(--faint); border: 1px solid var(--edge); border-radius: 2px;
       padding: 1px 5px; margin-left: 6px; vertical-align: 1px; }
.head { display: flex; justify-content: space-between; align-items: baseline;
        gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.head .meta { color: var(--faint); font-size: 12px; font-family: var(--mono); }
.key { display: flex; gap: 16px; flex-wrap: wrap; font-size: 11px; color: var(--dim);
       margin-top: 10px; margin-bottom: 4px; }
.key .unmarked { color: var(--faint); }
.key span { display: inline-flex; align-items: center; gap: 5px; }
.key i { width: 9px; height: 9px; border-radius: 1px; display: inline-block; font-style: normal; }
svg { display: block; width: 100%; height: auto; }
.plot { background: var(--panel); border: 1px solid var(--edge); border-radius: 3px;
        padding: 14px 16px 8px; }
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


def sentence(text: str) -> str:
    """A reason written to follow a colon, made to follow a full stop."""
    return text[:1].upper() + text[1:] if text else text


def number(value, decimals: int) -> str:
    if value is None:
        return "<span class=\"blank\">.</span>"
    return f"{value:.{decimals}f}"


MASTER_URL = "/master"


def controls(files: list[str], targets: list[str], chosen_file: str, chosen_target: str) -> str:
    def options(values, chosen):
        out = []
        for value in values:
            mark = " selected" if value == chosen else ""
            out.append(f"<option value=\"{escape(value)}\"{mark}>{escape(value)}</option>")
        return "".join(out)

    return (
        "<form class=\"controls\" method=\"get\" action=\"/\">"
        "<div class=\"control\"><label for=\"what\">File or folder</label>"
        f"<select id=\"what\" name=\"what\">{options(files, chosen_file)}</select></div>"
        "<div class=\"control\"><label for=\"target\">Target</label>"
        f"<select id=\"target\" name=\"target\">{options(['none'] + targets, chosen_target)}"
        "</select></div>"
        "<button type=\"submit\">Measure</button>"
        f"<button type=\"submit\" formmethod=\"post\" formaction=\"{MASTER_URL}\">Master</button>"
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
    return (
        "<h2>Spectrum</h2><div class=\"plot\">"
        f"<svg viewBox=\"0 0 {width} {height}\" role=\"img\">{''.join(parts)}</svg></div>"
        + ("<p class=\"note\">Outlined boxes are the target range for that band.</p>"
           if target is not None else "")
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
    heading = (f"{escape(str(where.parent) + os.sep)}<b>{escape(where.name)}</b>"
               if where.name else escape(str(where)))
    return (
        f"<div class=\"head\"><h1>{heading}</h1>"
        f"<span class=\"meta\">{len(sheet['files'])} files</span></div>"
        + (key() if graded else "")
        + "<div class=\"wrap\">"
        + f"<table><thead><tr><th>Track</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody>"
        + f"<tfoot><tr class=\"pause\"><td colspan=\"{len(columns) + 1}\"></td></tr>"
        f"<tr class=\"spread\"><td>Spread</td>{''.join(spread)}</tr>"
        f"<tr class=\"over\"><td>Files</td>{''.join(over)}</tr></tfoot></table></div>"
        + (f"<ul class=\"reasons\">{''.join(notes)}</ul>" if notes else "")
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

    return (
        f"<h2>Against {escape(result['target']['name'])}</h2>"
        f"<p>Built from {evidence['n']} reference"
        + ("s" if evidence["n"] != 1 else "") +
        (", all lossy." if evidence.get("all_sources_lossy") else ".") +
        f" {escape(verdict)}</p>"
        "<table><thead><tr><th>Field</th><th>Value</th><th>Plus minus</th><th>Target</th>"
        "<th>Deviation</th><th>Verdict</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        + (f"<ul class=\"reasons\">{''.join(gaps)}</ul>" if gaps else "")
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
    return (
        "<h2>Rates the signal also supports</h2>"
        "<p>Which of these is the beat is a musical judgement, not a property of the "
        "signal. Occupancy is the share of grid ticks that carry an onset, coverage the "
        "share of onsets that sit on a tick.</p>"
        "<table><thead><tr><th>Rate</th><th>Against the reported one</th>"
        "<th>Occupancy</th><th>Coverage</th><th>Onsets fitted</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
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
        f"<div class=\"head\"><h1>{escape(measurement.get('file', {}).get('name', 'file'))}</h1>"
        f"<span class=\"meta\">{escape(meta)}</span></div>"
        f"<h2>Measured</h2><table><tbody>{''.join(rows)}</tbody></table>"
        + (f"<ul class=\"reasons\">{''.join(missing)}</ul>" if missing else "")
        + octaves(measurement)
        + spectrum(measurement, target)
    )
    if result is not None:
        body += comparison_view(result)
    return body


def _master_row(field: str, was: dict, now: dict) -> str:
    decimals = fields.BY_PATH.get(field).decimals if field in fields.BY_PATH else 3
    cells = []
    for row in (was, now):
        klass = VERDICT_CLASS.get(row.get("verdict"), "gap") if row else "gap"
        cells.append(f"<td class=\"{klass}\">{number(row.get('value'), decimals)}</td>"
                     f"<td class=\"{klass}\">{escape(row.get('verdict', ''))}</td>")
    return (f"<tr><td class=\"name\">{escape(fields.name_of(field))}</td>"
            + "".join(cells) +
            f"<td class=\"blank\">{escape(_bound_text(now['bound']) if now.get('bound') else '')}"
            "</td></tr>")


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


def master_view(result: dict) -> str:
    """Before and after against the same target, coloured by the same rule as the
    folder table: only what is outside is marked."""
    before = {r["field"]: r for r in result["before"]["comparison"]["rows"]}
    rows = []
    for row in result["after"]["comparison"]["rows"]:
        if row["verdict"] == compare.NO_TARGET or row.get("advisory"):
            continue
        rows.append(_master_row(row["field"], before.get(row["field"], {}), row))

    landed = result["reached"]
    where = []
    for field, one in landed["fields"].items():
        if "value" not in one:
            where.append(f"{fields.name_of(field)} was not measured on the output")
            continue
        where.append(f"{fields.name_of(field)} landed at {one['value']} plus or minus "
                     f"{one['uncertainty']}, {one['verdict']}")
    arrived = (f"<p>{escape('; '.join(where))}. "
               + ("It arrived." if landed["arrived"] else "It did not arrive.") + "</p>")

    held = result["prediction"]
    checked = ""
    if held.get("checked"):
        parts = []
        for name, one in held["fields"].items():
            if "predicted" not in one:
                continue
            parts.append(f"{fields.name_of('loudness.' + name)} was predicted "
                         f"{one['predicted']} and measured {one['measured']}, apart by "
                         f"{one['gap']} against {one['uncertainty']} allowed")
        checked = (f"<p>Checked against {escape(held['against'])} instrument: "
                   + escape("; ".join(parts)) + ". "
                   + ("Every prediction held." if held.get("held")
                      else "Not every prediction held.") + "</p>")

    return (
        f"<h2>Mastered against {escape(result['after']['comparison']['target']['name'])}</h2>"
        f"<p>Read {escape(result['input'])}<br>Written {escape(result['output'])}</p>"
        + key() +
        "<div class=\"wrap\"><table><thead><tr><th>Field</th><th>Before</th><th>Was</th>"
        "<th>After</th><th>Now</th><th>Target</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"<h2>What it did</h2>{_plan_items(result['plan'])}"
        + arrived + checked
    )


WORKING_AGAIN_IN_S = 3


def mastering_view(job: dict) -> str:
    """A run in progress or a run that finished, in one view. The page reloads itself
    while it is working, so what is on screen is what has actually been written."""
    if job.get("refused"):
        return f"<h2>Not started</h2><p>{escape(sentence(job['refused']))}.</p>"

    where = f"<p>Writing into {escape(str(job['out_dir']))}</p>"
    if job["running"]:
        at = job.get("at") or ""
        of = f" of {job['total']}" if job["total"] else ""
        return (
            f"<h2>Mastering {escape(str(job['what']))}</h2>" + where +
            f"<p>{job['finished']}{of} finished."
            + (f" Working on {escape(at)}." if at else "") +
            " This page keeps itself up to date.</p>"
        )

    if job.get("failure"):
        return (f"<h2>Stopped</h2>{where}<p>The run stopped on an error.</p>"
                f"<pre>{escape(job['failure'])}</pre>")

    done, failed = job["done"], job["failed"]
    arrived = sum(1 for one in done if one["reached"]["arrived"])
    head = (f"<h2>Mastered {escape(str(job['what']))}</h2>{where}"
            f"<p>{len(done)} file" + ("" if len(done) == 1 else "s") +
            f" written, {arrived} of them inside the target on loudness and true peak.</p>")
    refused = ""
    if failed:
        items = "".join(f"<li><b>{escape(one['name'])}</b> {escape(sentence(one['why']))}.</li>"
                        for one in failed)
        refused = (f"<h2>Not mastered</h2><ul class=\"reasons\">{items}</ul>")
    return head + refused + "".join(master_view(one) for one in done)
