"""Master every file in a folder against a target, and print before and after.

Nothing is written over. The output folder has to be somewhere else, and a file that
is already there stops the run for that file rather than replacing it.

The table is printed and the same before and after view is written to mastered.html
in the output folder.

Run it: python tools/master_folder.py "path/to/folder" boom-bap "path/to/output"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bench import compare, fields, folder, master, page, report

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "targets"
PAGE = "mastered.html"

SUMMARY = ("loudness.integrated_lufs", "loudness.true_peak_dbtp", "levels.crest_db")


def _cell(value, decimals):
    return "" if value is None else f"{value:.{decimals}f}"


def audio_in(where: Path) -> list[Path]:
    return sorted(p for p in where.iterdir()
                  if p.is_file() and p.suffix.lower() in folder.AUDIO_SUFFIXES)


def summary_table(done: list[dict]) -> str:
    """One line per track, the three numbers a master is judged on, and the verdict
    count either side. The full field by field table is under each track."""
    header = ["track"]
    for path in SUMMARY:
        header += [f"{fields.get(path).short} before", "after"]
    header += ["inside", "on the line", "outside"]

    body = []
    for one in done:
        row = [Path(one["input"]).stem]
        for path in SUMMARY:
            decimals = fields.get(path).decimals
            row.append(_cell(compare.dig(one["before"]["measurement"], path), decimals))
            row.append(_cell(compare.dig(one["after"]["measurement"], path), decimals))
        counts = one["after"]["comparison"]["counts"]
        row.append(str(counts.get(compare.INSIDE, 0)))
        row.append(str(counts.get(compare.ON_THE_LINE, 0)))
        row.append(str(counts.get(compare.ABOVE, 0) + counts.get(compare.BELOW, 0)))
        body.append(row)

    widths = report._widths(header, body)
    out = [report._line(header, widths),
           report._line(["-" * len(h) for h in header], widths)]
    out += [report._line(row, widths) for row in body]
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    where, slug, out_dir = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    target = json.loads((TARGETS / f"{slug}.json").read_text(encoding="utf-8"))

    done, failed = master.run_each(audio_in(where), target, out_dir)
    for one in done:
        print(report.master_table(one))
        print()

    print()
    n = target["evidence"]["n"]
    print(f"Against {target['name']}, from {n} reference" + ("s" if n != 1 else ""))
    print()
    print(summary_table(done))
    for one in failed:
        print(f"\nNot mastered: {one['name']}. {one['why']}")
    if done:
        where = out_dir / PAGE
        where.write_text(page.document(
            f"Mastered against {target['name']}",
            "".join((page.master_view if len(done) == 1 else page.closed_view)(one)
                    for one in done)), encoding="utf-8")
        print()
        print(f"Page: {where}")
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
