"""One test per class of label that TiLiA's own parser mis-stores, rejects or raises on.

Each test asserts the outcome and the params that TiLiA's parser stores for the symbol. The
`raw` helper shows what TiLiA does with the label as written.
"""
import music21
import pytest
from tilia.timelines.harmony.components.harmony import get_params_from_text as tilia_chord
from tilia.timelines.harmony.components.mode import get_params_from_text as tilia_mode

from format_converters import _harte
from format_converters._tilia import parse_chord, pcs_from_params
from format_converters.harmony import ChordResult, translate_chord, translate_key


def pcs(*names):
    return frozenset(music21.pitch.Pitch(n).pitchClass for n in names)


def pc(name):
    return music21.pitch.Pitch(name).pitchClass


def raw(text, key="C"):
    """TiLiA's own parse of a label, as the CSV import calls it: params, None if rejected."""
    ok, params = tilia_chord(text, music21.key.Key(key))
    return params if ok else None


def check(result: ChordResult, outcome, symbol, key="C", **params):
    """The outcome, the symbol, and params that are exactly what TiLiA's parser stores for it."""
    assert result.outcome == outcome
    assert result.symbol == symbol
    assert result.params == parse_chord(symbol, key)
    for name, value in params.items():
        assert result.params[name] == value, (name, result.params)


# ---------------------------------------------------------------- Harte
def test_harte_is_rejected_as_written_and_rewritten_as_a_letter_symbol():
    assert raw("C:min7/G") is None
    r = translate_chord("C:min7/G", "harte", "C")
    check(r, "letter", "Cm7/G", step=0, accidental=0, quality="minor-seventh", inversion=2)
    assert r.display_mode == "letter" and r.custom_text == ""


def test_harte_interval_bass_is_the_same_chord_as_note_name_bass():
    by_name = translate_chord("C:min7/G", "harte", "C")
    by_interval = translate_chord("C:min7/5", "harte", "C")
    assert by_interval == by_name
    flat_third = translate_chord("C:min7/b3", "harte", "C")
    check(flat_third, "letter", "Cm7/Eb", inversion=1)
    assert translate_chord("C:min7/Eb", "harte", "C") == flat_third


@pytest.mark.parametrize("label, key, symbol", [
    ("C#:maj/3", "E", "C#/E#"),
    ("C#:7/3", "E", "C#7/E#"),
    ("Ab:min6/b3", "E-", "Abm6/Cb"),
    ("Db:min/b3", "E", "Dbm/Fb"),
])
def test_harte_interval_bass_is_named_from_the_root(label, key, symbol):
    # E#, Cb and Fb are not in the tables of flat and sharp names; the interval names them from the root
    assert translate_chord(label, "harte", key).symbol == symbol


def test_harte_bass_outside_the_chord_sounds_with_it():
    # as mir_eval reads Harte: D:maj/b7 is D-F#-A over C, a seventh chord in third inversion
    assert _harte.pitch_classes("D:maj/b7") == (pcs("D", "F#", "A", "C"), pc("C"))
    r = translate_chord("D:maj/b7", "harte", "C")
    check(r, "letter", "D7/C", step=1, quality="dominant-seventh", inversion=3)
    assert r.display_mode == "letter"
    check(translate_chord("C:min/b7", "harte", "c"), "letter", "Cm7/Bb", key="c", inversion=3)
    # a seventh over a pedal: no German sixth with the same four pitch classes and no G
    r = translate_chord("D:7/G", "harte", "C")
    check(r, "approx", "D7sus/G")
    assert pcs_from_params(r.params)[1] == pc("G")


def test_harte_foreign_bass_that_no_symbol_keeps_is_left_out_of_the_approximation():
    r = translate_chord("C:maj/#4", "harte", "C")
    check(r, "approx", "C", step=0, quality="major", inversion=0)
    assert r.display_mode == "custom" and r.custom_text == "C:maj/#4"
    assert r.comments == "the bass left out: TiLiA stores C"
    # Ebpower (Eb-Bb) would keep two tones but is written without the bass
    r = translate_chord("A:dim/Bb", "harte", "C")
    check(r, "approx", "Adim")
    assert r.comments == "the bass left out: TiLiA stores Adim"


