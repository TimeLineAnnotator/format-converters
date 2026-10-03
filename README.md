# format-converters

Readers that turn annotation formats into rows that [TiLiA](https://github.com/TimeLineAnnotator/desktop) can import.

The code is under the MIT licence. The first module, `format_converters.harmony`, translates chord and key
labels of four notations into the text that TiLiA's harmony timeline stores exactly.

## Why

TiLiA's harmony CSV import turns a `symbol` text into a chord (step, accidental, quality, inversion,
applied degree) with its own parser. That parser silently stores a different chord for some labels, rejects many,
and raises on a few:

- Harte labels (`C:min7/G`) are rejected, and Harte keys (`F:min`) make the key parser raise.
- BPS-FH's `-` (diminished) and `=` (half-diminished) are rejected or ignored; DCML's `%` is rejected.
- `V42/bVII` raises; `#vii` in a minor key is read as double-raised.
- Augmented sixths (`Ger6`, `It+6`) and the Neapolitan (`N6`) are rejected; TiLiA has them only as letter symbols and as `bII6`.
- `A-7` means A minor seventh; `C7b9` is stored as `C7`; `Cm/D#` gets the wrong inversion; `I+M7` is stored as a seven-note chord.

`translate_chord` searches for a symbol that TiLiA's parser reads back as exactly the source's pitch classes and
bass, and reports how good the match is.

## Install

```
pip install -e .            # needs Python 3.10 to 3.12; installs music21 and TiLiA 0.7.0
pip install -e . pytest     # to run the tests
```

TiLiA is installed from the commit of v0.7.0 (`@v0.7.0` would install 0.6.2, because a branch of that name shadows the tag).
Importing TiLiA's constants loads PySide6; on a machine without a display set `QT_QPA_PLATFORM=offscreen`.

## API

```python
from format_converters.harmony import translate_chord, translate_key, ChordResult
```

### `translate_key(label, standard, *, globalkey=None) -> str`

TiLiA key text: music21's tonic name, lowercase for minor. The result parses with TiLiA's key parser.

```python
translate_key("F:min", "harte")                 # 'f'
translate_key("Bb:maj", "bps-fh")               # 'B-'
translate_key("bb", "dcml")                     # 'b-'          a global key
translate_key("V", "dcml", globalkey="Eb")      # 'B-'          a local key, relative to the global key
translate_key("iv/V", "dcml", globalkey="c")    # 'c'
translate_key("vi", "dcml", globalkey="F")      # 'd'
translate_key("f#", "romantext")                # 'f#'
```

DCML's minor-mode degrees are those of the natural minor: in minor, `VI` and `VII` lie a minor sixth and a minor seventh above the tonic.
A tonic that needs more than one accidental is respelled (`#iv` in F# gives `c`, not B# minor).

### `translate_chord(label, standard, key, truth=None) -> ChordResult`

- `standard`: `"harte"` (`C:min7/G`, `C:(3,5,b7,b9)/Bb`, `N`), `"bps-fh"` (BPSD's Roman numerals), `"dcml"` (DCML's `chord` column), `"romantext"` (When in Rome / music21 figures).
- `key`: TiLiA key text as `translate_key` returns it, or a `music21.key.Key`. Roman numerals are read against it.
- `truth`: the source's chord as `(frozenset of pitch classes, bass pitch class)`.
  Required for `"bps-fh"` and `"dcml"` chords (`ValueError` if missing, except for no-chord labels): BPSD gives it in its `extended` column,
  DCML in `chord_tones`, `added_tones` and `bass_note`. For `"harte"` and `"romantext"` it is derived from the label when `None`
  (Harte intervals with a note-name or interval bass, so `C:min7/G` and `C:min7/5` are the same chord; RomanText through `music21.roman.RomanNumeral`).

```python
>>> translate_chord("C:min7/G", "harte", "C")
ChordResult(outcome='letter', symbol='Cm7/G', display_mode='letter', custom_text='', comments='',
            params={'step': 0, 'accidental': 0, 'inversion': 2, 'quality': 'minor-seventh', 'applied_to': 0})

>>> truth = (frozenset({11, 2, 5, 9}), 11)                 # B D F A, from the dataset
>>> translate_chord("vii%7", "dcml", "C", truth).symbol
'viiø7'

>>> translate_chord("Cad64/V", "romantext", "C")
ChordResult(outcome='approx', symbol='V/V', display_mode='custom', custom_text='Cad64/V',
            comments='cadential six-four (Cad64/V) stored as its function V/V', params={...})
```

`ChordResult` is a frozen dataclass:

| field | meaning |
| --- | --- |
| `outcome` | `"rn"`, `"letter"`, `"approx"`, `"none"` or `"no_chord"` |
| `symbol` | text for the CSV's `symbol` column; `None` for `none` and `no_chord` |
| `display_mode` | `"roman"`, `"letter"`, `"custom"` or `None` |
| `custom_text` | the source label, when `display_mode` is `"custom"` |
| `comments` | why, for an approximation or a label nothing reads |
| `params` | what TiLiA's parser stores for `symbol` under `key` |

### Outcome rules

- **rn**: a Roman numeral that TiLiA parses to exactly the truth's pitch classes and bass (for Italian, German and French sixths, equal
  pitch classes suffice: TiLiA fixes their bass). `display_mode` is `"roman"`.
