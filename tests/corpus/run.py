"""Translate every chord of the corpus, verify each symbol with TiLiA's parser, compare with the baseline."""
from __future__ import annotations

import collections
import gzip
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import fetch, loaders

HERE = Path(__file__).parent
OUTCOMES = ("rn", "letter", "approx", "none", "no_chord")
RANK = {"rn": 2, "letter": 2, "approx": 1, "none": 0}


def workers() -> int:
    return int(os.environ.get("FORMAT_CONVERTERS_WORKERS", min(4, os.cpu_count() or 1)))


def baseline() -> dict[str, dict[str, str]]:
    """source id -> {ref: prototype outcome, "*" appended where the function rule applies}."""
    with gzip.open(HERE / "baseline.json.gz", "rt") as f:
        return json.load(f)


def _translate(sig):
    """sig: (standard, label, key, truth) -> (outcome, problems). Runs in a worker process."""
    from format_converters._tilia import matches, parse_chord
    from format_converters.harmony import translate_chord

    standard, label, key, truth = sig
    try:
        r = translate_chord(label, standard, key, truth=truth)
    except Exception as exc:  # noqa: BLE001 the test reports it
        return "raised", [f"{type(exc).__name__}: {exc}"]
    problems = []
    if r.outcome in ("none", "no_chord"):
        if r.symbol is not None:
            problems.append(f"{r.outcome} with symbol {r.symbol!r}")
        return r.outcome, problems
    parsed = parse_chord(r.symbol, key)
    if parsed is None or r.params != parsed:
        problems.append(f"TiLiA does not read {r.symbol!r} under {key!r} as {r.params}")
    elif r.outcome in ("rn", "letter") and truth is not None and not matches(parsed, truth):
        problems.append(f"{r.symbol!r} is not the chord of {label!r}")
    return r.outcome, problems


def translate_all(items: list[dict]):
    """Per item (same order): the outcome; and a list of (item, problem)."""
    sigs = [(i["standard"], i["label"], i["key"], i["truth"]) for i in items]
    uniq = list(dict.fromkeys(sigs))
    n = workers()
    if n > 1:
        with ProcessPoolExecutor(n) as ex:
            res = dict(zip(uniq, ex.map(_translate, uniq, chunksize=64)))
    else:
        res = dict(zip(uniq, map(_translate, uniq)))
    outcomes = [res[s][0] for s in sigs]
    problems = [(it, p) for it, s in zip(items, sigs) for p in res[s][1]]
    return outcomes, problems


def run(cache: Path | None = None) -> dict:
    """The whole corpus. Returns counts per source id, the outcome of every chord, the comparison with
    the baseline (chords worse than it, refs that differ) and the verification problems."""
    items = loaders.all_items(cache, workers())
    outcomes, problems = translate_all(items)
    counts = collections.defaultdict(collections.Counter)
    by_ref = collections.defaultdict(dict)
    for it, out in zip(items, outcomes):
        counts[it["sid"]][out] += 1
        by_ref[it["sid"]][it["ref"]] = out
    base = baseline()
    worse, missing, extra, function = [], [], [], collections.Counter()
    for sid in sorted(set(base) | set(by_ref)):
        b, mine = base.get(sid, {}), by_ref.get(sid, {})
        missing += [f"{sid} {r}" for r in b.keys() - mine.keys()]
        extra += [f"{sid} {r}" for r in mine.keys() - b.keys()]
        for ref in b.keys() & mine.keys():
            want, star = b[ref].rstrip("*"), b[ref].endswith("*")
            got = mine[ref]
            if want == "no_chord" or got == "no_chord":
                if want != got:
                    worse.append((sid, ref, want, got))
                continue
            need = min(RANK[want], 1) if star else RANK[want]
            if got == "raised" or RANK[got] < need:
                worse.append((sid, ref, want, got))
            if star and got == "approx":
                kind = "cad64" if sid.startswith("wir") and "Cad" in label_of(items, sid, ref) else sid
                function[kind] += 1
    return {"counts": counts, "by_ref": by_ref, "worse": worse, "missing": missing, "extra": extra,
            "problems": problems, "function": function, "baseline": base}


_LABELS: dict = {}


def label_of(items, sid, ref):
    if not _LABELS:
        _LABELS.update({(i["sid"], i["ref"]): i["label"] for i in items})
    return _LABELS[(sid, ref)]


def format_counts(counts) -> list[str]:
    return [f"{sid} " + " ".join(f"{o}={counts[sid][o]}" for o in OUTCOMES) for sid in sorted(counts)]