def test_harte_root_is_kept_when_another_root_has_the_same_pitch_classes():
    check(translate_chord("A:min7", "harte", "C"), "letter", "Am7", step=5, quality="minor-seventh")
    check(translate_chord("Ab:7", "harte", "C"), "letter", "Ab7", step=5, accidental=-1,
          quality="dominant-seventh")


def test_harte_truth_given_by_the_caller_is_used():
    truth = (pcs("C", "E-", "G"), pc("G"))
    check(translate_chord("whatever", "harte", "C", truth=truth), "letter", "Cm/G", inversion=2)


def test_harte_degrees_only_label_with_omission():
    r = translate_chord("C:maj(*3)", "harte", "C")
    assert r.outcome in ("letter", "approx", "none")
    if r.outcome == "letter":
        assert pcs_from_params(r.params)[0] == pcs("C", "G")


def test_harte_chord_that_music21_has_no_kind_for_is_approx_and_says_why():
    r = translate_chord("E:maj/A", "harte", "C")
    assert r.outcome == "approx"
    assert r.display_mode == "custom" and r.custom_text == "E:maj/A"
    assert r.comments
    assert r.params == parse_chord(r.symbol, "C")


def test_harte_without_a_third_or_with_a_foreign_bass_is_none_or_approx_and_has_no_exact_symbol():
    r = translate_chord("F#:(b5,b7)/C", "harte", "C")
    assert r.outcome == "none" and r.symbol is None and r.params is None and r.comments


# ---------------------------------------------------------------- keys
@pytest.mark.parametrize("label, standard, text", [
    ("F:min", "harte", "f"),
    ("A:maj", "harte", "A"),
    ("Bb:maj", "harte", "B-"),
    ("C#:min", "harte", "c#"),
    ("F:min", "bps-fh", "f"),
    ("Eb:maj", "bps-fh", "E-"),
    ("Eb", "dcml", "E-"),
    ("c#", "dcml", "c#"),
    ("bb", "dcml", "b-"),
    ("F#", "dcml", "F#"),
    ("f#", "romantext", "f#"),
    ("B-", "romantext", "B-"),
    ("b-", "romantext", "b-"),
    # spelled as written within seven sharps or flats
    ("C#:maj", "harte", "C#"),
    ("A#:min", "harte", "a#"),
    ("Cb:maj", "harte", "C-"),
    ("Ab:min", "harte", "a-"),
    ("Gb:maj", "harte", "G-"),
    ("D#:min", "harte", "d#"),
    # respelled past seven
    ("D#:maj", "harte", "E-"),
    ("Fb:maj", "harte", "E"),
    ("A#:maj", "harte", "B-"),
    ("Db:min", "harte", "c#"),
])
def test_translate_key_global_keys(label, standard, text):
    assert translate_key(label, standard) == text
    k = music21.key.Key(text)
    ok, params = tilia_mode(text)
    assert ok and params["step"] == "CDEFGAB".index(k.tonic.step) and params["type"] == k.mode


def test_harte_keys_make_tilias_key_parser_raise():
    with pytest.raises(Exception):  # noqa: B017 TiLiA returns None and the caller unpacks it
        tilia_mode("F:min")
    assert tilia_mode(translate_key("F:min", "harte"))[0]


@pytest.mark.parametrize("label, globalkey, text", [
    ("V", "Eb", "B-"),
    ("iv/V", "c", "c"),
    ("vi", "F", "d"),
    ("I", "A", "A"),
    ("III", "a", "C"),
    ("VI", "c", "A-"),     # natural minor: a minor sixth above the tonic
    ("VII", "c", "B-"),    # natural minor: a minor seventh above the tonic
    ("#iv", "F#", "c"),    # B# minor is written as C minor
    ("bII", "F#", "G"),
    ("VI", "E", "C#"),     # seven sharps, as written
    ("III", "E", "A-"),    # G# major would have eight
])
def test_translate_key_dcml_local_keys_are_relative_to_the_global_key(label, globalkey, text):
    assert translate_key(label, "dcml", globalkey=globalkey) == text
    assert tilia_mode(text)[0]


def test_translate_key_rejects_what_is_no_key():
    with pytest.raises(ValueError):
        translate_key("X:maj", "harte")
    with pytest.raises(ValueError):
        translate_key("V", "unknown")


