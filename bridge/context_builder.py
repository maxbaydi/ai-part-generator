from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import MIDI_MAX, MIDI_MIN
    from midi_utils import note_to_midi
    from models import ContextInfo, EnsembleInfo, HorizontalContext
    from music_analysis import (
        analyze_melodic_context,
        analyze_previously_generated,
        analyze_rhythmic_pattern,
        analyze_horizontal_continuity,
        build_full_context_prompt,
        build_harmony_context_prompt,
        build_horizontal_continuity_prompt,
        build_melodic_context_prompt,
        build_rhythmic_context_prompt,
        extract_motif_from_notes,
    )
    from music_theory import (
        analyze_chord,
        detect_key_from_chords,
        extract_chords_lilchord_style,
        get_chord_degree_lilchord,
        pitch_to_note,
        velocity_to_dynamic,
    )
    from profile_utils import load_profile
except ImportError:
    from .constants import MIDI_MAX, MIDI_MIN
    from .midi_utils import note_to_midi
    from .models import ContextInfo, EnsembleInfo, HorizontalContext
    from .music_analysis import (
        analyze_melodic_context,
        analyze_previously_generated,
        analyze_rhythmic_pattern,
        analyze_horizontal_continuity,
        build_full_context_prompt,
        build_harmony_context_prompt,
        build_horizontal_continuity_prompt,
        build_melodic_context_prompt,
        build_rhythmic_context_prompt,
        extract_motif_from_notes,
    )
    from .music_theory import (
        analyze_chord,
        detect_key_from_chords,
        extract_chords_lilchord_style,
        get_chord_degree_lilchord,
        pitch_to_note,
        velocity_to_dynamic,
    )
    from .profile_utils import load_profile

POSITION_DESCRIPTIONS = {
    "start": "This is the BEGINNING of a musical section. There is existing material AFTER the generation area.",
    "middle": "This is the MIDDLE of a musical section. There is existing material BEFORE and AFTER the generation area.",
    "end": "This is the END of a musical section. There is existing material BEFORE the generation area.",
    "isolated": "This is an isolated section with no surrounding context on this track.",
}

ROLE_HINTS = {
    "melody": "MELODY: Carry the main theme. Clear, memorable lines. Be the focus.",
    "lead": "LEAD: Carry the main theme. Clear, memorable lines. Be the focus.",
    "bass": "BASS: Harmonic foundation. Play roots and fifths. Define the harmony.",
    "harmony": "HARMONY: Support the melody. Play chord tones. Fill the harmonic space.",
    "accompaniment": "ACCOMPANIMENT: Support the melody. Rhythmic patterns, arpeggios, sustained chords.",
    "rhythm": "RHYTHM: Define the pulse. Steady patterns. Don't overshadow melody.",
    "pad": "PAD: Sustained background. Long notes. Smooth dynamics.",
    "fill": "FILL: Ornamental passages. Fill gaps between phrases.",
    "strings": "STRINGS: Harmony and melody. Sustained chords or lyrical lines.",
    "woodwinds": "WOODWINDS: Color and melody. Lyrical countermelodies.",
    "brass": "BRASS: Power and drama. Heroic melodies or fanfares.",
    "drums": "PERCUSSION: Rhythm foundation. Define the groove.",
}

CC_TREND_WINDOW_RATIO = 0.2
CC_TREND_MIN_DELTA = 8
CC_TREND_MIN_EVENTS = 4
NOTE_CONTEXT_PREVIEW_LIMIT = 2000
ARTICULATION_CHANGE_PREVIEW_LIMIT = 300
SIMPLIFIED_MIDI_MAP_LIMIT = 600
HANDOFF_SUGGESTION_MAX_LEN = 1000
CC_LABELS = {
    1: "Dynamics",
    11: "Expression",
}

FREQUENCY_RANGES = {
    "low": (0, 48),
    "low_mid": (48, 60),
    "mid": (60, 72),
    "high_mid": (72, 84),
    "high": (84, 127),
}

RHYTHMIC_FEEL_THRESHOLDS = {
    "sustained": 2.0,
    "sparse": 0.5,
    "steady_pulse": 1.0,
    "dense": 4.0,
}


def parse_time_sig(time_sig: str) -> Tuple[int, int]:
    try:
        parts = time_sig.split("/")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 4, 4


def get_quarters_per_bar(time_sig: str) -> float:
    num, denom = parse_time_sig(time_sig)
    return num * (4.0 / denom)


