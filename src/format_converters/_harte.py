"""Harte chord labels (C:min7/G, C:(3,5,b7)/5): the chord they stand for."""
from __future__ import annotations

import re

from ._spelling import NATURAL_PC, note_pc

NO_CHORD = ("N", "X", "")

_SHORTHAND = {
    "maj": "3,5", "min": "b3,5", "dim": "b3,b5", "aug": "3,#5", "maj7": "3,5,7", "min7": "b3,5,b7",
    "7": "3,5,b7", "dim7": "b3,b5,bb7", "hdim7": "b3,b5,b7", "minmaj7": "b3,5,7", "maj6": "3,5,6",
    "min6": "b3,5,6", "9": "3,5,b7,9", "maj9": "3,5,7,9", "min9": "b3,5,b7,9", "sus2": "2,5",
    "sus4": "4,5", "11": "3,5,b7,9,11", "min11": "b3,5,b7,9,11", "maj11": "3,5,7,9,11",
    "13": "3,5,b7,9,11,13", "min13": "b3,5,b7,9,11,13", "maj13": "3,5,7,9,11,13", "1": "", "5": "5",
}
_DEGREE = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11, 8: 0, 9: 2, 10: 4, 11: 5, 12: 7, 13: 9}
_NOTE = re.compile(r"[A-Ga-g][#b]*$")
_LETTERS = "CDEFGAB"


def degree_pc(degree: str) -> int:
    """Semitones above the root of a Harte interval ('b7', '#5', 'bb7', '9')."""
    m = re.fullmatch(r"([#b]*)(\d+)", degree.strip())
    if not m or int(m.group(2)) not in _DEGREE:
        raise ValueError(f"not a Harte interval: {degree!r}")
    acc = m.group(1)
    return (_DEGREE[int(m.group(2))] + acc.count("#") - acc.count("b")) % 12


def is_no_chord(label: str) -> bool:
    return label.strip() in NO_CHORD


def pitch_classes(label: str) -> tuple[frozenset[int], int]:
    """'C:(3,5,b7)/E', 'C:min7/G' or 'C:min7/5' -> (pitch classes, bass pitch class)."""
    label = label.strip()
    root_s, colon, rest = label.partition(":")
    if not colon:  # a bare root, possibly with a bass: 'C', 'C/E'
        root_s, _, bass_s = root_s.partition("/")
        rest = "/" + bass_s if bass_s else ""
    root = note_pc(root_s)
    body, _, bass_s = rest.partition("/")
    body = body.strip()
    short, paren, degrees = body.partition("(")
    short = short.strip()
    if not short and not paren and not body:
        short = "maj"
    if short:
        if short not in _SHORTHAND:
            raise ValueError(f"unknown Harte shorthand: {short!r}")
        tones = [d for d in _SHORTHAND[short].split(",") if d]
    else:
        tones = []
    pcs = {root}
    pcs.update((root + degree_pc(d)) % 12 for d in tones)
    if paren:
        for d in degrees.rstrip(") ").split(","):
            d = d.strip()
            if not d:
                continue
            if d.startswith("*"):
                pcs.discard((root + degree_pc(d[1:])) % 12)
            else:
                pcs.add((root + degree_pc(d)) % 12)
    bass_s = bass_s.strip()
    if not bass_s:
        bass = root
    elif _NOTE.match(bass_s):
        bass = note_pc(bass_s)
    else:
        bass = (root + degree_pc(bass_s)) % 12
    return frozenset(pcs), bass


def interval_name(root: str, degree: str) -> str | None:
    """The note a Harte interval names above a root: 'C#' and '3' -> 'E#', 'Db' and 'b3' -> 'Fb'.
    None past a double sharp or flat."""
    m = re.fullmatch(r"([#b]*)(\d+)", degree.strip())
    if not m or int(m.group(2)) not in _DEGREE:
        raise ValueError(f"not a Harte interval: {degree!r}")
    letter = _LETTERS[(_LETTERS.index(root[0].upper()) + int(m.group(2)) - 1) % 7]
    alter = (note_pc(root) + degree_pc(degree) - NATURAL_PC[letter] + 6) % 12 - 6
    return letter + ("#" * alter if alter > 0 else "b" * -alter) if abs(alter) <= 2 else None


def spelling(label: str) -> dict[int, str]:
    """Pitch class -> note name for the root and the bass, as the label spells them. A bass given as an
    interval ('C#:maj/3') is named from the root: E#, not F."""
    root, _, rest = label.strip().partition(":")
    root, _, bass_inline = root.partition("/")
    spell = {}
    if root and root[0] in NATURAL_PC:
        spell[note_pc(root)] = root
    bass = (rest.partition("/")[2] or bass_inline).strip()
    if bass and bass[0] in NATURAL_PC and _NOTE.match(bass):
        spell[note_pc(bass)] = bass
    elif bass and root and root[0] in NATURAL_PC:
        name = interval_name(root, bass)
        if name:
            spell[note_pc(name)] = name
    return spell


def root_pc(label: str) -> int | None:
    """Pitch class of the root a Harte label names."""
    root = label.strip().partition(":")[0].partition("/")[0]
    return note_pc(root) if root and root[0] in NATURAL_PC else None