- **letter**: a letter symbol that does the same. `display_mode` is `"letter"` for Harte; for the other standards it is `"custom"` with
  `custom_text` the source label, so the analyst's numeral stays visible.
- **approx**: TiLiA accepts the symbol but it is not the sounding chord. `display_mode` is `"custom"`, `custom_text` the source label, and `comments` says why.
  For Harte this is the chord with one or two tones other than the bass dropped.
- **none**: nothing TiLiA accepts; `symbol` is `None`. A converter puts such labels on a marker timeline.
- **no_chord**: Harte `N` or `X`, DCML `@none` or an empty label.

Every symbol is parsed back with TiLiA's parser under `key` before it is returned, and `params` is that parse. Accidentals outside -2..2,
which TiLiA's validator refuses, never come out. The function never raises for a label: where TiLiA's parser raises
(applied chords to chromatic degrees such as `V42/bVII`) other spellings are tried.

Roman numerals are tried first, because they keep applied chords. Then letter symbols are built from the chord's pitch classes over music21's
chord kinds, spelled as the source spells them (a flat is written `b`, never `-`: TiLiA reads `A-7` as A minor seventh; a bass is tried flat first,
because `Cm/D#` has the wrong inversion). The Roman-numeral spellings for the sixth and seventh degrees in minor (`#vii`, `bVII`, `vii`) are all tried.

### The function rule

Suspensions, retardations, added and omitted notes, and cadential six-fours store the *function*, not the sounding chord:
the numeral without the changes, as `approx`, with the source label as custom text.

- DCML labels with a parenthesised changes group: `V(64)` is stored as `V`, `V7(4)` as `V7`, `I(94)` as `I`, `V(64)/V` as `V/V`.
- RomanText figures with `[no...]` or `[add...]` brackets (any bracket): `V7[no3]` is stored as `V7`.
- Cadential six-fours: `Cad64` is stored as `V`, `Cad64/V` as `V/V`.

The spellings of the function figure in minor are tried (`minor_variants`), preferring one rooted in the sounding chord.
Only if no spelling of the function parses does the ordinary translation apply (for example `V9[b9]`, whose function `V9` TiLiA cannot read, comes out as a letter symbol).

## Tests

```
pytest                                  # unit tests and the corpus test
pytest --ignore=tests/test_corpus.py    # unit tests only (seconds)
python scripts/harmony_report.py        # counts per source; same corpus run as the corpus test
```

`tests/test_harmony.py` has a test for each class of label that TiLiA mis-stores, rejects or raises on.

