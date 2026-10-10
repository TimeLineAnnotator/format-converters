"""Chord and key labels of published datasets as text that TiLiA's harmony timeline stores exactly.

TiLiA's CSV import turns a "symbol" text into a chord with its own parser. That parser rejects
or silently mis-stores many labels of the datasets (Harte's C:min7/G, BPS-FH's "-" and "=", DCML's "%",
Cm/D#, C7b9, ...) and raises on some. `translate_chord` finds, for a label, a symbol that the
parser reads back as the source's exact pitch classes and bass, and says how good the match is.
"""
from __future__ import annotations

import dataclasses
import itertools
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import music21

from .. import _harte
from .._spelling import (
    NATURAL_PC,
    fifths_from_name,
    letter_figures,
    minor_variants,
    name_from_fifths,
    note_pc,
)
from .._tilia import as_key, matches, parse_chord, parse_key

STANDARDS = ("harte", "bps-fh", "dcml", "romantext")
Truth = tuple[frozenset[int], int]


@dataclass(frozen=True)
class ChordResult:
    """What to write for one chord.

    outcome: "rn" (a Roman numeral that TiLiA parses to exactly the source's chord), "letter" (a letter
        symbol that does), "approx" (TiLiA accepts the symbol, but it is not the sounding chord),
        "none" (nothing TiLiA accepts) or "no_chord".
    symbol: text for the CSV's symbol column; None for "none" and "no_chord".
    display_mode: "roman", "letter", "custom" or None.
    custom_text: the source label, when display_mode is "custom".
    comments: why, for an approximation or a chord nothing parses.
    params: what TiLiA's parser stores for `symbol` under the key.
    """

    outcome: str
    symbol: str | None = None
    display_mode: str | None = None
    custom_text: str = ""
    comments: str = ""
    params: dict | None = None


# ------------------------------------------------------------------ keys
_KEY_NAME = re.compile(r"([A-Ga-g])([#b\-]*)$")
_MAJOR_DEGREE_FIFTHS = {"I": 0, "II": 2, "III": 4, "IV": -1, "V": 1, "VI": 3, "VII": 5}
# DCML's degrees in minor are those of the natural minor scale
_MINOR_DEGREE_FIFTHS = {"I": 0, "II": 2, "III": -3, "IV": -1, "V": 1, "VI": -4, "VII": -2}
_LOCAL_PART = re.compile(r"([#b]*)([IViv]+)$")


def _tilia_key_name(tonic: str, minor: bool) -> str:
    """Tonic name -> TiLiA key text: music21's '-' for flat, lowercase for minor."""
    name = tonic[0].upper() + tonic[1:].replace("b", "-")
    return name.lower() if minor else name


def _checked_key(fifths: int, minor: bool) -> str:
    """TiLiA key text for a tonic on the line of fifths, spelled as written (C# major stays C#, not D-flat).
    A tonic with more than one accidental, or a key with more than seven in its signature, is respelled
    enharmonically (F## -> G, D# major -> E-flat)."""
    shift = 3 if minor else 0  # the signature of a minor key is three fifths below its tonic's
    for f in (fifths, *sorted((fifths - 12, fifths + 12), key=lambda f: abs(f - shift))):
        text = _tilia_key_name(name_from_fifths(f), minor)
        if len(text) <= 2 and abs(f - shift) <= 7 and parse_key(text) is not None:
            return text
    raise ValueError(f"no key text for {name_from_fifths(fifths)}")


def _read_key_name(label: str) -> tuple[str, bool]:
    m = _KEY_NAME.match(label.strip())
    if not m:
        raise ValueError(f"not a key name: {label!r}")
    letter, acc = m.groups()
    return letter.upper() + acc, letter.islower()


