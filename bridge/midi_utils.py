from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import (
        DEFAULT_DRUM_VELOCITY,
        DEFAULT_PITCH,
        DEFAULT_VELOCITY,
        MIDI_CHAN_MAX,
        MIDI_CHAN_MIN,
        MIDI_CHAN_ZERO_BASE_MAX,
        MIDI_MAX,
        MIDI_MIN,
        MIDI_VEL_MIN,
        MIN_NOTE_DUR_Q,
        MIN_NOTE_GAP_Q,
    )
    from utils import clamp
except ImportError:
    from .constants import (
        DEFAULT_DRUM_VELOCITY,
        DEFAULT_PITCH,
        DEFAULT_VELOCITY,
        MIDI_CHAN_MAX,
        MIDI_CHAN_MIN,
        MIDI_CHAN_ZERO_BASE_MAX,
        MIDI_MAX,
        MIDI_MIN,
        MIDI_VEL_MIN,
        MIN_NOTE_DUR_Q,
        MIN_NOTE_GAP_Q,
    )
    from .utils import clamp

NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")


def note_to_midi(note: Any) -> int:
    if isinstance(note, int):
        return note
    if isinstance(note, float) and note.is_integer():
        return int(note)
    if isinstance(note, str):
        if note.isdigit() or (note.startswith("-") and note[1:].isdigit()):
            return int(note)
        match = NOTE_RE.match(note.strip())
        if not match:
            raise ValueError(f"Invalid note format: {note}")
        letter, accidental, octave_str = match.groups()
        octave = int(octave_str)
        base_map = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        semitone = base_map[letter.upper()]
        if accidental == "#":
            semitone += 1
        elif accidental == "b":
            semitone -= 1
        midi = (octave + 1) * 12 + semitone
        return int(midi)
    raise ValueError(f"Unsupported note value: {note}")


def parse_range(range_data: Any) -> Optional[Tuple[int, int]]:
    if not range_data or not isinstance(range_data, list) or len(range_data) != 2:
        return None
    low = note_to_midi(range_data[0])
    high = note_to_midi(range_data[1])
    low = max(MIDI_MIN, min(MIDI_MAX, low))
    high = max(MIDI_MIN, min(MIDI_MAX, high))
    return (min(low, high), max(low, high))


def fit_pitch_to_range(pitch: int, abs_range: Optional[Tuple[int, int]], policy: str) -> int:
    if not abs_range:
        return pitch
    low, high = abs_range
    if low <= pitch <= high:
        return pitch
    if policy == "octave_shift_to_fit":
        shifted = pitch
        if shifted < low:
            while shifted < low:
                shifted += 12
        elif shifted > high:
            while shifted > high:
                shifted -= 12
        if low <= shifted <= high:
            return shifted
    return int(clamp(pitch, low, high))


def normalize_channel(value: Optional[Any], default_chan: int) -> int:
    if value is None:
        return default_chan
    try:
        chan = int(value)
    except (TypeError, ValueError):
        return default_chan
    if 0 <= chan <= MIDI_CHAN_ZERO_BASE_MAX:
        return chan + 1
    if MIDI_CHAN_MIN <= chan <= MIDI_CHAN_MAX:
        return chan
    return default_chan


def normalize_notes(
    notes: List[Dict[str, Any]],
    length_q: float,
    default_chan: int,
    abs_range: Optional[Tuple[int, int]],
    fix_policy: str,
    mono: bool,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for note in notes:
        try:
            start_q = float(note.get("start_q", 0.0))
            dur_q = float(note.get("dur_q", MIN_NOTE_DUR_Q))
            pitch = int(note.get("pitch", DEFAULT_PITCH))
            vel = int(note.get("vel", DEFAULT_VELOCITY))
            chan = normalize_channel(note.get("chan"), default_chan)
        except (TypeError, ValueError):
            continue

        start_q = clamp(start_q, 0.0, max(0.0, length_q - MIN_NOTE_DUR_Q))
        dur_q = max(MIN_NOTE_DUR_Q, dur_q)
        if start_q + dur_q > length_q:
            dur_q = max(MIN_NOTE_DUR_Q, length_q - start_q)

        pitch = fit_pitch_to_range(pitch, abs_range, fix_policy)
        pitch = int(clamp(pitch, MIDI_MIN, MIDI_MAX))
        vel = int(clamp(vel, MIDI_VEL_MIN, MIDI_MAX))

        normalized.append(
            {
                "start_q": start_q,
                "dur_q": dur_q,
                "pitch": pitch,
                "vel": vel,
                "chan": chan,
            }
        )

    if not mono:
        return normalized

    normalized.sort(key=lambda n: (n["start_q"], n["pitch"]))
    mono_notes: List[Dict[str, Any]] = []
    for note in normalized:
        if not mono_notes:
            mono_notes.append(note)
            continue
        prev = mono_notes[-1]
        prev_end = prev["start_q"] + prev["dur_q"]
        if prev_end > note["start_q"]:
            new_dur = max(MIN_NOTE_DUR_Q, note["start_q"] - prev["start_q"] - MIN_NOTE_GAP_Q)
            prev["dur_q"] = new_dur
        mono_notes.append(note)
    return mono_notes


def normalize_drums(
    drums: List[Dict[str, Any]],
    drum_map: Dict[str, Any],
    length_q: float,
    default_chan: int,
) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    for hit in drums:
        name = hit.get("drum") or hit.get("name")
        if not name:
            continue
        pitch_raw = drum_map.get(str(name).lower()) or drum_map.get(name)
        if pitch_raw is None:
            continue
        try:
            pitch = note_to_midi(pitch_raw)
        except ValueError:
            continue
        start_q = float(hit.get("time_q", 0.0))
        dur_q = float(hit.get("dur_q", MIN_NOTE_DUR_Q))
        vel = int(hit.get("vel", DEFAULT_DRUM_VELOCITY))
        chan = normalize_channel(hit.get("chan"), default_chan)
        start_q = clamp(start_q, 0.0, max(0.0, length_q))
        dur_q = max(MIN_NOTE_DUR_Q, dur_q)
        if start_q + dur_q > length_q:
            dur_q = max(0.0, length_q - start_q)
        if dur_q <= 0:
            continue
        vel = int(clamp(vel, MIDI_VEL_MIN, MIDI_MAX))
        notes.append(
            {
                "start_q": start_q,
                "dur_q": dur_q,
                "pitch": int(clamp(pitch, MIDI_MIN, MIDI_MAX)),
                "vel": vel,
                "chan": chan,
            }
        )
    return notes
