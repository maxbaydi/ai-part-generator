from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

ENHARMONIC_MAP = {
    "C": ["B#", "Dbb"], "C#": ["Db", "B##"], "D": ["C##", "Ebb"],
    "D#": ["Eb", "Fbb"], "E": ["D##", "Fb"], "F": ["E#", "Gbb"],
    "F#": ["Gb", "E##"], "G": ["F##", "Abb"], "G#": ["Ab"],
    "A": ["G##", "Bbb"], "A#": ["Bb", "Cbb"], "B": ["A##", "Cb"],
}

NOTE_TO_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5, "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11, "B#": 0,
    "C##": 2, "D##": 4, "E##": 6, "F##": 7, "G##": 9, "A##": 11, "B##": 1,
    "Cbb": 10, "Dbb": 0, "Ebb": 2, "Fbb": 3, "Gbb": 5, "Abb": 7, "Bbb": 9,
}

INTERVALS = {
    0: ("P1", "unison", "perfect unison"),
    1: ("m2", "minor second", "semitone"),
    2: ("M2", "major second", "whole tone"),
    3: ("m3", "minor third", "augmented second"),
    4: ("M3", "major third", "diminished fourth"),
    5: ("P4", "perfect fourth", "augmented third"),
    6: ("TT", "tritone", "augmented fourth", "diminished fifth"),
    7: ("P5", "perfect fifth", "diminished sixth"),
    8: ("m6", "minor sixth", "augmented fifth"),
    9: ("M6", "major sixth", "diminished seventh"),
    10: ("m7", "minor seventh", "augmented sixth"),
    11: ("M7", "major seventh", "diminished octave"),
    12: ("P8", "octave", "perfect octave"),
    13: ("m9", "minor ninth", "flat nine"),
    14: ("M9", "major ninth", "ninth"),
    15: ("m10", "minor tenth", "augmented ninth", "sharp nine"),
    16: ("M10", "major tenth"),
    17: ("P11", "perfect eleventh", "eleventh"),
    18: ("A11", "augmented eleventh", "sharp eleven"),
    19: ("P12", "perfect twelfth", "tritave"),
    20: ("m13", "minor thirteenth", "flat thirteen"),
    21: ("M13", "major thirteenth", "thirteenth"),
    22: ("m14", "minor fourteenth"),
    23: ("M14", "major fourteenth"),
    24: ("P15", "double octave", "fifteenth"),
}

INTERVAL_QUALITIES = {
    "diminished": -1, "minor": 0, "perfect": 0, "major": 0, "augmented": 1,
    "dim": -1, "min": 0, "perf": 0, "maj": 0, "aug": 1,
    "d": -1, "m": 0, "P": 0, "M": 0, "A": 1,
}

