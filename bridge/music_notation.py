from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

DURATION_NAMES = {
    4.0: "whole",
    3.0: "dotted-half",
    2.0: "half",
    1.5: "dotted-quarter",
    1.0: "quarter",
    0.75: "dotted-8th",
    0.5: "8th",
    0.375: "dotted-16th",
    0.25: "16th",
    0.125: "32nd",
    0.0625: "64th",
}

DURATION_ABBREV = {
    4.0: "w",
    3.0: "dh",
    2.0: "h",
    1.5: "dq",
    1.0: "q",
    0.75: "d8",
    0.5: "8",
    0.375: "d16",
    0.25: "16",
    0.125: "32",
    0.0625: "64",
}

DURATION_FROM_NAME = {
    "whole": 4.0, "w": 4.0,
    "dotted-half": 3.0, "dh": 3.0,
    "half": 2.0, "h": 2.0,
    "dotted-quarter": 1.5, "dq": 1.5,
    "quarter": 1.0, "q": 1.0,
    "dotted-8th": 0.75, "d8": 0.75,
    "8th": 0.5, "8": 0.5, "eighth": 0.5,
    "dotted-16th": 0.375, "d16": 0.375,
    "16th": 0.25, "16": 0.25, "sixteenth": 0.25,
    "32nd": 0.125, "32": 0.125,
    "64th": 0.0625, "64": 0.0625,
}

DYNAMICS_MAP = {
    (0, 20): ("ppp", "pianississimo"),
    (20, 36): ("pp", "pianissimo"),
    (36, 52): ("p", "piano"),
    (52, 68): ("mp", "mezzo-piano"),
    (68, 84): ("mf", "mezzo-forte"),
    (84, 100): ("f", "forte"),
    (100, 116): ("ff", "fortissimo"),
    (116, 128): ("fff", "fortississimo"),
}

DYNAMICS_TO_VELOCITY = {
    "ppp": 16, "pianississimo": 16,
    "pp": 33, "pianissimo": 33,
    "p": 49, "piano": 49,
    "mp": 64, "mezzo-piano": 64,
    "mf": 80, "mezzo-forte": 80,
    "f": 96, "forte": 96,
    "ff": 112, "fortissimo": 112,
    "fff": 124, "fortississimo": 124,
}


