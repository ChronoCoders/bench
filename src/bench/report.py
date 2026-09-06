"""Text output. Formats what it is given and decides nothing."""

from __future__ import annotations

from pathlib import Path

from bench import compare, fields, toolchain

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


def bound_shown(bound: dict | None) -> str:
    if not bound:
        return BLANK
    if "max" in bound:
        return f"at most {bound['max']}"
    return f"{bound['low']} to {bound['high']}"


def comparison_table(result: dict) -> str:
    evidence = result["target"]["evidence"]
    out = [f"Target {result['target']['name']}, band set {result['target']['band_set']}, "
           f"from {evidence['n']} reference" + ("s" if evidence["n"] != 1 else "")]
    if evidence.get("all_sources_lossy"):
        out.append("Every reference is lossy. Fields that a lossy source cannot support are "
                   "listed at the bottom without a bound.")
    if result.get("toolchain_differs"):
        out.append(toolchain.sentence(result["toolchain_differs"]))
    out.append("")

    placed = [r for r in result["rows"]
              if r["verdict"] != compare.NO_TARGET and not r.get("advisory")]
    header = ["field", "value", "plus minus", "target", "deviation", "verdict"]
    body = []
    for row in placed:
        bound = row.get("bound") or {}
        shown = bound_shown(bound) if bound else BLANK
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


def _decimals(field: str) -> int:
    found = fields.BY_PATH.get(field)
    return found.decimals if found else 3


def _placed(comparison: dict) -> dict:
    return {row["field"]: row for row in comparison["rows"]
            if row["verdict"] != compare.NO_TARGET and not row.get("advisory")}


def _applied(plan: dict) -> list[str]:
    out = []
    for one in plan["steps"]:
        if one["correction"] == "low cut":
            out.append(f"  Low cut at {one['hz']:.0f} Hz, order {one['order']}.")
            out.append(f"    Applied because {one['from']}.")
            if "moved_bands_by_pct" in one:
                out.append(f"    Moved the bands above it by at most "
                           f"{one['moved_bands_by_pct']} points.")
        elif one["correction"] == "gain":
            out.append(f"  Gain {one['db']:+.3f} dB, set by {one['bound_by']}.")
            out.append(f"    Aimed {one['from']}.")
            if "corrected_by_db" in one:
                out.append(f"    Of that, {one['corrected_by_db']:+.3f} dB is a correction: "
                           f"{one['correction_from']}.")
        elif one["correction"] == "limiter":
            out.append(f"  Limiter to {one['ceiling_dbtp']} dBTP, attack "
                       f"{one['attack_ms']} ms, release {one['release_ms']} ms.")
            out.append(f"    Chosen because {one['chosen_from']}.")
            worked = one["gain_reduction"]
            out.append(f"    Took at most {worked['largest_db']} dB off. "
                       f"{worked['share_over_the_ceiling'] * 100:.2f} percent of the file "
                       "was over the ceiling before it ran.")
            if worked.get("constant_trim_db"):
                out.append("    The envelope missed the ceiling and a constant "
                           f"{worked['constant_trim_db']} dB was taken after it.")
            out.append(f"    Moved the widest band by {one['largest_band_move_pct']} points, "
                       + ("more" if one["balance_moved_more_than_measurement_resolution"]
                          else "less") + " than this measurement can resolve.")
            if one.get("at_search_edge"):
                out.append(f"    {one['at_search_edge'][0].upper()}{one['at_search_edge'][1:]}.")
            if "why_it_stopped" in one:
                out.append(f"    {one['why_it_stopped']}")
    return out


def master_table(result: dict) -> str:
    """Before and after, in the same words and against the same target as the folder
    table. What was applied is quoted from the plan, not restated."""
    before, after = _placed(result["before"]["comparison"]), _placed(result["after"]["comparison"])
    header = ["field", "before", "was", "after", "now", "target"]
    body = []
    for field, row in after.items():
        was = before.get(field, {})
        decimals = _decimals(field)
        body.append([fields.name_of(field),
                     _cell(was.get("value"), decimals), was.get("verdict", BLANK),
                     _cell(row.get("value"), decimals), row["verdict"],
                     bound_shown(row.get("bound"))])

    widths = _widths(header, body)
    out = [f"Mastered {Path(result['input']).name}",
           f"  read    {result['input']}",
           f"  written {result['output']}",
           ""]
    out.append(_line(header, widths))
    out.append(_line(["-" * len(h) for h in header], widths))
    out += [_line(row, widths) for row in body]

    moved = [row[0] for row in body if row[2] != row[4]]
    out.append("")
    out.append("Changed verdict: " + (", ".join(moved) if moved else "none"))

    steps = _applied(result["plan"])
    if steps:
        out += ["", "Applied"] + steps
    if result["plan"]["not_applied"]:
        out += ["", "Not applied"]
        for one in result["plan"]["not_applied"]:
            out.append(f"  {one['correction'].capitalize()}. {one['why'][0].upper()}"
                       f"{one['why'][1:]}.")

    tags = result.get("tags")
    if tags:
        out += ["", "What the file says about itself"]
        for name, value in tags["written"].items():
            out.append(f"  {name}: {value}")
        out.append("  Read back off the file: " + ("it holds." if tags["held"]
                                                   else "that is not what it says."))
        for name, value in tags.get("came_back_different", {}).items():
            out.append(f"    {name} came back as {value!r}")
        for name, value in tags.get("not_asked_for", {}).items():
            out.append(f"    {name} is there and was not asked for: {value!r}")

    landed = result["reached"]
    out += ["", "Where it landed"]
    for field, one in landed["fields"].items():
        if "value" not in one:
            out.append(f"  {fields.name_of(field)}: not measured on the output.")
            continue
        out.append(f"  {fields.name_of(field)}: {one['value']} plus or minus "
                   f"{one['uncertainty']}, {one['verdict']}"
                   + (f", off by {one['deviation']}." if one["deviation"] else "."))
    out.append("  Arrived: " + ("yes" if landed["arrived"] else "no"))

    held = result["prediction"]
    if held.get("checked"):
        out += ["", f"What the plan predicted, checked against {held['against']}"]
        for name, one in held["fields"].items():
            if not one.get("held") and "why" in one:
                out.append(f"  {name}: {one['why']}")
                continue
            out.append(f"  {name}: said {one['predicted']}, measured {one['measured']}, "
                       f"apart by {one['gap']} against {one['uncertainty']} allowed. "
                       + ("Held." if one["held"] else "Did not hold."))
    return "\n".join(out)
