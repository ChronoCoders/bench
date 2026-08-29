"""HTML output. Formats what it is given and decides nothing.

No request leaves the page. Fonts are the ones already on the machine.
"""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

from bench import compare, fields, measurement, typeface

STYLE = """
:root {
  --bg: #08090b; --panel: #0d0f13; --panel-hi: #12151a;
  --edge: #1a1d23; --edge-soft: #141720; --edge-hi: #2a2f3a;
  --text: #efe9de; --muted: #cfc9be; --dim: #5f6672; --faint: #3d434d;
  --unclaimed: #6a7280; --src: #6a7280; --mst: #efe9de;
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
            padding: 13px 15px; border: 1px solid var(--edge); border-radius: 9px;
            background: linear-gradient(180deg, var(--panel-hi), var(--panel));
            margin-bottom: 16px; }
.control.grow { flex: 1 1 auto; max-width: 400px; }
.control.grow select { width: 100%; }
button.reads { color: var(--dim); border-color: var(--edge); }
button.reads:hover { color: var(--accent); border-color: var(--accent); }
.control .said { font-family: var(--mono); font-size: 12px; color: var(--faint);
                 padding: 7px 0; white-space: nowrap; }
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

.bar { display: flex; align-items: flex-end; gap: 12px;
       background: linear-gradient(180deg, var(--panel-hi), var(--panel));
       border: 1px solid var(--edge); border-radius: 9px; padding: 13px 15px;
       margin-bottom: 16px; flex-wrap: wrap; }
.bar .control.grow { flex: 1 1 auto; max-width: 400px; }
.bar .reads { color: var(--dim); border-color: var(--edge); background: transparent; }
.bar .said { display: flex; flex-direction: column; gap: 6px; font-family: var(--mono);
             font-size: 11px; color: var(--faint); padding-bottom: 8px; }

.card { background: var(--panel); border: 1px solid var(--edge); border-radius: 9px;
        margin-bottom: 16px; }
.ch { display: flex; align-items: baseline; gap: 16px; padding: 12px 15px 11px;
      border-bottom: 1px solid var(--edge-soft); }
.ch h3 { font-size: 9px; letter-spacing: 0.26em; color: var(--dim); font-weight: 500;
         text-transform: uppercase; margin: 0; }
.ch .where { margin-left: auto; font-family: var(--mono); font-size: 11px;
             color: var(--faint); text-align: right; }

.plan { display: grid; grid-template-columns: repeat(7, 1fr); }
.pc { padding: 12px 15px; border-right: 1px solid var(--edge-soft); }
.pc:last-child { border-right: none; }
.pc span { display: block; font-size: 9px; letter-spacing: 0.2em; color: var(--dim);
           margin-bottom: 6px; text-transform: uppercase; }
.pc b { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 15px;
        font-weight: 400; color: var(--text); }
.pc.q b { color: var(--dim); font-size: 13px; }

.wv { padding: 11px 15px 13px; border-bottom: 1px solid var(--edge-soft); }
.wv:last-child { border-bottom: none; }
.wh { display: flex; align-items: baseline; gap: 14px; margin-bottom: 8px; }
.wh b { font-size: 10px; letter-spacing: 0.24em; font-weight: 500; text-transform: uppercase; }
.wh .s { color: var(--dim); }
.wh .m { color: var(--text); }
.wh .figs { margin-left: auto; display: flex; gap: 22px; font-family: var(--mono);
            font-variant-numeric: tabular-nums; font-size: 12px; color: var(--muted); }
.wh .figs i { font-style: normal; color: var(--faint); margin-right: 6px; font-size: 10px;
              letter-spacing: 0.14em; }
svg.wave { display: block; width: 100%; height: 56px; }
svg.wave path { fill: var(--src); }
svg.wave.m path { fill: var(--mst); }
.wv.hold svg.wave { border-top: 1px solid var(--edge-soft); }

.split { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: stretch; }
.split .card { display: flex; flex-direction: column; margin-bottom: 0; min-height: 26em; }
.split .card table, .split .card .bands { flex: 1 1 auto; }

table.ab th { font-size: 9px; font-weight: 500; letter-spacing: 0.2em; color: var(--dim);
              text-align: right; padding: 0 0 8px 16px; border-bottom: 1px solid var(--edge);
              text-transform: uppercase; }
table.ab th.l, table.ab td.fld { text-align: left; padding-left: 15px; }
table.ab th:first-child, table.ab td:first-child { width: auto; padding-right: 0; }
table.ab td { padding: 7px 0 7px 16px; border-bottom: 1px solid var(--edge-soft);
              text-align: right; font-size: 12.5px; font-family: var(--mono);
              font-variant-numeric: tabular-nums; color: var(--muted); }
table.ab tr:last-child td { border-bottom: none; }
table.ab td.fld { font-family: 'Chakra Petch', system-ui, sans-serif; }
table.ab td.u { color: var(--faint); font-size: 10px; letter-spacing: 0.12em;
                text-align: left; padding-left: 7px; }
table.ab td.t { color: var(--dim); font-size: 11px; }
table.ab td.d { color: var(--dim); }
table.ab td.dev { padding-right: 15px; }
table.ab td.grp { border-left: 1px solid var(--edge-soft); padding-left: 16px; }
table.ab th.grp { border-left: 1px solid var(--edge-soft); padding-left: 16px; }
table.ab td.out { color: var(--kill); }
table.ab td.line { color: var(--cue); }
table.ab td.none, table.ab td.fld.none { color: var(--unclaimed); }
table.ab tbody tr:hover td { background: var(--panel-hi); }

.bands { padding: 8px 15px 12px; display: flex; flex-direction: column; }
.bhead, .bnd { display: grid; grid-template-columns: 84px 1fr 54px 54px 54px; gap: 10px;
               text-align: right; }
.bhead { font-size: 9px; letter-spacing: 0.2em; color: var(--dim); padding-bottom: 8px;
         border-bottom: 1px solid var(--edge); text-transform: uppercase; }
.bhead span:first-child, .bhead span:nth-child(2) { text-align: left; }
.bnd { align-items: center; padding: 3px 0; border-bottom: 1px solid var(--edge-soft);
       flex: 1 1 auto; }
.bnd:last-child { border-bottom: none; }
.bl { font-size: 11px; color: var(--dim); text-align: left; }
.bar2 { position: relative; height: 11px; background: var(--bg);
        border: 1px solid var(--edge-soft); border-radius: 2px; overflow: hidden; }
.bar2 i { position: absolute; left: 0; display: block; }
.sb { top: 1px; height: 4px; background: var(--src); }
.mb { bottom: 1px; height: 4px; background: var(--mst); }
.bv { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 11.5px;
      color: var(--muted); }
.bnd .bv.s { color: var(--dim); }
.bd { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 11.5px;
      color: var(--faint); }
.hold, .hold b, .hold .bv, .hold .bd { color: var(--faint); }
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


def controls(files: list[str], targets: list[str], chosen_file: str, chosen_target: str,
             writes_into: str = "") -> str:
    def options(values, chosen):
        out = []
        for value in values:
            mark = " selected" if value == chosen else ""
            out.append(f"<option value=\"{escape(value)}\"{mark}>{escape(value)}</option>")
        return "".join(out)

    written = ""
    if writes_into:
        written = ("<div class=\"control\"><label>Output</label>"
                   f"<span class=\"said\">{escape(writes_into)}</span></div>")
    return (
        "<form class=\"controls\" method=\"get\" action=\"/\">"
        "<div class=\"control grow\"><label for=\"what\">File or folder</label>"
        f"<select id=\"what\" name=\"what\">{options(files, chosen_file)}</select></div>"
        "<div class=\"control\"><label for=\"target\">Target</label>"
        f"<select id=\"target\" name=\"target\">{options(['none'] + targets, chosen_target)}"
        "</select></div>" + written +
        "<button class=\"reads\" type=\"submit\">Measure</button>"
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
WAVE_HEIGHT = 56
WAVE_WIDTH = 1000
FIGURES = (("lufs", "loudness.integrated_lufs"), ("dbtp", "loudness.true_peak_dbtp"),
           ("crest", "levels.crest_db"))


def _wave(shape: list, master_side: bool) -> str:
    """A picture of the file, drawn from the samples that were written. Nothing reads
    it back and no verdict rests on it, which is why it is the only thing on this page
    that is allowed to be a shape rather than a number."""
    middle = WAVE_HEIGHT / 2.0
    if not shape:
        return (f"<svg class=\"wave{' m' if master_side else ''}\" viewBox=\"0 0 "
                f"{WAVE_WIDTH} {WAVE_HEIGHT}\" preserveAspectRatio=\"none\"></svg>")
    step = WAVE_WIDTH / len(shape)
    top = " ".join(f"{i * step:.1f},{middle - v * middle:.1f}" for i, v in enumerate(shape))
    bottom = " ".join(f"{i * step:.1f},{middle + v * middle:.1f}"
                      for i, v in reversed(list(enumerate(shape))))
    return (f"<svg class=\"wave{' m' if master_side else ''}\" viewBox=\"0 0 "
            f"{WAVE_WIDTH} {WAVE_HEIGHT}\" preserveAspectRatio=\"none\">"
            f"<path d=\"M{top} L{bottom} Z\"></path></svg>")


def _figures(measurement: dict) -> str:
    out = []
    for unit, path in FIGURES:
        field = fields.BY_PATH.get(path)
        out.append(f"<span><i>{escape(unit)}</i>"
                   f"{number(compare.dig(measurement, path), field.decimals if field else 1)}"
                   "</span>")
    return "".join(out)


def _side(name: str, side: dict, master_side: bool) -> str:
    klass = "m" if master_side else "s"
    figures = _figures(side.get("measurement", {})) if side else ""
    return (f"<div class=\"wv\"><div class=\"wh\"><b class=\"{klass}\">{escape(name)}</b>"
            f"<span class=\"figs\">{figures}</span></div>"
            + _wave(side.get("waveform") or [], master_side) + "</div>")


def _plan_cell(label: str, value: str, quiet: bool = False) -> str:
    return (f"<div class=\"pc{' q' if quiet else ''}\"><span>{escape(label)}</span>"
            f"<b>{value}</b></div>")


def _signed(value, decimals: int) -> str:
    if value is None:
        return number(None, decimals)
    return f"{value:+.{decimals}f}"


def plan_strip(result: dict) -> str:
    """Seven numbers across the top, in the order the layer decides them."""
    built = result.get("plan") or {"steps": []}
    gain = _step(built, "gain")
    cut = _step(built, "low cut")
    squash = _step(built, "limiter")
    after = (result.get("after") or {}).get("measurement", {})
    predicted = built.get("predicted") or {}

    ceiling = None
    for row in ((result.get("after") or {}).get("comparison") or {}).get("rows", []):
        if row["field"] == "loudness.true_peak_dbtp" and row.get("bound"):
            ceiling = row["bound"].get("max")

    setting = number(None, 1)
    if squash:
        setting = f"{squash['attack_ms']:g} / {squash['release_ms']:g}"
    return (
        "<div class=\"plan\">"
        + _plan_cell("gain", _signed(gain["db"] if gain else None, 2))
        + _plan_cell("low cut", f"{cut['hz']:.0f}" if cut else number(None, 0))
        + _plan_cell("ceiling", number(ceiling, 2))
        + _plan_cell("limiter", setting)
        + _plan_cell("reduction", number(
            squash["gain_reduction"]["largest_db"] if squash else None, 2))
        + _plan_cell("predicted", number(predicted.get("integrated_lufs"), 2), quiet=True)
        + _plan_cell("measured", number(
            compare.dig(after, "loudness.integrated_lufs"), 2), quiet=True)
        + "</div>"
    )


def _step(built: dict, correction: str):
    for one in built.get("steps", []):
        if one["correction"] == correction:
            return one
    return None


def _ab_row(field: str, was: dict, now: dict) -> str:
    one = fields.BY_PATH.get(field)
    decimals = one.decimals if one else 3
    unit = one.unit if one else ""
    bound = now.get("bound") or {}
    shown = _bound_text(bound) if bound else ""
    delta = None
    if was.get("value") is not None and now.get("value") is not None:
        delta = round(now["value"] - was["value"], decimals)
    advisory = now.get("advisory") or now["verdict"] in (compare.NO_TARGET, compare.NOT_MEASURED)
    was_class = "none" if advisory else VERDICT_CLASS.get(was.get("verdict"), "")
    now_class = "none" if advisory else VERDICT_CLASS.get(now.get("verdict"), "")
    dev = "" if advisory else (number(now.get("deviation"), decimals)
                               if now["verdict"] != compare.INSIDE else "")
    return (
        f"<tr><td class=\"fld{' none' if advisory else ''}\">"
        f"{escape(fields.name_of(field))}</td>"
        f"<td class=\"{was_class}\">{number(was.get('value'), decimals)}</td>"
        f"<td class=\"{now_class}\">{number(now.get('value'), decimals)}</td>"
        f"<td class=\"d\">{_signed(delta, decimals)}</td>"
        f"<td class=\"u\">{escape(unit)}</td>"
        f"<td class=\"t grp\">{escape(shown)}</td>"
        f"<td class=\"dev {now_class}\">{dev}</td></tr>"
    )


def against_panel(result: dict) -> str:
    was = {r["field"]: r for r in (result["before"]["comparison"]).get("rows", [])}
    rows = []
    for row in result["after"]["comparison"].get("rows", []):
        if row["field"].startswith("spectral.band_pct."):
            continue
        rows.append(_ab_row(row["field"], was.get(row["field"], {}), row))
    return (
        "<div class=\"card\"><div class=\"ch\"><h3>Source against master</h3></div>"
        "<table class=\"ab\"><thead><tr><th class=\"l\">Field</th><th>Source</th>"
        "<th>Master</th><th>Delta</th><th></th><th class=\"grp\">Target</th>"
        "<th class=\"dev\">Off by</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


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
        label = one.short if one else key
        decimals = one.decimals if one else 2
        rows.append(
            "<div class=\"bnd\">"
            f"<span class=\"bl\">{escape(label)}</span>"
            f"<span class=\"bar2\"><i class=\"sb\" style=\"width:{100.0 * source['pct'] / top:.1f}%\"></i>"
            f"<i class=\"mb\" style=\"width:{100.0 * made['pct'] / top:.1f}%\"></i></span>"
            f"<span class=\"bv s\">{number(source['pct'], decimals)}</span>"
            f"<span class=\"bv\">{number(made['pct'], decimals)}</span>"
            f"<span class=\"bd\">{_signed(round(made['pct'] - source['pct'], decimals), decimals)}</span>"
            "</div>")
    return (
        "<div class=\"card\"><div class=\"ch\"><h3>Spectral balance</h3></div>"
        "<div class=\"bands\"><div class=\"bhead\"><span>Band</span><span></span>"
        "<span>Source</span><span>Master</span><span>Delta</span></div>"
        f"{''.join(rows)}</div></div>"
    )


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
        if not row.get("why"):
            continue
        said.append(f"<li><b>{escape(fields.name_of(row['field']))}</b> carries no verdict. "
                    f"{escape(sentence(row['why']))}.</li>")

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
    return ("<div class=\"card\"><div class=\"ch\"><h3>What it did</h3></div>"
            f"<div class=\"bands\">{_plan_items(result['plan'])}"
            f"<ul class=\"reasons\">{''.join(said)}</ul></div></div>")


def master_view(result: dict) -> str:
    """One file: the plan across the top, the two waveforms stacked under it, and the
    field table beside the spectral balance."""
    name = Path(result["input"]).name
    return (
        "<div class=\"card\"><div class=\"ch\"><h3>Plan</h3>"
        f"<span class=\"where\">{escape(name)} into {escape(str(Path(result['output']).parent))}"
        "</span></div>" + plan_strip(result) + "</div>"
        "<div class=\"card\">"
        + _side("source", result["before"], False)
        + _side("master", result["after"], True) +
        "</div>"
        f"<div class=\"split\">{against_panel(result)}{bands_panel(result)}</div>"
        + _notes(result)
    )


def waiting_view(name: str) -> str:
    """The same shape with nothing in it yet, so the page does not jump when the run
    lands. Every card here is the size of the card that replaces it."""
    empty_rows = "".join(
        "<tr><td class=\"fld\"></td><td></td><td></td><td class=\"d\"></td>"
        "<td class=\"u\"></td><td class=\"t grp\"></td><td class=\"dev\"></td></tr>"
        for _ in range(8))
    empty_bands = "".join("<div class=\"bnd\"><span class=\"bl\"></span>"
                          "<span class=\"bar2\"></span><span class=\"bv\"></span>"
                          "<span class=\"bv\"></span><span class=\"bd\"></span></div>"
                          for _ in range(10))
    cells = "".join(_plan_cell(label, number(None, 2), quiet=label in ("predicted", "measured"))
                    for label in ("gain", "low cut", "ceiling", "limiter", "reduction",
                                  "predicted", "measured"))
    return (
        "<div class=\"card hold\"><div class=\"ch\"><h3>Plan</h3>"
        f"<span class=\"where\">{escape(name)}</span></div>"
        f"<div class=\"plan\">{cells}</div></div>"
        "<div class=\"card hold\">"
        "<div class=\"wv hold\"><div class=\"wh\"><b class=\"s\">source</b></div>"
        + _wave([], False) + "</div>"
        "<div class=\"wv hold\"><div class=\"wh\"><b class=\"m\">master</b></div>"
        + _wave([], True) + "</div></div>"
        "<div class=\"split\">"
        "<div class=\"card hold\"><div class=\"ch\"><h3>Source against master</h3></div>"
        "<table class=\"ab\"><thead><tr><th class=\"l\">Field</th><th>Source</th>"
        "<th>Master</th><th>Delta</th><th></th><th class=\"grp\">Target</th>"
        f"<th class=\"dev\">Off by</th></tr></thead><tbody>{empty_rows}</tbody></table></div>"
        "<div class=\"card hold\"><div class=\"ch\"><h3>Spectral balance</h3></div>"
        "<div class=\"bands\"><div class=\"bhead\"><span>Band</span><span></span>"
        "<span>Source</span><span>Master</span><span>Delta</span></div>"
        f"{empty_bands}</div></div></div>"
    )


def mastering_view(job: dict) -> str:
    """A run in progress or a run that finished, in one view. While it works the page
    reloads itself, so what is on screen is what has actually been written."""
    if job.get("refused"):
        return ("<div class=\"card\"><div class=\"ch\"><h3>Not started</h3></div>"
                f"<div class=\"bands\"><p>{escape(sentence(job['refused']))}.</p></div></div>")

    if job.get("failure"):
        return ("<div class=\"card\"><div class=\"ch\"><h3>Stopped</h3></div>"
                "<div class=\"bands\"><p>The run stopped on an error.</p>"
                f"<pre>{escape(job['failure'])}</pre></div></div>")

    done, failed = job["done"], job["failed"]
    arrived = sum(1 for one in done if one["reached"]["arrived"])
    if job["running"]:
        at = job.get("at") or ""
        of = f" of {job['total']}" if job["total"] else ""
        said = (f"{job['finished']}{of} finished, {arrived} inside the target. "
                + (f"Working on {escape(at)}. " if at else "")
                + "This page keeps itself up to date.")
    else:
        said = (f"{len(done)} file" + ("" if len(done) == 1 else "s") +
                f" written, {arrived} of them inside the target on loudness and true peak.")

    head = ("<div class=\"card\"><div class=\"ch\">"
            f"<h3>{'Mastering' if job['running'] else 'Mastered'} "
            f"{escape(str(job['what']))}</h3>"
            f"<span class=\"where\">{escape(str(job['out_dir']))}</span></div>"
            f"<div class=\"bands\"><p>{said}</p>{key()}</div></div>")

    refused = ""
    if failed:
        items = "".join(f"<li><b>{escape(one['name'])}</b> {escape(sentence(one['why']))}.</li>"
                        for one in failed)
        refused = ("<div class=\"card\"><div class=\"ch\"><h3>Not mastered</h3></div>"
                   f"<div class=\"bands\"><ul class=\"reasons\">{items}</ul></div></div>")

    blocks = "".join(master_view(one) for one in done)
    if job["running"]:
        blocks += waiting_view(job.get("at") or str(job["what"]))
    return head + refused + blocks
