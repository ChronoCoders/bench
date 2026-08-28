"""Text output. Formats what it is given and decides nothing."""

from __future__ import annotations

from bench import compare

BLANK = ""
GAP = 2


def _cell(value, decimals: int) -> str:
    return BLANK if value is None else f"{value:.{decimals}f}"


def _widths(header: list[str], rows: list[list[str]]) -> list[int]:
    return [max(len(header[i]), *(len(r[i]) for r in rows)) if rows else len(header[i])
            for i in range(len(header))]


def _line(cells: list[str], widths: list[int], first_left: bool = True) -> str:
    out = []
    for i, (cell, width) in enumerate(zip(cells, widths)):
        out.append(cell.ljust(width) if i == 0 and first_left else cell.rjust(width))
    return (" " * GAP).join(out).rstrip()


def folder_table(sheet: dict) -> str:
    columns = sheet["columns"]
    header = ["track"] + [c["label"] for c in columns]
    body = []
    for row in sheet["files"]:
        body.append([row.get("label", row["name"])] +
                    [_cell(row["values"][c["path"]], c["decimals"]) for c in columns])

    spread_cells, note_cells = ["spread"], ["files"]
    for c in columns:
        found = sheet["spread"][c["path"]]
        spread_cells.append(BLANK if "withheld" in found
                            else _cell(found.get("spread"), c["decimals"]))
        note_cells.append(BLANK if found["n"] == 0 else str(found["n"]))

    widths = _widths(header, body + [spread_cells, note_cells])
    out = [_line(header, widths), _line(["-" * len(h) for h in header], widths)]
    out += [_line(r, widths) for r in body]
    out.append(_line(["-" * len(h) for h in header], widths))
    out.append(_line(spread_cells, widths))
    out.append(_line(note_cells, widths))

    for c in columns:
        found = sheet["spread"][c["path"]]
        if "withheld" in found:
            out.append("")
            out.append(f"No spread for {c['label']}: {found['withheld']}")
    partial = [c["label"] for c in columns
               if "withheld" not in sheet["spread"][c["path"]]
               and 0 < sheet["spread"][c["path"]]["n"] < len(sheet["files"])]
    if partial:
        out.append("")
        out.append("Spread taken over fewer files than the folder holds: " + ", ".join(partial))
    empty = [c["label"] for c in columns if sheet["spread"][c["path"]]["n"] == 0]
    if empty:
        out.append("No file in this folder has a value for: " + ", ".join(empty))
    for skip in sheet["skipped"]:
        out.append(f"Not read: {skip['name']}. {skip['why']}")
    return "\n".join(out)


def comparison_table(result: dict) -> str:
    evidence = result["target"]["evidence"]
    out = [f"Target {result['target']['name']}, band set {result['target']['band_set']}, "
           f"from {evidence['n']} reference" + ("s" if evidence["n"] != 1 else "")]
    if evidence.get("all_sources_lossy"):
        out.append("Every reference is lossy. Fields that a lossy source cannot support are "
                   "listed at the bottom without a bound.")
    out.append("")

    placed = [r for r in result["rows"]
              if r["verdict"] != compare.NO_TARGET and not r.get("advisory")]
    header = ["field", "value", "plus minus", "target", "deviation", "verdict"]
    body = []
    for row in placed:
        bound = row.get("bound") or {}
        if "max" in bound:
            shown = f"at most {bound['max']}"
        elif "low" in bound:
            shown = f"{bound['low']} to {bound['high']}"
        else:
            shown = BLANK
        body.append([
            row["field"],
            _cell(row.get("value"), 3),
            _cell(row.get("uncertainty"), 3),
            shown,
            _cell(row.get("deviation"), 3),
            row["verdict"],
        ])
    widths = _widths(header, body)
    out.append(_line(header, widths))
    out.append(_line(["-" * len(h) for h in header], widths))
    out += [_line(r, widths) for r in body]

    advisory = [r for r in result["rows"] if r.get("advisory")]
    if advisory:
        out.append("")
        out.append("Information, no verdict claimed:")
        for row in advisory:
            bound = row["bound"]
            shown = f"{bound['low']} to {bound['high']}" if "low" in bound else str(bound)
            out.append(f"  {row['field']} {_cell(row.get('value'), 3)} against {shown}")
            out.append(f"    {row.get('why', '')}")

    withheld = [r for r in result["rows"] if r["verdict"] == compare.NO_TARGET]
    if withheld:
        out.append("")
        out.append("No target for these, and the reason:")
        for row in withheld:
            value = _cell(row.get("value"), 3)
            out.append(f"  {row['field']} {value}".rstrip())
            out.append(f"    {row['why']}")

    unplaced = [r for r in placed if r["verdict"] == compare.NOT_MEASURED]
    if unplaced:
        out.append("")
        out.append("Could not be placed against the target:")
        for row in unplaced:
            out.append(f"  {row['field']}: {row['why']}")

    out.append("")
    on_the_line = result["counts"].get(compare.ON_THE_LINE, 0)
    if on_the_line:
        out.append(f"{on_the_line} field" + ("s" if on_the_line != 1 else "") +
                   " sit on a boundary once the measurement's own uncertainty is counted. "
                   "Those are not passes.")
    out.append("Every field inside its target: " + ("yes" if result["all_inside"] else "no"))
    return "\n".join(out)