def _dcml_local_fifths(globalkey: str, local: str) -> tuple[int, bool]:
    tonic, minor = _read_key_name(globalkey)
    fifths = fifths_from_name(tonic)
    for part in reversed(local.split("/")):
        m = _LOCAL_PART.match(part)
        if not m or m.group(2).upper() not in _MAJOR_DEGREE_FIFTHS:
            raise ValueError(f"not a DCML local key: {local!r}")
        table = _MINOR_DEGREE_FIFTHS if minor else _MAJOR_DEGREE_FIFTHS
        fifths += table[m.group(2).upper()] + 7 * (m.group(1).count("#") - m.group(1).count("b"))
        minor = m.group(2).islower()
    return fifths, minor


def translate_key(label: str, standard: str, *, globalkey: str | None = None) -> str:
    """TiLiA key text for a key label: music21's tonic name, lowercase for minor.

    harte, bps-fh: "F:min" -> "f", "Bb:maj" -> "B-".
    dcml: a global key ("Eb" -> "E-", "bb" -> "b-"), or with `globalkey` a local key relative to it
        ("V" in Eb -> "B-", "iv/V" in c -> "c"); minor-mode degrees are those of the natural minor.
    romantext: music21's key names ("f#", "B-").
    The result parses with TiLiA's key parser; ValueError for a label that is no key.
    """
    if standard not in STANDARDS:
        raise ValueError(f"unknown standard {standard!r}")
    label = label.strip()
    if standard in ("harte", "bps-fh"):
        root, _, mode = label.partition(":")
        tonic, _ = _read_key_name(root)
        minor = mode.lower().startswith("min")
        if root[0].islower() and not mode:
            minor = True
        return _checked_key(fifths_from_name(tonic), minor)
    if standard == "dcml" and globalkey is not None:
        fifths, minor = _dcml_local_fifths(globalkey, label)
        return _checked_key(fifths, minor)
    tonic, minor = _read_key_name(label)
    return _checked_key(fifths_from_name(tonic), minor)


# ------------------------------------------------------------------ labels -> candidate figures
@dataclass
class _Plan:
    """The candidate symbols for one label, in the order to try them."""

    rn: list[str]  # Roman numerals that should parse to the truth
    function: list[str]  # the numeral without the changes (the function rule)
    function_note: str = ""
    spell: dict[int, str] | None = None
    root: int | None = None  # tried first as the root of a letter symbol
    approx: Iterable[str] = ()  # symbols TiLiA accepts although they are not the chord
    approx_note: str = "TiLiA stores {symbol}, which is not the sounding chord"
    letters: bool = True
    letter_display: str = "custom"


_BPS_REPLACEMENTS = (("Gr+6", "Ger6"), ("It+6", "It6"), ("Fr+6", "Fr6"))


def _bps_figures(label: str) -> list[str]:
    s = label
    for old, new in _BPS_REPLACEMENTS:
        s = s.replace(old, new)
    s = re.sub(r"^N6", "bII6", s)
    cands = [label, s, s.replace("-", "o").replace("=", "ø"), s.replace("-", "o").replace("=", "/o")]
    return list(dict.fromkeys(f for c in cands for f in minor_variants(c)))


_DCML = re.compile(
    r"""^(?P<num>[#b]*(?:VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i))
        (?P<form>%|o|\+M|\+|M)?(?P<fb>65|43|42|64|7|6|2)?
        (?:\((?P<changes>[^)]*)\))?(?:/(?P<rel>.+))?$""",
    re.X,
)
_DCML_SPECIAL = re.compile(r"^(?P<kind>Ger|It|Fr)(?P<fb>65|43|42|64|7|6|2)?(?:\((?P<changes>[^)]*)\))?(?:/(?P<rel>.+))?$")
_DCML_FORM = {"%": "ø"}
# DCML's Ger6 is viio65(b3)/V, It6 viio6(b3)/V, Fr6 V43(b5)/V; the figures with the changes dropped
_DCML_SPECIAL_FIGURE = {
    "Ger": ("viio", {"6": "65", "65": "65", "43": "43", "7": "7"}, "V"),
    "It": ("viio", {"6": "6", "64": "64", "7": "7"}, "V"),
    "Fr": ("V", {"6": "43", "43": "43", "42": "42"}, "V"),
}


