import os
from collections import Counter
from pathlib import Path

import pytest

from format_converters.dez import DezLabel, read_dez, to_tilia_rows

FIXTURES = Path(__file__).parent / "fixtures" / "dez"
DEZ = FIXTURES / "K279-1_texture.dez"
MM = FIXTURES / "K279-1.mm.json"


@pytest.fixture(scope="module")
def labels():
    return read_dez(DEZ)


def of_type(labels, t):
    return [lab for lab in labels if lab.type == t]


def test_counts(labels):
    assert len(labels) == 134
    assert Counter(lab.type for lab in labels) == {"Texture": 100, "Structure": 9, "Positive Feedback": 25}
    assert isinstance(labels[0], DezLabel)
    assert "start" not in labels[0].raw and labels[0].start == 0
    assert labels[0].comment == ""


def test_structure_levels(labels):
    rows = to_tilia_rows(of_type(labels, "Structure"), MM, "hierarchy")
    assert len(rows) == 9
    by_level = {}
    for r in rows:
        by_level.setdefault(r["level"], []).append(r["label"])
    assert sorted(by_level[2]) == ["Development", "Exposition", "Recapitulation"]
    assert sorted(by_level[1]) == sorted(["First subject", "Transition", "Second subject"] * 2)


def test_row_counts(labels):
    texture = of_type(labels, "Texture")
    assert len(to_tilia_rows(texture, MM, "marker")) == 100
    ranges = to_tilia_rows(texture, MM, "range")
    assert len(ranges) == 100
    assert {r["row"] for r in ranges} == {"Texture"}


def test_marker_positions(labels):
    # 4/4 throughout: quarter q is in bar q // 4 + 1 at fraction (q % 4) / 4
    texture = of_type(labels, "Texture")
    for lab, row in zip(texture, to_tilia_rows(texture, MM, "marker")):
        q = lab.start
        assert row["measure"] == q // 4 + 1
        assert row["fraction"] == float(q % 4) / 4
        assert row["label"] == lab.tag


def test_exposition_end(labels):
    exposition = next(lab for lab in labels if lab.tag == "Exposition")
    row = to_tilia_rows([exposition], MM, "range")[0]
    assert (row["start"], row["start_fraction"]) == (1, 0.0)
    assert (row["end"], row["end_fraction"]) == (38, 0.625)


def test_end_on_measure_boundary_and_end_of_piece():
    mm = [{"number": n, "qstamp": 4.0 * (n - 1), "actual_length": 4.0} for n in (1, 2, 3)]
    one = DezLabel("T", "a", 0, 4, None, "", {})
    last = DezLabel("T", "b", 8, 4, None, "c", {})
    assert to_tilia_rows([one], mm, "range")[0]["end"] == 1
    assert to_tilia_rows([one], mm, "range")[0]["end_fraction"] == 1.0
    row = to_tilia_rows([last], mm, "hierarchy")[0]
    assert (row["end"], row["end_fraction"], row["comments"]) == (3, 1.0, "c")
    with pytest.raises(ValueError, match="b"):
        to_tilia_rows([DezLabel("T", "b", 12, 0, None, "", {})], mm, "marker")


def test_whole_fixture_end_of_piece(labels):
    last = DezLabel("T", "end", 396, 4, None, "", {})
    row = to_tilia_rows([last], MM, "range")[0]
    assert (row["end"], row["end_fraction"]) == (100, 1.0)


def test_equal_spans_share_a_level_and_nesting():
    mm = [{"number": n, "qstamp": 4.0 * (n - 1), "actual_length": 4.0} for n in (1, 2, 3)]
    ls = [DezLabel("S", t, s, d, None, "", {}) for t, s, d in
          [("all", 0, 12), ("a", 0, 4), ("a2", 0, 4), ("b", 4, 8), ("b1", 4, 4)]]
    levels = {r["label"]: r["level"] for r in to_tilia_rows(ls, mm, "hierarchy")}
    assert levels == {"all": 3, "a": 1, "a2": 1, "b": 2, "b1": 1}


def test_bad_kind(labels):
    with pytest.raises(ValueError):
        to_tilia_rows(labels, MM, "csv")


@pytest.mark.skipif("DEZRANN_MOZART" not in os.environ, reason="DEZRANN_MOZART is not set")
def test_whole_release():
    root = Path(os.environ["DEZRANN_MOZART"])
    files = sorted((root / "analysis").glob("*.dez"))
    assert files
    for dez in files:
        mm = root / "measure-map" / f"{dez.name.split('_')[0]}.mm.json"
        labs = read_dez(dez)
        for t in {lab.type for lab in labs}:
            sub = of_type(labs, t)
            for kind in ("hierarchy", "marker", "range"):
                assert len(to_tilia_rows(sub, mm, kind)) == len(sub), (dez.name, t, kind)