def analyze_harmony_progression(
    existing_notes: List[Dict],
    time_sig: str = "4/4",
    length_q: float = 16.0
) -> Tuple[str, str]:
    if not existing_notes:
        return "", "unknown"

    quarters_per_bar = get_quarters_per_bar(time_sig)
    num, denom = parse_time_sig(time_sig)
    beat_q = 4.0 / denom if denom else 1.0

    chord_segments = extract_chords_lilchord_style(existing_notes)

    progression: List[str] = []
    chord_roots: List[int] = []
    chord_items: List[Tuple[float, str, int, int, List[int]]] = []

    for seg in chord_segments:
        start_q = float(seg.get("start_q", 0.0) or 0.0)
        pitches = seg.get("pitches") or []
        if not isinstance(pitches, list) or len(pitches) < 2:
            continue

        chord_pitches = [int(p) for p in pitches]
        chord_name, root = analyze_chord(chord_pitches)
        if root is None:
            continue

        # LilChord treats unison/octave-only clusters as "note".
        # For harmony progression this is noise (pedal/octave doubling), so skip it.
        if chord_name.endswith("note") and len({p % 12 for p in chord_pitches}) <= 1:
            continue
        bass_pc = int(min(chord_pitches)) % 12
        chord_roots.append(root)
        chord_items.append((start_q, chord_name, root, bass_pc, chord_pitches))

    detected_key = detect_key_from_chords(chord_roots)
    last_chord_name: Optional[str] = None
    for start_q, chord_name, root, bass_pc, chord_pitches in chord_items:
        if chord_name == last_chord_name:
            continue
        last_chord_name = chord_name

        degree = (
            None
            if detected_key == "unknown"
            else get_chord_degree_lilchord(
                chord_pitches=chord_pitches,
                chord_root_pc=root,
                key_str=detected_key,
                bass_pc=bass_pc,
            )
        )

        label = chord_name if not degree else f"{chord_name}({degree})"
        if quarters_per_bar > 0 and beat_q > 0:
            bar_num = int(start_q // quarters_per_bar) + 1
            beat_in_bar = ((start_q % quarters_per_bar) / beat_q) + 1.0
            if num:
                beat_in_bar = max(1.0, min(float(num), beat_in_bar))
            beat_str = f"{beat_in_bar:.2f}".rstrip("0").rstrip(".")
            progression.append(f"B{bar_num}.{beat_str}:{label}")
        else:
            progression.append(f"@{start_q:.2f}:{label}")
    return " | ".join(progression), detected_key


def build_chord_map_from_sketch(
    notes: List[Dict[str, Any]],
    time_sig: str = "4/4",
    length_q: float = 16.0,
) -> Tuple[str, str]:
    if not notes:
        return "", "unknown"

    quarters_per_bar = get_quarters_per_bar(time_sig)
    num, denom = parse_time_sig(time_sig)
    beat_q = 4.0 / denom if denom else 1.0

    chord_segments = extract_chords_lilchord_style(notes)

    chord_entries: List[Dict[str, Any]] = []
    chord_roots: List[int] = []

    for seg in chord_segments:
        start_q = float(seg.get("start_q", 0.0) or 0.0)
        pitches = seg.get("pitches") or []
        if not isinstance(pitches, list) or len(pitches) < 2:
            continue

        chord_pitches = [int(p) for p in pitches]
        chord_name, root = analyze_chord(chord_pitches)
        if root is None:
            continue

        if chord_name.endswith("note") and len({p % 12 for p in chord_pitches}) <= 1:
            continue

        bass_pc = int(min(chord_pitches)) % 12
        chord_roots.append(root)
        pitch_classes = sorted(set(p % 12 for p in chord_pitches))

        chord_entries.append({
            "start_q": start_q,
            "chord_name": chord_name,
            "root_pc": root,
            "bass_pc": bass_pc,
            "pitch_classes": pitch_classes,
            "chord_pitches": chord_pitches,
        })

    detected_key = detect_key_from_chords(chord_roots)

    lines = ["```"]
    lines.append("time_q | bar.beat | chord | roman | chord_tones (pitch classes)")

    last_chord_name: Optional[str] = None
    for entry in chord_entries:
        chord_name = entry["chord_name"]
        if chord_name == last_chord_name:
            continue
        last_chord_name = chord_name

        start_q = entry["start_q"]
        root_pc = entry["root_pc"]
        bass_pc = entry["bass_pc"]
        pitch_classes = entry["pitch_classes"]
        chord_pitches = entry["chord_pitches"]

        degree = (
            ""
            if detected_key == "unknown"
            else get_chord_degree_lilchord(
                chord_pitches=chord_pitches,
                chord_root_pc=root_pc,
                key_str=detected_key,
                bass_pc=bass_pc,
            ) or ""
        )

        bar_num = int(start_q // quarters_per_bar) + 1 if quarters_per_bar > 0 else 1
        beat_in_bar = 1.0
        if quarters_per_bar > 0 and beat_q > 0:
            beat_in_bar = ((start_q % quarters_per_bar) / beat_q) + 1.0
            if num:
                beat_in_bar = max(1.0, min(float(num), beat_in_bar))
        beat_str = f"{beat_in_bar:.1f}".rstrip("0").rstrip(".")

        pc_str = str(pitch_classes)
        lines.append(f"{start_q:6.1f} | {bar_num}.{beat_str:<4} | {chord_name:<6} | {degree:<5} | {pc_str}")

    lines.append("```")

    return "\n".join(lines), detected_key


def analyze_horizontal_notes(notes: List[Dict[str, Any]], label: str) -> str:
    if not notes:
        return ""

    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))

    pitches = [n.get("pitch", 60) for n in sorted_notes]
    min_pitch = min(pitches)
    max_pitch = max(pitches)

    first_few = sorted_notes[:min(8, len(sorted_notes))]
    last_few = sorted_notes[-min(4, len(sorted_notes)):] if len(sorted_notes) > 8 else []

    parts = [f"{label} ({len(notes)} notes, range {pitch_to_note(min_pitch)}-{pitch_to_note(max_pitch)}):"]

    note_strs = []
    for note in first_few:
        extra = collect_note_extras(note)
        extra_str = f"({','.join(extra)})" if extra else ""
        note_strs.append(f"{pitch_to_note(note['pitch'])}@{note.get('start_q', 0):.2f}{extra_str}")

    if last_few and last_few != first_few:
        note_strs.append("...")
        for note in last_few:
            extra = collect_note_extras(note)
            extra_str = f"({','.join(extra)})" if extra else ""
            note_strs.append(f"{pitch_to_note(note['pitch'])}@{note.get('start_q', 0):.2f}{extra_str}")

    parts.append(" ".join(note_strs))

    return " ".join(parts)


