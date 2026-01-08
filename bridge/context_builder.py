from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import MIDI_MAX, MIDI_MIN
    from midi_utils import note_to_midi
    from models import ContextInfo, EnsembleInfo, HorizontalContext
    from music_theory import analyze_chord, detect_key_from_chords, pitch_to_note, velocity_to_dynamic
    from profile_utils import load_profile
except ImportError:
    from .constants import MIDI_MAX, MIDI_MIN
    from .midi_utils import note_to_midi
    from .models import ContextInfo, EnsembleInfo, HorizontalContext
    from .music_theory import analyze_chord, detect_key_from_chords, pitch_to_note, velocity_to_dynamic
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
NOTE_CONTEXT_PREVIEW_LIMIT = 30
ARTICULATION_CHANGE_PREVIEW_LIMIT = 6
CC_LABELS = {
    1: "Dynamics",
    11: "Expression",
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

    chord_unit = quarters_per_bar / 2 if quarters_per_bar >= 2 else quarters_per_bar

    segments: Dict[int, List[int]] = {}
    for note in existing_notes:
        start_q = note.get("start_q", 0)
        pitch = note.get("pitch", 60)
        dur_q = note.get("dur_q", 0.5)

        seg_start = int(start_q // chord_unit)
        seg_end = int((start_q + dur_q) // chord_unit)

        for seg_idx in range(seg_start, seg_end + 1):
            if seg_idx not in segments:
                segments[seg_idx] = []
            if pitch not in segments[seg_idx]:
                segments[seg_idx].append(pitch)

    progression = []
    chord_roots = []
    segments_per_bar = max(1, int(quarters_per_bar / chord_unit))

    for seg_idx in sorted(segments.keys()):
        bar_num = (seg_idx // segments_per_bar) + 1
        beat_in_bar = (seg_idx % segments_per_bar) + 1
        chord_name, root = analyze_chord(segments[seg_idx])
        if root is not None:
            chord_roots.append(root)
        if segments_per_bar > 1:
            progression.append(f"B{bar_num}.{beat_in_bar}:{chord_name}")
        else:
            progression.append(f"B{bar_num}:{chord_name}")

    detected_key = detect_key_from_chords(chord_roots)
    return " | ".join(progression), detected_key


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


def build_horizontal_context_summary(horizontal: Optional[HorizontalContext]) -> Tuple[str, str]:
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


def build_ensemble_context(ensemble: Optional[EnsembleInfo], current_profile_name: str) -> str:
    if not ensemble or ensemble.total_instruments <= 1:
        return ""

    parts: List[str] = []
    current_inst = ensemble.current_instrument or {}
    current_track = str(current_inst.get("track_name", "")).strip().lower()
    current_profile = str(current_inst.get("profile_name", "")).strip().lower()

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
        parts.append(f"  {inst.index}. {label} ({detail}){marker}{done_marker}")

    parts.append("")

    if ensemble.is_sequential and ensemble.previously_generated:
        parts.append("### PREVIOUSLY GENERATED PARTS - YOU MUST COMPLEMENT THESE")
        parts.append("The following parts have already been composed. Study them carefully!")
        parts.append("")

        for prev_part in ensemble.previously_generated:
            part_name = prev_part.get("profile_name", prev_part.get("track_name", "Unknown"))
            part_role = str(prev_part.get("role") or "").strip()
            if part_role.lower() == "unknown":
                part_role = ""
            prev_notes = prev_part.get("notes", [])
            role_suffix = f" (role: {part_role})" if part_role else ""
            parts.append(f"**{part_name}**{role_suffix}:")

            if prev_notes:
                note_summary = format_notes_for_context(prev_notes, NOTE_CONTEXT_PREVIEW_LIMIT)
                parts.append(f"  Notes (start_q, pitch, dur_q, vel, chan): {note_summary}")

                pitches = [n.get("pitch", 60) for n in prev_notes]
                if pitches:
                    parts.append(f"  Pitch range: {min(pitches)}-{max(pitches)}")

                note_count = len(prev_notes)
                parts.append(f"  Total notes: {note_count}")
            parts.append("")

        parts.append("CRITICAL RULES FOR COMPLEMENTING EXISTING PARTS:")
        parts.append("1. DO NOT DUPLICATE melodies or rhythms from parts above")
        parts.append("2. Use DIFFERENT register (higher or lower than existing parts)")
        parts.append("3. Create COUNTERPOINT - when melody moves, you can hold; when melody holds, you can move")
        parts.append("4. Match the HARMONIC RHYTHM - change chords when the bass/harmony changes")
        parts.append("5. Support the PHRASE STRUCTURE - breathe when the melody breathes")
        parts.append("")

    parts.append("ENSEMBLE COORDINATION RULES:")
    parts.append("1. AVOID UNISON: Don't duplicate exact same notes as other instruments")
    parts.append("2. REGISTER SEPARATION: Stay in your instrument's typical register")
    parts.append("3. RHYTHMIC VARIETY: Mix long and short notes across the ensemble")
    parts.append("4. HARMONIC ROLES: Bass=roots, mid=3rds/5ths, high=melody")
    parts.append("5. CALL & RESPONSE: Create phrases that leave space for other instruments")
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
        parts.append("  - MELODY layer: Main theme carrier")
        parts.append("  - HARMONY layer: Chords/sustained notes")
        parts.append("  - BASS layer: Foundation and roots")
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
    length_q: float = 16.0
) -> Tuple[str, str, str]:
    if not context:
        return "", "unknown", "isolated"

    parts: List[str] = []
    detected_key = "unknown"
    position = "isolated"

    horizontal_summary, position = build_horizontal_context_summary(context.horizontal)
    if horizontal_summary:
        parts.append(horizontal_summary)

    notes_for_progression = context.extended_progression or context.existing_notes
    if notes_for_progression:
        progression, detected_key = analyze_harmony_progression(notes_for_progression, time_sig, length_q)
        if progression:
            parts.append(f"### HARMONY CONTEXT\nCHORD PROGRESSION: {progression}")

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
