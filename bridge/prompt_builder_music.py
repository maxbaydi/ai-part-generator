from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import QUARTERS_PER_WHOLE
    from music_theory import detect_key_from_chords
    from prompt_builder_common import (
        BAR_RANGE_END_OFFSET,
        BAR_RANGE_SEPARATOR,
        DEFAULT_BAR_INDEX,
        DEFAULT_BEAT_UNIT,
        DEFAULT_BEATS_PER_BAR,
        DEFAULT_TIME_SIGNATURE,
        MIN_BARS_COUNT,
        MIN_MAX_NOTES_DELTA,
        MIN_NOTES_COUNT,
        SEMITONES_PER_OCTAVE,
        TIME_SIGNATURE_SEPARATOR,
        UNKNOWN_VALUE,
        ZERO_TIME_Q,
        is_non_empty_list,
        normalize_lower,
        normalize_text,
    )
except ImportError:
    from .constants import QUARTERS_PER_WHOLE
    from .music_theory import detect_key_from_chords
    from .prompt_builder_common import (
        BAR_RANGE_END_OFFSET,
        BAR_RANGE_SEPARATOR,
        DEFAULT_BAR_INDEX,
        DEFAULT_BEAT_UNIT,
        DEFAULT_BEATS_PER_BAR,
        DEFAULT_TIME_SIGNATURE,
        MIN_BARS_COUNT,
        MIN_MAX_NOTES_DELTA,
        MIN_NOTES_COUNT,
        SEMITONES_PER_OCTAVE,
        TIME_SIGNATURE_SEPARATOR,
        UNKNOWN_VALUE,
        ZERO_TIME_Q,
        is_non_empty_list,
        normalize_lower,
        normalize_text,
    )


CHORD_ROOTS = (
    "C#", "Db", "D#", "Eb", "F#", "Gb", "G#", "Ab",
    "A#", "Bb", "C", "D", "E", "F", "G", "A", "B",
)
CHORD_ROOT_NAME_MAP = {
    "C": "C", "C#": "C#", "Db": "Db", "D": "D", "D#": "D#", "Eb": "Eb",
    "E": "E", "F": "F", "F#": "F#", "Gb": "Gb", "G": "G", "G#": "G#",
    "Ab": "Ab", "A": "A", "A#": "A#", "Bb": "Bb", "B": "B",
}
CHORD_ROOT_PC_MAP = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

MINOR_TOKEN = "m"
MAJOR_TOKEN = "maj"
DIM_TOKEN = "dim"
DIM_SYMBOL = "°"
HALF_DIM_TOKEN = "m7b5"
HALF_DIM_SYMBOL = "ø"
AUG_TOKEN = "aug"
AUG_SYMBOL = "+"
SUS4_TOKEN = "sus4"
SUS2_TOKEN = "sus2"
ADD9_TOKEN = "add9"
ADD_TOKEN = "add"
ADD11_TOKEN = "11"
MIN9_TOKEN = "m9"
DOM9_TOKEN = "9"
MIN7_TOKEN = "m7"
MIN7_ALT_TOKEN = "min7"
DOM7_TOKEN = "7"
MIN_TOKEN = "min"

INTERVALS_MAJOR7 = [0, 4, 7, 11]
INTERVALS_HALF_DIM7 = [0, 3, 6, 10]
INTERVALS_DIM7 = [0, 3, 6, 9]
INTERVALS_DIM_TRIAD = [0, 3, 6]
INTERVALS_AUG_TRIAD = [0, 4, 8]
INTERVALS_SUS4 = [0, 5, 7]
INTERVALS_SUS2 = [0, 2, 7]
INTERVALS_ADD9 = [0, 4, 7, 14]
INTERVALS_ADD11 = [0, 4, 7, 17]
INTERVALS_MINOR9 = [0, 3, 7, 10, 14]
INTERVALS_DOM9 = [0, 4, 7, 10, 14]
INTERVALS_MINOR7 = [0, 3, 7, 10]
INTERVALS_DOM7 = [0, 4, 7, 10]
INTERVALS_MINOR_TRIAD = [0, 3, 7]
INTERVALS_MAJOR_TRIAD = [0, 4, 7]