def build_horizontal_context_summary(
    horizontal: Optional[HorizontalContext],
    key_str: str = "C major",
) -> Tuple[str, str]:
    if not horizontal:
        return "", "isolated"

    parts: List[str] = []

    position = horizontal.position or "isolated"
    parts.append(f"### TEMPORAL POSITION\n{POSITION_DESCRIPTIONS.get(position, POSITION_DESCRIPTIONS['isolated'])}")

    if horizontal.before:
        before_summary = analyze_horizontal_notes(horizontal.before, "BEFORE (preceding notes)")
        if before_summary:
            parts.append(before_summary)

        last_notes = sorted(horizontal.before, key=lambda n: n.get("start_q", 0))[-4:]
        if last_notes:
            last_pitches = [n.get("pitch", 60) for n in last_notes]
            parts.append(f"Last notes before target: {', '.join(pitch_to_note(p) for p in last_pitches)}")

        continuity_analysis = analyze_horizontal_continuity(
            horizontal.before,
            horizontal.after if horizontal.after else [],
            key_str,
        )
        continuity_prompt = build_horizontal_continuity_prompt(continuity_analysis)
        if continuity_prompt:
            parts.append("")
            parts.append(continuity_prompt)

    if horizontal.after:
        after_summary = analyze_horizontal_notes(horizontal.after, "AFTER (following notes)")
        if after_summary:
            parts.append(after_summary)

        first_notes = sorted(horizontal.after, key=lambda n: n.get("start_q", 0))[:4]
        if first_notes:
            first_pitches = [n.get("pitch", 60) for n in first_notes]
            parts.append(f"First notes after target: {', '.join(pitch_to_note(p) for p in first_pitches)}")

    return "\n".join(parts), position


def format_notes_for_context(notes: List[Dict[str, Any]], max_notes: int = 50) -> str:
    if not notes:
        return ""

    limited = notes[:max_notes]
    note_strs = []
    for note in limited:
        start = note.get("start_q", 0)
        dur = note.get("dur_q", 1)
        pitch = note.get("pitch", 60)
        extra = collect_note_extras(note)
        extra_str = f", {', '.join(extra)}" if extra else ""
        note_strs.append(f"({start:.1f}, {pitch}, {dur:.2f}{extra_str})")

    return ", ".join(note_strs)


def safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def average(values: List[int]) -> float:
    return sum(values) / len(values)


def collect_note_extras(note: Dict[str, Any]) -> List[str]:
    extras: List[str] = []
    vel = note.get("vel")
    chan = note.get("chan")
    if vel is not None:
        extras.append(f"v{vel}")
    if chan is not None:
        extras.append(f"ch{chan}")
    return extras


def summarize_velocity_context(notes: List[Dict[str, Any]]) -> List[str]:
    velocities: List[int] = []
    channel_counts: Dict[int, int] = {}

    for note in notes:
        vel = safe_int(note.get("vel"))
        if vel is not None:
            vel = max(MIDI_MIN, min(MIDI_MAX, vel))
            velocities.append(vel)
        chan = safe_int(note.get("chan"))
        if chan is not None:
            channel_counts[chan] = channel_counts.get(chan, 0) + 1

    parts: List[str] = []
    if velocities:
        min_vel = min(velocities)
        max_vel = max(velocities)
        avg_vel = average(velocities)
        min_dyn = velocity_to_dynamic(min_vel)
        max_dyn = velocity_to_dynamic(max_vel)
        avg_dyn = velocity_to_dynamic(int(round(avg_vel)))
        span = max_vel - min_vel
        parts.append(
            f"Velocity range: {min_vel}-{max_vel} ({min_dyn}-{max_dyn}), avg {avg_vel:.1f} ({avg_dyn}), span {span}"
        )

    if channel_counts:
        channel_str = ", ".join(
            f"ch{chan}:{count}" for chan, count in sorted(channel_counts.items(), key=lambda x: x[0])
        )
        parts.append(f"Channel usage: {channel_str}")

    return parts


def summarize_cc_trend(values: List[int]) -> str:
    if len(values) < CC_TREND_MIN_EVENTS:
        return "unknown"
    window = max(1, int(len(values) * CC_TREND_WINDOW_RATIO))
    start_avg = average(values[:window])
    end_avg = average(values[-window:])
    delta = end_avg - start_avg
    if abs(delta) < CC_TREND_MIN_DELTA:
        return "stable"
    return "rising (crescendo)" if delta > 0 else "falling (decrescendo)"


def format_cc_label(cc_num: int) -> str:
    name = CC_LABELS.get(cc_num)
    if name:
        return f"{name} (CC{cc_num})"
    return f"CC{cc_num}"