CHORD_TYPES = {
    frozenset([0, 4, 7]): "",
    frozenset([0, 3, 7]): "m",
    frozenset([0, 4, 7, 11]): "maj7",
    frozenset([0, 3, 7, 10]): "m7",
    frozenset([0, 4, 7, 10]): "7",
    frozenset([0, 3, 6]): "dim",
    frozenset([0, 3, 6, 9]): "dim7",
    frozenset([0, 3, 6, 10]): "m7b5",
    frozenset([0, 4, 8]): "aug",
    frozenset([0, 4, 8, 10]): "aug7",
    frozenset([0, 4, 8, 11]): "augmaj7",
    frozenset([0, 5, 7]): "sus4",
    frozenset([0, 2, 7]): "sus2",
    frozenset([0, 2, 5, 7]): "sus2sus4",
    frozenset([0, 7]): "5",
    frozenset([0, 4]): "(no5)",
    frozenset([0, 3]): "m(no5)",
    frozenset([0, 4, 7, 9]): "6",
    frozenset([0, 3, 7, 9]): "m6",
    frozenset([0, 4, 7, 10, 14]): "9",
    frozenset([0, 3, 7, 10, 14]): "m9",
    frozenset([0, 4, 7, 11, 14]): "maj9",
    frozenset([0, 4, 7, 10, 13]): "7b9",
    frozenset([0, 4, 7, 10, 15]): "7#9",
    frozenset([0, 4, 7, 10, 14, 17]): "11",
    frozenset([0, 3, 7, 10, 14, 17]): "m11",
    frozenset([0, 4, 7, 11, 14, 17]): "maj11",
    frozenset([0, 4, 7, 10, 14, 21]): "13",
    frozenset([0, 3, 7, 10, 14, 21]): "m13",
    frozenset([0, 4, 7, 11, 14, 21]): "maj13",
    frozenset([0, 5, 7, 10]): "7sus4",
    frozenset([0, 2, 7, 10]): "7sus2",
    frozenset([0, 5, 7, 10, 14]): "9sus4",
    frozenset([0, 5, 7, 11]): "maj7sus4",
    frozenset([0, 2, 7, 11]): "maj7sus2",
    frozenset([0, 2, 4, 7]): "add2",
    frozenset([0, 4, 5, 7]): "add4",
    frozenset([0, 4, 7, 14]): "add9",
    frozenset([0, 3, 7, 14]): "madd9",
    frozenset([0, 4, 7, 17]): "add11",
    frozenset([0, 3, 7, 17]): "madd11",
    frozenset([0, 4, 10]): "7(no5)",
    frozenset([0, 3, 10]): "m7(no5)",
    frozenset([0, 4, 11]): "maj7(no5)",
    frozenset([0, 3, 11]): "mM7(no5)",
    frozenset([0, 3, 7, 11]): "mM7",
    frozenset([0, 4, 6, 10]): "7b5",
    frozenset([0, 4, 8, 10]): "7#5",
    frozenset([0, 4, 6, 11]): "maj7b5",
    frozenset([0, 4, 8, 11]): "maj7#5",
    frozenset([0, 4, 6, 7]): "add#11",
    frozenset([0, 4, 7, 18]): "add#11",
    frozenset([0, 1, 7]): "addb9",
    frozenset([0, 3, 8]): "m#5",
    frozenset([0, 4, 6]): "b5",
    frozenset([0, 1, 4, 7]): "addb2",
    frozenset([0, 4, 7, 10, 14, 18]): "11#11",
    frozenset([0, 2]): "sus2(no5)",
    frozenset([0, 5]): "sus4(no5)",
    frozenset([0, 4, 9]): "6(no5)",
    frozenset([0, 3, 9]): "m6(no5)",
    frozenset([0, 7, 10]): "m7(no3)",
    frozenset([0, 7, 11]): "maj7(no3)",
    frozenset([0, 4, 7, 9, 14]): "6/9",
    frozenset([0, 3, 7, 9, 14]): "m6/9",
    frozenset([0, 4, 6, 10, 13]): "7b5b9",
    frozenset([0, 4, 6, 10, 15]): "7b5#9",
    frozenset([0, 4, 8, 10, 13]): "7#5b9",
    frozenset([0, 4, 8, 10, 15]): "7#5#9",
    frozenset([0, 4, 6, 10, 14]): "9b5",
    frozenset([0, 4, 8, 10, 14]): "9#5",
    frozenset([0, 4, 7, 10, 13, 18]): "7b9#11",
    frozenset([0, 4, 7, 10, 15, 18]): "7#9#11",
    frozenset([0, 4, 7, 10, 14, 18, 21]): "13#11",
    frozenset([0, 4, 7, 10, 13, 21]): "13b9",
    frozenset([0, 4, 7, 10, 15, 21]): "13#9",
    frozenset([0, 4, 7, 10, 20]): "7b13",
    frozenset([0, 4, 7, 10, 14, 20]): "9b13",
    frozenset([0, 3, 7, 10, 13]): "m7b9",
    frozenset([0, 3, 7, 11, 14]): "mM9",
    frozenset([0, 3, 7, 11, 14, 17]): "mM11",
    frozenset([0, 3, 7, 11, 14, 21]): "mM13",
    frozenset([0, 4, 7, 10, 17]): "7add11",
    frozenset([0, 4, 7, 11, 18]): "maj7#11",
    frozenset([0, 4, 7, 11, 14, 18]): "maj9#11",
    frozenset([0, 4, 7, 11, 14, 18, 21]): "maj13#11",
    frozenset([0, 5, 7, 10, 14, 17]): "11sus4",
    frozenset([0, 5, 7, 10, 14, 21]): "13sus4",
    frozenset([0, 2, 7, 10, 14]): "9sus2",
    frozenset([0, 4, 7, 9, 11]): "maj7add6",
    frozenset([0, 3, 7, 9, 11]): "mM7add6",
    frozenset([0, 3, 6, 9, 14]): "dim9",
    frozenset([0, 3, 6, 10, 14]): "m9b5",
    frozenset([0, 3, 6, 10, 14, 17]): "m11b5",
    frozenset([0, 4, 7, 21]): "add13",
    frozenset([0, 3, 7, 21]): "madd13",
    frozenset([0, 5, 10]): "7sus4(no5)",
    frozenset([0, 2, 10]): "7sus2(no5)",
    frozenset([0, 5, 7, 9]): "6sus4",
    frozenset([0, 2, 7, 9]): "6sus2",
    frozenset([0, 4, 7, 9, 10]): "7add6",
    frozenset([0, 3, 7, 9, 10]): "m7add6",
    frozenset([0, 1, 5, 7]): "sus4b9",
    frozenset([0, 5, 7, 10, 13]): "7sus4b9",
    frozenset([0, 4, 7, 10, 14, 17, 21]): "13",
    frozenset([0, 3, 7, 10, 14, 17, 21]): "m13",
    frozenset([0, 5, 5, 7]): "sus4add4",
    frozenset([0, 1, 4, 7, 10]): "7addb9",
    frozenset([0, 3, 4, 7]): "add#9",
    frozenset([0, 4, 7, 10, 15, 14]): "7#9add9",
    frozenset([0, 4, 6, 9]): "6b5",
    frozenset([0, 3, 6, 9, 11]): "dim7M7",
    frozenset([0, 1, 4, 8]): "augaddb9",
    frozenset([0, 2, 4, 8]): "augadd9",
    frozenset([0, 4, 8, 10, 14]): "aug9",
    frozenset([0, 4, 8, 11, 14]): "augmaj9",
    frozenset([0, 5, 7, 11, 14]): "maj9sus4",
    frozenset([0, 2, 7, 11, 14]): "maj9sus2",
    frozenset([0]): "note",
}

CHORD_TENSIONS = {
    "b9": 1, "9": 2, "#9": 3,
    "11": 5, "#11": 6,
    "b13": 8, "13": 9,
}

CHORD_FUNCTION = {
    "I": "tonic",
    "i": "tonic",
    "II": "supertonic",
    "ii": "supertonic",
    "bII": "neapolitan",
    "III": "mediant",
    "iii": "mediant",
    "bIII": "mediant",
    "IV": "subdominant",
    "iv": "subdominant",
    "V": "dominant",
    "v": "dominant",
    "VI": "submediant",
    "vi": "submediant",
    "bVI": "submediant",
    "VII": "leading tone",
    "vii": "leading tone",
    "viio": "leading tone",
    "bVII": "subtonic",
}