# ---------------------------------------------------------------- BPS-FH
def test_bpsfh_equals_sign_is_half_diminished_and_tilia_ignores_it():
    truth = (pcs("B", "D", "F", "A"), pc("B"))
    assert raw("vii=7") is None  # TiLiA rejects the label
    r = translate_chord("vii=7", "bps-fh", "C", truth)
    check(r, "rn", "viiø7", quality="half-diminished-seventh")
    assert r.display_mode == "roman" and r.custom_text == ""


def test_bpsfh_minus_sign_is_diminished_and_tilia_ignores_it():
    truth = (pcs("B", "D", "F", "A-"), pc("F"))
    assert raw("vii-43")["quality"] == "minor-seventh"  # the sign is dropped: a different chord
    check(translate_chord("vii-43", "bps-fh", "C", truth), "rn", "viio43", quality="diminished-seventh",
          inversion=2)


def test_bpsfh_triad_with_minus_sign():
    truth = (pcs("G#", "B", "D"), pc("G#"))
    assert raw("vii-", "a")["quality"] == "minor"
    check(translate_chord("vii-", "bps-fh", "a", truth), "rn", translate_chord("vii-", "bps-fh", "a", truth).symbol,
          key="a", quality="diminished")


def test_bpsfh_neapolitan_is_only_stored_as_bII6():
    truth = (pcs("D-", "F", "A-"), pc("F"))
    assert raw("N6", "c") is None
    r = translate_chord("N6", "bps-fh", "c", truth)
    check(r, "rn", "bII6", key="c", step=1, accidental=-1, quality="major", inversion=1)


@pytest.mark.parametrize("label, pitch_names, bass, quality", [
    ("Gr+6", ("A-", "C", "E-", "F#"), "A-", "German"),
    ("It+6", ("A-", "C", "F#"), "A-", "Italian"),
    ("Fr+6", ("A-", "C", "D", "F#"), "A-", "French"),
])
def test_bpsfh_augmented_sixths_only_as_letter_symbols(label, pitch_names, bass, quality):
    assert raw(label, "c") is None
    r = translate_chord(label, "bps-fh", "c", (pcs(*pitch_names), pc(bass)))
    assert r.outcome == "letter" and r.params["quality"] == quality
    assert r.display_mode == "custom" and r.custom_text == label  # the analyst's numeral stays visible
    assert r.params == parse_chord(r.symbol, "c")


def test_bpsfh_chord_applied_to_a_chromatic_degree_raises_in_tilia_and_is_stored_as_a_letter_symbol():
    key = music21.key.Key("C")
    with pytest.raises(Exception):  # noqa: B017
        tilia_chord("V42/bVII", key)
    truth = (pcs("F", "A", "C", "E-"), pc("E-"))
    r = translate_chord("V42/bVII", "bps-fh", "C", truth)
    check(r, "letter", "F7/Eb", quality="dominant-seventh", inversion=3)
    assert r.display_mode == "custom" and r.custom_text == "V42/bVII"


def test_bpsfh_exact_numeral_keeps_applied_chord():
    truth = (pcs("D", "F#", "A", "C"), pc("D"))
    check(translate_chord("V7/V", "bps-fh", "C", truth), "rn", "V7/V", applied_to=4,
          quality="dominant-seventh")


# ---------------------------------------------------------------- DCML
def test_dcml_sharp_vii_in_minor_is_double_raised_by_tilia():
    truth = (pcs("G#", "B", "D", "F"), pc("G#"))
    assert raw("#viio7", "a")["accidental"] == 2
    r = translate_chord("#viio7", "dcml", "a", truth)
    assert r.outcome == "rn" and r.symbol != "#viio7"
    check(r, "rn", r.symbol, key="a", step=4, accidental=1, quality="diminished-seventh")


def test_dcml_natural_minor_degrees_are_stored_as_the_sounding_chord():
    truth = (pcs("G", "B", "D"), pc("G"))  # VII in A minor is G major, not the leading-tone chord
    r = translate_chord("VII", "dcml", "a", truth)
    assert r.outcome in ("rn", "letter")
    assert pcs_from_params(r.params) == truth
    assert r.params["step"] == 4 and r.params["accidental"] == 0


def test_dcml_percent_is_half_diminished():
    truth = (pcs("B", "D", "F", "A"), pc("B"))
    assert raw("vii%7") is None
    check(translate_chord("vii%7", "dcml", "C", truth), "rn", "viiø7", quality="half-diminished-seventh")