def summarize_cc_events(cc_events: List[Dict[str, Any]]) -> List[str]:
    grouped: Dict[int, List[Tuple[float, int]]] = {}
    for evt in cc_events:
        cc = safe_int(evt.get("cc") or evt.get("controller"))
        value = safe_int(evt.get("value") or evt.get("val"))
        if cc is None or value is None:
            continue
        time_q = safe_float(evt.get("time_q") or evt.get("start_q") or 0.0) or 0.0
        value = max(MIDI_MIN, min(MIDI_MAX, value))
        grouped.setdefault(cc, []).append((time_q, value))

    lines: List[str] = []
    for cc_num in sorted(grouped.keys()):
        events = sorted(grouped[cc_num], key=lambda x: x[0])
        values = [v for _, v in events]
        if not values:
            continue
        min_val = min(values)
        max_val = max(values)
        avg_val = average(values)
        trend = summarize_cc_trend(values)
        label = format_cc_label(cc_num)
        lines.append(
            f"{label}: range {min_val}-{max_val}, avg {avg_val:.1f}, trend {trend}, events {len(values)}"
        )
    return lines


def build_keyswitch_map(art_cfg: Dict[str, Any]) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    art_map = art_cfg.get("map", {})
    octave_offset = safe_int(art_cfg.get("octave_offset")) or 0
    if not isinstance(art_map, dict):
        return mapping
    for name, data in art_map.items():
        if not isinstance(data, dict):
            continue
        pitch = data.get("pitch")
        if pitch is None:
            continue
        try:
            midi_pitch = note_to_midi(pitch) + (octave_offset * 12)
        except ValueError:
            continue
        mapping[midi_pitch] = name
    return mapping


def collect_keyswitch_changes(
    notes: List[Dict[str, Any]],
    mapping: Dict[int, str],
) -> List[Tuple[float, str]]:
    changes: List[Tuple[float, str]] = []
    if not mapping:
        return changes
    for note in notes:
        pitch = safe_int(note.get("pitch"))
        if pitch is None:
            continue
        name = mapping.get(pitch)
        if not name:
            continue
        time_q = safe_float(note.get("start_q") or 0.0) or 0.0
        changes.append((time_q, name))
    changes.sort(key=lambda x: x[0])
    return changes


def collect_cc_articulation_changes(
    cc_events: List[Dict[str, Any]],
    art_cfg: Dict[str, Any],
) -> List[Tuple[float, str]]:
    cc_num = safe_int(art_cfg.get("cc_number"))
    if cc_num is None:
        return []
    value_to_name: Dict[int, str] = {}
    art_map = art_cfg.get("map", {})
    if isinstance(art_map, dict):
        for name, data in art_map.items():
            if not isinstance(data, dict):
                continue
            raw_val = data.get("cc_value") or data.get("value") or data.get("cc")
            val = safe_int(raw_val)
            if val is not None:
                value_to_name[val] = name

    changes: List[Tuple[float, str]] = []
    for evt in cc_events:
        cc = safe_int(evt.get("cc") or evt.get("controller"))
        if cc != cc_num:
            continue
        val = safe_int(evt.get("value") or evt.get("val"))
        if val is None:
            continue
        name = value_to_name.get(val)
        if not name:
            continue
        time_q = safe_float(evt.get("time_q") or evt.get("start_q") or 0.0) or 0.0
        changes.append((time_q, name))

    changes.sort(key=lambda x: x[0])
    return changes


def summarize_legato_keyswitch(
    notes: List[Dict[str, Any]],
    legato_cfg: Dict[str, Any],
) -> Optional[str]:
    if not legato_cfg or str(legato_cfg.get("mode", "")).lower() != "keyswitch":
        return None
    keyswitch = legato_cfg.get("keyswitch")
    if not keyswitch:
        return None
    try:
        ks_pitch = note_to_midi(keyswitch)
    except ValueError:
        return None

    vel_on = safe_int(legato_cfg.get("velocity_on"))
    vel_off = safe_int(legato_cfg.get("velocity_off"))
    events: List[str] = []

    for note in notes:
        pitch = safe_int(note.get("pitch"))
        if pitch != ks_pitch:
            continue
        vel = safe_int(note.get("vel"))
        state = None
        if vel is not None:
            if vel_on is not None and vel >= vel_on:
                state = "ON"
            elif vel_off is not None and vel <= vel_off:
                state = "OFF"
        events.append(state or "TOGGLE")

    if not events:
        return None
    last_state = next((state for state in reversed(events) if state in {"ON", "OFF"}), None)
    if last_state:
        return f"legato keyswitch: {len(events)} events, last {last_state}"
    return f"legato keyswitch: {len(events)} events"


def compress_changes(changes: List[Tuple[float, str]]) -> List[str]:
    seq: List[str] = []
    for _, name in changes:
        if not seq or seq[-1] != name:
            seq.append(name)
    return seq