SCALE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "natural minor": [0, 2, 3, 5, 7, 8, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "harmonic minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic minor": [0, 2, 3, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "pentatonic major": [0, 2, 4, 7, 9],
    "pentatonic minor": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "blues major": [0, 2, 3, 4, 7, 9],
    "whole tone": [0, 2, 4, 6, 8, 10],
    "chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "diminished hw": [0, 1, 3, 4, 6, 7, 9, 10],
    "diminished wh": [0, 2, 3, 5, 6, 8, 9, 11],
    "augmented": [0, 3, 4, 7, 8, 11],
    "dorian b2": [0, 1, 3, 5, 7, 9, 10],
    "lydian augmented": [0, 2, 4, 6, 8, 9, 11],
    "lydian dominant": [0, 2, 4, 6, 7, 9, 10],
    "mixolydian b6": [0, 2, 4, 5, 7, 8, 10],
    "locrian #2": [0, 2, 3, 5, 6, 8, 10],
    "altered": [0, 1, 3, 4, 6, 8, 10],
    "superlocrian": [0, 1, 3, 4, 6, 8, 10],
    "locrian #6": [0, 1, 3, 5, 6, 9, 10],
    "ionian #5": [0, 2, 4, 5, 8, 9, 11],
    "dorian #4": [0, 2, 3, 6, 7, 9, 10],
    "phrygian dominant": [0, 1, 4, 5, 7, 8, 10],
    "lydian #2": [0, 3, 4, 6, 7, 9, 11],
    "ultralocrian": [0, 1, 3, 4, 6, 8, 9],
    "bebop dominant": [0, 2, 4, 5, 7, 9, 10, 11],
    "bebop major": [0, 2, 4, 5, 7, 8, 9, 11],
    "bebop minor": [0, 2, 3, 5, 7, 8, 9, 10],
    "bebop dorian": [0, 2, 3, 4, 5, 7, 9, 10],
    "hungarian minor": [0, 2, 3, 6, 7, 8, 11],
    "hungarian major": [0, 3, 4, 6, 7, 9, 10],
    "neapolitan minor": [0, 1, 3, 5, 7, 8, 11],
    "neapolitan major": [0, 1, 3, 5, 7, 9, 11],
    "persian": [0, 1, 4, 5, 6, 8, 11],
    "arabic": [0, 2, 4, 5, 6, 8, 10],
    "double harmonic": [0, 1, 4, 5, 7, 8, 11],
    "byzantine": [0, 1, 4, 5, 7, 8, 11],
    "japanese": [0, 1, 5, 7, 8],
    "hirajoshi": [0, 2, 3, 7, 8],
    "in-sen": [0, 1, 5, 7, 10],
    "iwato": [0, 1, 5, 6, 10],
    "kumoi": [0, 2, 3, 7, 9],
    "pelog": [0, 1, 3, 7, 8],
    "chinese": [0, 4, 6, 7, 11],
    "egyptian": [0, 2, 5, 7, 10],
    "indian": [0, 4, 5, 7, 10],
    "romanian minor": [0, 2, 3, 6, 7, 9, 10],
    "spanish gypsy": [0, 1, 4, 5, 7, 8, 10],
    "flamenco": [0, 1, 4, 5, 7, 8, 11],
    "jewish": [0, 1, 4, 5, 7, 8, 10],
    "enigmatic": [0, 1, 4, 6, 8, 10, 11],
    "prometheus": [0, 2, 4, 6, 9, 10],
    "tritone": [0, 1, 4, 6, 7, 10],
    "leading whole tone": [0, 2, 4, 6, 8, 10, 11],
    "balinese": [0, 1, 3, 7, 8],
    "javanese": [0, 1, 3, 5, 7, 9, 10],
    "overtone": [0, 2, 4, 6, 7, 9, 10],
    "acoustic": [0, 2, 4, 6, 7, 9, 10],
    "harmonic major": [0, 2, 4, 5, 7, 8, 11],
    "double harmonic major": [0, 1, 4, 5, 7, 8, 11],
    "lydian minor": [0, 2, 4, 6, 7, 8, 10],
    "phrygian b4": [0, 1, 3, 4, 7, 8, 10],
}

SCALE_DEGREES = {
    "major": ["I", "ii", "iii", "IV", "V", "vi", "vii°"],
    "minor": ["i", "ii°", "III", "iv", "v", "VI", "VII"],
    "natural minor": ["i", "ii°", "III", "iv", "v", "VI", "VII"],
    "harmonic minor": ["i", "ii°", "III+", "iv", "V", "VI", "vii°"],
    "dorian": ["i", "ii", "III", "IV", "v", "vi°", "VII"],
    "phrygian": ["i", "II", "III", "iv", "v°", "VI", "vii"],
    "lydian": ["I", "II", "iii", "#iv°", "V", "vi", "vii"],
    "mixolydian": ["I", "ii", "iii°", "IV", "v", "vi", "VII"],
    "locrian": ["i°", "II", "iii", "iv", "V", "VI", "vii"],
}

CHORD_PROGRESSIONS = {
    "pop_1": ["I", "V", "vi", "IV"],
    "pop_2": ["I", "IV", "V", "I"],
    "pop_3": ["vi", "IV", "I", "V"],
    "pop_4": ["I", "vi", "IV", "V"],
    "jazz_2_5_1": ["ii7", "V7", "Imaj7"],
    "jazz_2_5_1_minor": ["ii7b5", "V7", "i"],
    "jazz_1_6_2_5": ["Imaj7", "vi7", "ii7", "V7"],
    "jazz_3_6_2_5": ["iii7", "VI7", "ii7", "V7"],
    "jazz_tritone_sub": ["ii7", "bII7", "Imaj7"],
    "blues_12_bar": ["I7", "I7", "I7", "I7", "IV7", "IV7", "I7", "I7", "V7", "IV7", "I7", "V7"],
    "blues_quick_change": ["I7", "IV7", "I7", "I7", "IV7", "IV7", "I7", "I7", "V7", "IV7", "I7", "V7"],
    "minor_blues": ["i7", "i7", "i7", "i7", "iv7", "iv7", "i7", "i7", "VI7", "V7", "i7", "V7"],
    "andalusian": ["i", "VII", "VI", "V"],
    "pachelbel": ["I", "V", "vi", "iii", "IV", "I", "IV", "V"],
    "circle_of_fifths": ["I", "IV", "vii°", "iii", "vi", "ii", "V", "I"],
    "royal_road": ["IV", "V", "iii", "vi"],
    "rock_1": ["I", "bVII", "IV", "I"],
    "rock_2": ["I", "IV", "bVII", "IV"],
    "doo_wop": ["I", "vi", "IV", "V"],
    "50s_progression": ["I", "vi", "IV", "V"],
    "ragtime": ["I", "I", "IV", "iv", "I", "V7", "I", "V7"],
    "rhythm_changes_a": ["Imaj7", "vi7", "ii7", "V7", "iii7", "VI7", "ii7", "V7"],
    "coltrane_changes": ["Imaj7", "bIIImaj7", "Vmaj7", "bVIImaj7"],
    "backdoor": ["IVmaj7", "bVII7", "Imaj7"],
    "modal_interchange": ["I", "bVII", "bVI", "V"],
    "chromatic_mediants": ["I", "bVI", "I", "bIII"],
    "line_cliche_major": ["Imaj7", "Imaj7#5", "I6", "I#5"],
    "line_cliche_minor": ["i", "iM7", "i7", "i6"],
    "deceptive_cadence": ["V", "vi"],
    "plagal_cadence": ["IV", "I"],
    "authentic_cadence": ["V", "I"],
    "half_cadence": ["I", "V"],
}

CIRCLE_OF_FIFTHS = {
    "major": ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"],
    "minor": ["A", "E", "B", "F#", "C#", "G#", "D#", "Bb", "F", "C", "G", "D"],
    "sharps": {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7},
    "flats": {"C": 0, "F": 1, "Bb": 2, "Eb": 3, "Ab": 4, "Db": 5, "Gb": 6, "Cb": 7},
}

RELATIVE_KEYS = {
    "C": "Am", "G": "Em", "D": "Bm", "A": "F#m", "E": "C#m", "B": "G#m",
    "F#": "D#m", "Gb": "Ebm", "Db": "Bbm", "Ab": "Fm", "Eb": "Cm",
    "Bb": "Gm", "F": "Dm",
    "Am": "C", "Em": "G", "Bm": "D", "F#m": "A", "C#m": "E", "G#m": "B",
    "D#m": "F#", "Ebm": "Gb", "Bbm": "Db", "Fm": "Ab", "Cm": "Eb",
    "Gm": "Bb", "Dm": "F",
}

PARALLEL_KEYS = {
    "C": "Cm", "G": "Gm", "D": "Dm", "A": "Am", "E": "Em", "B": "Bm",
    "F#": "F#m", "Gb": "Gbm", "Db": "Dbm", "Ab": "Abm", "Eb": "Ebm",
    "Bb": "Bbm", "F": "Fm",
    "Cm": "C", "Gm": "G", "Dm": "D", "Am": "A", "Em": "E", "Bm": "B",
    "F#m": "F#", "Gbm": "Gb", "Dbm": "Db", "Abm": "Ab", "Ebm": "Eb",
    "Bbm": "Bb", "Fm": "F",
}

TIME_SIGNATURES = {
    "4/4": {"beats": 4, "beat_value": 4, "name": "common time", "feel": "duple"},
    "3/4": {"beats": 3, "beat_value": 4, "name": "waltz time", "feel": "triple"},
    "2/4": {"beats": 2, "beat_value": 4, "name": "march time", "feel": "duple"},
    "6/8": {"beats": 6, "beat_value": 8, "name": "compound duple", "feel": "compound duple"},
    "9/8": {"beats": 9, "beat_value": 8, "name": "compound triple", "feel": "compound triple"},
    "12/8": {"beats": 12, "beat_value": 8, "name": "compound quadruple", "feel": "compound quadruple"},
    "2/2": {"beats": 2, "beat_value": 2, "name": "cut time", "feel": "duple"},
    "5/4": {"beats": 5, "beat_value": 4, "name": "quintuple", "feel": "irregular"},
    "7/4": {"beats": 7, "beat_value": 4, "name": "septuple", "feel": "irregular"},
    "7/8": {"beats": 7, "beat_value": 8, "name": "irregular", "feel": "irregular"},
    "5/8": {"beats": 5, "beat_value": 8, "name": "irregular", "feel": "irregular"},
    "11/8": {"beats": 11, "beat_value": 8, "name": "irregular", "feel": "irregular"},
    "15/8": {"beats": 15, "beat_value": 8, "name": "irregular", "feel": "irregular"},
    "3/8": {"beats": 3, "beat_value": 8, "name": "simple triple", "feel": "triple"},
}

TEMPO_MARKINGS = {
    "larghissimo": (1, 24), "grave": (25, 45), "largo": (40, 60),
    "lento": (45, 60), "larghetto": (60, 66), "adagio": (66, 76),
    "adagietto": (70, 80), "andante": (76, 108), "andantino": (80, 108),
    "marcia moderato": (83, 85), "andante moderato": (92, 112),
    "moderato": (108, 120), "allegretto": (112, 120), "allegro moderato": (116, 120),
    "allegro": (120, 156), "vivace": (156, 176), "vivacissimo": (172, 176),
    "allegrissimo": (172, 176), "presto": (168, 200), "prestissimo": (200, 300),
}

DYNAMICS = {
    "ppp": ("pianississimo", 16),
    "pp": ("pianissimo", 33),
    "p": ("piano", 49),
    "mp": ("mezzo piano", 64),
    "mf": ("mezzo forte", 80),
    "f": ("forte", 96),
    "ff": ("fortissimo", 112),
    "fff": ("fortississimo", 127),
    "sfz": ("sforzando", None),
    "fp": ("fortepiano", None),
    "sfp": ("sforzando piano", None),
    "rfz": ("rinforzando", None),
}

ARTICULATIONS = {
    "staccato": "short, detached",
    "staccatissimo": "very short, detached",
    "legato": "smooth, connected",
    "tenuto": "held for full value",
    "accent": "emphasized",
    "marcato": "strongly accented",
    "portato": "slightly detached",
    "spiccato": "bouncing bow (strings)",
    "pizzicato": "plucked (strings)",
    "arco": "bowed (strings)",
    "tremolo": "rapid repetition",
    "trill": "rapid alternation with adjacent note",
    "mordent": "rapid alternation with lower note",
    "turn": "ornamental figure",
    "glissando": "slide between notes",
    "fermata": "pause, hold",
}

VOICE_LEADING_RULES = {
    "parallel_fifths": "Avoid parallel perfect fifths between voices",
    "parallel_octaves": "Avoid parallel octaves between voices",
    "hidden_fifths": "Avoid hidden/direct fifths in outer voices",
    "hidden_octaves": "Avoid hidden/direct octaves in outer voices",
    "voice_crossing": "Avoid crossing of adjacent voices",
    "voice_overlap": "Avoid overlap between adjacent voices",
    "large_leaps": "Large leaps (>P5) should resolve stepwise in opposite direction",
    "leading_tone": "Leading tone should resolve up to tonic",
    "seventh_resolution": "Chord sevenths should resolve down by step",
    "doubled_leading_tone": "Avoid doubling the leading tone",
    "tritone_resolution": "Tritone should resolve inward (dim5) or outward (aug4)",
}


def pitch_to_note(pitch: int) -> str:
    return NOTE_NAMES[pitch % 12] + str(pitch // 12 - 1)


def pitch_to_note_flat(pitch: int) -> str:
    return NOTE_NAMES_FLAT[pitch % 12] + str(pitch // 12 - 1)


def note_to_pitch(note: str) -> int:
    note = note.strip()
    if not note:
        return 60

    octave = 4
    note_part = note

    for i, char in enumerate(note):
        if char.isdigit() or (char == '-' and i > 0):
            note_part = note[:i]
            try:
                octave = int(note[i:])
            except ValueError:
                octave = 4
            break

    pc = NOTE_TO_PC.get(note_part, NOTE_TO_PC.get(note_part.capitalize(), 0))
    return (octave + 1) * 12 + pc


def get_interval(pitch1: int, pitch2: int) -> Tuple[int, str]:
    semitones = abs(pitch2 - pitch1)
    interval_info = INTERVALS.get(semitones % 24, INTERVALS.get(semitones % 12, ("?", "unknown")))
    return semitones, interval_info[1]


def get_interval_name(semitones: int) -> str:
    interval_info = INTERVALS.get(abs(semitones) % 24, INTERVALS.get(abs(semitones) % 12))
    if interval_info:
        return interval_info[1]
    return f"{abs(semitones)} semitones"


def transpose_pitch(pitch: int, semitones: int) -> int:
    return pitch + semitones


def transpose_to_key(pitch: int, from_key: str, to_key: str) -> int:
    from_root, _ = parse_key(from_key)
    to_root, _ = parse_key(to_key)
    interval = (to_root - from_root) % 12
    return pitch + interval


def get_relative_key(key_str: str) -> str:
    root_pc, scale_type = parse_key(key_str)
    root_name = NOTE_NAMES[root_pc]

    if scale_type == "minor":
        relative_root = (root_pc + 3) % 12
        return f"{NOTE_NAMES[relative_root]} major"
    else:
        relative_root = (root_pc - 3) % 12
        return f"{NOTE_NAMES[relative_root]} minor"


def get_parallel_key(key_str: str) -> str:
    root_pc, scale_type = parse_key(key_str)
    root_name = NOTE_NAMES[root_pc]

    if scale_type == "minor":
        return f"{root_name} major"
    else:
        return f"{root_name} minor"


def get_circle_of_fifths_distance(key1: str, key2: str) -> int:
    root1, type1 = parse_key(key1)
    root2, type2 = parse_key(key2)

    if type1 == "minor":
        root1 = (root1 + 3) % 12
    if type2 == "minor":
        root2 = (root2 + 3) % 12

    distance = (root2 - root1) % 12
    fifths = (distance * 7) % 12

    return min(fifths, 12 - fifths)


def parse_key(key_str: str) -> Tuple[int, str]:
    if not key_str or key_str.lower() == "unknown":
        return 0, "major"

    key_str = key_str.strip()
    key_lower = key_str.lower()

    for scale_name in SCALE_INTERVALS.keys():
        if scale_name in key_lower:
            root_str = key_str.lower().replace(scale_name, "").strip()
            if root_str:
                root_pc = NOTE_TO_PC.get(root_str, NOTE_TO_PC.get(root_str.capitalize(), 0))
            else:
                root_pc = 0
            return root_pc, scale_name

    is_minor = "minor" in key_lower or "min" in key_lower or key_str.endswith("m")
    scale_type = "minor" if is_minor else "major"

    root_str = key_str.replace("minor", "").replace("Minor", "").replace("major", "").replace("Major", "")
    root_str = root_str.replace("min", "").replace("Min", "").replace("maj", "").replace("Maj", "")
    root_str = root_str.strip()

    if root_str.endswith("m") and len(root_str) > 1:
        root_str = root_str[:-1]

    root_str = root_str.strip()
    if not root_str:
        return 0, scale_type

    root_pc = NOTE_TO_PC.get(root_str, NOTE_TO_PC.get(root_str.capitalize(), 0))
    return root_pc, scale_type


def get_scale_notes(key_str: str, pitch_low: int, pitch_high: int) -> List[int]:
    root_pc, scale_type = parse_key(key_str)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])

    scale_pcs = set((root_pc + i) % 12 for i in intervals)

    if scale_type in ("minor", "natural minor", "aeolian"):
        harmonic_intervals = SCALE_INTERVALS.get("harmonic minor", [])
        for i in harmonic_intervals:
            scale_pcs.add((root_pc + i) % 12)

    valid_pitches = []
    for pitch in range(pitch_low, pitch_high + 1):
        if pitch % 12 in scale_pcs:
            valid_pitches.append(pitch)

    return valid_pitches


def get_scale_pitch_classes(key_str: str) -> Set[int]:
    root_pc, scale_type = parse_key(key_str)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])
    scale_pcs = set((root_pc + i) % 12 for i in intervals)

    if scale_type in ("minor", "natural minor", "aeolian"):
        harmonic_intervals = SCALE_INTERVALS.get("harmonic minor", [])
        for i in harmonic_intervals:
            scale_pcs.add((root_pc + i) % 12)

    return scale_pcs