def _dcml_plan(label: str) -> _Plan | None:
    m = _DCML.match(label)
    if m:
        fig = m["num"] + _DCML_FORM.get(m["form"] or "", m["form"] or "") + (m["fb"] or "")
        if m["rel"]:
            fig += "/" + m["rel"]
        figures = minor_variants(fig)
        note = ""
        if m["changes"] is not None:
            note = f"suspensions, additions or omissions ({label}) stored as their function {{symbol}}"
        return _Plan(rn=figures if m["changes"] is None else [], function=figures if m["changes"] is not None else [],
                     function_note=note, approx=figures)
    m = _DCML_SPECIAL.match(label)
    if m:
        base, fbs, rel = _DCML_SPECIAL_FIGURE[m["kind"]]
        fig = base + fbs.get(m["fb"] or "6", m["fb"] or "") + "/" + rel + ("/" + m["rel"] if m["rel"] else "")
        figures = minor_variants(fig)
        function = figures if m["changes"] is not None else []
        note = f"changes ({label}) stored as their function {{symbol}}" if function else ""
        return _Plan(rn=[], function=function, function_note=note, approx=figures)
    return None


_BRACKET = re.compile(r"\[[^\]]*\]")


def _romantext_plan(label: str) -> _Plan:
    rn = label
    function: list[str] = []
    note = ""
    if label.startswith("Cad"):
        rn = "I" + label[3:]
        function = minor_variants("V" + re.sub(r"^Cad(64)?", "", label))
        note = f"cadential six-four ({label}) stored as its function {{symbol}}"
    elif "[" in label:
        function = minor_variants(_BRACKET.sub("", label))
        note = f"suspensions, additions or omissions ({label}) stored as their function {{symbol}}"
    return _Plan(rn=minor_variants(rn), function=function, function_note=note,
                 approx=minor_variants(_BRACKET.sub("", rn)) if "[" in rn else ())


# ------------------------------------------------------------------ truth
def _romantext_truth(label: str, key: music21.key.Key) -> Truth | None:
    rn = "I" + label[3:] if label.startswith("Cad") else label
    try:
        r = music21.roman.RomanNumeral(rn, key)
        return frozenset(p.pitchClass for p in r.pitches), r.bass().pitchClass
    except Exception:
        return None


# ------------------------------------------------------------------ the search
_FIGURE_ROOT = re.compile(r"[A-G][#b]*")


def _drop_tones(truth: Truth, spell: dict[int, str], sharps: bool, root: int | None) -> Iterator[str]:
    """Letter symbols for a Harte chord with one or two non-bass tones removed."""
    pcs, bass = truth
    for drop in (1, 2):
        for removed in itertools.combinations(sorted(pcs - {bass}), drop):
            for fig in letter_figures(frozenset(pcs - set(removed)), bass, spell, sharps, root):
                # a power chord or an augmented sixth is written without the bass: keep it only on its own bass
                if "/" in fig or note_pc(_FIGURE_ROOT.match(fig).group()) == bass:
                    yield fig


def _root_pc(params: dict) -> int:
    return (NATURAL_PC["CDEFGAB"[params["step"]]] + params["accidental"]) % 12


def _first_function(figures: list[str], key: music21.key.Key, truth: Truth | None):
    """The first spelling of the function that TiLiA parses; one rooted in the sounding chord first."""
    parsed = [(f, parse_chord(f, key)) for f in figures]
    parsed = [(f, p) for f, p in parsed if p is not None]
    for f, p in parsed:
        if truth is not None and _root_pc(p) in truth[0]:
            return f, p
    return parsed[0] if parsed else (None, None)


def _result(outcome, symbol, params, label, plan, comments=""):
    if outcome == "rn":
        return ChordResult("rn", symbol, "roman", "", comments, params)
    if outcome == "letter":
        if plan.letter_display == "letter":
            return ChordResult("letter", symbol, "letter", "", comments, params)
        return ChordResult("letter", symbol, "custom", label, comments, params)
    return ChordResult("approx", symbol, "custom", label, comments, params)