`tests/test_corpus.py` runs every chord of four public datasets through `translate_chord`, re-parses each symbol with TiLiA, and compares each
chord with `tests/corpus/baseline.json.gz`, the outcome of the research prototype for each chord (it holds no labels). It fails on an exception, on any
chord that ends lower than the baseline (the function rule aside), and on a source with more `none` than the baseline.

The sources are pinned (`tests/corpus/sources.json`, `dcml_files.txt` and `wir_paths.txt` hold only URLs, commits, file names and paths). They are downloaded
into `$FORMAT_CONVERTERS_CACHE` (default `~/.cache/format-converters`) on the first run, about 5 MB: the two Zenodo zips are read by HTTP range requests, only the needed members.
music21's parse of the 277 RomanText files takes about 9 minutes on 8 processes the first time; it is cached per file in the same directory, for the file's md5 and the installed music21 version. An empty cached file counts as missing and is downloaded again.
`FORMAT_CONVERTERS_WORKERS` sets the number of processes (default: up to 4). To fill a cache from an earlier download, call `tests/corpus/fetch.py: seed(directory)`.

`scripts/harmony_report.py` prints one line per source id, such as `bpsd rn=10971 letter=218 approx=0 none=0 no_chord=0`, then the prototype's counts, and how many chords were stored as their function.

### Datasets the corpus test downloads

None of them is stored in this repository, and the repository holds no chord labels.

| source | what is read | licence |
| --- | --- | --- |
| [Beethoven Piano Sonata Dataset v2](https://doi.org/10.5281/zenodo.12783403) (BPSD) | the score chord annotations | CC BY 3.0 |
| [Schubert Winterreise Dataset v2.1](https://doi.org/10.5281/zenodo.10839767) (SWD) | the score and audio chord annotations | CC BY 3.0 |
| [DCMLab/mozart_piano_sonatas](https://github.com/DCMLab/mozart_piano_sonatas) at a pinned commit | the harmony tables | CC BY-NC-SA 4.0 |
| [MarkGotham/When-in-Rome](https://github.com/MarkGotham/When-in-Rome) at a pinned commit | RomanText analyses of Winterreise, the Mozart sonatas and Beethoven's first movements | CC BY-SA 4.0 (see that repository for the licence of each analysis) |

The non-commercial and share-alike terms apply to the downloaded files, not to this code.

## Dezrann (`format_converters.dez`)

Reads [Dezrann](https://www.dezrann.net) `.dez` analyses and turns their labels into rows for TiLiA's CSV import by measure.

```python
from format_converters.dez import read_dez, to_tilia_rows

labels = read_dez("K279-1_texture.dez")                  # list[DezLabel], in file order
rows = to_tilia_rows(labels, "K279-1.mm.json", "range")  # "hierarchy", "marker" or "range"
```

- `DezLabel` has `type`, `tag` (`""` if absent), `start` and `duration` (`Fraction`, quarter notes, 0 if absent), `line`, `comment` and `raw`.
- Positions are quarter notes from the start of the score, as written (repeats are not unfolded). The measure map (`*.mm.json`, a path or the parsed list) turns them into a bar `number` plus a fraction of that bar, rounded to 6 decimals. A position outside the map is a `ValueError` naming the label.
- A label's end is `start + duration`; an end exactly on a measure's start is written as the end of the measure before it (`(n, 1.0)`). An end past the last bar (a few labels of the release do this) is written as the end of the last bar.
- `hierarchy`: the labels passed nest by containment; `level` is 1 for a label containing no other, else 1 + the highest level inside it. Labels with identical spans share a level. When the labels sit on several display lines of one stem (`bot.1`, `bot.2`), a label's level is at least the rank of its line, so a section with no sub-section in the file (a Development) is still above the sub-sections. Pass the labels of one type.
- `marker` has one row at each label's start; `range` uses the label's type as `row`. One row per label, in order.
- `tests/test_dez.py` runs on a K279-1 fixture (see `tests/fixtures/dez/NOTICE`); set `DEZRANN_MOZART` to the unzipped Mozart release to convert all of its files.
