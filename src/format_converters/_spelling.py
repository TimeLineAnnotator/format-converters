"""Note names, the line of fifths, letter symbols for a set of pitch classes, numeral spellings."""
from __future__ import annotations

import itertools
import re
from collections.abc import Iterator

import music21

LINE_OF_FIFTHS = "FCGDAEB"
NATURAL_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
FLAT_NAMES = {0: "C", 1: "Db", 2: "D", 3: "Eb", 4: "E", 5: "F", 6: "Gb", 7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B"}
SHARP_NAMES = {0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F", 6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B"}

_DEGREE_SEMITONES = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11, 9: 2, 11: 5, 13: 9}
_NOT_CHORDS = ("Neapolitan", "pedal")


def note_pc(name: str) -> int:
    """'Eb', 'F#', 'Bbb', 'E-' -> pitch class."""
    name = name.strip()
    pc = NATURAL_PC[name[0].upper()]
    for ch in name[1:]:
        pc += {"#": 1, "b": -1, "-": -1}.get(ch, 0)
    return pc % 12


def fifths_from_name(name: str) -> int:
    """Position on the line of fifths: F = -1, C = 0, G = 1; '#' and 'b' or '-' move by seven."""
    f = LINE_OF_FIFTHS.index(name[0].upper()) - 1
    for ch in name[1:]:
        f += {"#": 7, "b": -7, "-": -7}.get(ch, 0)
    return f


def name_from_fifths(f: int) -> str:
    """Inverse of fifths_from_name, with flats written 'b'."""
    idx = f + 1
    acc = idx // 7
    return LINE_OF_FIFTHS[idx % 7] + ("#" * acc if acc > 0 else "b" * -acc)


def _kind_semitones(spec: str) -> list[int]:
    out = []
    for tok in spec.split(","):
        n = int(tok.lstrip("#-"))
        out.append((_DEGREE_SEMITONES[n] + tok.count("#") - tok.count("-")) % 12)
    return out


# music21's chord kinds: name -> (semitones above the root, the abbreviation TiLiA writes)
KINDS = {
    k: (_kind_semitones(v[0]), v[1][0])
    for k, v in music21.harmony.CHORD_TYPES.items()
    if k not in _NOT_CHORDS
}
# kinds whose bass TiLiA fixes: a "/bass" after them is not written
_NO_SLASH = ("Italian", "German", "French", "Tristan", "power")


def _names(pc: int, spell: dict[int, str], sharps: bool, bass: bool = False) -> list[str]:
    """Candidate spellings of a pitch class: the source's, then the key's preference, then the other.
    TiLiA/music21 misread a sharp after the slash ('Cm/D#' has bass C), so a bass is tried flat first.
    Never a '-' after a note name: TiLiA reads 'A-7' as A minor seventh."""
    first, second = (SHARP_NAMES, FLAT_NAMES) if sharps else (FLAT_NAMES, SHARP_NAMES)
    if bass:
        cands = [FLAT_NAMES[pc], spell.get(pc), SHARP_NAMES[pc]]
    else:
        cands = [spell.get(pc), first[pc], second[pc]]
    return list(dict.fromkeys(c for c in cands if c))


def letter_figures(
    pcs: frozenset[int],
    bass: int,
    spell: dict[int, str] | None = None,
    sharps: bool = False,
    root: int | None = None,
) -> Iterator[str]:
    """Letter symbols (Cm7/G) for the pitch classes, over every chord kind of music21.
    spell: pitch class -> preferred spelled name ('Bb', 'F#'), from the source.
    root: the pitch class to try as the chord's root first (Harte names it)."""
    spell = spell or {}
    roots = sorted(sorted(pcs), key=lambda pc: pc != root)
    for root in roots:
        for kind, (semis, abbr) in KINDS.items():
            if {(root + s) % 12 for s in semis} != set(pcs):
                continue
            for rname in _names(root, spell, sharps):
                if bass != root and kind not in _NO_SLASH:
                    for bname in _names(bass, spell, sharps, bass=True):
                        yield rname + abbr + "/" + bname
                else:
                    yield rname + abbr


def minor_variants(fig: str) -> list[str]:
    """Spellings of one numeral under other conventions for #/b on 6 and 7 (and none), per side of '/'."""
    opts = []
    for t in re.split(r"(/)", fig):
        if t == "/":
            opts.append(["/"])
            continue
        m = re.match(r"([#b]*)(vii|vi|VII|VI)(.*)", t)
        if m:
            core, rest = m.group(2), m.group(3)
            opts.append(list(dict.fromkeys([t, core + rest, "#" + core + rest, "b" + core + rest])))
        else:
            opts.append([t])
    return ["".join(c) for c in itertools.product(*opts)]