def test_dcml_percent_applied_chord():
    truth = (pcs("F#", "A", "C", "E"), pc("F#"))
    check(translate_chord("vii%7/V", "dcml", "C", truth), "rn", "viiø7/V", applied_to=4)


@pytest.mark.parametrize("label, pitch_names, bass, quality", [
    ("Ger6", ("A-", "C", "E-", "F#"), "A-", "German"),
    ("It6", ("A-", "C", "F#"), "A-", "Italian"),
    ("Fr6", ("A-", "C", "D", "F#"), "A-", "French"),
])
def test_dcml_augmented_sixths_only_as_letter_symbols(label, pitch_names, bass, quality):
    r = translate_chord(label, "dcml", "C", (pcs(*pitch_names), pc(bass)))
    assert r.outcome == "letter" and r.params["quality"] == quality
    assert r.display_mode == "custom" and r.custom_text == label


def test_romantext_augmented_sixths_only_as_letter_symbols():
    for label, quality in (("Ger65", "German"), ("It6", "Italian"), ("Fr43", "French")):
        r = translate_chord(label, "romantext", "C")
        assert r.outcome == "letter" and r.params["quality"] == quality, label
        assert r.display_mode == "custom" and r.custom_text == label


def test_dcml_neapolitan_is_only_stored_as_bII6():
    truth = (pcs("D-", "F", "A-"), pc("F"))
    check(translate_chord("bII6", "dcml", "c", truth), "rn", "bII6", key="c", inversion=1)
    check(translate_chord("bII6", "romantext", "c"), "rn", "bII6", key="c", inversion=1)


def test_dcml_augmented_major_seventh_is_stored_as_a_letter_symbol_not_the_seven_note_chord():
    truth = (pcs("C", "E", "G#", "B"), pc("C"))
    assert len(pcs_from_params(raw("I+M7"))[0]) != 4  # TiLiA stores a seven-note chord
    r = translate_chord("I+M7", "dcml", "C", truth)
    check(r, "letter", "C+M7", quality="augmented-major-seventh")
    assert r.display_mode == "custom" and r.custom_text == "I+M7"


def test_dcml_needs_the_truth():
    with pytest.raises(ValueError):
        translate_chord("V7", "dcml", "C")
    with pytest.raises(ValueError):
        translate_chord("V7", "bps-fh", "C")


# ---------------------------------------------------------------- letter symbols
def test_flat_after_a_note_name_is_written_b_never_minus():
    # TiLiA reads "A-7" as A minor seventh
    wrong = raw("A-7")
    assert wrong["step"] == 5 and wrong["accidental"] == 0 and wrong["quality"] == "minor-seventh"
    r = translate_chord("Ab:7", "harte", "C")
    assert r.symbol == "Ab7"
    assert r.params["accidental"] == -1 and r.params["quality"] == "dominant-seventh"
    for label in ("Ab:7", "Bb:min7/Db", "Eb:maj/Bb", "Db:min/Fb"):
        sym = translate_chord(label, "harte", "C").symbol
        assert sym is None or "-" not in sym, sym


def test_altered_tones_that_tilia_drops_are_not_stored_as_exact():
    dropped = raw("C7b9")
    assert dropped["quality"] == "dominant-seventh"  # the b9 is gone
    truth = (pcs("C", "E", "G", "B-", "D-"), pc("C"))
    r = translate_chord("C:7(b9)", "harte", "C")
    assert r.symbol != "C7b9"
    if r.outcome == "letter":
        assert pcs_from_params(r.params) == truth
    else:
        assert r.outcome in ("approx", "none")


def test_sharp_bass_is_written_flat_because_tilia_misreads_it():
    assert raw("Cm/D#")["inversion"] != 1
    r = translate_chord("C:min/D#", "harte", "C")
    check(r, "letter", "Cm/Eb", inversion=1, quality="minor")