def get_scale_note_names(key_str: str) -> str:
    root_pc, scale_type = parse_key(key_str)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])

    note_names = []
    for interval in intervals:
        pc = (root_pc + interval) % 12
        note_names.append(NOTE_NAMES[pc])

    if scale_type in ("minor", "natural minor", "aeolian"):
        raised_7th = (root_pc + 11) % 12
        natural_7th_name = NOTE_NAMES[(root_pc + 10) % 12]
        raised_7th_name = NOTE_NAMES[raised_7th]
        if natural_7th_name in note_names:
            idx = note_names.index(natural_7th_name)
            note_names[idx] = f"{natural_7th_name}/{raised_7th_name}"

    return ", ".join(note_names)


def get_available_scales() -> List[str]:
    return list(SCALE_INTERVALS.keys())


def get_chord_tones(chord_name: str) -> List[int]:
    root_str = ""
    chord_suffix = ""

    for i, char in enumerate(chord_name):
        if char in "mMdas#b1234567890()+/o°ø":
            root_str = chord_name[:i]
            chord_suffix = chord_name[i:]
            break
    else:
        root_str = chord_name
        chord_suffix = ""

    if not root_str:
        root_str = "C"

    root_pc = NOTE_TO_PC.get(root_str, NOTE_TO_PC.get(root_str.capitalize(), 0))

    for intervals, suffix in CHORD_TYPES.items():
        if suffix == chord_suffix:
            return [(root_pc + i) % 12 for i in sorted(intervals)]

    return [root_pc]