def build_simplified_midi_map(
    notes: List[Dict[str, Any]],
    max_notes: int = SIMPLIFIED_MIDI_MAP_LIMIT,
    time_sig: str = "4/4",
) -> str:
    if not notes:
        return ""
    
    try:
        from music_notation import midi_to_note, dur_q_to_name, velocity_to_dynamic, time_q_to_bar_beat
    except ImportError:
        from .music_notation import midi_to_note, dur_q_to_name, velocity_to_dynamic, time_q_to_bar_beat
    
    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    limited = sorted_notes[:max_notes]
    
    entries = []
    for note in limited:
        start_q = note.get("start_q", 0)
        pitch = note.get("pitch", 60)
        dur_q = note.get("dur_q", 1.0)
        vel = note.get("vel", 80)
        
        bar, beat = time_q_to_bar_beat(start_q, time_sig)
        note_name = midi_to_note(pitch)
        dur_name = dur_q_to_name(dur_q, abbrev=True)
        dyn = velocity_to_dynamic(vel)
        
        entries.append(f"{bar}.{beat}:{note_name}({dur_name},{dyn})")
    
    result = ", ".join(entries)
    if len(sorted_notes) > max_notes:
        result += f" ... (+{len(sorted_notes) - max_notes} more)"
    return result


def detect_occupied_range(notes: List[Dict[str, Any]]) -> str:
    if not notes:
        return "unknown"
    pitches = [n.get("pitch", 60) for n in notes]
    min_pitch = min(pitches)
    max_pitch = max(pitches)
    avg_pitch = sum(pitches) / len(pitches)
    pitch_span = max_pitch - min_pitch
    if pitch_span > 24:
        return "wide"
    for range_name, (low, high) in FREQUENCY_RANGES.items():
        if low <= avg_pitch < high:
            return range_name
    return "mid"


