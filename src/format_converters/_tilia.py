"""TiLiA's own chord and key parsers, called as its CSV import calls them, and what they store."""
from __future__ import annotations

from functools import lru_cache

import music21
from tilia.timelines.harmony.components.harmony import get_params_from_text as _harmony_params
from tilia.timelines.harmony.components.mode import get_params_from_text as _mode_params
from tilia.ui.timelines.harmony.constants import INT_TO_NOTE_NAME, QUALITY_TO_ABBREVIATION

# accidentals TiLiA's validator accepts, as the text a chord name takes
ACC = {0: "", 1: "#", -1: "-", 2: "##", -2: "--"}

# TiLiA stores these without a root of their own: the bass is fixed by the quality
FIXED_BASS_QUALITIES = ("Italian", "German", "French")


def key_text(key: str | music21.key.Key) -> str:
    """TiLiA key text of a key: music21 tonic name, lowercase for minor."""
    if isinstance(key, str):
        return key
    name = key.tonic.name
    return name.lower() if key.mode == "minor" else name


@lru_cache(maxsize=None)
def _key(text: str) -> music21.key.Key:
    return music21.key.Key(text)


def as_key(key: str | music21.key.Key) -> music21.key.Key:
    return _key(key) if isinstance(key, str) else key


@lru_cache(maxsize=None)
def _parse(text: str, key: str):
    try:
        ok, params = _harmony_params(text, _key(key))
    except Exception:  # TiLiA's parser raises on some labels; the import would abort
        return None
    if not ok or params["accidental"] not in ACC:  # TiLiA's validator refuses the others
        return None
    return params


def parse_chord(text: str, key: str | music21.key.Key) -> dict | None:
    """What TiLiA's parser stores for `text` under `key`, or None if it rejects, raises or
    gives an accidental the validator refuses."""
    params = _parse(text, key_text(key))
    return None if params is None else dict(params)


@lru_cache(maxsize=None)
def _pcs(step: int, accidental: int, quality: str, inversion: int):
    name = INT_TO_NOTE_NAME[step] + ACC[accidental]
    try:
        sym = music21.harmony.ChordSymbol(name + QUALITY_TO_ABBREVIATION[quality], inversion=inversion)
    except Exception:
        sym = music21.harmony.ChordSymbol(root=name, kind=quality)
    return frozenset(p.pitchClass for p in sym.pitches), sym.bass().pitchClass


def pcs_from_params(params: dict) -> tuple[frozenset[int], int]:
    """Pitch classes and bass pitch class that TiLiA renders for stored chord params."""
    return _pcs(params["step"], params["accidental"], params["quality"], params["inversion"])


def matches(params: dict | None, truth: tuple[frozenset[int], int] | None) -> bool:
    """Do the stored params sound the truth? Italian, German and French need equal pitch classes only."""
    if params is None or truth is None:
        return False
    pcs, bass = pcs_from_params(params)
    if pcs != truth[0]:
        return False
    return bass == truth[1] or params["quality"] in FIXED_BASS_QUALITIES


def parse_key(text: str) -> dict | None:
    """What TiLiA's key parser stores for `text`, or None if it rejects or raises."""
    try:
        res = _mode_params(text)
    except Exception:
        return None
    ok, params = res
    return params if ok else None