NOTE_DENSITY_RULES = [
    (("melody",), 2, 8, "moderate melodic density with varied rhythms"),
    (("arpeggio",), 8, 16, "continuous arpeggiated pattern"),
    (("bass",), 1, 4, "sparse but rhythmically strong bass notes"),
    (("chord",), 1, 4, "chord changes, multiple simultaneous notes per chord"),
    (("pad", "sustain"), 0.5, 2, "long sustained notes with smooth transitions"),
    (("rhythm",), 4, 16, "rhythmic pattern with clear pulse"),
    (("counter",), 2, 6, "independent melodic line that complements the main melody"),
    (("accomp",), 2, 8, "supportive accompaniment pattern"),
]
DEFAULT_DENSITY_MIN = 2
DEFAULT_DENSITY_MAX = 8
DEFAULT_DENSITY_DESC = "appropriate musical content"


def split_time_signature(time_sig: str) -> Tuple[int, int]:
    if not time_sig:
        return DEFAULT_BEATS_PER_BAR, DEFAULT_BEAT_UNIT
    try:
        parts = str(time_sig).split(TIME_SIGNATURE_SEPARATOR)
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError, TypeError):
        return DEFAULT_BEATS_PER_BAR, DEFAULT_BEAT_UNIT


def parse_chord_root(chord_name: str) -> Tuple[str, int, str]:
    chord_str = normalize_text(chord_name)
    if not chord_str:
        return "", 0, ""
    for root in CHORD_ROOTS:
        if chord_str.startswith(root):
            return (
                CHORD_ROOT_NAME_MAP.get(root, root),
                CHORD_ROOT_PC_MAP.get(root, 0),
                chord_str[len(root):],
            )
    return "", 0, chord_str


def extract_key_from_chord_map(chord_map: Optional[List[Dict[str, Any]]]) -> str:
    if not is_non_empty_list(chord_map):
        return UNKNOWN_VALUE

    first_chord = chord_map[0]
    if not isinstance(first_chord, dict):
        return UNKNOWN_VALUE

    chord_name = normalize_text(first_chord.get("chord"))
    if not chord_name:
        return UNKNOWN_VALUE

    root, _root_pc, suffix = parse_chord_root(chord_name)
    if not root:
        return UNKNOWN_VALUE

    suffix_lower = suffix.lower()
    if MINOR_TOKEN in suffix_lower and MAJOR_TOKEN not in suffix_lower:
        return f"{root} minor"
    return f"{root} major"


def bar_to_time_q(bar: int, time_sig: str = DEFAULT_TIME_SIGNATURE) -> float:
    num, denom = split_time_signature(time_sig)
    quarters_per_bar = num * (QUARTERS_PER_WHOLE / denom)
    return (bar - DEFAULT_BAR_INDEX) * quarters_per_bar


def bars_range_to_time_q(bars_str: str, time_sig: str = DEFAULT_TIME_SIGNATURE) -> Tuple[float, float]:
    if not bars_str:
        return ZERO_TIME_Q, ZERO_TIME_Q
    try:
        if BAR_RANGE_SEPARATOR in bars_str:
            parts = bars_str.split(BAR_RANGE_SEPARATOR)
            start_bar = int(parts[0])
            end_bar = int(parts[1])
        else:
            start_bar = int(bars_str)
            end_bar = start_bar
    except (ValueError, IndexError):
        return ZERO_TIME_Q, ZERO_TIME_Q

    start_q = bar_to_time_q(start_bar, time_sig)
    end_q = bar_to_time_q(end_bar + BAR_RANGE_END_OFFSET, time_sig)
    return start_q, end_q


