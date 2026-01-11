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

DURATION_NAME_TO_Q = {
    "whole": 4.0, "w": 4.0,
    "dotted-half": 3.0, "dh": 3.0, "dotted half": 3.0,
    "half": 2.0, "h": 2.0,
    "dotted-quarter": 1.5, "dq": 1.5, "dotted quarter": 1.5,
    "quarter": 1.0, "q": 1.0,
    "dotted-8th": 0.75, "d8": 0.75, "dotted 8th": 0.75, "dotted-eighth": 0.75,
    "8th": 0.5, "8": 0.5, "eighth": 0.5,
    "dotted-16th": 0.375, "d16": 0.375, "dotted 16th": 0.375,
    "16th": 0.25, "16": 0.25, "sixteenth": 0.25,
    "32nd": 0.125, "32": 0.125,
    "64th": 0.0625, "64": 0.0625,
}

DYNAMIC_TO_VELOCITY = {
    "ppp": 16, "pianississimo": 16,
    "pp": 33, "pianissimo": 33,
    "p": 49, "piano": 49,
    "mp": 64, "mezzo-piano": 64, "mezzo piano": 64,
    "mf": 80, "mezzo-forte": 80, "mezzo forte": 80,
    "f": 96, "forte": 96,
    "ff": 112, "fortissimo": 112,
    "fff": 124, "fortississimo": 124,
}


def parse_duration(dur: Any) -> float:
    if isinstance(dur, (int, float)):
        return float(dur)
    if isinstance(dur, str):
        dur_lower = dur.lower().strip()
        if dur_lower in DURATION_NAME_TO_Q:
            return DURATION_NAME_TO_Q[dur_lower]
        try:
            return float(dur)
        except ValueError:
            pass
    return MIN_NOTE_DUR_Q


def parse_dynamic(dyn: Any) -> int:
    if isinstance(dyn, int):
        return dyn
    if isinstance(dyn, float):
        return int(dyn)
    if isinstance(dyn, str):
        dyn_lower = dyn.lower().strip()
        if dyn_lower in DYNAMIC_TO_VELOCITY:
            return DYNAMIC_TO_VELOCITY[dyn_lower]
        try:
            return int(dyn)
        except ValueError:
            pass
    return DEFAULT_VELOCITY


def bar_beat_to_start_q(bar: Any, beat: Any, time_sig: str = "4/4") -> float:
    try:
        parts = time_sig.split("/")
        num = int(parts[0])
        denom = int(parts[1])
    except (ValueError, IndexError):
        num, denom = 4, 4
    
    quarters_per_bar = num * (4.0 / denom)
    beat_q = 4.0 / denom
    
    try:
        bar_num = int(bar)
        beat_num = float(beat)
    except (TypeError, ValueError):
        return 0.0
    
    return (bar_num - 1) * quarters_per_bar + (beat_num - 1) * beat_q


def convert_musical_note_format(note: Dict[str, Any], time_sig: str = "4/4") -> Dict[str, Any]:
    if "start_q" in note and "pitch" in note:
        return note
    
    converted = {}
    
    if "bar" in note and "beat" in note:
        converted["start_q"] = bar_beat_to_start_q(note["bar"], note["beat"], time_sig)
    elif "start_q" in note:
        converted["start_q"] = float(note.get("start_q", 0))
    elif "time_q" in note:
        converted["start_q"] = float(note.get("time_q", 0))
    else:
        converted["start_q"] = 0.0
    
    if "note" in note:
        try:
            converted["pitch"] = note_to_midi(note["note"])
        except ValueError:
            converted["pitch"] = DEFAULT_PITCH
    elif "pitch" in note:
        try:
            converted["pitch"] = note_to_midi(note["pitch"])
        except ValueError:
            converted["pitch"] = DEFAULT_PITCH
    else:
        converted["pitch"] = DEFAULT_PITCH
    
    if "dur" in note:
        converted["dur_q"] = parse_duration(note["dur"])
    elif "dur_q" in note:
        converted["dur_q"] = float(note.get("dur_q", MIN_NOTE_DUR_Q))
    elif "duration" in note:
        converted["dur_q"] = parse_duration(note["duration"])
    else:
        converted["dur_q"] = MIN_NOTE_DUR_Q
    
    if "dyn" in note:
        converted["vel"] = parse_dynamic(note["dyn"])
    elif "vel" in note:
        converted["vel"] = int(note.get("vel", DEFAULT_VELOCITY))
    elif "velocity" in note:
        converted["vel"] = int(note.get("velocity", DEFAULT_VELOCITY))
    elif "dynamic" in note:
        converted["vel"] = parse_dynamic(note["dynamic"])
    elif "dynamics" in note:
        converted["vel"] = parse_dynamic(note["dynamics"])
    else:
        converted["vel"] = DEFAULT_VELOCITY
    
    if "chan" in note:
        converted["chan"] = note["chan"]
    elif "channel" in note:
        converted["chan"] = note["channel"]
    
    if "art" in note:
        converted["articulation"] = note["art"]
    elif "articulation" in note:
        converted["articulation"] = note["articulation"]
    
    return converted


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
    if chan == 0:
        return 1
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
    time_sig: str = "4/4",
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        
        converted = convert_musical_note_format(note, time_sig)
        
        try:
            start_q = float(converted.get("start_q", 0.0))
            dur_q = float(converted.get("dur_q", MIN_NOTE_DUR_Q))
            pitch = int(converted.get("pitch", DEFAULT_PITCH))
            vel = int(converted.get("vel", DEFAULT_VELOCITY))
            chan = normalize_channel(converted.get("chan"), default_chan)
        except (TypeError, ValueError):
            continue

        start_q = clamp(start_q, 0.0, max(0.0, length_q - MIN_NOTE_DUR_Q))
        dur_q = max(MIN_NOTE_DUR_Q, dur_q)
        if start_q + dur_q > length_q:
            dur_q = max(MIN_NOTE_DUR_Q, length_q - start_q)

        pitch = fit_pitch_to_range(pitch, abs_range, fix_policy)
        pitch = int(clamp(pitch, MIDI_MIN, MIDI_MAX))
        vel = int(clamp(vel, MIDI_VEL_MIN, MIDI_MAX))

        result_note = {
            "start_q": start_q,
            "dur_q": dur_q,
            "pitch": pitch,
            "vel": vel,
            "chan": chan,
        }
        
        if "articulation" in converted:
            result_note["articulation"] = converted["articulation"]
        
        normalized.append(result_note)

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
