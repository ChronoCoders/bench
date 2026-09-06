"""A measurement against a target. Consumes structured data, produces structured data.

A target says where a field should sit. This layer says where the file sits against it,
and refuses to call anything passed when the measurement's own uncertainty reaches the
boundary.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from bench import toolchain

INSIDE = "inside"
ABOVE = "above"
BELOW = "below"
ON_THE_LINE = "on the line"
NO_TARGET = "no target"
NOT_MEASURED = "not measured"

VERDICTS_THAT_PASS = (INSIDE,)


class BandSetMismatch(ValueError):
    pass


class TargetError(ValueError):
    pass


def _refuse_constant(name: str):
    """json accepts bare NaN and Infinity by default. They are not JSON, and a bound
    made of one compares false against every measurement, which arrives as a verdict
    rather than as an error. Refused where the file is parsed, so a malformed target
    fails as a document rather than resting on the bound checks below to catch it."""
    def refuse(token: str):
        raise TargetError(
            f"target {name} contains {token}, which is not a number JSON can carry"
        )
    return refuse


def _bound_number(name: str, field: str, key: str, value) -> float:
    """A bound has to be a number, and a bool is not one. True would compare as 1.0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TargetError(
            f"target {name}: {field} gives {value!r} for {key!r}, which is a "
            f"{type(value).__name__} rather than a number"
        )
    if not math.isfinite(value):
        raise TargetError(
            f"target {name}: {field} gives {value!r} for {key!r}, which is not a bound"
        )
    return float(value)


def load(path: str | Path) -> dict:
    name = Path(path).name
    target = json.loads(Path(path).read_text(encoding="utf-8"),
                        parse_constant=_refuse_constant(name))
    for required in ("name", "band_set", "evidence", "fields"):
        if required not in target:
            raise TargetError(f"target {name} has no {required!r}")
    if "n" not in target["evidence"]:
        raise TargetError(f"target {name} does not say how many references it rests on")
    for section in ("fields", "limits"):
        for field, bound in target.get(section, {}).items():
            if "max" not in bound and not ("low" in bound and "high" in bound):
                raise TargetError(
                    f"target {name}: {field} must give either max, or both low and high")
            got = {key: _bound_number(name, field, key, bound[key])
                   for key in ("low", "high", "max") if key in bound}
            if "low" in got and "high" in got and got["low"] > got["high"]:
                raise TargetError(
                    f"target {name}: {field} gives low {got['low']} above high "
                    f"{got['high']}, and no measurement can be inside that"
                )
    for field, bound in target.get("limits", {}).items():
        if not bound.get("declared_by"):
            raise TargetError(f"target {name}: limit {field} must say who declared it")
    return target


def dig(measurement: dict, path: str):
    node = measurement
    for step in path.split("."):
        if not isinstance(node, dict) or step not in node:
            return None
        node = node[step]
    return node


def uncertainty_of(measurement: dict, path: str) -> float | None:
    module, _, rest = path.partition(".")
    leaf = rest.rsplit(".", 1)[-1]
    found = dig(measurement, f"{module}.uncertainty.{leaf}")
    return float(found) if isinstance(found, (int, float)) else None


def verdict(value: float, uncertainty: float, bound: dict) -> str:
    low, high = bound.get("low"), bound.get("high", bound.get("max"))
    if low is None:
        if value + uncertainty <= high:
            return INSIDE
        return ABOVE if value - uncertainty > high else ON_THE_LINE
    if value - uncertainty >= low and value + uncertainty <= high:
        return INSIDE
    if value - uncertainty > high:
        return ABOVE
    if value + uncertainty < low:
        return BELOW
    return ON_THE_LINE


def deviation(value: float, bound: dict) -> float:
    low, high = bound.get("low"), bound.get("high", bound.get("max"))
    if low is not None and value < low:
        return round(value - low, 4)
    if value > high:
        return round(value - high, 4)
    return 0.0


def against(measurement: dict, target: dict) -> dict:
    measured_set = dig(measurement, "spectral.band_set")
    if measured_set is not None and measured_set != target["band_set"]:
        raise BandSetMismatch(
            f"the file was measured under band set {measured_set!r} and the target "
            f"{target['name']!r} was built under {target['band_set']!r}. Percentages from "
            "different band edges are different quantities, so this comparison is refused."
        )

    rows = []
    seeded = [(f, b, "measured references") for f, b in target["fields"].items()]
    declared = [(f, b, "declared") for f, b in target.get("limits", {}).items()]
    for field, bound, basis in seeded + declared:
        value = dig(measurement, field)
        if not isinstance(value, (int, float)):
            rows.append({"field": field, "bound": bound, "basis": basis,
                         "verdict": NOT_MEASURED,
                         "why": dig(measurement, f"{field.split('.')[0]}.unmeasurable")
                         or "the file has no value for this field"})
            continue
        unit = uncertainty_of(measurement, field)
        if unit is None:
            rows.append({"field": field, "bound": bound, "basis": basis, "value": value,
                         "verdict": NOT_MEASURED,
                         "why": "this field reports no uncertainty, so it cannot be placed "
                                "against a boundary"})
            continue
        row = {
            "field": field,
            "bound": bound,
            "basis": basis,
            "value": value,
            "uncertainty": unit,
            "deviation": deviation(float(value), bound),
            "verdict": verdict(float(value), unit, bound),
            "from_lossy": bool(bound.get("from_lossy", False)),
            "advisory": bool(bound.get("advisory")),
        }
        if row["advisory"]:
            row["why"] = bound.get("advisory", "")
        rows.append(row)

    for field, why in target.get("withheld", {}).items():
        rows.append({"field": field, "verdict": NO_TARGET, "why": why,
                     "value": dig(measurement, field)})

    counts = {}
    for row in rows:
        if row.get("advisory"):
            continue
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return {
        "target": {"name": target["name"], "band_set": target["band_set"],
                   "evidence": target["evidence"]},
        "rows": rows,
        "counts": counts,
        "advisory": sum(1 for r in rows if r.get("advisory")),
        "all_inside": all(r["verdict"] in VERDICTS_THAT_PASS for r in judged(rows)),
        # Reported, never acted on. A different ffmpeg is a reason to look at a figure,
        # not a reason to refuse it, and a comparison refused on provenance would be a
        # tool that stops working every time something is upgraded.
        "toolchain_differs": toolchain.differences(
            measurement.get("toolchain"), target.get("evidence", {}).get("toolchain")),
    }


def judged(rows: list[dict]) -> list[dict]:
    """The rows a verdict is claimed for. Advisory bounds and gaps are not among them."""
    return [r for r in rows
            if not r.get("advisory") and r["verdict"] not in (NO_TARGET, NOT_MEASURED)]
