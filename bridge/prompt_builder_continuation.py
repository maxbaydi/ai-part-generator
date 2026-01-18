from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import (
        CONTINUATION_MODES,
        DEFAULT_CONTINUATION_MODE,
        DEFAULT_SECTION_POSITION,
        SECTION_POSITIONS,
        DEFAULT_PITCH,
    )
    from context_builder import get_profile_keyswitch_pitches
    from music_analysis import extract_motif_from_notes
    from prompt_builder_common import import_music_notation, normalize_lower, normalize_text
    from prompt_builder_sketch import format_sketch_notes
    from profile_utils import load_profile
except ImportError:
    from .constants import (
        CONTINUATION_MODES,
        DEFAULT_CONTINUATION_MODE,
        DEFAULT_SECTION_POSITION,
        SECTION_POSITIONS,
        DEFAULT_PITCH,
    )
    from .context_builder import get_profile_keyswitch_pitches
    from .music_analysis import extract_motif_from_notes
    from .prompt_builder_common import import_music_notation, normalize_lower, normalize_text
    from .prompt_builder_sketch import format_sketch_notes
    from .profile_utils import load_profile


MOTIF_MAX_NOTES = 8
MOTIF_NOTE_DECIMALS = 2
DEFAULT_START_Q = 0.0
DEFAULT_DUR_Q = 1.0
DEFAULT_TRACK_LABEL = "Unknown"
FULL_CONTEXT_HEADER = "### FULL SELECTION CONTEXT (ALL NOTES/CC)"
DYNAMICS_CC_CONTROLLERS = {1, 11}
NO_EVENTS_LABEL = "(no cc events)"
CC_TIME_PRECISION = 3
CC_SIMPLIFY_TOLERANCE = 1.0
CC_SIMPLIFY_MIN_POINTS = 3
DEFAULT_CC_CONTROLLER = -1
DEFAULT_CC_VALUE = 0


def resolve_continuation_mode(value: Any) -> str:
    mode = normalize_lower(value)
    if mode in CONTINUATION_MODES:
        return mode
    return DEFAULT_CONTINUATION_MODE


def resolve_section_position(value: Any) -> str:
    position = normalize_lower(value)
    if position in SECTION_POSITIONS:
        return position
    return DEFAULT_SECTION_POSITION


def format_motif_notes(notes: List[Dict[str, Any]], midi_to_note) -> str:
    entries: List[str] = []
    for note in notes:
        start_q = float(note.get("start_q", DEFAULT_START_Q))
        dur_q = float(note.get("dur_q", DEFAULT_DUR_Q))
        pitch = int(note.get("pitch", DEFAULT_PITCH))
        entries.append(
            f"({start_q:.{MOTIF_NOTE_DECIMALS}f}, {midi_to_note(pitch)}, {dur_q:.{MOTIF_NOTE_DECIMALS}f})"
        )
    return ", ".join(entries)


def filter_cc_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not events:
        return []
    filtered = []
    for evt in events:
        try:
            cc = int(evt.get("cc", -1))
        except (TypeError, ValueError):
            continue
        if cc in DYNAMICS_CC_CONTROLLERS:
            filtered.append(evt)
    return filtered


def build_cc_points(events: List[Dict[str, Any]]) -> List[Tuple[float, int]]:
    points: List[Tuple[float, int]] = []
    for evt in events:
        try:
            time_q = float(evt.get("time_q", DEFAULT_START_Q))
            value = int(evt.get("value", DEFAULT_CC_VALUE))
        except (TypeError, ValueError):
            continue
        points.append((time_q, value))
    points.sort(key=lambda p: (p[0], p[1]))
    deduped: List[Tuple[float, int]] = []
    for time_q, value in points:
        if not deduped or time_q != deduped[-1][0]:
            deduped.append((time_q, value))
        else:
            deduped[-1] = (time_q, value)
    return deduped


