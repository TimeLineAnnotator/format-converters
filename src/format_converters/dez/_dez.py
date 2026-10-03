import json
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

KINDS = ("hierarchy", "marker", "range")


@dataclass(frozen=True)
class DezLabel:
    type: str
    tag: str
    start: Fraction
    duration: Fraction
    line: "str | None"
    comment: str
    raw: dict

    @property
    def end(self):
        return self.start + self.duration


def _fraction(value):
    # str() keeps 0.1 as 1/10 instead of the binary float's long fraction
    return Fraction(str(value))


def read_dez(path):
    """The labels of a .dez file, in file order. A missing start or duration is 0."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        DezLabel(
            type=raw.get("type", ""),
            tag=raw.get("tag", ""),
            start=_fraction(raw.get("start", 0)),
            duration=_fraction(raw.get("duration", 0)),
            line=raw.get("line"),
            comment=raw.get("comment", ""),
            raw=raw,
        )
        for raw in data["labels"]
    ]


class _Bars:
    def __init__(self, measure_map):
        if isinstance(measure_map, (str, Path)):
            with open(measure_map, encoding="utf-8") as f:
                measure_map = json.load(f)
        self.measures = sorted(measure_map, key=lambda m: m["qstamp"])
        self.starts = [_fraction(m["qstamp"]) for m in self.measures]
        self.ends = [s + _fraction(m["actual_length"]) for s, m in zip(self.starts, self.measures)]

    def _locate(self, q, label):
        i = bisect_right(self.starts, q) - 1
        if i < 0 or q >= self.ends[i]:
            raise ValueError(f"position {q} of label {label.type} {label.tag!r} is outside the measure map")
        return i

    def start(self, q, label):
        i = self._locate(q, label)
        return self.measures[i]["number"], _round((q - self.starts[i]) / (self.ends[i] - self.starts[i]))

    def end(self, label):
        q = label.end
        if q > label.start:
            # an end on a measure's start is the end of the measure before it
            i = bisect_right(self.ends, q - 1) - 1
            for j in (i, i + 1):
                if 0 <= j < len(self.ends) and self.ends[j] == q:
                    return self.measures[j]["number"], 1.0
        if q > self.ends[-1]:
            # a few labels of the release run past the last bar: they end with the piece
            return self.measures[-1]["number"], 1.0
        return self.start(q, label)


def _round(fraction):
    return round(float(fraction), 6)


def _line_floors(labels):
    """Lowest level that the display line of each label asks for.

    Dezrann draws the levels of a hierarchy on lines of one stem ("bot.1" under "bot.2"), which also
    tells a section with no sub-section in the file (a Development) from the sub-sections.
    """
    stems = {}
    for lab in labels:
        stem, _, number = (lab.line or "").rpartition(".")
        if number.isdigit():
            stems.setdefault(stem, set()).add(int(number))
    floors = []
    for lab in labels:
        stem, _, number = (lab.line or "").rpartition(".")
        numbers = sorted(stems.get(stem, ())) if number.isdigit() else []
        floors.append(numbers.index(int(number)) + 1 if len(numbers) > 1 else 1)
    return floors


def _levels(labels):
    """Level of each label: 1 + the highest level among the labels whose span it strictly contains,
    and at least the rank of its display line. Labels with the same span share the higher level."""
    floor = {}
    for lab, f in zip(labels, _line_floors(labels)):
        span = (lab.start, lab.end)
        floor[span] = max(floor.get(span, 1), f)
    spans = sorted(floor, key=lambda s: s[1] - s[0])
    level = {}
    for i, (a, b) in enumerate(spans):
        inner = [level[s] for s in spans[:i] if a <= s[0] and s[1] <= b and s != (a, b)]
        level[(a, b)] = max(floor[(a, b)], 1 + max(inner, default=0))
    return [level[(lab.start, lab.end)] for lab in labels]


def to_tilia_rows(labels, measure_map, kind):
    """One row per label, with the columns of TiLiA's CSV import of `kind` by measure."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    bars = _Bars(measure_map)
    levels = _levels(labels) if kind == "hierarchy" else None
    rows = []
    for n, lab in enumerate(labels):
        measure, fraction = bars.start(lab.start, lab)
        if kind == "marker":
            rows.append({"measure": measure, "fraction": fraction, "label": lab.tag, "comments": lab.comment})
            continue
        end, end_fraction = bars.end(lab)
        row = {"start": measure, "start_fraction": fraction, "end": end, "end_fraction": end_fraction}
        if kind == "hierarchy":
            row["level"] = levels[n]
        else:
            row["row"] = lab.type
        row.update(label=lab.tag, comments=lab.comment)
        rows.append(row)
    return rows