def get_chord_tones_from_name(chord_name: str) -> List[int]:
    chord_str = normalize_text(chord_name)
    if not chord_str:
        return []

    _root_name, root_pc, suffix = parse_chord_root(chord_str)
    suffix_lower = suffix.lower()

    if "maj7" in suffix_lower or "maj9" in suffix_lower:
        intervals = INTERVALS_MAJOR7
    elif HALF_DIM_TOKEN in suffix_lower or HALF_DIM_SYMBOL in suffix:
        intervals = INTERVALS_HALF_DIM7
    elif "dim7" in suffix_lower or f"{DIM_SYMBOL}7" in suffix:
        intervals = INTERVALS_DIM7
    elif DIM_TOKEN in suffix_lower or DIM_SYMBOL in suffix:
        intervals = INTERVALS_DIM_TRIAD
    elif AUG_TOKEN in suffix_lower or AUG_SYMBOL in suffix:
        intervals = INTERVALS_AUG_TRIAD
    elif SUS4_TOKEN in suffix_lower:
        intervals = INTERVALS_SUS4
    elif SUS2_TOKEN in suffix_lower:
        intervals = INTERVALS_SUS2
    elif ADD9_TOKEN in suffix_lower:
        intervals = INTERVALS_ADD9
    elif ADD_TOKEN in suffix_lower and ADD11_TOKEN in suffix_lower:
        intervals = INTERVALS_ADD11
    elif MIN9_TOKEN in suffix_lower:
        intervals = INTERVALS_MINOR9
    elif DOM9_TOKEN in suffix_lower and MINOR_TOKEN not in suffix_lower:
        intervals = INTERVALS_DOM9
    elif MIN7_TOKEN in suffix_lower or MIN7_ALT_TOKEN in suffix_lower:
        intervals = INTERVALS_MINOR7
    elif DOM7_TOKEN in suffix_lower:
        intervals = INTERVALS_DOM7
    elif suffix_lower.startswith(MINOR_TOKEN) or MIN_TOKEN in suffix_lower:
        intervals = INTERVALS_MINOR_TRIAD
    else:
        intervals = INTERVALS_MAJOR_TRIAD

    return [(root_pc + i) % SEMITONES_PER_OCTAVE for i in intervals]


def estimate_note_count(length_q: float, bpm: float, time_sig: str, generation_type: str) -> Tuple[int, int, str]:
    """Estimate recommended note count based on musical context."""
    beats_per_bar, beat_unit = split_time_signature(time_sig)

    quarters_per_bar = beats_per_bar * (QUARTERS_PER_WHOLE / beat_unit)
    bars = length_q / quarters_per_bar if quarters_per_bar > 0 else length_q / QUARTERS_PER_WHOLE
    bars = max(MIN_BARS_COUNT, bars)

    gen_type_lower = normalize_lower(generation_type)
    notes_per_bar_min = DEFAULT_DENSITY_MIN
    notes_per_bar_max = DEFAULT_DENSITY_MAX
    density_desc = DEFAULT_DENSITY_DESC

    for keywords, min_val, max_val, desc in NOTE_DENSITY_RULES:
        if any(k in gen_type_lower for k in keywords):
            notes_per_bar_min = min_val
            notes_per_bar_max = max_val
            density_desc = desc
            break

    min_notes = max(MIN_NOTES_COUNT, int(bars * notes_per_bar_min))
    max_notes = max(min_notes + MIN_MAX_NOTES_DELTA, int(bars * notes_per_bar_max))

    return min_notes, max_notes, density_desc


def infer_key_from_plan_chord_map(chord_map: Any) -> str:
    if not isinstance(chord_map, list) or not chord_map:
        return UNKNOWN_VALUE
    roots: List[int] = []
    for entry in chord_map:
        if not isinstance(entry, dict):
            continue
        tones = entry.get("chord_tones")
        if not isinstance(tones, list) or not tones:
            continue
        try:
            root_pc = int(tones[0]) % SEMITONES_PER_OCTAVE
        except (TypeError, ValueError):
            continue
        roots.append(root_pc)
    return detect_key_from_chords(roots)
