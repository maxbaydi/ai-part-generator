from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


UNKNOWN_VALUE = "unknown"
DEFAULT_TIME_SIGNATURE = "4/4"
TIME_SIGNATURE_SEPARATOR = "/"
DEFAULT_BEATS_PER_BAR = 4
DEFAULT_BEAT_UNIT = 4
MIN_BARS_COUNT = 1
MIN_NOTES_COUNT = 1
MIN_MAX_NOTES_DELTA = 1
BAR_RANGE_SEPARATOR = "-"
BAR_RANGE_END_OFFSET = 1
DEFAULT_GENERATION_ORDER = 1
DEFAULT_BAR_INDEX = 1
ZERO_TIME_Q = 0.0
RANGE_BOUND_COUNT = 2
SEMITONES_PER_OCTAVE = 12

ROLE_KEYWORDS = {
    "melody": ("melody", "lead", "theme", "motif", "solo"),
    "bass": ("bass", "low end", "root"),
    "harmony": ("harmony", "chord", "pad", "support", "accompaniment"),
    "rhythm": ("rhythm", "groove", "percussion", "drum", "pulse", "ostinato"),
    "countermelody": ("countermelody", "counter-melody", "counter line"),
}

FAMILY_ROLE_DEFAULTS = {
    "bass": "bass",
    "drums": "rhythm",
    "percussion": "rhythm",
    "strings": "harmony",
    "woodwinds": "melody",
    "brass": "melody",
}


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_lower(value: Any) -> str:
    return normalize_text(value).lower()


def is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def import_music_notation():
    try:
        from music_notation import midi_to_note, dur_q_to_name, velocity_to_dynamic
    except ImportError:
        from .music_notation import midi_to_note, dur_q_to_name, velocity_to_dynamic
    return midi_to_note, dur_q_to_name, velocity_to_dynamic


def import_note_to_midi():
    try:
        from midi_utils import note_to_midi
    except ImportError:
        from .midi_utils import note_to_midi
    return note_to_midi


def infer_role_from_text(text: str) -> str:
    text_lower = normalize_lower(text)
    if not text_lower:
        return UNKNOWN_VALUE
    for role, keywords in ROLE_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return role
    return UNKNOWN_VALUE


def infer_role_from_family(family: str) -> str:
    return FAMILY_ROLE_DEFAULTS.get(normalize_lower(family), UNKNOWN_VALUE)


def extract_role_from_plan(
    plan: Optional[Dict[str, Any]],
    instrument_name: str,
    track_name: str = "",
    instrument_index: Optional[int] = None,
    family: str = "",
) -> str:
    if not isinstance(plan, dict):
        role = infer_role_from_family(family)
        return role if role != UNKNOWN_VALUE else UNKNOWN_VALUE

    role_guidance = plan.get("role_guidance", [])
    if not isinstance(role_guidance, list):
        role = infer_role_from_family(family)
        return role if role != UNKNOWN_VALUE else UNKNOWN_VALUE

    instrument_lower = normalize_lower(instrument_name)
    track_lower = normalize_lower(track_name)

    for entry in role_guidance:
        if not isinstance(entry, dict):
            continue
        entry_index = entry.get("instrument_index")
        if entry_index is not None and instrument_index is not None:
            try:
                if int(entry_index) != int(instrument_index):
                    continue
            except (TypeError, ValueError):
                pass
        else:
            entry_instrument = normalize_lower(entry.get("instrument"))
            if not entry_instrument:
                continue
            if entry_instrument not in {instrument_lower, track_lower}:
                continue

        role = normalize_text(entry.get("role"))
        if role:
            return role
        guidance = normalize_text(entry.get("guidance") or entry.get("musical_intent"))
        inferred = infer_role_from_text(guidance)
        if inferred != UNKNOWN_VALUE:
            return inferred

    inferred = infer_role_from_text(f"{instrument_name} {track_name}")
    if inferred != UNKNOWN_VALUE:
        return inferred

    role = infer_role_from_family(family)
    return role if role != UNKNOWN_VALUE else UNKNOWN_VALUE