def build_chord(root: int, quality: str = "") -> List[int]:
    for intervals, suffix in CHORD_TYPES.items():
        if suffix == quality:
            return [(root + i) % 12 for i in sorted(intervals)]

    return [root % 12, (root + 4) % 12, (root + 7) % 12]


def get_diatonic_chords(key_str: str) -> List[Tuple[str, str]]:
    root_pc, scale_type = parse_key(key_str)
    degrees = SCALE_DEGREES.get(scale_type, SCALE_DEGREES["major"])
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])

    chords = []
    for i, degree in enumerate(degrees):
        chord_root_pc = (root_pc + intervals[i]) % 12
        chord_root_name = NOTE_NAMES[chord_root_pc]
        chords.append((chord_root_name, degree))

    return chords


def analyze_chord(pitches: List[int]) -> Tuple[str, Optional[int]]:
    if not pitches:
        return "?", None
    if len(pitches) == 1:
        root = pitches[0] % 12
        return NOTE_NAMES[root], root

    pitch_classes = sorted(set(p % 12 for p in pitches))
    bass_pc = min(pitches) % 12

    for root_pc in pitch_classes:
        intervals = frozenset((pc - root_pc) % 12 for pc in pitch_classes)
        if intervals in CHORD_TYPES:
            chord_name = NOTE_NAMES[root_pc] + CHORD_TYPES[intervals]
            if root_pc != bass_pc:
                chord_name += "/" + NOTE_NAMES[bass_pc]
            return chord_name, root_pc

    best_match = _find_best_chord_match(pitch_classes, bass_pc)
    if best_match:
        return best_match

    inferred = _infer_chord_from_intervals(pitch_classes, bass_pc)
    if inferred:
        return inferred

    return NOTE_NAMES[bass_pc] + "(?)", bass_pc