def simplify_cc_points(points: List[Tuple[float, int]], tolerance: float) -> List[Tuple[float, int]]:
    if len(points) <= 2:
        return points
    start_t, start_v = points[0]
    end_t, end_v = points[-1]
    denom = end_t - start_t
    max_err = -1.0
    max_idx = 0
    if denom == 0:
        for idx in range(1, len(points) - 1):
            err = abs(points[idx][1] - start_v)
            if err > max_err:
                max_err = err
                max_idx = idx
    else:
        for idx in range(1, len(points) - 1):
            t, v = points[idx]
            ratio = (t - start_t) / denom
            expected = start_v + ratio * (end_v - start_v)
            err = abs(v - expected)
            if err > max_err:
                max_err = err
                max_idx = idx
    if max_err <= tolerance:
        return [points[0], points[-1]]
    left = simplify_cc_points(points[: max_idx + 1], tolerance)
    right = simplify_cc_points(points[max_idx:], tolerance)
    return left[:-1] + right


def format_cc_points(points: List[Tuple[float, int]]) -> str:
    entries = [f"{time_q:.{CC_TIME_PRECISION}f}:{int(value)}" for time_q, value in points]
    return ", ".join(entries)


def resolve_track_label(track: Dict[str, Any]) -> str:
    return normalize_text(track.get("name") or track.get("track") or track.get("track_name") or DEFAULT_TRACK_LABEL)


def resolve_profile_keyswitches(profile_id: str) -> set[int]:
    if not profile_id:
        return set()
    try:
        profile = load_profile(profile_id)
    except Exception:
        return set()
    return get_profile_keyswitch_pitches(profile)


def format_full_notes(notes: List[Dict[str, Any]], time_sig: str) -> str:
    count = len(notes)
    limit = count if count > 0 else 0
    return format_sketch_notes(notes, time_sig, limit=limit)


def format_full_cc(events: List[Dict[str, Any]], length_q: float) -> Tuple[str, str]:
    filtered = filter_cc_events(events)
    if not filtered:
        return NO_EVENTS_LABEL, "(none)"
    by_key: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    controllers: set[int] = set()
    for evt in filtered:
        try:
            cc = int(evt.get("cc", DEFAULT_CC_CONTROLLER))
            chan = int(evt.get("chan", 1))
        except (TypeError, ValueError):
            continue
        controllers.add(cc)
        by_key.setdefault((cc, chan), []).append(evt)
    lines: List[str] = []
    for (cc, chan) in sorted(by_key.keys()):
        points = build_cc_points(by_key[(cc, chan)])
        simplified = (
            simplify_cc_points(points, CC_SIMPLIFY_TOLERANCE)
            if len(points) >= CC_SIMPLIFY_MIN_POINTS else points
        )
        lines.append(f"CC{cc} ch{chan} points (orig={len(points)}, simplified={len(simplified)}):")
        lines.append(format_cc_points(simplified))
    controllers_str = ", ".join(f"CC{cc}" for cc in sorted(controllers))
    return "\n".join(lines), controllers_str


def build_full_selection_context(
    context: Optional[Any],
    time_sig: str,
    length_q: float,
    target_profile: Optional[Dict[str, Any]] = None,
) -> List[str]:
    if not context:
        return []

    if isinstance(context, dict):
        continuation_source = context.get("continuation_source")
        continuation_cc = context.get("continuation_cc_events")
        selected_tracks_full = context.get("selected_tracks_full")
    else:
        continuation_source = getattr(context, "continuation_source", None)
        continuation_cc = getattr(context, "continuation_cc_events", None)
        selected_tracks_full = getattr(context, "selected_tracks_full", None)

    if not continuation_source and not selected_tracks_full:
        return []

    lines = [FULL_CONTEXT_HEADER]

    target_keyswitches = get_profile_keyswitch_pitches(target_profile)
    if continuation_source:
        filtered_source = filter_keyswitch_notes(continuation_source, target_keyswitches)
        lines.append("TARGET TRACK (selected for continuation)")
        lines.append(f"Notes: {len(filtered_source)}")
        lines.append(format_full_notes(filtered_source, time_sig))
        cc_formatted, cc_controllers = format_full_cc(continuation_cc or [], length_q)
        lines.append(f"CC Controllers: {cc_controllers}")
        lines.append(cc_formatted)

    if selected_tracks_full:
        lines.append("OTHER SELECTED TRACKS")
        for track in selected_tracks_full:
            if not isinstance(track, dict):
                continue
            label = resolve_track_label(track)
            notes = track.get("notes", []) if isinstance(track.get("notes"), list) else []
            profile_id = str(track.get("profile_id") or "")
            keyswitches = resolve_profile_keyswitches(profile_id)
            filtered_notes = filter_keyswitch_notes(notes, keyswitches)
            lines.append(f"{label} • Notes: {len(filtered_notes)}")
            lines.append(format_full_notes(filtered_notes, time_sig))
            cc_events = track.get("cc_events", []) if isinstance(track.get("cc_events"), list) else []
            cc_formatted, cc_controllers = format_full_cc(cc_events, length_q)
            lines.append(f"CC Controllers: {cc_controllers}")
            lines.append(cc_formatted)

    return lines


