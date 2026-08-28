"""HTML output. Formats what it is given and decides nothing.

No request leaves the page. Fonts are the ones already on the machine.
"""

from __future__ import annotations

from html import escape

from bench import compare, fields, typeface

STYLE = """
:root {
  --bg: #08090c; --panel: #14161c; --panel-hi: #1b1e26;
  --edge: #2a2f3a; --edge-hi: #3a4150;
  --text: #c7ccd6; --dim: #6b7280; --faint: #454b57;
  --accent: #34e7de; --play: #3ee87a; --cue: #ffb020; --kill: #ff4d5e;
  --mono: 'JetBrains Mono', ui-monospace, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  min-height: 100%;
  background: radial-gradient(1200px 700px at 50% -10%, #12151b 0%, var(--bg) 60%) fixed;
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
table { border-collapse: collapse; width: 100%; }
th, td { padding: 7px 16px; border-bottom: 1px solid var(--edge); white-space: nowrap; }
th:first-child, td:first-child { width: 1%; padding-left: 0; }
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


def document(title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{escape(title)}</title>"
        f"<style>{typeface.css()}</style><style>{STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>\n"
    )


def number(value, decimals: int) -> str:
    if value is None:
        return "<span class=\"blank\">.</span>"
    return f"{value:.{decimals}f}"


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
        "<button type=\"submit\">Measure</button></form>"
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


KEY = (("var(--kill)", "outside the target"), ("var(--cue)", "on the line"))


def key() -> str:
    marks = "".join(f"<span><i style=\"background:{colour}\"></i>{escape(text)}</span>"
                    for colour, text in KEY)
    return (f"<div class=\"key\">{marks}"
            "<span class=\"unmarked\">unmarked is inside the target</span></div>")


def folder_view(sheet: dict) -> str:
    columns = sheet["columns"]
    head = "".join(f"<th>{escape(c['label'])}</th>" for c in columns)
    rows = []
    for row in sheet["files"]:
        verdicts = row.get("verdicts", {})
        cells = []
        for c in columns:
            klass = VERDICT_CLASS.get(verdicts.get(c["path"]), "")
            mark = f' class="{klass}"' if klass else ""
            cells.append(f"<td{mark}>{number(row['values'][c['path']], c['decimals'])}</td>")
        rows.append(f"<tr><td class=\"name\">{escape(row['name'])}</td>{''.join(cells)}</tr>")

    spread, over = [], []
    for c in columns:
        found = sheet["spread"][c["path"]]
        spread.append("<td>" + ("<span class=\"blank\">.</span>" if "withheld" in found
                                else number(found.get("spread"), c["decimals"])) + "</td>")
        over.append("<td>" + ("" if found["n"] == 0 else str(found["n"])) + "</td>")

    notes = []
    for c in columns:
        found = sheet["spread"][c["path"]]
        if "withheld" in found:
            notes.append(f"<li><b>{escape(c['label'])}</b> has no spread. "
                         f"{escape(found['withheld'])}.</li>")
    partial = [c["label"] for c in columns if "withheld" not in sheet["spread"][c["path"]]
               and 0 < sheet["spread"][c["path"]]["n"] < len(sheet["files"])]
    if partial:
        notes.append("<li><b>" + escape(", ".join(partial)) +
                     "</b> covers fewer files than the folder holds. The row below the spread "
                     "says how many.</li>")
    for skip in sheet["skipped"]:
        notes.append(f"<li><b>{escape(skip['name'])}</b> could not be read. "
                     f"{escape(skip['why'])}</li>")

    graded = any(row.get("verdicts") for row in sheet["files"])
    return (
        f"<div class=\"head\"><h1>{escape(sheet['folder'])}</h1>"
        f"<span class=\"meta\">{len(sheet['files'])} files</span></div>"
        + (key() if graded else "")
        + f"<table><thead><tr><th>Track</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody>"
        + f"<tfoot><tr class=\"pause\"><td colspan=\"{len(columns) + 1}\"></td></tr>"
        f"<tr class=\"spread\"><td>Spread</td>{''.join(spread)}</tr>"
        f"<tr class=\"over\"><td>Over</td>{''.join(over)}</tr></tfoot></table>"
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
                    f"{escape(row.get('why', ''))}</li>")
    for row in result["rows"]:
        if row["verdict"] != compare.NO_TARGET:
            continue
        field = fields.BY_PATH.get(row["field"])
        shown = number(row.get("value"), field.decimals if field else 3)
        gaps.append(f"<li><b>{escape(fields.name_of(row['field']))}</b> measures {shown}, "
                    f"and has no target. {escape(row['why'])}</li>")
    for row in result["rows"]:
        if row["verdict"] == compare.NOT_MEASURED:
            gaps.append(f"<li><b>{escape(fields.name_of(row['field']))}</b> could not be "
                        f"placed. {escape(row['why'])}</li>")

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
                           f"{escape(found['unmeasurable'])}</li>")
        for name, why in (found.get("absent_because") or {}).items():
            missing.append(f"<li><b>{escape(fields.name_of(f'{block}.{name}'))}</b> is not "
                           f"reported. {escape(why)}</li>")
        for caveat in found.get("caveats", []):
            missing.append(f"<li><b>{escape(block.title())}</b>: {escape(caveat)}.</li>")

    body = (
        f"<div class=\"head\"><h1>{escape(measurement.get('file', {}).get('name', 'file'))}</h1>"
        f"<span class=\"meta\">{escape(meta)}</span></div>"
        f"<h2>Measured</h2><table><tbody>{''.join(rows)}</tbody></table>"
        + (f"<ul class=\"reasons\">{''.join(missing)}</ul>" if missing else "")
        + spectrum(measurement, target)
    )
    if result is not None:
        body += comparison_view(result)
    return body