def _find_best_chord_match(
    pitch_classes: List[int], bass_pc: int
) -> Optional[Tuple[str, int]]:
    best_score = 0
    best_result: Optional[Tuple[str, int]] = None

    for root_pc in pitch_classes:
        intervals = frozenset((pc - root_pc) % 12 for pc in pitch_classes)
        for chord_intervals, chord_suffix in CHORD_TYPES.items():
            common = len(intervals & chord_intervals)
            missing = len(chord_intervals - intervals)
            extra = len(intervals - chord_intervals)

            if common < 2:
                continue

            score = common * 10 - missing * 5 - extra * 2

            has_root = 0 in intervals
            has_third = 3 in intervals or 4 in intervals
            has_fifth = 7 in intervals or 6 in intervals or 8 in intervals

            if has_root:
                score += 5
            if has_third:
                score += 3
            if has_fifth:
                score += 2

            if score > best_score and missing <= 2 and extra <= 2:
                best_score = score
                suffix = chord_suffix
                if extra > 0:
                    extra_intervals = intervals - chord_intervals
                    if extra_intervals:
                        suffix += _describe_extensions(extra_intervals)
                chord_name = NOTE_NAMES[root_pc] + suffix
                if root_pc != bass_pc:
                    chord_name += "/" + NOTE_NAMES[bass_pc]
                best_result = (chord_name, root_pc)

    return best_result


