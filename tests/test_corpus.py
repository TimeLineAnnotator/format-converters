"""The whole corpus (112,826 chords of BPSD, Winterreise, DCML's Mozart sonatas and When in Rome)
against baseline.json.gz, the outcome of the research prototype for every chord.

The sources are downloaded into $FORMAT_CONVERTERS_CACHE (default ~/.cache/format-converters) on the
first run; the music21 parse of the RomanText files is cached there too. Nothing is stored in the repository.
"""
import collections

import pytest
from corpus import fetch, loaders, run


@pytest.fixture(scope="session")
def corpus():
    fetch.fetch_all()
    return run.run()


def test_nothing_raises_and_every_symbol_is_read_back_by_tilia(corpus):
    # a chord that raised is reported as a problem; so is a symbol TiLiA's parser does not read as stored
    assert not corpus["problems"][:10], corpus["problems"][:10]


def test_every_chord_of_the_baseline_is_translated_and_none_is_extra(corpus):
    assert not corpus["missing"][:10] and not corpus["extra"][:10]


def test_no_chord_is_worse_than_the_prototype(corpus):
    # the function rule may turn rn and letter into approx; nothing else may go down
    assert not corpus["worse"][:10], corpus["worse"][:10]


def test_no_source_has_more_none_than_the_baseline(corpus):
    for sid, refs in corpus["baseline"].items():
        base_none = sum(v.rstrip("*") == "none" for v in refs.values())
        assert corpus["counts"][sid]["none"] <= base_none, sid


def test_the_function_rule_stores_the_function_of_what_the_prototype_found_parses(corpus):
    assert corpus["function"]["dcml"] >= 1595
    assert corpus["function"]["cad64"] >= 1210


def test_source_ids_are_the_baseline_ones(corpus):
    assert set(corpus["counts"]) == set(corpus["baseline"])
    assert sum(sum(c.values()) for c in corpus["counts"].values()) == 112826


def test_counts_line_per_source_id(corpus):
    lines = run.format_counts(corpus["counts"])
    assert len(lines) == len(corpus["baseline"])
    assert all(l.split()[1].startswith("rn=") for l in lines)


def test_each_source_downloads_from_its_pinned_url(tmp_path):
    """The download path, on one file of each source (the rest of the run reads the cache)."""
    assert fetch.fetch_zip_members("bpsd", tmp_path, only=1) == 1
    assert fetch.fetch_zip_members("swd", tmp_path, only=1) == 1
    assert fetch.fetch_dcml(tmp_path, only=1) == 1
    assert fetch.fetch_wir(tmp_path, only=1) == 1
    first = collections.Counter(p.parent.name for p in tmp_path.rglob("*") if p.is_file())
    assert {"ann_score_chord", "dcml", "wir"} <= set(first)
    row = next(loaders.read_rows(next(tmp_path.glob("bpsd/ann_score_chord")), "*.csv", ";"))
    assert row[2]["roman"]
    row = next(loaders.read_rows(tmp_path / "dcml", "K*.harmonies.tsv", "\t"))
    assert row[2]["chord"]
    assert (tmp_path / "wir" / fetch.wir_fid(0)).read_text().strip()
