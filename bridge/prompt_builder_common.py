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


def extract_role_from_plan(plan: Optional[Dict[str, Any]], instrument_name: str, track_name: str = "") -> str:
    if not isinstance(plan, dict):
        return UNKNOWN_VALUE

    role_guidance = plan.get("role_guidance", [])
    if not isinstance(role_guidance, list):
        return UNKNOWN_VALUE

    instrument_lower = normalize_lower(instrument_name)
    track_lower = normalize_lower(track_name)

    for entry in role_guidance:
        if not isinstance(entry, dict):
            continue
        entry_instrument = normalize_lower(entry.get("instrument"))
        if not entry_instrument:
            continue
        if entry_instrument in {instrument_lower, track_lower}:
            role = normalize_text(entry.get("role"))
            if role:
                return role

    return UNKNOWN_VALUE