def _describe_extensions(extra_intervals: frozenset) -> str:
    ext_map = {
        1: "b9", 2: "9", 3: "#9", 5: "11", 6: "#11",
        8: "b13", 9: "13", 10: "7", 11: "maj7"
    }
    extensions = []
    for interval in sorted(extra_intervals):
        if interval in ext_map:
            extensions.append(ext_map[interval])
    if extensions:
        return "add(" + ",".join(extensions) + ")"
    return ""


def _infer_chord_from_intervals(
    pitch_classes: List[int], bass_pc: int
) -> Optional[Tuple[str, int]]:
    if len(pitch_classes) < 2:
        return None

    for root_pc in pitch_classes:
        intervals = set((pc - root_pc) % 12 for pc in pitch_classes)

        has_major_third = 4 in intervals
        has_minor_third = 3 in intervals
        has_perfect_fifth = 7 in intervals
        has_dim_fifth = 6 in intervals
        has_aug_fifth = 8 in intervals
        has_minor_seventh = 10 in intervals
        has_major_seventh = 11 in intervals
        has_ninth = 2 in intervals or 14 in intervals
        has_fourth = 5 in intervals
        has_sixth = 9 in intervals

        chord_type = ""

        if has_major_third and has_perfect_fifth:
            chord_type = ""
        elif has_minor_third and has_perfect_fifth:
            chord_type = "m"
        elif has_minor_third and has_dim_fifth:
            chord_type = "dim"
        elif has_major_third and has_aug_fifth:
            chord_type = "aug"
        elif has_fourth and has_perfect_fifth:
            chord_type = "sus4"
        elif has_ninth and has_perfect_fifth and not has_major_third and not has_minor_third:
            chord_type = "sus2"
        elif has_major_third and not has_perfect_fifth and not has_dim_fifth and not has_aug_fifth:
            chord_type = "(no5)"
        elif has_minor_third and not has_perfect_fifth and not has_dim_fifth:
            chord_type = "m(no5)"
        elif has_perfect_fifth and not has_major_third and not has_minor_third:
            chord_type = "5"
        else:
            continue

        if has_major_seventh:
            if chord_type == "m":
                chord_type = "mM7"
            elif chord_type == "":
                chord_type = "maj7"
            elif chord_type == "aug":
                chord_type = "augmaj7"
            else:
                chord_type += "maj7"
        elif has_minor_seventh:
            if chord_type == "dim":
                chord_type = "m7b5"
            elif chord_type == "m":
                chord_type = "m7"
            elif chord_type == "":
                chord_type = "7"
            elif chord_type == "sus4":
                chord_type = "7sus4"
            elif chord_type == "sus2":
                chord_type = "7sus2"
            else:
                chord_type += "7"

        if has_sixth and "7" not in chord_type:
            chord_type += "6"

        if has_ninth and "sus2" not in chord_type:
            if "7" in chord_type or "maj7" in chord_type:
                chord_type = chord_type.replace("7", "9").replace("maj9", "maj9")
            else:
                chord_type += "add9"

        chord_name = NOTE_NAMES[root_pc] + chord_type
        if root_pc != bass_pc:
            chord_name += "/" + NOTE_NAMES[bass_pc]
        return chord_name, root_pc

    return None


def is_in_scale(pitch: int, key_str: str) -> bool:
    scale_pcs = get_scale_pitch_classes(key_str)
    return pitch % 12 in scale_pcs


def find_nearest_scale_note(pitch: int, key_str: str, direction: int = 0) -> int:
    scale_pcs = get_scale_pitch_classes(key_str)
    pc = pitch % 12

    if pc in scale_pcs:
        return pitch

    if direction >= 0:
        for offset in range(1, 7):
            if (pc + offset) % 12 in scale_pcs:
                return pitch + offset
            if direction == 0 and (pc - offset) % 12 in scale_pcs:
                return pitch - offset
    else:
        for offset in range(1, 7):
            if (pc - offset) % 12 in scale_pcs:
                return pitch - offset

    return pitch


