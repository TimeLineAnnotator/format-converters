"""The corpus as translate_chord inputs: one item per chord, as the prototype's loaders counted them.

Rows are csv.DictReader rows per file in sorted file-name order; RomanText chords come in music21's
order. An item's `ref` is "<file name>:<row>" (BPSD, SWD, DCML) or "<When in Rome path>:<chord index>".
"""
from __future__ import annotations

import csv
import json
import re
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from format_converters import _harte
from format_converters._spelling import fifths_from_name, note_pc
from format_converters.harmony import _dcml_local_fifths, translate_key

from . import fetch

SOURCE_IDS_TABULAR = ("bpsd", "swd-score", "swd-performances", "dcml")


def read_rows(directory: Path, pattern: str, delimiter: str):
    for fn in sorted(directory.glob(pattern)):
        with open(fn, encoding="utf-8") as f:
            for i, r in enumerate(csv.DictReader(f, delimiter=delimiter)):
                yield fn.name, i, {k.strip(): (v or "").strip().strip('"') for k, v in r.items()}


def item(sid, standard, ref, label, key, truth):
    return {"sid": sid, "standard": standard, "ref": ref, "label": label, "key": key, "truth": truth}


def bpsd_items(cache: Path):
    for fn, i, r in read_rows(cache / "bpsd" / "ann_score_chord", "*.csv", ";"):
        yield item("bpsd", "bps-fh", f"{fn}:{i}", r["roman"], translate_key(r["localkey"], "bps-fh"),
                   _harte.pitch_classes(r["extended"]))


def swd_items(cache: Path):
    for sid, kind in (("swd-score", "ann_score_chord"), ("swd-performances", "ann_audio_chord")):
        for fn, i, r in read_rows(cache / "swd" / kind, "*.csv", ";"):
            label = r["shorthand"]
            truth = None if _harte.is_no_chord(label) else _harte.pitch_classes(r["extended"])
            yield item(sid, "harte", f"{fn}:{i}", label, "C", truth)


def dcml_items(cache: Path):
    for fn, i, r in read_rows(cache / "dcml", "K*.harmonies.tsv", "\t"):
        ref = f"{fn}:{i}"
        if r["chord"] in ("", "@none") or not r["chord_tones"]:
            yield item("dcml", "dcml", ref, r["chord"], "C", None)
            continue
        fifths, minor = _dcml_local_fifths(r["globalkey"], r["localkey"])
        key = translate_key(r["localkey"], "dcml", globalkey=r["globalkey"])
        tones = [int(x) for x in r["chord_tones"].split(",")]
        if r["added_tones"]:
            tones += [int(x) for x in r["added_tones"].split(",")]
        truth = (frozenset((7 * (fifths + t)) % 12 for t in tones), (7 * (fifths + int(r["bass_note"]))) % 12)
        yield item("dcml", "dcml", ref, r["chord"], key, truth)


# ---------------------------------------------------------------- When in Rome
def wir_sid(path: str) -> str:
    corpus = "winterreise" if "Winterreise" in path else ("mozart" if "Mozart" in path else "beethoven")
    fn = path.rsplit("/", 1)[1]
    if fn.startswith("analysis_automatic"):
        kind = "automatic"
    elif fn.startswith("analysis_"):
        kind = fn[len("analysis_"):-4]
    else:
        kind = "analysis"
    return f"wir-{corpus}-{kind}"


def _parse_romantext(path: str) -> list[dict]:
    """music21's reading of one RomanText file: figure, key, pitch names and bass of every chord."""
    warnings.filterwarnings("ignore")
    import music21

    try:
        s = music21.converter.parse(path, format="romantext")
    except Exception:  # noqa: BLE001 music21 cannot read some files; they have no chords
        return []
    out = []
    for rn in s.recurse().getElementsByClass("RomanNumeral"):
        try:
            names, bass = [p.name for p in rn.pitches], rn.bass().name
        except Exception:  # noqa: BLE001
            names, bass = [], None
        k = rn.key
        out.append({"fig": rn.figure, "tonic": k.tonic.name if k else "C",
                    "mode": k.mode if k else "major", "names": names, "bass": bass})
    return out


def _parse_task(args):
    src, dst = args
    import music21

    chords = _parse_romantext(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    tmp.write_text(json.dumps({"music21": music21.__version__, "chords": chords}))
    tmp.replace(dst)


def parsed_wir(cache: Path, workers: int = 1) -> dict[str, list[dict]]:
    """path -> music21's chords. Parses a file only if the cache lacks it for this music21 version
    (about 9 minutes for all 277 files on 8 processes)."""
    import music21

    paths = fetch.names("wir")
    todo, out = [], {}
    for i, path in enumerate(paths):
        cached = cache / "wir_parsed" / (fetch.wir_fid(i)[:-4] + ".json")
        if cached.exists():
            data = json.loads(cached.read_text())
            if data["music21"] == music21.__version__:
                out[path] = data["chords"]
                continue
        todo.append((str(cache / "wir" / fetch.wir_fid(i)), cached))
    if todo:
        if workers > 1:
            with ProcessPoolExecutor(workers) as ex:
                list(ex.map(_parse_task, todo, chunksize=2))
        else:
            for t in todo:
                _parse_task(t)
        return parsed_wir(cache, 1)
    return out


def wir_items(cache: Path, workers: int = 1):
    parsed = parsed_wir(cache, workers)
    for path in fetch.names("wir"):
        sid = wir_sid(path)
        for idx, c in enumerate(parsed[path]):
            truth = (frozenset(note_pc(n) for n in c["names"]), note_pc(c["bass"])) if c["names"] else None
            key = translate_key(c["tonic"].lower() if c["mode"] == "minor" else c["tonic"], "romantext")
            yield item(sid, "romantext", f"{path}:{idx}", c["fig"], key, truth)


def all_items(cache: Path | None = None, workers: int = 1) -> list[dict]:
    cache = cache or fetch.cache_dir()
    items = []
    for gen in (bpsd_items, swd_items, dcml_items):
        items += list(gen(cache))
    items += list(wir_items(cache, workers))
    return items