def _search(label: str, key: music21.key.Key, truth: Truth | None, plan: _Plan, sharps: bool) -> ChordResult:
    # the function rule: suspensions, additions, omissions and cadential six-fours store the function
    if plan.function:
        fig, params = _first_function(plan.function, key, truth)
        if fig is not None:
            return _result("approx", fig, params, label, plan, plan.function_note.format(symbol=fig))
    for fig in plan.rn:
        params = parse_chord(fig, key)
        if matches(params, truth):
            return _result("rn", fig, params, label, plan)
    if truth is not None and plan.letters:
        for fig in letter_figures(truth[0], truth[1], plan.spell, sharps, plan.root):
            params = parse_chord(fig, key)
            if matches(params, truth):
                return _result("letter", fig, params, label, plan)
    for fig in plan.approx:
        params = parse_chord(fig, key)
        if params is not None:
            return _result("approx", fig, params, label, plan, plan.approx_note.format(symbol=fig))
    return ChordResult("none", None, None, "", "no symbol that TiLiA's parser reads as this chord")


def _no_chord(label: str) -> ChordResult:
    return ChordResult("no_chord", None, None, "", "")


def translate_chord(
    label: str,
    standard: str,
    key: str | music21.key.Key,
    truth: Truth | None = None,
) -> ChordResult:
    """Find the symbol to write in TiLiA's CSV for a chord label.

    standard: "harte", "bps-fh", "dcml" or "romantext".
    key: TiLiA key text as `translate_key` returns it ("C", "E-", "f#"), or a music21 Key.
    truth: the source's chord as (pitch classes, bass pitch class). Required for "bps-fh" and "dcml"
        chords; for "harte" and "romantext" it is derived from the label when None.
    A symbol is returned only after TiLiA's parser read it back (see `ChordResult.params`).
    Raises ValueError for an unknown standard or a missing truth; never for a label.
    """
    if standard not in STANDARDS:
        raise ValueError(f"unknown standard {standard!r}; expected one of {STANDARDS}")
    label = label.strip()
    k = as_key(key)
    sharps = k.sharps > 0

    if standard == "harte":
        if _harte.is_no_chord(label):
            return _no_chord(label)
        try:
            truth = truth or _harte.pitch_classes(label)
        except (ValueError, KeyError):
            return ChordResult("none", None, None, "", f"not a Harte label: {label!r}")
        spell = _harte.spelling(label)
        root = _harte.root_pc(label)
        try:
            written, _ = _harte.pitch_classes(label, bass_sounds=False)
        except (ValueError, KeyError):  # a truth given for a label that is no Harte label
            written = truth[0]
        # last, the chord without a bass from outside it
        unslashed = list(letter_figures(written, root, spell, sharps, root)) if written != truth[0] else []
        plan = _Plan(rn=[], function=[], spell=spell, root=root,
                     approx=itertools.chain(_drop_tones(truth, spell, sharps, root), unslashed),
                     approx_note="one or two tones other than the bass dropped: TiLiA stores {symbol}",
                     letter_display="letter")
        result = _search(label, k, truth, plan, sharps)
        if result.outcome == "approx" and result.symbol in unslashed:
            result = dataclasses.replace(result, comments=f"the bass left out: TiLiA stores {result.symbol}")
        return result

    if standard == "dcml":
        if label in ("", "@none"):
            return _no_chord(label)
        if truth is None:
            raise ValueError("DCML chords need truth=(pitch classes, bass pitch class)")
        plan = _dcml_plan(label) or _Plan(rn=[], function=[])
        return _search(label, k, truth, plan, sharps)

    if standard == "bps-fh":
        if label in ("", "N", "X"):
            return _no_chord(label)
        if truth is None:
            raise ValueError("BPS-FH chords need truth=(pitch classes, bass pitch class)")
        return _search(label, k, truth, _Plan(rn=_bps_figures(label), function=[]), sharps)

    # romantext
    if not label:
        return ChordResult("none", None, None, "", "empty label")
    if truth is None:
        truth = _romantext_truth(label, k)
    return _search(label, k, truth, _romantext_plan(label), sharps)


__all__ = ["ChordResult", "translate_chord", "translate_key", "STANDARDS"]