def get_chord_progression(progression_name: str) -> Optional[List[str]]:
    return CHORD_PROGRESSIONS.get(progression_name)


def get_available_progressions() -> List[str]:
    return list(CHORD_PROGRESSIONS.keys())


def suggest_next_chords(current_chord: str, key_str: str) -> List[str]:
    root_pc, scale_type = parse_key(key_str)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])

    common_movements = {
        "I": ["IV", "V", "vi", "ii"],
        "ii": ["V", "IV", "vii°"],
        "iii": ["vi", "IV", "ii"],
        "IV": ["V", "I", "ii", "vii°"],
        "V": ["I", "vi", "IV"],
        "vi": ["IV", "ii", "V"],
        "vii°": ["I", "iii"],
        "i": ["iv", "V", "VI", "ii°"],
        "ii°": ["V", "iv"],
        "III": ["VI", "iv"],
        "iv": ["V", "i", "ii°"],
        "v": ["i", "VI"],
        "VI": ["iv", "ii°", "V"],
        "VII": ["i", "III"],
    }

    return common_movements.get(current_chord, ["I", "IV", "V"])


def get_tempo_description(bpm: int) -> str:
    for tempo_name, (min_bpm, max_bpm) in TEMPO_MARKINGS.items():
        if min_bpm <= bpm <= max_bpm:
            return tempo_name
    if bpm < 24:
        return "extremely slow"
    return "extremely fast"


def velocity_to_dynamic(velocity: int) -> str:
    for dynamic, (name, vel) in DYNAMICS.items():
        if vel is not None and velocity <= vel:
            return dynamic
    return "fff"


def dynamic_to_velocity(dynamic: str) -> int:
    if dynamic in DYNAMICS:
        vel = DYNAMICS[dynamic][1]
        return vel if vel is not None else 80
    return 80


def detect_key_from_chords(chord_roots: List[int]) -> str:
    if not chord_roots:
        return "unknown"

    root_counts: Dict[int, int] = {}
    for root in chord_roots:
        if root is not None:
            root_counts[root] = root_counts.get(root, 0) + 1

    if not root_counts:
        return "unknown"

    most_common = max(root_counts.keys(), key=lambda r: root_counts[r])

    major_scale = [0, 2, 4, 5, 7, 9, 11]
    minor_scale = [0, 2, 3, 5, 7, 8, 10]

    for tonic in range(12):
        major_notes = set((tonic + i) % 12 for i in major_scale)
        minor_notes = set((tonic + i) % 12 for i in minor_scale)

        if all(r in major_notes for r in root_counts.keys()):
            return f"{NOTE_NAMES[tonic]} major"
        if all(r in minor_notes for r in root_counts.keys()):
            return f"{NOTE_NAMES[tonic]} minor"

    return f"{NOTE_NAMES[most_common]} (estimated)"


def detect_key_from_notes(pitches: List[int]) -> str:
    if not pitches:
        return "unknown"

    pitch_classes = [p % 12 for p in pitches]
    pc_counts: Dict[int, int] = {}
    for pc in pitch_classes:
        pc_counts[pc] = pc_counts.get(pc, 0) + 1

    best_key = "C major"
    best_score = 0

    for scale_name in ["major", "minor", "dorian", "mixolydian", "phrygian"]:
        for tonic in range(12):
            intervals = SCALE_INTERVALS[scale_name]
            scale_pcs = set((tonic + i) % 12 for i in intervals)

            score = sum(pc_counts.get(pc, 0) for pc in scale_pcs)
            non_scale = sum(pc_counts.get(pc, 0) for pc in range(12) if pc not in scale_pcs)
            score -= non_scale * 0.5

            tonic_weight = pc_counts.get(tonic, 0) * 2
            fifth_weight = pc_counts.get((tonic + 7) % 12, 0) * 1.5
            score += tonic_weight + fifth_weight

            if score > best_score:
                best_score = score
                best_key = f"{NOTE_NAMES[tonic]} {scale_name}"

    return best_key


def get_mode_of_scale(scale_name: str, degree: int) -> Optional[str]:
    base_intervals = SCALE_INTERVALS.get(scale_name)
    if not base_intervals:
        return None

    rotated = base_intervals[degree - 1:] + base_intervals[:degree - 1]
    normalized = [(i - rotated[0]) % 12 for i in rotated]

    for name, intervals in SCALE_INTERVALS.items():
        if intervals == normalized:
            return name

    return None


def calculate_voice_leading_cost(chord1_pitches: List[int], chord2_pitches: List[int]) -> int:
    if not chord1_pitches or not chord2_pitches:
        return 0

    total_movement = 0
    for p1 in chord1_pitches:
        min_distance = min(abs(p2 - p1) for p2 in chord2_pitches)
        total_movement += min_distance

    return total_movement


def smooth_voice_leading(
    from_pitches: List[int],
    to_chord_pcs: List[int],
    pitch_low: int,
    pitch_high: int
) -> List[int]:
    result = []

    for pitch in from_pitches:
        best_pitch = pitch
        min_distance = float('inf')

        for pc in to_chord_pcs:
            for octave in range((pitch_low // 12) - 1, (pitch_high // 12) + 2):
                target = pc + octave * 12
                if pitch_low <= target <= pitch_high:
                    distance = abs(target - pitch)
                    if distance < min_distance:
                        min_distance = distance
                        best_pitch = target

        if pitch_low <= best_pitch <= pitch_high:
            result.append(best_pitch)

    return sorted(set(result))