def filter_keyswitch_notes(notes: List[Dict[str, Any]], keyswitch_pitches: set[int]) -> List[Dict[str, Any]]:
    if not notes:
        return []
    if not keyswitch_pitches:
        return list(notes)
    filtered: List[Dict[str, Any]] = []
    for note in notes:
        try:
            pitch = int(note.get("pitch", DEFAULT_PITCH))
        except (TypeError, ValueError):
            pitch = DEFAULT_PITCH
        if pitch in keyswitch_pitches:
            continue
        filtered.append(note)
    return filtered


def build_continuation_prompt(
    continuation: Optional[Any],
    context: Optional[Any],
    target_profile: Optional[Dict[str, Any]] = None,
) -> List[str]:
    if not continuation:
        return []

    mode = resolve_continuation_mode(getattr(continuation, "mode", ""))
    section_position = resolve_section_position(getattr(continuation, "section_position", ""))

    lines = [
        "### CONTINUATION MODE (MANDATORY)",
        f"- Mode: {mode}",
        f"- Section position (user-selected): {section_position}",
        "- Preserve horizontal continuity with the selected preceding material",
        "- Preserve vertical consistency with accompanying tracks in the selection",
        "- Keep key and harmony fixed unless the user explicitly requests a change",
        "- If any suggested melody range conflicts with the continuation source, follow the continuation source register",
    ]

    if mode == "continue":
        lines.append("- Avoid final cadential formulas and full resolution")
    elif mode == "finish":
        lines.append("- End with a clear cadence/resolution in the current key/harmony")

    keyswitch_pitches = get_profile_keyswitch_pitches(target_profile)
    source_notes = None
    if isinstance(context, dict):
        source_notes = context.get("continuation_source")
        horizontal = context.get("horizontal")
    else:
        source_notes = getattr(context, "continuation_source", None) if context else None
        horizontal = getattr(context, "horizontal", None) if context else None

    before_notes = None
    if horizontal:
        before_notes = horizontal.get("before") if isinstance(horizontal, dict) else getattr(horizontal, "before", None)

    if source_notes:
        source_notes = filter_keyswitch_notes(source_notes, keyswitch_pitches)
    elif before_notes:
        source_notes = filter_keyswitch_notes(before_notes, keyswitch_pitches)

    if source_notes:
        midi_to_note, _dur_q_to_name, _velocity_to_dynamic = import_music_notation()
        pitches = [n.get("pitch", DEFAULT_PITCH) for n in source_notes if isinstance(n, dict)]
        if pitches:
            min_pitch = min(pitches)
            max_pitch = max(pitches)
            lines.append(
                f"- Target line register (from selected material): "
                f"{midi_to_note(min_pitch)}-{midi_to_note(max_pitch)} (MIDI {min_pitch}-{max_pitch})"
            )

        sorted_source = sorted(source_notes, key=lambda n: n.get("start_q", DEFAULT_START_Q))
        motif_source = sorted_source[-MOTIF_MAX_NOTES:]
        motif = extract_motif_from_notes(motif_source, max_notes=MOTIF_MAX_NOTES)
        if motif:
            motif_notes = motif.get("notes", [])
            intervals = motif.get("intervals", [])
            rhythm_pattern = motif.get("rhythm_pattern", [])
            start_pitch = motif.get("start_pitch", DEFAULT_PITCH)
            character = motif.get("character", "")
            lines.extend([
                "",
                "### MOTIF TO PRESERVE (from preceding material)",
                f"- Start pitch: {midi_to_note(start_pitch)} (MIDI {start_pitch})",
                f"- Intervals: {intervals}",
                f"- Rhythm pattern (dur_q): {rhythm_pattern}",
                f"- Character: {character}",
            ])
            if motif_notes:
                lines.append(f"- Motif notes (start_q, note, dur_q): {format_motif_notes(motif_notes, midi_to_note)}")

    return lines