# ---------------------------------------------------------------- the function rule
@pytest.mark.parametrize("label, truth_names, bass, function, applied", [
    ("V(64)", ("C", "E", "G"), "G", "V", 0),
    ("V7(4)", ("G", "B", "D", "F", "C"), "G", "V7", 0),
    ("I(94)", ("C", "E", "G", "D", "F"), "C", "I", 0),
    ("V(64)/V", ("D", "F#", "A", "G", "B"), "A", "V/V", 4),
])
def test_function_rule_dcml_changes_store_the_numeral_without_them(label, truth_names, bass, function, applied):
    r = translate_chord(label, "dcml", "C", (pcs(*truth_names), pc(bass)))
    assert r.outcome == "approx" and r.symbol == function
    assert r.display_mode == "custom" and r.custom_text == label
    assert r.comments
    assert r.params == parse_chord(function, "C") and r.params["applied_to"] == applied


def test_function_rule_applies_even_when_the_sounding_chord_is_storable():
    # V(64) sounds as I64, which TiLiA stores exactly; the project stores the function
    r = translate_chord("V(64)", "dcml", "C", (pcs("C", "E", "G"), pc("G")))
    assert r.outcome == "approx" and r.symbol == "V"


def test_function_rule_tries_the_spellings_of_the_function_in_minor():
    r = translate_chord("VII(4)", "dcml", "a", (pcs("G", "B-", "D", "C"), pc("G")))
    assert r.outcome == "approx" and r.symbol.endswith("VII")
    assert r.params == parse_chord(r.symbol, "a")


@pytest.mark.parametrize("label, function", [
    ("V7[no3]", "V7"),
    ("V7[add4]", "V7"),
    ("viio65[no5]/V", "viio65/V"),
    ("V[no3no5]", "V"),
])
def test_function_rule_romantext_brackets(label, function):
    r = translate_chord(label, "romantext", "C")
    assert r.outcome == "approx" and r.symbol == function
    assert r.display_mode == "custom" and r.custom_text == label and r.comments
    assert r.params == parse_chord(function, "C")


@pytest.mark.parametrize("label, function", [("Cad64", "V"), ("Cad64/V", "V/V"), ("Cad64/ii", "V/ii")])
def test_function_rule_cadential_six_four_is_the_dominant(label, function):
    r = translate_chord(label, "romantext", "C")
    assert r.outcome == "approx" and r.symbol == function
    assert r.display_mode == "custom" and r.custom_text == label
    assert r.params == parse_chord(function, "C")


def test_function_rule_falls_back_to_the_ordinary_translation_when_no_function_parses():
    assert parse_chord("V9", "C") is None  # the function of V9[b9] is a numeral TiLiA cannot read
    r = translate_chord("V9[b9]", "romantext", "C")
    assert r.outcome == "letter" and r.symbol is not None
    assert pcs_from_params(r.params) == (pcs("G", "B", "D", "F", "A-"), pc("G"))
    assert r.display_mode == "custom" and r.custom_text == "V9[b9]"


# ---------------------------------------------------------------- no chord, and never raising
@pytest.mark.parametrize("label, standard", [("N", "harte"), ("X", "harte"), ("@none", "dcml"), ("", "dcml")])
def test_no_chord_labels(label, standard):
    r = translate_chord(label, standard, "C")
    assert r == ChordResult("no_chord")
    assert r.symbol is None and r.params is None


@pytest.mark.parametrize("label, standard", [
    ("???", "romantext"), ("V42/bVII", "romantext"), ("C:foo", "harte"), ("Cad64/bVII", "romantext"),
    ("", "romantext"), ("#VII42/bII", "romantext"), ("v4", "romantext"), ("It6(2)", "dcml"),
    ("V9[b9b5]", "romantext"),
])
def test_labels_never_raise(label, standard):
    truth = (pcs("C", "E", "G"), pc("C")) if standard == "dcml" else None
    r = translate_chord(label, standard, "C", truth)
    assert r.outcome in ("rn", "letter", "approx", "none")
    if r.symbol is None:
        assert r.params is None and r.display_mode is None
    else:
        assert r.params == parse_chord(r.symbol, "C")


def test_key_may_be_a_music21_key():
    truth = (pcs("D", "F#", "A"), pc("D"))
    assert translate_chord("V", "dcml", music21.key.Key("G"), truth) == translate_chord("V", "dcml", "G", truth)
    assert translate_chord("v", "dcml", music21.key.Key("g"), (pcs("D", "F", "A"), pc("D"))).symbol == "v"


def test_unknown_standard_is_an_error():
    with pytest.raises(ValueError):
        translate_chord("V", "nashville", "C")