def midi_to_note(pitch: int, use_flats: bool = False) -> str:
    if pitch < 0 or pitch > 127:
        pitch = max(0, min(127, pitch))
    note_names = NOTE_NAMES_FLAT if use_flats else NOTE_NAMES
    note = note_names[pitch % 12]
    octave = (pitch // 12) - 1
    return f"{note}{octave}"


def note_to_midi(note_str: str) -> int:
    note_str = note_str.strip()
    if not note_str:
        return 60
    
    note_part = ""
    octave_part = ""
    
    i = 0
    while i < len(note_str) and (note_str[i].isalpha() or note_str[i] in "#b"):
        note_part += note_str[i]
        i += 1
    octave_part = note_str[i:]
    
    note_upper = note_part[0].upper() + note_part[1:] if note_part else "C"
    
    note_to_pc = {
        "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
        "E": 4, "Fb": 4, "E#": 5, "F": 5, "F#": 6, "Gb": 6,
        "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10,
        "B": 11, "Cb": 11, "B#": 0,
    }
    
    pc = note_to_pc.get(note_upper, 0)
    
    try:
        octave = int(octave_part) if octave_part else 4
    except ValueError:
        octave = 4
    
    return (octave + 1) * 12 + pc


def dur_q_to_name(dur_q: float, abbrev: bool = True) -> str:
    if dur_q <= 0:
        return "0"
    
    lookup = DURATION_ABBREV if abbrev else DURATION_NAMES
    
    if dur_q in lookup:
        return lookup[dur_q]
    
    closest_dur = min(lookup.keys(), key=lambda d: abs(d - dur_q))
    if abs(closest_dur - dur_q) < 0.1:
        return lookup[closest_dur]
    
    if abbrev:
        return f"{dur_q:.2f}q"
    return f"{dur_q:.2f} quarters"


def name_to_dur_q(name: str) -> float:
    name_lower = name.lower().strip()
    
    if name_lower in DURATION_FROM_NAME:
        return DURATION_FROM_NAME[name_lower]
    
    if name_lower.endswith("q"):
        try:
            return float(name_lower[:-1])
        except ValueError:
            pass
    
    try:
        return float(name_lower)
    except ValueError:
        return 1.0


def velocity_to_dynamic(vel: int) -> str:
    vel = max(0, min(127, vel))
    for (low, high), (abbrev, _) in DYNAMICS_MAP.items():
        if low <= vel < high:
            return abbrev
    return "fff"


def velocity_to_dynamic_full(vel: int) -> str:
    vel = max(0, min(127, vel))
    for (low, high), (_, full_name) in DYNAMICS_MAP.items():
        if low <= vel < high:
            return full_name
    return "fortississimo"


def dynamic_to_velocity(dynamic: str) -> int:
    dynamic_lower = dynamic.lower().strip()
    return DYNAMICS_TO_VELOCITY.get(dynamic_lower, 80)


def format_note_musical(
    pitch: int,
    dur_q: float,
    vel: int,
    start_q: Optional[float] = None,
    time_sig: str = "4/4",
    use_abbrev: bool = True,
) -> str:
    note_name = midi_to_note(pitch)
    dur_name = dur_q_to_name(dur_q, abbrev=use_abbrev)
    dyn = velocity_to_dynamic(vel)
    
    if start_q is not None:
        bar, beat = time_q_to_bar_beat(start_q, time_sig)
        return f"{bar}.{beat}:{note_name}({dur_name},{dyn})"
    
    return f"{note_name}({dur_name},{dyn})"


def time_q_to_bar_beat(time_q: float, time_sig: str = "4/4") -> Tuple[int, str]:
    try:
        parts = time_sig.split("/")
        num = int(parts[0])
        denom = int(parts[1])
    except (ValueError, IndexError):
        num, denom = 4, 4
    
    quarters_per_bar = num * (4.0 / denom)
    beat_q = 4.0 / denom
    
    bar = int(time_q // quarters_per_bar) + 1
    beat_in_bar = ((time_q % quarters_per_bar) / beat_q) + 1.0
    
    beat_str = f"{beat_in_bar:.2f}".rstrip("0").rstrip(".")
    
    return bar, beat_str


def bar_beat_to_time_q(bar: int, beat: float, time_sig: str = "4/4") -> float:
    try:
        parts = time_sig.split("/")
        num = int(parts[0])
        denom = int(parts[1])
    except (ValueError, IndexError):
        num, denom = 4, 4
    
    quarters_per_bar = num * (4.0 / denom)
    beat_q = 4.0 / denom
    
    return (bar - 1) * quarters_per_bar + (beat - 1) * beat_q


def format_notes_as_bars(
    notes: List[Dict[str, Any]],
    time_sig: str = "4/4",
    max_bars: int = 32,
) -> str:
    if not notes:
        return ""
    
    try:
        parts = time_sig.split("/")
        num = int(parts[0])
        denom = int(parts[1])
    except (ValueError, IndexError):
        num, denom = 4, 4
    
    quarters_per_bar = num * (4.0 / denom)
    
    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    
    bars: Dict[int, List[str]] = {}
    
    for note in sorted_notes:
        start_q = note.get("start_q", 0)
        pitch = note.get("pitch", 60)
        dur_q = note.get("dur_q", 1.0)
        vel = note.get("vel", 80)
        
        bar_num = int(start_q // quarters_per_bar) + 1
        if bar_num > max_bars:
            continue
        
        note_str = format_note_musical(pitch, dur_q, vel, use_abbrev=True)
        
        if bar_num not in bars:
            bars[bar_num] = []
        bars[bar_num].append(note_str)
    
    lines = []
    for bar_num in sorted(bars.keys()):
        notes_str = " ".join(bars[bar_num])
        lines.append(f"Bar {bar_num}: {notes_str}")
    
    return "\n".join(lines)


def format_chord_tones_as_notes(
    chord_tones: List[int],
    instrument_range: Tuple[int, int],
    chord_name: str = "",
) -> str:
    if not chord_tones:
        return ""
    
    low, high = instrument_range
    
    notes_in_range = []
    for pc in chord_tones:
        for octave in range(-1, 10):
            midi = pc + (octave + 1) * 12
            if low <= midi <= high:
                notes_in_range.append(midi_to_note(midi))
    
    if chord_name:
        return f"{chord_name}: {', '.join(notes_in_range[:8])}"
    return ", ".join(notes_in_range[:8])


def format_chord_map_musical(
    chord_map: List[Dict[str, Any]],
    time_sig: str = "4/4",
    instrument_range: Optional[Tuple[int, int]] = None,
) -> str:
    if not chord_map:
        return ""
    
    lines = []
    lines.append("```")
    lines.append("Bar.Beat | Chord    | Notes in your range")
    lines.append("---------|----------|--------------------")
    
    for entry in chord_map:
        time_q = entry.get("time_q", 0)
        chord = entry.get("chord", "?")
        roman = entry.get("roman", "")
        chord_tones = entry.get("chord_tones", [])
        
        bar, beat = time_q_to_bar_beat(time_q, time_sig)
        
        if instrument_range and chord_tones:
            notes_str = get_chord_notes_in_range(chord_tones, instrument_range)
        else:
            notes_str = ", ".join(midi_to_note(60 + pc) for pc in chord_tones[:5])
        
        chord_label = f"{chord}"
        if roman:
            chord_label = f"{chord} ({roman})"
        
        lines.append(f"{bar}.{beat:<4}    | {chord_label:<8} | {notes_str}")
    
    lines.append("```")
    return "\n".join(lines)


def get_chord_notes_in_range(
    chord_tones: List[int],
    instrument_range: Tuple[int, int],
) -> str:
    low, high = instrument_range
    notes = []
    
    for pc in chord_tones:
        for octave in range(-1, 10):
            midi = pc + (octave + 1) * 12
            if low <= midi <= high:
                notes.append(midi_to_note(midi))
                break
    
    return ", ".join(notes[:6])


def format_motif_as_notes(
    intervals: List[int],
    rhythm: List[float],
    start_pitch: int,
) -> str:
    if not intervals or not rhythm:
        return ""
    
    notes = []
    current_pitch = start_pitch
    
    for i, (interval, dur) in enumerate(zip(intervals, rhythm)):
        if i == 0:
            current_pitch = start_pitch
        else:
            current_pitch += interval
        
        note_name = midi_to_note(current_pitch)
        dur_name = dur_q_to_name(dur, abbrev=True)
        notes.append(f"{note_name}({dur_name})")
    
    return " → ".join(notes)


def format_context_notes_musical(
    notes: List[Dict[str, Any]],
    time_sig: str = "4/4",
    max_notes: int = 50,
    role: str = "",
) -> str:
    if not notes:
        return ""
    
    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    limited = sorted_notes[:max_notes]
    
    pitches = [n.get("pitch", 60) for n in limited]
    min_pitch = min(pitches)
    max_pitch = max(pitches)
    
    range_str = f"{midi_to_note(min_pitch)}-{midi_to_note(max_pitch)}"
    
    note_strs = []
    for note in limited:
        pitch = note.get("pitch", 60)
        dur_q = note.get("dur_q", 1.0)
        vel = note.get("vel", 80)
        start_q = note.get("start_q", 0)
        
        bar, beat = time_q_to_bar_beat(start_q, time_sig)
        note_name = midi_to_note(pitch)
        dur_name = dur_q_to_name(dur_q, abbrev=True)
        dyn = velocity_to_dynamic(vel)
        
        note_strs.append(f"{bar}.{beat}:{note_name}({dur_name},{dyn})")
    
    header = f"[{role}] " if role else ""
    header += f"Range: {range_str} | {len(notes)} notes"
    
    if len(sorted_notes) > max_notes:
        note_strs.append(f"... (+{len(sorted_notes) - max_notes} more)")
    
    return f"{header}\n  {', '.join(note_strs[:20])}"


def format_dynamic_arc_musical(
    dynamic_arc: List[Dict[str, Any]],
    time_sig: str = "4/4",
) -> str:
    if not dynamic_arc:
        return ""
    
    lines = []
    lines.append("```")
    lines.append("Bar.Beat | Dynamics | Velocity | Direction")
    lines.append("---------|----------|----------|----------")
    
    for entry in dynamic_arc:
        time_q = entry.get("time_q", 0)
        level = entry.get("level", "mf")
        target_vel = entry.get("target_velocity", 80)
        trend = entry.get("trend", "stable")
        
        bar, beat = time_q_to_bar_beat(time_q, time_sig)
        
        trend_arrow = {
            "stable": "→",
            "building": "↗",
            "climax": "★",
            "fading": "↘",
            "resolving": "↓",
        }.get(trend, "→")
        
        lines.append(f"{bar}.{beat:<4}    | {level:<8} | {target_vel:<8} | {trend_arrow} {trend}")
    
    lines.append("```")
    return "\n".join(lines)


def format_phrase_structure_musical(
    phrases: List[Dict[str, Any]],
    time_sig: str = "4/4",
) -> str:
    if not phrases:
        return ""
    
    lines = []
    
    for phrase in phrases:
        name = phrase.get("name", "phrase")
        bars = phrase.get("bars", "")
        start_q = phrase.get("start_q", 0)
        end_q = phrase.get("end_q", 0)
        function = phrase.get("function", "")
        breathing = phrase.get("breathing_points", [])
        climax = phrase.get("climax_point", {})
        
        start_bar, _ = time_q_to_bar_beat(start_q, time_sig)
        end_bar, _ = time_q_to_bar_beat(end_q, time_sig)
        
        lines.append(f"**{name.upper()}** (Bars {start_bar}-{end_bar})")
        
        if function:
            lines.append(f"  Function: {function}")
        
        if breathing:
            breath_strs = []
            for b in breathing:
                b_bar, b_beat = time_q_to_bar_beat(b, time_sig)
                breath_strs.append(f"Bar {b_bar}.{b_beat}")
            lines.append(f"  Breathe at: {', '.join(breath_strs)}")
        
        if climax:
            c_time = climax.get("time_q", 0)
            c_bar, c_beat = time_q_to_bar_beat(c_time, time_sig)
            c_intensity = climax.get("intensity", "medium")
            lines.append(f"  Climax: Bar {c_bar}.{c_beat} ({c_intensity})")
    
    return "\n".join(lines)


def format_harmonic_grid_musical(
    parts: List[Dict[str, Any]],
    time_sig: str = "4/4",
    max_notes_per_part: int = 30,
) -> str:
    if not parts:
        return ""
    
    lines = []
    
    for part in parts:
        part_name = part.get("profile_name", part.get("track_name", "Unknown"))
        role = part.get("role", "")
        notes = part.get("notes", [])
        
        if not notes:
            continue
        
        pitches = [n.get("pitch", 60) for n in notes]
        min_pitch = min(pitches)
        max_pitch = max(pitches)
        range_str = f"{midi_to_note(min_pitch)}-{midi_to_note(max_pitch)}"
        
        role_str = f" [{role}]" if role and role.lower() != "unknown" else ""
        lines.append(f"**{part_name}**{role_str} (Range: {range_str}):")
        
        sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
        limited = sorted_notes[:max_notes_per_part]
        
        bars: Dict[int, List[str]] = {}
        try:
            parts_ts = time_sig.split("/")
            num = int(parts_ts[0])
            denom = int(parts_ts[1])
        except (ValueError, IndexError):
            num, denom = 4, 4
        quarters_per_bar = num * (4.0 / denom)
        
        for note in limited:
            start_q = note.get("start_q", 0)
            pitch = note.get("pitch", 60)
            dur_q = note.get("dur_q", 1.0)
            vel = note.get("vel", 80)
            
            bar_num = int(start_q // quarters_per_bar) + 1
            beat_in_bar = ((start_q % quarters_per_bar) / (4.0 / denom)) + 1.0
            beat_str = f"{beat_in_bar:.1f}".rstrip("0").rstrip(".")
            
            note_name = midi_to_note(pitch)
            dur_name = dur_q_to_name(dur_q, abbrev=True)
            dyn = velocity_to_dynamic(vel)
            
            if bar_num not in bars:
                bars[bar_num] = []
            bars[bar_num].append(f"{beat_str}:{note_name}({dur_name},{dyn})")
        
        bar_strs = []
        for bar_num in sorted(bars.keys())[:12]:
            bar_content = " ".join(bars[bar_num])
            bar_strs.append(f"  Bar {bar_num}: {bar_content}")
        
        lines.extend(bar_strs)
        
        if len(sorted_notes) > max_notes_per_part:
            lines.append(f"  ... (+{len(sorted_notes) - max_notes_per_part} more notes)")
        
        lines.append("")
    
    return "\n".join(lines)


def parse_musical_note(note_str: str) -> Dict[str, Any]:
    note_str = note_str.strip()
    
    result = {
        "pitch": 60,
        "dur_q": 1.0,
        "vel": 80,
    }
    
    if "(" in note_str and ")" in note_str:
        note_part = note_str[:note_str.index("(")]
        params_part = note_str[note_str.index("(") + 1:note_str.index(")")]
        
        result["pitch"] = note_to_midi(note_part)
        
        params = [p.strip() for p in params_part.split(",")]
        for param in params:
            if param in DURATION_FROM_NAME or param.endswith("q"):
                result["dur_q"] = name_to_dur_q(param)
            elif param in DYNAMICS_TO_VELOCITY:
                result["vel"] = DYNAMICS_TO_VELOCITY[param]
            else:
                try:
                    val = int(param)
                    if 1 <= val <= 127:
                        result["vel"] = val
                except ValueError:
                    pass
    else:
        result["pitch"] = note_to_midi(note_str)
    
    return result


def format_output_example(time_sig: str = "4/4") -> str:
    return '''EXAMPLE OUTPUT (follow this format):
{
  "notes": [
    {"bar": 1, "beat": 1, "note": "C5", "dur": "quarter", "dyn": "mf"},
    {"bar": 1, "beat": 2, "note": "E5", "dur": "8th", "dyn": "mf"},
    {"bar": 1, "beat": 2.5, "note": "G5", "dur": "8th", "dyn": "f"},
    {"bar": 1, "beat": 3, "note": "C6", "dur": "half", "dyn": "f"}
  ],
  "curves": {
    "expression": {"interp": "cubic", "breakpoints": [
      {"bar": 1, "beat": 1, "value": 70},
      {"bar": 2, "beat": 1, "value": 100}
    ]},
    "dynamics": {"interp": "cubic", "breakpoints": [...]}
  }
}'''