def detect_rhythmic_feel(notes: List[Dict[str, Any]], length_q: float) -> str:
    if not notes or length_q <= 0:
        return "unknown"
    note_count = len(notes)
    notes_per_quarter = note_count / length_q
    avg_dur = sum(n.get("dur_q", 1.0) for n in notes) / note_count if note_count else 1.0
    if avg_dur >= RHYTHMIC_FEEL_THRESHOLDS["sustained"]:
        return "sustained"
    if notes_per_quarter <= RHYTHMIC_FEEL_THRESHOLDS["sparse"]:
        return "sparse"
    if notes_per_quarter >= RHYTHMIC_FEEL_THRESHOLDS["dense"]:
        return "dense"
    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    starts = [n.get("start_q", 0) for n in sorted_notes]
    if len(starts) >= 4:
        intervals = [starts[i+1] - starts[i] for i in range(len(starts)-1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else 1.0
        variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals) if intervals else 0
        if variance < 0.1:
            return "steady_pulse"
        if any(abs(i - round(i * 2) / 2) > 0.1 for i in starts[:8]):
            return "syncopated"
    return "moderate"


def detect_intensity_curve(notes: List[Dict[str, Any]]) -> str:
    if not notes or len(notes) < 4:
        return "static"
    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    velocities = [n.get("vel", 80) for n in sorted_notes]
    window = max(2, len(velocities) // 4)
    start_avg = sum(velocities[:window]) / window
    end_avg = sum(velocities[-window:]) / window
    mid_start = len(velocities) // 3
    mid_end = 2 * len(velocities) // 3
    mid_avg = sum(velocities[mid_start:mid_end]) / max(1, mid_end - mid_start)
    delta = end_avg - start_avg
    if mid_avg > start_avg + 10 and mid_avg > end_avg + 10:
        return "arc"
    if abs(delta) < 10:
        return "static"
    if delta > 15:
        return "building"
    if delta < -15:
        return "fading"
    if mid_avg > max(start_avg, end_avg) + 15:
        return "climax"
    return "static"


def generate_synthetic_handoff(
    notes: List[Dict[str, Any]],
    role: str = "",
    length_q: float = 16.0,
) -> Dict[str, Any]:
    try:
        from music_notation import midi_to_note
    except ImportError:
        from .music_notation import midi_to_note
    
    if not notes:
        return {
            "musical_function": role or "unknown",
            "occupied_range": "unknown",
            "rhythmic_feel": "unknown",
            "intensity_curve": "static",
            "gaps_for_others": "entire range available",
            "suggestion_for_next": "Free to play any part",
        }
    
    pitches = [n.get("pitch", 60) for n in notes]
    min_pitch = min(pitches)
    max_pitch = max(pitches)
    
    min_note = midi_to_note(min_pitch)
    max_note = midi_to_note(max_pitch)
    
    range_category = detect_occupied_range(notes)
    occupied_range = f"{min_note}-{max_note} ({range_category})"
    
    rhythmic_feel = detect_rhythmic_feel(notes, length_q)
    intensity_curve = detect_intensity_curve(notes)
    
    musical_function = role.lower() if role and role.lower() != "unknown" else "harmonic_support"
    if rhythmic_feel in ("dense", "steady_pulse", "syncopated"):
        musical_function = "rhythmic_foundation"
    elif rhythmic_feel == "sustained":
        musical_function = "harmonic_pad"
    elif max_pitch > 72 and len(notes) < length_q * 2:
        musical_function = "melodic_lead"
    
    gaps = []
    if max_pitch < 72:
        gaps.append(f"high register open (above {max_note})")
    if min_pitch > 48:
        gaps.append(f"low register available (below {min_note})")
    if rhythmic_feel in ("sustained", "sparse"):
        gaps.append("rhythmic space available")
    elif rhythmic_feel in ("dense", "steady_pulse"):
        gaps.append("sustained notes would complement")
    gaps_str = ", ".join(gaps) if gaps else "limited space available"
    
    suggestions = []
    if range_category in ("low", "low_mid"):
        suggestions.append(f"add melody above {max_note}")
    elif range_category in ("high", "high_mid"):
        suggestions.append(f"add bass/harmony below {min_note}")
    if rhythmic_feel in ("dense", "syncopated"):
        suggestions.append("play sparser, longer notes")
    elif rhythmic_feel == "sustained":
        suggestions.append("add rhythmic motion")
    
    suggestion = "; ".join(suggestions) if suggestions else "complement existing part"
    
    return {
        "musical_function": musical_function,
        "occupied_range": occupied_range,
        "rhythmic_feel": rhythmic_feel,
        "intensity_curve": intensity_curve,
        "gaps_for_others": gaps_str,
        "suggestion_for_next": suggestion[:HANDOFF_SUGGESTION_MAX_LEN],
    }


def validate_and_fix_handoff(handoff: Optional[Dict[str, Any]], notes: List[Dict[str, Any]], length_q: float) -> Dict[str, Any]:
    if not handoff or not isinstance(handoff, dict):
        return generate_synthetic_handoff(notes, "", length_q)
    required_fields = ["musical_function", "occupied_range", "rhythmic_feel", "intensity_curve", "gaps_for_others"]
    for field in required_fields:
        if field not in handoff or not handoff[field]:
            synthetic = generate_synthetic_handoff(notes, "", length_q)
            handoff[field] = synthetic.get(field, "unknown")
    if notes:
        actual_range = detect_occupied_range(notes)
        actual_rhythmic = detect_rhythmic_feel(notes, length_q)
        claimed_range = str(handoff.get("occupied_range", "")).lower()
        claimed_rhythmic = str(handoff.get("rhythmic_feel", "")).lower()
        range_mismatch = (
            (actual_range in ("low", "low_mid") and claimed_range in ("high", "high_mid")) or
            (actual_range in ("high", "high_mid") and claimed_range in ("low", "low_mid"))
        )
        rhythmic_mismatch = (
            (actual_rhythmic == "dense" and claimed_rhythmic == "sparse") or
            (actual_rhythmic == "sparse" and claimed_rhythmic == "dense") or
            (actual_rhythmic == "sustained" and claimed_rhythmic in ("dense", "syncopated"))
        )
        if range_mismatch:
            handoff["occupied_range"] = actual_range
            handoff["_range_corrected"] = True
        if rhythmic_mismatch:
            handoff["rhythmic_feel"] = actual_rhythmic
            handoff["_rhythmic_corrected"] = True
    if "suggestion_for_next" in handoff:
        handoff["suggestion_for_next"] = str(handoff["suggestion_for_next"])[:HANDOFF_SUGGESTION_MAX_LEN]
    return handoff


def format_handoff_for_prompt(handoff: Dict[str, Any], instrument_name: str) -> str:
    lines = [f"**MESSAGE FROM {instrument_name.upper()}:**"]
    function = handoff.get("musical_function", "unknown")
    occupied = handoff.get("occupied_range", "unknown")
    rhythmic = handoff.get("rhythmic_feel", "unknown")
    intensity = handoff.get("intensity_curve", "static")
    gaps = handoff.get("gaps_for_others", "")
    suggestion = handoff.get("suggestion_for_next", "")
    lines.append(f"  Function: {function} | Range: {occupied} | Rhythm: {rhythmic} | Dynamics: {intensity}")
    if gaps:
        lines.append(f"  Space left: {gaps}")
    if suggestion:
        lines.append(f"  → Suggestion: {suggestion}")
    return "\n".join(lines)


def summarize_articulation_context(context_tracks: Optional[List[Dict[str, Any]]]) -> List[str]:
    if not context_tracks:
        return []

    summaries: List[str] = []
    for track in context_tracks:
        track_name = str(track.get("name") or track.get("track") or track.get("track_name") or "").strip()
        profile_id = str(track.get("profile_id") or "").strip()
        if not profile_id:
            continue
        try:
            profile = load_profile(profile_id)
        except Exception:
            continue

        art_cfg = profile.get("articulations", {}) if isinstance(profile, dict) else {}
        mode = str(art_cfg.get("mode", "none")).lower()
        notes = track.get("notes", []) if isinstance(track.get("notes"), list) else []
        cc_events = track.get("cc_events", []) if isinstance(track.get("cc_events"), list) else []

        changes: List[Tuple[float, str]] = []
        if mode == "keyswitch":
            mapping = build_keyswitch_map(art_cfg)
            changes = collect_keyswitch_changes(notes, mapping)
        elif mode == "cc":
            changes = collect_cc_articulation_changes(cc_events, art_cfg)

        seq = compress_changes(changes)
        if seq:
            preview = " -> ".join(seq[:ARTICULATION_CHANGE_PREVIEW_LIMIT])
            if len(seq) > ARTICULATION_CHANGE_PREVIEW_LIMIT:
                preview = f"{preview} -> ..."
            name_prefix = f"{track_name}: " if track_name else ""
            summaries.append(f"{name_prefix}{preview} (changes {len(seq)})")

        legato_summary = summarize_legato_keyswitch(notes, profile.get("legato", {}))
        if legato_summary:
            name_prefix = f"{track_name}: " if track_name else ""
            summaries.append(f"{name_prefix}{legato_summary}")

    return summaries


def build_ensemble_context(
    ensemble: Optional[EnsembleInfo],
    current_profile_name: str,
    time_sig: str = "4/4",
    length_q: float = 16.0,
    has_plan_chord_map: bool = False,
) -> str:
    if not ensemble or ensemble.total_instruments <= 1:
        return ""

    parts: List[str] = []
    current_inst = ensemble.current_instrument or {}
    current_track = str(current_inst.get("track_name", "")).strip().lower()
    current_profile = str(current_inst.get("profile_name", "")).strip().lower()
    current_role = str(current_inst.get("role", "")).strip()

    def format_inst_label(inst: Any) -> str:
        track = str(inst.track_name or "").strip()
        profile = str(inst.profile_name or "").strip()
        if track and profile and track != profile:
            return f"{track} ({profile})"
        return track or profile or "Unknown"

    if ensemble.is_sequential:
        parts.append("### SEQUENTIAL ENSEMBLE GENERATION - BUILDING COHESIVE COMPOSITION")
        parts.append(f"You are generating part {ensemble.generation_order} of {ensemble.total_instruments} for a unified composition.")
        if ensemble.generation_order > 1:
            parts.append("Previous parts have ALREADY BEEN GENERATED. You MUST complement them, not duplicate.")
        parts.append("")
    else:
        parts.append("### ENSEMBLE GENERATION - CRITICAL FOR COHESIVE COMPOSITION")
        parts.append(f"You are generating ONE PART of a {ensemble.total_instruments}-instrument ensemble.")
        parts.append("All parts are being generated SIMULTANEOUSLY and must work together as a unified composition.")
        parts.append("")

    parts.append("ENSEMBLE INSTRUMENTS (in generation order):")

    for inst in ensemble.instruments:
        inst_track = str(inst.track_name or "").strip().lower()
        inst_profile = str(inst.profile_name or "").strip().lower()
        if current_track:
            is_current = inst_track == current_track
        elif current_profile:
            is_current = inst_profile == current_profile
        else:
            is_current = inst.profile_name == current_profile_name
        marker = " ← YOU ARE GENERATING THIS" if is_current else ""
        already_done = inst.index < ensemble.generation_order
        done_marker = " [ALREADY GENERATED]" if already_done and ensemble.is_sequential else ""
        family = inst.family.lower() if inst.family else "unknown"
        role = str(inst.role or "").strip()
        if role.lower() == "unknown":
            role = ""
        label = format_inst_label(inst)
        detail = family
        if role:
            detail = f"{detail}, role: {role}"
        range_info = inst.range or {}
        preferred = range_info.get("preferred", [])
        if preferred and len(preferred) == 2:
            detail = f"{detail}, range: {preferred[0]}-{preferred[1]}"
        parts.append(f"  {inst.index}. {label} ({detail}){marker}{done_marker}")

    parts.append("")

    if ensemble.is_sequential and ensemble.previously_generated:
        full_analysis_prompt = build_full_context_prompt(
            ensemble.previously_generated,
            time_sig,
            length_q,
            current_role,
            skip_auto_harmony=has_plan_chord_map,
        )
        if full_analysis_prompt:
            parts.append(full_analysis_prompt)
            parts.append("")

        has_handoffs = any(prev_part.get("handoff") for prev_part in ensemble.previously_generated)
        if has_handoffs:
            parts.append("### MESSAGES FROM PREVIOUS MUSICIANS (HANDOFF)")
            parts.append("These musicians have already played. Read their guidance carefully:")
            parts.append("")
            for prev_part in ensemble.previously_generated:
                part_name = prev_part.get("profile_name", prev_part.get("track_name", "Unknown"))
                prev_notes = prev_part.get("notes", [])
                handoff = prev_part.get("handoff")
                if handoff:
                    validated_handoff = validate_and_fix_handoff(handoff, prev_notes, length_q)
                else:
                    part_role = str(prev_part.get("role") or "").strip()
                    validated_handoff = generate_synthetic_handoff(prev_notes, part_role, length_q)
                parts.append(format_handoff_for_prompt(validated_handoff, part_name))
                parts.append("")
            parts.append("HANDOFF PRIORITY:")
            parts.append("- Consult the GLOBAL PLAN for overall direction")
            parts.append("- Use HANDOFFS to understand what space is available")
            parts.append("- If handoff conflicts with plan, FOLLOW THE PLAN")
            parts.append("")

        parts.append("### PREVIOUSLY GENERATED PARTS (in musical notation)")
        parts.append("Format: Bar.Beat:Note(duration,dynamics)")
        parts.append("")

        for prev_part in ensemble.previously_generated:
            part_name = prev_part.get("profile_name", prev_part.get("track_name", "Unknown"))
            part_role = str(prev_part.get("role") or "").strip()
            if part_role.lower() == "unknown":
                part_role = ""
            prev_notes = prev_part.get("notes", [])
            role_suffix = f" [{part_role}]" if part_role else ""
            midi_map = build_simplified_midi_map(prev_notes, SIMPLIFIED_MIDI_MAP_LIMIT, time_sig)
            if midi_map:
                pitches = [n.get("pitch", 60) for n in prev_notes]
                range_str = f"(Range: {pitch_to_note(min(pitches))}-{pitch_to_note(max(pitches))})" if pitches else ""
                parts.append(f"**{part_name}**{role_suffix} {range_str}:")
                parts.append(f"  {midi_map}")
                parts.append("")

    parts.append("ENSEMBLE COORDINATION RULES:")
    parts.append("1. AVOID UNISON: Don't duplicate exact same notes as other instruments")
    parts.append("2. REGISTER SEPARATION: Stay in your instrument's typical register")
    parts.append("3. RHYTHMIC VARIETY: Mix long and short notes across the ensemble")
    parts.append("4. HARMONIC ROLES: Bass=roots, mid=3rds/5ths, high=melody")
    parts.append("5. CALL & RESPONSE: Create phrases that leave space for other instruments")
    parts.append("6. FOLLOW HARMONY: Play the same chord changes as existing parts")
    parts.append("7. PHRASE TOGETHER: Start and end phrases at similar times")
    parts.append("")

    current_inst = ensemble.current_instrument
    if current_inst:
        role = current_inst.get("role", "unknown").lower()
        family = current_inst.get("family", "unknown").lower()
        hint = ROLE_HINTS.get(role) or ROLE_HINTS.get(family, "")
        if hint:
            current_label = str(current_inst.get("track_name") or "").strip()
            current_profile_name = str(current_inst.get("profile_name") or "").strip()
            if current_label and current_profile_name and current_label != current_profile_name:
                current_label = f"{current_label} ({current_profile_name})"
            if not current_label:
                current_label = current_profile_name or "instrument"
            parts.append(f"YOUR ROLE ({current_label}): {hint}")
            parts.append("")

    if ensemble.total_instruments >= 3:
        parts.append("ORCHESTRATION LAYERS:")
        parts.append("  - MELODY layer: Main theme carrier (lead instrument)")
        parts.append("  - HARMONY layer: Chords/sustained notes (support)")
        parts.append("  - BASS layer: Foundation and roots (anchor)")
        parts.append("  - COLOR layer: Countermelodies, fills (embellishment)")
        parts.append("")

    return "\n".join(parts)


def collect_context_notes_for_velocity(context: ContextInfo) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    if context.existing_notes:
        notes.extend(context.existing_notes)
    if context.horizontal:
        if context.horizontal.before:
            notes.extend(context.horizontal.before)
        if context.horizontal.after:
            notes.extend(context.horizontal.after)
    return notes


def build_context_summary(
    context: Optional[ContextInfo],
    time_sig: str = "4/4",
    length_q: float = 16.0,
    key_str: str = "unknown",
    skip_auto_harmony: bool = False,
) -> Tuple[str, str, str]:
    if not context:
        return "", "unknown", "isolated"

    parts: List[str] = []
    detected_key = "unknown"
    position = "isolated"

    notes_for_progression = context.extended_progression or context.existing_notes
    if notes_for_progression and not skip_auto_harmony:
        progression, detected_key = analyze_harmony_progression(notes_for_progression, time_sig, length_q)
        if progression:
            parts.append(f"### HARMONY CONTEXT\nCHORD PROGRESSION: {progression}")

    effective_key = key_str if key_str != "unknown" else detected_key
    horizontal_summary, position = build_horizontal_context_summary(context.horizontal, effective_key)
    if horizontal_summary:
        parts.append(horizontal_summary)

    if context.existing_notes:
        if context.pitch_range:
            min_p = context.pitch_range.get("min", 48)
            max_p = context.pitch_range.get("max", 72)
            parts.append(f"Vertical context range: {pitch_to_note(min_p)} to {pitch_to_note(max_p)} (MIDI {min_p}-{max_p})")
            suggested_low = max_p
            suggested_high = min(max_p + 12, 96)
            parts.append(f"SUGGESTED MELODY RANGE: MIDI {suggested_low}-{suggested_high} (above existing parts)")
        note_summary = format_notes_for_context(context.existing_notes, NOTE_CONTEXT_PREVIEW_LIMIT)
        if note_summary:
            parts.append(f"Context notes (start_q, pitch, dur_q, vel, chan): {note_summary}")

    velocity_notes = collect_context_notes_for_velocity(context)
    dynamics_lines = summarize_velocity_context(velocity_notes)
    if dynamics_lines:
        parts.append("### DYNAMICS CONTEXT\n" + "\n".join(dynamics_lines))

    cc_lines = summarize_cc_events(context.cc_events or [])
    if cc_lines:
        parts.append("### CC CONTEXT\n" + "\n".join(cc_lines))

    articulation_lines = summarize_articulation_context(context.context_tracks)
    if articulation_lines:
        parts.append("### ARTICULATION CONTEXT\n" + "\n".join(articulation_lines))

    if context.context_notes:
        parts.append(context.context_notes.strip())

    if context.selected_tracks_midi:
        names = []
        for track in context.selected_tracks_midi:
            if isinstance(track, str):
                names.append(track)
            elif hasattr(track, "name") and track.name:
                names.append(track.name)
            elif isinstance(track, dict) and track.get("name"):
                names.append(track["name"])
        if names:
            parts.append(f"Accompanying tracks: {', '.join(names)}")

    return "\n".join([part for part in parts if part]), detected_key, position
