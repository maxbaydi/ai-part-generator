from __future__ import annotations

import re

from typing import Any, Dict, List, Optional, Tuple

from bisect import bisect_right

try:
    from logger_config import logger
except ImportError:
    from .logger_config import logger

try:
    from constants import (
        ARTICULATION_MAX_DUR_Q,
        ARTICULATION_PRE_ROLL_Q,
        DEFAULT_ARTICULATION_CC,
        DEFAULT_KEYSWITCH_VELOCITY,
        KEYSWITCH_DUR_Q,
        MAX_TEMPO_MARKERS,
        MIDI_MAX,
        MIDI_MIN,
        MIDI_VEL_MIN,
        MIN_NOTE_DUR_Q,
        MIN_NOTE_GAP_Q,
        SHORT_ARTICULATION_FALLBACK_MAX_Q,
        TEMPO_MARKER_MAX_BPM,
        TEMPO_MARKER_MIN_BPM,
        TEMPO_MARKER_MIN_GAP_Q,
        TIME_SIG_MAX_NUM,
        TIME_SIG_MIN_NUM,
        TIME_SIG_VALID_DENOM,
        WIND_BRASS_FAMILIES,
        WIND_BRASS_MAX_NOTE_DUR_Q,
        STRINGS_MAX_NOTE_DUR_Q,
        STRINGS_FAMILIES,
        MAX_NOTE_DUR_Q_DEFAULT,
        ARRANGEMENT_MAX_NOTE_DUR_BARS,
    )
    from context_builder import generate_synthetic_handoff, get_quarters_per_bar, validate_and_fix_handoff
    from curve_utils import build_cc_events
    from midi_utils import (
        bar_beat_to_start_q,
        normalize_channel,
        normalize_drums,
        normalize_notes,
        note_to_midi,
        parse_range,
    )
    from music_analysis import extract_motif_from_notes
    from music_theory import NOTE_TO_PC, get_chord_tones
    from utils import clamp
except ImportError:
    from .constants import (
        ARTICULATION_MAX_DUR_Q,
        ARTICULATION_PRE_ROLL_Q,
        DEFAULT_ARTICULATION_CC,
        DEFAULT_KEYSWITCH_VELOCITY,
        KEYSWITCH_DUR_Q,
        MAX_TEMPO_MARKERS,
        MIDI_MAX,
        MIDI_MIN,
        MIDI_VEL_MIN,
        MIN_NOTE_DUR_Q,
        MIN_NOTE_GAP_Q,
        SHORT_ARTICULATION_FALLBACK_MAX_Q,
        TEMPO_MARKER_MAX_BPM,
        TEMPO_MARKER_MIN_BPM,
        TEMPO_MARKER_MIN_GAP_Q,
        TIME_SIG_MAX_NUM,
        TIME_SIG_MIN_NUM,
        TIME_SIG_VALID_DENOM,
        WIND_BRASS_FAMILIES,
        WIND_BRASS_MAX_NOTE_DUR_Q,
        STRINGS_MAX_NOTE_DUR_Q,
        STRINGS_FAMILIES,
        MAX_NOTE_DUR_Q_DEFAULT,
        ARRANGEMENT_MAX_NOTE_DUR_BARS,
    )
    from .context_builder import generate_synthetic_handoff, get_quarters_per_bar, validate_and_fix_handoff
    from .curve_utils import build_cc_events
    from .midi_utils import (
        bar_beat_to_start_q,
        normalize_channel,
        normalize_drums,
        normalize_notes,
        note_to_midi,
        parse_range,
    )
    from .music_analysis import extract_motif_from_notes
    from .music_theory import NOTE_TO_PC, get_chord_tones
    from .utils import clamp


MIN_NOTE_DUR_FOR_DYNAMICS = 1.0
LONG_NOTE_DUR_FOR_DYNAMICS = 2.0
SWELL_PEAK_RATIO = 0.35
DYNAMICS_DECAY_RATIO = 0.75
DYNAMICS_RELEASE_RATIO = 0.9
DYNAMICS_BASE_VALUE = 64
DYNAMICS_SWELL_AMOUNT = 12

EXPRESSION_DEFAULT_MIN = 70
EXPRESSION_DEFAULT_MAX = 100

MAX_DYNAMICS_JUMP = 20
SMOOTH_TRANSITION_STEP = 0.25

HARMONY_VALIDATION_TOLERANCE_Q = 0.125

NOTE_NAME_RE = re.compile(r"\b([A-Ga-g])([#b]?)\b")
MIN_PER_NOTE_DYNAMICS_POINTS = 3
LONG_NOTE_DYNAMICS_POINTS = 4
BREAKPOINT_NEAR_WINDOW_Q = 0.02


def smooth_breakpoint_transitions(breakpoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(breakpoints) < 2:
        return breakpoints
    
    sorted_bps = sorted(breakpoints, key=lambda x: float(x.get("time_q", 0)))
    result = []
    
    for i, bp in enumerate(sorted_bps):
        time_q = float(bp.get("time_q", 0))
        value = float(bp.get("value", DYNAMICS_BASE_VALUE))
        
        if i == 0:
            result.append({"time_q": time_q, "value": int(value)})
            continue
        
        prev_bp = result[-1]
        prev_time = float(prev_bp.get("time_q", 0))
        prev_value = float(prev_bp.get("value", DYNAMICS_BASE_VALUE))
        
        time_gap = time_q - prev_time
        value_jump = abs(value - prev_value)
        
        if value_jump > MAX_DYNAMICS_JUMP and time_gap < SMOOTH_TRANSITION_STEP * 2:
            mid_time = prev_time + time_gap * 0.5
            mid_value = prev_value + (value - prev_value) * 0.5
            result.append({"time_q": round(mid_time, 4), "value": int(mid_value)})
        
        result.append({"time_q": time_q, "value": int(value)})
    
    return result


def normalize_chord_tones(raw_tones: Any) -> List[int]:
    if not raw_tones:
        return []

    if isinstance(raw_tones, str):
        tokens = NOTE_NAME_RE.findall(raw_tones)
        raw_tones = ["".join(token) for token in tokens]

    tones: List[int] = []
    for tone in raw_tones if isinstance(raw_tones, list) else []:
        if isinstance(tone, str):
            name = tone.strip()
            if not name:
                continue
            pc = NOTE_TO_PC.get(name, NOTE_TO_PC.get(name.capitalize()))
            if pc is None:
                continue
            tones.append(int(pc) % 12)
        else:
            try:
                tones.append(int(tone) % 12)
            except (TypeError, ValueError):
                continue

    return sorted(set(tones))


def extract_chord_tones_from_notes_available(notes_available: Any) -> List[int]:
    if not notes_available:
        return []
    if not isinstance(notes_available, str):
        notes_available = str(notes_available)
    tokens = NOTE_NAME_RE.findall(notes_available)
    if not tokens:
        return []
    names = ["".join(token) for token in tokens]
    return normalize_chord_tones(names)


def normalize_chord_map_for_validation(
    chord_map: Optional[List[Dict[str, Any]]],
    time_sig: str,
) -> List[Dict[str, Any]]:
    if not chord_map:
        return []

    normalized: List[Dict[str, Any]] = []
    for entry in chord_map:
        if not isinstance(entry, dict):
            continue
        time_q = safe_float(entry.get("time_q"))
        if time_q is None:
            bar = entry.get("bar")
            beat = entry.get("beat")
            if bar is not None and beat is not None:
                time_q = bar_beat_to_start_q(bar, beat, time_sig)
            else:
                time_q = 0.0

        chord_tones = normalize_chord_tones(entry.get("chord_tones"))
        if not chord_tones:
            chord_tones = extract_chord_tones_from_notes_available(entry.get("notes_available"))
        if not chord_tones:
            chord_name = entry.get("chord") or entry.get("chord_name") or ""
            chord_tones = normalize_chord_tones(get_chord_tones(str(chord_name)))

        normalized.append({
            **entry,
            "time_q": float(time_q),
            "chord_tones": chord_tones,
        })

    return normalized


def get_active_chord_at_time(
    time_q: float,
    chord_map: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not chord_map:
        return None
    times = [float(c.get("time_q", 0)) for c in chord_map]
    idx = bisect_right(times, time_q) - 1
    if idx < 0:
        return chord_map[0] if chord_map else None
    return chord_map[idx]


def find_nearest_chord_tone(pitch: int, chord_tones: List[int], direction: int = 0) -> int:
    if not chord_tones:
        return pitch
    pc = pitch % 12
    if pc in chord_tones:
        return pitch
    
    best_pitch = pitch
    min_distance = 12
    
    for offset in range(1, 7):
        up_pc = (pc + offset) % 12
        down_pc = (pc - offset) % 12
        
        if direction >= 0 and up_pc in chord_tones:
            if offset < min_distance:
                min_distance = offset
                best_pitch = pitch + offset
                if direction > 0:
                    break
        
        if direction <= 0 and down_pc in chord_tones:
            if offset < min_distance:
                min_distance = offset
                best_pitch = pitch - offset
                if direction < 0:
                    break
    
    return best_pitch


def validate_notes_against_harmony(
    notes: List[Dict[str, Any]],
    chord_map: List[Dict[str, Any]],
    abs_range: Optional[Tuple[int, int]] = None,
    tolerance_q: float = HARMONY_VALIDATION_TOLERANCE_Q,
) -> Tuple[List[Dict[str, Any]], int]:
    if not chord_map or not notes:
        return notes, 0
    
    chord_map_sorted = sorted(chord_map, key=lambda c: float(c.get("time_q", 0)))
    corrected_count = 0
    
    for note in notes:
        if not isinstance(note, dict):
            continue
        
        try:
            start_q = float(note.get("start_q", 0))
            pitch = int(note.get("pitch", 60))
        except (TypeError, ValueError):
            continue
        
        active_chord = get_active_chord_at_time(start_q, chord_map_sorted)
        if not active_chord:
            continue
        
        chord_tones = active_chord.get("chord_tones", [])
        if not chord_tones or not isinstance(chord_tones, list):
            continue
        
        chord_tones_int = []
        for ct in chord_tones:
            try:
                chord_tones_int.append(int(ct) % 12)
            except (TypeError, ValueError):
                continue
        
        if not chord_tones_int:
            continue
        
        pc = pitch % 12
        if pc in chord_tones_int:
            continue
        
        next_chord_time = None
        for chord in chord_map_sorted:
            ct = float(chord.get("time_q", 0))
            if ct > start_q:
                next_chord_time = ct
                break
        
        if next_chord_time is not None and (next_chord_time - start_q) <= tolerance_q:
            next_chord = get_active_chord_at_time(next_chord_time, chord_map_sorted)
            if next_chord:
                next_tones = next_chord.get("chord_tones", [])
                next_tones_int = [int(t) % 12 for t in next_tones if isinstance(t, (int, float))]
                if pc in next_tones_int:
                    continue
        
        new_pitch = find_nearest_chord_tone(pitch, chord_tones_int, direction=0)
        
        if abs_range:
            pitch_low, pitch_high = abs_range
            new_pitch = max(pitch_low, min(pitch_high, new_pitch))
        
        if new_pitch != pitch:
            note["pitch"] = new_pitch
            corrected_count += 1
            logger.debug(
                "Harmony correction: pitch %d -> %d at time_q %.2f (chord %s, tones %s)",
                pitch, new_pitch, start_q, active_chord.get("chord", "?"), chord_tones_int
            )
    
    if corrected_count > 0:
        logger.info("Harmony validation: corrected %d notes to match chord_map", corrected_count)
    
    return notes, corrected_count


def ensure_per_note_dynamics(
    curves: Dict[str, Any],
    notes: List[Dict[str, Any]],
    length_q: float,
    time_sig: str = "4/4",
) -> Dict[str, Any]:
    if not notes:
        return curves

    curves = dict(curves) if curves else {}
    dynamics_curve = curves.get("dynamics", {})
    raw_breakpoints = dynamics_curve.get("breakpoints", [])
    
    time_sig_parts = time_sig.split("/") if time_sig else ["4", "4"]
    try:
        sig_num = int(time_sig_parts[0])
        sig_denom = int(time_sig_parts[1])
        quarters_per_bar = sig_num * (4.0 / sig_denom)
    except (ValueError, IndexError):
        quarters_per_bar = 4.0
    
    existing_breakpoints = []
    for bp in raw_breakpoints:
        if not isinstance(bp, dict):
            continue
        if "time_q" in bp:
            existing_breakpoints.append(bp)
        elif "bar" in bp:
            bar = float(bp.get("bar", 1))
            beat = float(bp.get("beat", 1))
            beat_q = 4.0 / sig_denom if sig_denom > 0 else 1.0
            time_q = (bar - 1) * quarters_per_bar + (beat - 1) * beat_q
            existing_breakpoints.append({"time_q": time_q, "value": bp.get("value", DYNAMICS_BASE_VALUE)})
        else:
            existing_breakpoints.append(bp)

    sustained_notes = [
        n for n in notes
        if isinstance(n, dict) and float(n.get("dur_q", 0)) >= MIN_NOTE_DUR_FOR_DYNAMICS
    ]

    if not sustained_notes:
        return curves

    new_breakpoints = list(existing_breakpoints)

    def count_breakpoints_in_range(start: float, end: float) -> int:
        return sum(
            1 for bp in new_breakpoints
            if start <= float(bp.get("time_q", 0)) <= end
        )

    def has_breakpoint_near(time_q: float) -> bool:
        return any(
            abs(float(bp.get("time_q", 0)) - time_q) <= BREAKPOINT_NEAR_WINDOW_Q
            for bp in new_breakpoints
        )

    for note in sustained_notes:
        start_q = float(note.get("start_q", 0))
        dur_q = float(note.get("dur_q", 1))
        end_q = min(start_q + dur_q, length_q)
        vel = int(note.get("vel", 80))

        min_required = LONG_NOTE_DYNAMICS_POINTS if dur_q >= LONG_NOTE_DUR_FOR_DYNAMICS else MIN_PER_NOTE_DYNAMICS_POINTS
        if count_breakpoints_in_range(start_q, end_q) >= min_required:
            continue

        note_dynamics = int(clamp(vel * 1.0, 40, 127))
        swell_amount = int(DYNAMICS_SWELL_AMOUNT * clamp(vel / 80.0, 0.7, 1.3))

        peak_time = start_q + dur_q * SWELL_PEAK_RATIO
        decay_time = start_q + dur_q * DYNAMICS_DECAY_RATIO
        release_time = start_q + dur_q * DYNAMICS_RELEASE_RATIO

        start_value = int(clamp(note_dynamics - swell_amount * 0.2, 40, 127))
        peak_value = int(clamp(note_dynamics + swell_amount * 0.5, 40, 127))
        decay_value = int(clamp(note_dynamics - swell_amount * 0.4, 40, 127))
        release_value = int(clamp(note_dynamics - swell_amount * 0.3, 40, 127))

        if not has_breakpoint_near(start_q):
            new_breakpoints.append({"time_q": round(start_q, 4), "value": start_value})
        if not has_breakpoint_near(peak_time):
            new_breakpoints.append({"time_q": round(peak_time, 4), "value": peak_value})
        if dur_q >= LONG_NOTE_DUR_FOR_DYNAMICS and not has_breakpoint_near(decay_time):
            new_breakpoints.append({"time_q": round(decay_time, 4), "value": decay_value})
        if not has_breakpoint_near(release_time):
            new_breakpoints.append({"time_q": round(release_time, 4), "value": release_value})

    new_breakpoints.sort(key=lambda x: float(x.get("time_q", 0)))
    new_breakpoints = smooth_breakpoint_transitions(new_breakpoints)

    added_count = len(new_breakpoints) - len(existing_breakpoints)
    if added_count > 0:
        logger.info("Dynamics per-note: added %d breakpoints for %d sustained notes (model had %d)",
                   added_count, len(sustained_notes), len(existing_breakpoints))

    curves["dynamics"] = {
        "interp": dynamics_curve.get("interp", "cubic"),
        "breakpoints": new_breakpoints,
    }

    return curves


def ensure_expression_baseline(
    curves: Dict[str, Any],
    length_q: float,
) -> Dict[str, Any]:
    curves = dict(curves) if curves else {}
    expression_curve = curves.get("expression", {})
    existing_breakpoints = expression_curve.get("breakpoints", [])
    
    if existing_breakpoints:
        return curves
    
    if length_q <= 0:
        return curves

    mid_time = length_q * 0.5
    breakpoints = [
        {"time_q": 0.0, "value": int(EXPRESSION_DEFAULT_MIN)},
        {"time_q": round(mid_time, 4), "value": int(EXPRESSION_DEFAULT_MAX)},
        {"time_q": round(length_q, 4), "value": int(EXPRESSION_DEFAULT_MIN)},
    ]
    
    curves["expression"] = {
        "interp": "cubic",
        "breakpoints": breakpoints,
    }
    
    logger.info("Expression fallback: created %d breakpoints (model had %d)", 
                len(breakpoints), len(existing_breakpoints))
    
    return curves


def get_keyswitch_pitch(data: Dict[str, Any], art_cfg: Dict[str, Any]) -> int:
    pitch = note_to_midi(data.get("pitch"))
    octave_offset = art_cfg.get("octave_offset", 0)
    return pitch + (octave_offset * 12)


def get_articulation_cc_value(data: Dict[str, Any]) -> Optional[int]:
    cc_value = data.get("cc_value")
    if cc_value is not None:
        return int(clamp(int(cc_value), MIDI_MIN, MIDI_MAX))
    return None


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


def parse_bar_beat_string(value: Any) -> Optional[Tuple[int, float]]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = text.split(".")
    if len(parts) < 2:
        return None
    try:
        bar = int(parts[0])
    except ValueError:
        return None
    beat_str = ".".join(parts[1:])
    try:
        beat = float(beat_str)
    except ValueError:
        return None
    return bar, beat


def parse_articulation_change_time(change: Dict[str, Any], time_sig: str) -> Optional[float]:
    if "time_q" in change:
        time_q = safe_float(change.get("time_q"))
        if time_q is not None:
            return time_q
    if "start_q" in change:
        time_q = safe_float(change.get("start_q"))
        if time_q is not None:
            return time_q
    if "time" in change:
        time_q = safe_float(change.get("time"))
        if time_q is not None:
            return time_q

    bar = safe_int(change.get("bar"))
    beat = safe_float(change.get("beat"))
    if bar is not None and beat is not None:
        return bar_beat_to_start_q(bar, beat, time_sig)

    parsed = parse_bar_beat_string(change.get("bar_beat") or change.get("position"))
    if parsed:
        return bar_beat_to_start_q(parsed[0], parsed[1], time_sig)
    return None


def normalize_articulation_changes(raw_changes: Any, time_sig: str) -> List[Dict[str, Any]]:
    if not raw_changes:
        return []
    if isinstance(raw_changes, dict):
        raw_changes = [raw_changes]
    if not isinstance(raw_changes, list):
        return []

    changes: List[Dict[str, Any]] = []
    for change in raw_changes:
        if not isinstance(change, dict):
            continue
        name = change.get("articulation") or change.get("art") or change.get("name")
        if not name:
            continue
        time_q = parse_articulation_change_time(change, time_sig)
        if time_q is None:
            continue
        changes.append({
            "time_q": max(0.0, float(time_q)),
            "articulation": str(name).strip(),
        })

    if not changes:
        return []

    changes.sort(key=lambda c: c["time_q"])
    deduped: List[Dict[str, Any]] = []
    for change in changes:
        if not deduped:
            deduped.append(change)
            continue
        if change["articulation"] == deduped[-1]["articulation"]:
            continue
        deduped.append(change)

    return deduped


def extract_context_cc_events(context: Optional[Any]) -> List[Dict[str, Any]]:
    if not context:
        return []
    if isinstance(context, dict):
        return context.get("cc_events") or []
    return getattr(context, "cc_events", []) or []


def extract_context_horizontal(context: Optional[Any]) -> Optional[Any]:
    if not context:
        return None
    if isinstance(context, dict):
        return context.get("horizontal")
    return getattr(context, "horizontal", None)


def extract_context_existing_notes(context: Optional[Any]) -> List[Dict[str, Any]]:
    if not context:
        return []
    if isinstance(context, dict):
        return context.get("existing_notes") or []
    return getattr(context, "existing_notes", []) or []


def extract_horizontal_notes(horizontal: Optional[Any], key: str) -> List[Dict[str, Any]]:
    if not horizontal:
        return []
    if isinstance(horizontal, dict):
        return horizontal.get(key) or []
    return getattr(horizontal, key, []) or []


def normalize_track_name(value: Any) -> str:
    return str(value or "").strip().lower()


def extract_context_track_names(context: Optional[Any]) -> set[str]:
    if not context:
        return set()
    if isinstance(context, dict):
        tracks = context.get("context_tracks") or []
    else:
        tracks = getattr(context, "context_tracks", []) or []

    names: set[str] = set()
    for track in tracks:
        if isinstance(track, dict):
            name = normalize_track_name(track.get("name") or track.get("track") or track.get("track_name"))
        else:
            name = normalize_track_name(
                getattr(track, "name", None)
                or getattr(track, "track", None)
                or getattr(track, "track_name", None)
            )
        if name:
            names.add(name)
    return names


def pick_context_state(events: List[Tuple[float, str]]) -> Optional[str]:
    if not events:
        return None
    events = sorted(events, key=lambda x: x[0])
    before = [e for e in events if e[0] <= 0]
    if before:
        return before[-1][1]
    return events[0][1]


def detect_context_articulation(profile: Dict[str, Any], context: Optional[Any]) -> Optional[str]:
    if not context:
        return None
    art_cfg = profile.get("articulations", {})
    mode = str(art_cfg.get("mode", "none")).lower()
    art_map = art_cfg.get("map", {})
    if mode == "none" or not isinstance(art_map, dict):
        return None

    if mode == "cc":
        cc_num = safe_int(art_cfg.get("cc_number", DEFAULT_ARTICULATION_CC))
        if cc_num is None:
            return None
        value_to_name: Dict[int, str] = {}
        for name, data in art_map.items():
            if not isinstance(data, dict):
                continue
            raw_val = data.get("cc_value") or data.get("value") or data.get("cc")
            val = safe_int(raw_val)
            if val is not None:
                value_to_name[val] = name
        events: List[Tuple[float, str]] = []
        excluded_tracks = extract_context_track_names(context)
        for evt in extract_context_cc_events(context):
            if not isinstance(evt, dict):
                continue
            if excluded_tracks:
                evt_track = normalize_track_name(evt.get("track") or evt.get("track_name") or evt.get("name"))
                if evt_track and evt_track in excluded_tracks:
                    continue
            cc = safe_int(evt.get("cc") or evt.get("controller"))
            if cc != cc_num:
                continue
            val = safe_int(evt.get("value") or evt.get("val"))
            name = value_to_name.get(val)
            if not name:
                continue
            time_q = safe_float(evt.get("time_q") or evt.get("start_q") or 0.0) or 0.0
            events.append((time_q, name))
        return pick_context_state(events)

    if mode == "keyswitch":
        pitch_to_name: Dict[int, str] = {}
        for name, data in art_map.items():
            if not isinstance(data, dict):
                continue
            pitch = data.get("pitch")
            if pitch is None:
                continue
            try:
                midi_pitch = note_to_midi(pitch)
            except ValueError:
                continue
            pitch_to_name[midi_pitch] = name

        notes: List[Dict[str, Any]] = []
        horizontal = extract_context_horizontal(context)
        if horizontal:
            notes.extend(extract_horizontal_notes(horizontal, "before"))
            notes.extend(extract_horizontal_notes(horizontal, "after"))
        notes.extend(extract_context_existing_notes(context))

        events: List[Tuple[float, str]] = []
        for note in notes:
            pitch = safe_int(note.get("pitch"))
            name = pitch_to_name.get(pitch)
            if not name:
                continue
            time_q = safe_float(note.get("start_q") or 0.0) or 0.0
            events.append((time_q, name))
        return pick_context_state(events)

    return None


def user_requests_articulation_change(user_prompt: str, profile: Dict[str, Any]) -> bool:
    text = str(user_prompt or "").lower()
    if not text:
        return False
    if "articulation" in text or "articulations" in text or "артикуляц" in text:
        return True
    art_cfg = profile.get("articulations", {})
    art_map = art_cfg.get("map", {})
    if not isinstance(art_map, dict):
        return False
    for name in art_map.keys():
        if not name:
            continue
        name_lower = str(name).lower()
        if name_lower in text:
            return True
        if name_lower.replace("_", " ") in text:
            return True
    return False


def get_short_articulations(profile: Dict[str, Any]) -> set[str]:
    art_cfg = profile.get("articulations", {})
    short_list = art_cfg.get("short_articulations") or []
    if short_list:
        return {str(name).lower() for name in short_list}
    art_map = art_cfg.get("map", {})
    if not isinstance(art_map, dict):
        return set()
    return {
        name.lower()
        for name, data in art_map.items()
        if isinstance(data, dict) and data.get("dynamics") == "velocity"
    }


def clamp_wind_brass_durations(notes: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    family = str(profile.get("family", "")).lower()
    if family not in WIND_BRASS_FAMILIES:
        logger.info("clamp_wind_brass: skipping, family=%s not in %s", family, WIND_BRASS_FAMILIES)
        return notes
    
    breath_gap = 0.25
    max_phrase = WIND_BRASS_MAX_NOTE_DUR_Q
    result = []
    long_notes_found = 0
    
    for note in notes:
        if not isinstance(note, dict):
            result.append(note)
            continue
        try:
            dur_q = float(note.get("dur_q", 0))
            start_q = float(note.get("start_q", 0))
        except (TypeError, ValueError):
            result.append(note)
            continue
        
        if dur_q <= max_phrase:
            result.append(note)
            continue
        
        long_notes_found += 1
        pitch = note.get("pitch", 60)
        vel = note.get("vel", 80)
        chan = note.get("chan", 1)
        
        remaining = dur_q
        current_start = start_q
        segment_count = 0
        
        while remaining > 0:
            segment_dur = min(max_phrase, remaining)
            
            if remaining - segment_dur < breath_gap * 2 and remaining <= max_phrase * 1.5:
                segment_dur = remaining
            
            new_note = {
                "start_q": round(current_start, 4),
                "dur_q": round(segment_dur - breath_gap if segment_dur > breath_gap * 2 else segment_dur, 4),
                "pitch": pitch,
                "vel": vel,
                "chan": chan,
            }
            result.append(new_note)
            
            current_start += segment_dur
            remaining -= segment_dur
            segment_count += 1
            
            if segment_count > 20:
                break
        
        if segment_count > 1:
            logger.info("Wind/brass: split %.1fq note into %d segments with breath gaps", dur_q, segment_count)
    
    if long_notes_found > 0:
        logger.info("Wind/brass: processed %d long notes (family=%s)", long_notes_found, family)
    
    return result


def clamp_short_articulation_durations(
    notes: List[Dict[str, Any]],
    profile: Dict[str, Any],
    default_articulation: Optional[str],
) -> None:
    short_articulations = get_short_articulations(profile)
    if not short_articulations:
        return
    for note in notes:
        if not isinstance(note, dict):
            continue
        articulation = note.get("articulation") or default_articulation
        if not articulation:
            continue
        art_lower = str(articulation).lower()
        if art_lower not in short_articulations:
            continue
        try:
            dur_q = float(note.get("dur_q"))
        except (TypeError, ValueError):
            continue
        max_dur = ARTICULATION_MAX_DUR_Q.get(art_lower, SHORT_ARTICULATION_FALLBACK_MAX_Q)
        if dur_q > max_dur:
            note["dur_q"] = max_dur


def clamp_arrangement_note_durations(
    notes: List[Dict[str, Any]],
    time_sig: str,
    source_sketch: Optional[Dict[str, Any]],
) -> None:
    if not notes:
        return

    quarters_per_bar = get_quarters_per_bar(time_sig)
    max_dur_by_bars_q = quarters_per_bar * float(ARRANGEMENT_MAX_NOTE_DUR_BARS)

    sketch_max_dur_q = 0.0
    if source_sketch and isinstance(source_sketch, dict):
        sketch_notes = source_sketch.get("notes", [])
        if isinstance(sketch_notes, list) and sketch_notes:
            for n in sketch_notes:
                if not isinstance(n, dict):
                    continue
                try:
                    dur_q = float(n.get("dur_q", 0.0))
                except (TypeError, ValueError):
                    continue
                if dur_q > sketch_max_dur_q:
                    sketch_max_dur_q = dur_q

    max_allowed_q = min(max_dur_by_bars_q, sketch_max_dur_q) if sketch_max_dur_q > 0 else max_dur_by_bars_q
    if max_allowed_q <= 0:
        return

    for note in notes:
        if not isinstance(note, dict):
            continue
        try:
            dur_q = float(note.get("dur_q", 0.0))
        except (TypeError, ValueError):
            continue
        if dur_q > max_allowed_q:
            note["dur_q"] = max_allowed_q


def resolve_same_pitch_overlaps(notes: List[Dict[str, Any]]) -> None:
    grouped: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for n in notes:
        if not isinstance(n, dict):
            continue
        try:
            pitch = int(n.get("pitch", 60))
            chan = int(n.get("chan", 1))
            start_q = float(n.get("start_q", 0.0))
            dur_q = float(n.get("dur_q", MIN_NOTE_DUR_Q))
        except (TypeError, ValueError):
            continue
        if dur_q <= 0:
            continue
        n["_start_q"] = start_q
        n["_end_q"] = start_q + dur_q
        grouped.setdefault((chan, pitch), []).append(n)

    for group in grouped.values():
        group.sort(key=lambda x: (float(x.get("_start_q", 0.0)), float(x.get("_end_q", 0.0))))
        for i in range(len(group) - 1):
            curr = group[i]
            nxt = group[i + 1]
            curr_start = float(curr.get("_start_q", 0.0))
            curr_end = float(curr.get("_end_q", curr_start))
            next_start = float(nxt.get("_start_q", 0.0))
            max_end = next_start - MIN_NOTE_GAP_Q
            if curr_end > max_end:
                new_dur = max_end - curr_start
                if new_dur <= MIN_NOTE_DUR_Q:
                    curr["dur_q"] = MIN_NOTE_DUR_Q
                else:
                    curr["dur_q"] = new_dur

    for n in notes:
        if isinstance(n, dict):
            n.pop("_start_q", None)
            n.pop("_end_q", None)


CHORD_TIME_THRESHOLD_Q = 0.05


def resolve_melodic_overlaps(notes: List[Dict[str, Any]]) -> None:
    if not notes:
        return
    
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for n in notes:
        if not isinstance(n, dict):
            continue
        try:
            chan = int(n.get("chan", 1))
            start_q = float(n.get("start_q", 0.0))
            dur_q = float(n.get("dur_q", MIN_NOTE_DUR_Q))
        except (TypeError, ValueError):
            continue
        if dur_q <= 0:
            continue
        n["_start_q"] = start_q
        n["_end_q"] = start_q + dur_q
        grouped.setdefault(chan, []).append(n)
    
    for channel_notes in grouped.values():
        channel_notes.sort(key=lambda x: (float(x.get("_start_q", 0.0)), float(x.get("pitch", 60))))
        
        events: List[Tuple[float, List[Dict[str, Any]]]] = []
        current_time: Optional[float] = None
        current_group: List[Dict[str, Any]] = []
        
        for note in channel_notes:
            note_start = float(note.get("_start_q", 0.0))
            if current_time is None or abs(note_start - current_time) > CHORD_TIME_THRESHOLD_Q:
                if current_group:
                    events.append((current_time, current_group))
                current_time = note_start
                current_group = [note]
            else:
                current_group.append(note)
        
        if current_group and current_time is not None:
            events.append((current_time, current_group))
        
        for i in range(len(events) - 1):
            curr_time, curr_notes = events[i]
            next_time, _ = events[i + 1]
            max_end = next_time - MIN_NOTE_GAP_Q
            
            for note in curr_notes:
                note_end = float(note.get("_end_q", 0.0))
                if note_end > max_end:
                    new_dur = max_end - curr_time
                    if new_dur < MIN_NOTE_DUR_Q:
                        new_dur = MIN_NOTE_DUR_Q
                    note["dur_q"] = new_dur
    
    for n in notes:
        if isinstance(n, dict):
            n.pop("_start_q", None)
            n.pop("_end_q", None)


def rearticulate_long_notes(
    notes: List[Dict[str, Any]],
    time_sig: str,
    profile: Dict[str, Any],
    length_q: float,
) -> List[Dict[str, Any]]:
    family = str(profile.get("family", "")).lower()
    if family not in STRINGS_FAMILIES:
        logger.info("rearticulate_long_notes: skipping, family=%s", family)
        return notes

    quarters_per_bar = get_quarters_per_bar(time_sig)
    if quarters_per_bar <= 0:
        logger.info("rearticulate_long_notes: skipping, quarters_per_bar=%s", quarters_per_bar)
        return notes

    max_bow_q = max(MIN_NOTE_DUR_Q, min(quarters_per_bar, quarters_per_bar * float(ARRANGEMENT_MAX_NOTE_DUR_BARS)))
    logger.info("rearticulate_long_notes: processing %d notes, max_bow_q=%.2f", len(notes), max_bow_q)

    out: List[Dict[str, Any]] = []
    for n in notes:
        if not isinstance(n, dict):
            continue
        try:
            start_q = float(n.get("start_q", 0.0))
            dur_q = float(n.get("dur_q", MIN_NOTE_DUR_Q))
        except (TypeError, ValueError):
            continue
        if dur_q <= max_bow_q:
            out.append(n)
            continue

        remaining = dur_q
        curr_start = start_q
        max_iterations = int(dur_q / MIN_NOTE_DUR_Q) + 10
        iteration = 0
        while remaining > MIN_NOTE_DUR_Q and iteration < max_iterations:
            iteration += 1
            seg = min(max_bow_q, remaining)
            if seg <= 0:
                break
            add_gap = remaining > seg and seg > (MIN_NOTE_DUR_Q + MIN_NOTE_GAP_Q)
            if add_gap:
                seg_dur = max(MIN_NOTE_DUR_Q, seg - MIN_NOTE_GAP_Q)
            else:
                seg_dur = max(MIN_NOTE_DUR_Q, seg)

            new_note = dict(n)
            new_note["start_q"] = curr_start
            new_note["dur_q"] = min(seg_dur, max(MIN_NOTE_DUR_Q, length_q - curr_start))
            out.append(new_note)

            curr_start = curr_start + seg
            remaining = dur_q - (curr_start - start_q)
            if curr_start >= length_q - MIN_NOTE_DUR_Q:
                break

    out.sort(key=lambda x: (float(x.get("start_q", 0.0)), int(x.get("pitch", 60))))
    return out


def expand_pattern_notes(raw: Dict[str, Any], time_sig: str = "4/4") -> List[Dict[str, Any]]:
    try:
        from midi_utils import bar_beat_to_start_q, parse_duration
    except ImportError:
        from .midi_utils import bar_beat_to_start_q, parse_duration
    
    patterns = raw.get("patterns", [])
    repeats = raw.get("repeats", [])
    if not isinstance(patterns, list) or not isinstance(repeats, list):
        return []

    try:
        parts = time_sig.split("/")
        num = int(parts[0])
        denom = int(parts[1])
    except (ValueError, IndexError):
        num, denom = 4, 4
    quarters_per_bar = num * (4.0 / denom)

    def get_note_start_q(note: Dict[str, Any]) -> float:
        if "bar" in note and "beat" in note:
            bar = note.get("bar", 1)
            beat = note.get("beat", 1)
            try:
                bar_int = int(bar)
                beat_float = float(beat)
            except (TypeError, ValueError):
                return 0.0
            return (bar_int - 1) * quarters_per_bar + (beat_float - 1) * (4.0 / denom)
        
        if "start_q" in note:
            try:
                return float(note["start_q"])
            except (TypeError, ValueError):
                return 0.0
        if "time_q" in note:
            try:
                return float(note["time_q"])
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def get_note_dur_q(note: Dict[str, Any]) -> float:
        if "dur" in note:
            return parse_duration(note["dur"])
        if "dur_q" in note:
            try:
                return float(note["dur_q"])
            except (TypeError, ValueError):
                return 0.25
        return 0.25

    pattern_map: Dict[str, Dict[str, Any]] = {}
    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue
        pattern_id = str(pattern.get("id") or "").strip()
        notes = pattern.get("notes", [])
        if not pattern_id or not isinstance(notes, list):
            continue
        
        length_q = None
        length_bars = pattern.get("length_bars")
        if length_bars is not None:
            try:
                length_q = float(length_bars) * quarters_per_bar
            except (TypeError, ValueError):
                pass
        
        if length_q is None and "length_q" in pattern:
            try:
                length_q = float(pattern.get("length_q"))
            except (TypeError, ValueError):
                pass
        
        if length_q is None:
            max_end = 0.0
            for note in notes:
                if not isinstance(note, dict):
                    continue
                note_start = get_note_start_q(note)
                dur_q = get_note_dur_q(note)
                end_q = note_start + dur_q
                if end_q > max_end:
                    max_end = end_q
            if max_end > 0:
                length_q = max_end
            else:
                length_q = quarters_per_bar
        
        pattern_map[pattern_id] = {"notes": notes, "length_q": length_q}

    expanded: List[Dict[str, Any]] = []
    for repeat in repeats:
        if not isinstance(repeat, dict):
            continue
        pattern_id = str(repeat.get("pattern") or "").strip()
        pattern_data = pattern_map.get(pattern_id)
        if not pattern_data:
            continue
        times = repeat.get("times")
        if times is None:
            times = repeat.get("count")
        try:
            times = int(times)
        except (TypeError, ValueError):
            continue
        if times <= 0:
            continue
        
        start_q = 0.0
        if "start_bar" in repeat:
            try:
                start_bar = int(repeat["start_bar"])
                start_q = (start_bar - 1) * quarters_per_bar
            except (TypeError, ValueError):
                pass
        elif "start_q" in repeat:
            try:
                start_q = float(repeat["start_q"])
            except (TypeError, ValueError):
                pass
        
        step_q = repeat.get("step_q")
        if step_q is None:
            step_q = pattern_data.get("length_q")
        try:
            step_q = float(step_q)
        except (TypeError, ValueError):
            step_q = quarters_per_bar

        for i in range(times):
            offset = start_q + (i * step_q)
            for note in pattern_data.get("notes", []):
                if not isinstance(note, dict):
                    continue
                note_start = get_note_start_q(note)
                new_note = dict(note)
                new_note["start_q"] = offset + note_start
                for key in ["bar", "beat", "time_q"]:
                    new_note.pop(key, None)
                expanded.append(new_note)

    return expanded


def validate_time_signature(num: Any, denom: Any) -> Tuple[Optional[int], Optional[int]]:
    try:
        num_int = int(num)
        denom_int = int(denom)
    except (TypeError, ValueError):
        return None, None
    if num_int < TIME_SIG_MIN_NUM or num_int > TIME_SIG_MAX_NUM:
        return None, None
    if denom_int not in TIME_SIG_VALID_DENOM:
        return None, None
    return num_int, denom_int


def normalize_tempo_markers(raw_markers: Any, length_q: float) -> List[Dict[str, Any]]:
    if not isinstance(raw_markers, list):
        return []

    length_q = max(0.0, float(length_q or 0.0))
    cleaned: List[Dict[str, Any]] = []
    for marker in raw_markers:
        if not isinstance(marker, dict):
            continue
        time_q = marker.get("time_q", marker.get("start_q", marker.get("time")))
        try:
            time_q = float(time_q)
        except (TypeError, ValueError):
            continue
        time_q = clamp(time_q, 0.0, length_q)

        bpm_raw = marker.get("bpm", marker.get("tempo"))
        bpm: Optional[float] = None
        if bpm_raw is not None:
            try:
                bpm = float(bpm_raw)
                bpm = clamp(bpm, TEMPO_MARKER_MIN_BPM, TEMPO_MARKER_MAX_BPM)
            except (TypeError, ValueError):
                pass

        num_raw = marker.get("num", marker.get("numerator", marker.get("time_sig_num")))
        denom_raw = marker.get("denom", marker.get("denominator", marker.get("time_sig_denom")))
        num, denom = validate_time_signature(num_raw, denom_raw)

        if bpm is None and num is None:
            continue

        linear = bool(marker.get("linear") or marker.get("ramp"))
        entry: Dict[str, Any] = {
            "time_q": round(time_q, 6),
            "linear": linear,
        }
        if bpm is not None:
            entry["bpm"] = round(bpm, 3)
        if num is not None and denom is not None:
            entry["num"] = num
            entry["denom"] = denom
        cleaned.append(entry)

    cleaned.sort(key=lambda m: m["time_q"])

    result: List[Dict[str, Any]] = []
    last_time: Optional[float] = None
    for marker in cleaned:
        if last_time is None or abs(marker["time_q"] - last_time) >= TEMPO_MARKER_MIN_GAP_Q:
            result.append(marker)
            last_time = marker["time_q"]
        if len(result) >= MAX_TEMPO_MARKERS:
            break

    return result


def apply_articulation(
    articulation: Optional[str],
    profile: Dict[str, Any],
    notes: List[Dict[str, Any]],
    default_chan: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    if not articulation:
        return notes, [], [], [], None
    art_cfg = profile.get("articulations", {})
    mode = art_cfg.get("mode", "none")
    art_map = art_cfg.get("map", {})
    data = art_map.get(articulation)
    if not data:
        return notes, [], [], [], articulation

    if mode == "keyswitch":
        try:
            pitch = get_keyswitch_pitch(data, art_cfg)
        except ValueError:
            return notes, [], [], [], articulation
        vel = int(clamp(int(data.get("vel", DEFAULT_KEYSWITCH_VELOCITY)), MIDI_VEL_MIN, MIDI_MAX))
        chan = normalize_channel(data.get("chan"), default_chan)
        return (
            notes,
            [{"time_q": 0.0, "pitch": pitch, "vel": vel, "chan": chan, "dur_q": KEYSWITCH_DUR_Q}],
            [],
            [],
            articulation,
        )
    if mode == "cc":
        cc_num = int(art_cfg.get("cc_number", DEFAULT_ARTICULATION_CC))
        cc_value = get_articulation_cc_value(data)
        if cc_value is not None:
            chan = normalize_channel(data.get("chan"), default_chan)
            cc_event = {"time_q": 0.0, "cc": cc_num, "value": cc_value, "chan": chan}
            return notes, [], [], [cc_event], articulation
        return notes, [], [], [], articulation
    if mode == "program_change":
        program = int(clamp(int(data.get("program", 0)), MIDI_MIN, MIDI_MAX))
        chan = normalize_channel(data.get("chan"), default_chan)
        return notes, [], [{"time_q": 0.0, "program": program, "chan": chan}], [], articulation
    if mode == "channel":
        chan = normalize_channel(data.get("chan") or data.get("channel"), default_chan)
        for note in notes:
            note["chan"] = chan
        return notes, [], [], [], articulation
    return notes, [], [], [], articulation


def resolve_articulation_data(
    name: str,
    art_map: Dict[str, Any],
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    if name in art_map:
        data = art_map.get(name)
        return name, data if isinstance(data, dict) else None
    name_lower = str(name).lower()
    for key, data in art_map.items():
        if str(key).lower() == name_lower and isinstance(data, dict):
            return key, data
    return None, None


def apply_articulation_changes(
    changes: List[Dict[str, Any]],
    profile: Dict[str, Any],
    notes: List[Dict[str, Any]],
    default_chan: int,
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    Optional[str],
    List[Dict[str, Any]],
]:
    if not changes:
        return notes, [], [], [], None, []

    art_cfg = profile.get("articulations", {})
    mode = str(art_cfg.get("mode", "none")).lower()
    art_map = art_cfg.get("map", {})
    if mode == "none" or not isinstance(art_map, dict) or not art_map:
        return notes, [], [], [], None, []

    keyswitches: List[Dict[str, Any]] = []
    program_changes: List[Dict[str, Any]] = []
    articulation_cc: List[Dict[str, Any]] = []
    applied_changes: List[Dict[str, Any]] = []

    if mode == "channel":
        for change in changes:
            name = change.get("articulation")
            if not name:
                continue
            resolved, data = resolve_articulation_data(str(name), art_map)
            if not data:
                continue
            chan = normalize_channel(data.get("chan") or data.get("channel"), default_chan)
            for note in notes:
                note["chan"] = chan
            applied_changes.append({"time_q": change.get("time_q", 0.0), "articulation": resolved})
            break
    else:
        for change in changes:
            name = change.get("articulation")
            if not name:
                continue
            resolved, data = resolve_articulation_data(str(name), art_map)
            if not data:
                continue
            time_q = float(change.get("time_q", 0.0))
            if mode == "keyswitch":
                try:
                    pitch = get_keyswitch_pitch(data, art_cfg)
                except ValueError:
                    continue
                vel = int(clamp(int(data.get("vel", data.get("velocity_on", DEFAULT_KEYSWITCH_VELOCITY))), MIDI_VEL_MIN, MIDI_MAX))
                chan = normalize_channel(data.get("chan"), default_chan)
                ks_time = max(0.0, time_q - ARTICULATION_PRE_ROLL_Q)
                keyswitches.append({
                    "time_q": ks_time,
                    "pitch": pitch,
                    "vel": vel,
                    "chan": chan,
                    "dur_q": KEYSWITCH_DUR_Q,
                })
            elif mode == "cc":
                cc_value = get_articulation_cc_value(data)
                if cc_value is None:
                    continue
                cc_num = int(art_cfg.get("cc_number", DEFAULT_ARTICULATION_CC))
                chan = normalize_channel(data.get("chan"), default_chan)
                cc_time = max(0.0, time_q - ARTICULATION_PRE_ROLL_Q)
                articulation_cc.append({
                    "time_q": cc_time,
                    "cc": cc_num,
                    "value": cc_value,
                    "chan": chan,
                })
            elif mode == "program_change":
                program = int(clamp(int(data.get("program", 0)), MIDI_MIN, MIDI_MAX))
                chan = normalize_channel(data.get("chan"), default_chan)
                program_changes.append({
                    "time_q": time_q,
                    "program": program,
                    "chan": chan,
                })
            applied_changes.append({"time_q": time_q, "articulation": resolved})

    art_name: Optional[str] = None
    if applied_changes:
        unique = {c.get("articulation", "").lower() for c in applied_changes if c.get("articulation")}
        if len(unique) == 1:
            art_name = applied_changes[0].get("articulation")
        else:
            art_name = "mixed"

    return notes, keyswitches, program_changes, articulation_cc, art_name, applied_changes


def apply_per_note_articulations(
    notes: List[Dict[str, Any]],
    profile: Dict[str, Any],
    default_chan: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    art_cfg = profile.get("articulations", {})
    mode = art_cfg.get("mode", "none")
    art_map = art_cfg.get("map", {})

    if mode == "none" or not art_map:
        return notes, [], [], []

    notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    keyswitches: List[Dict[str, Any]] = []
    program_changes: List[Dict[str, Any]] = []
    articulation_cc: List[Dict[str, Any]] = []
    current_articulation: Optional[str] = None

    for note in notes:
        note_art = note.pop("articulation", None)
        if note_art and note_art != current_articulation:
            data = art_map.get(note_art)
            if data:
                handled = False
                
                if mode == "cc" or "cc_value" in data:
                    cc_value = get_articulation_cc_value(data)
                    if cc_value is not None:
                        cc_num = int(art_cfg.get("cc_number", DEFAULT_ARTICULATION_CC))
                        chan = normalize_channel(data.get("chan"), default_chan)
                        cc_time = max(0.0, note["start_q"] - ARTICULATION_PRE_ROLL_Q)
                        articulation_cc.append({
                            "time_q": cc_time,
                            "cc": cc_num,
                            "value": cc_value,
                            "chan": chan,
                        })
                        handled = True
                
                if not handled and (mode == "keyswitch" or "keyswitch" in data):
                    try:
                        pitch = get_keyswitch_pitch(data, art_cfg)
                        vel = int(clamp(int(data.get("vel", data.get("velocity_on", DEFAULT_KEYSWITCH_VELOCITY))), MIDI_VEL_MIN, MIDI_MAX))
                        chan = normalize_channel(data.get("chan"), default_chan)
                        ks_time = max(0.0, note["start_q"] - ARTICULATION_PRE_ROLL_Q)
                        keyswitches.append({
                            "time_q": ks_time,
                            "pitch": pitch,
                            "vel": vel,
                            "chan": chan,
                            "dur_q": KEYSWITCH_DUR_Q,
                        })
                        handled = True
                    except ValueError:
                        pass
                
                if not handled and mode == "program_change":
                    program = int(clamp(int(data.get("program", 0)), MIDI_MIN, MIDI_MAX))
                    chan = normalize_channel(data.get("chan"), default_chan)
                    program_changes.append({
                        "time_q": note["start_q"],
                        "program": program,
                        "chan": chan,
                    })
                    handled = True
                
                if not handled and mode == "channel":
                    chan = normalize_channel(data.get("chan") or data.get("channel"), default_chan)
                    note["chan"] = chan
                
                current_articulation = note_art

    return notes, keyswitches, program_changes, articulation_cc


def make_keyswitches_legato(
    keyswitches: List[Dict[str, Any]],
    length_q: float,
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    art_cfg = profile.get("articulations", {})
    if not art_cfg.get("send_keyswitch_on_every_change", False):
        return keyswitches
    
    if not keyswitches:
        return keyswitches
    
    keyswitches = sorted(keyswitches, key=lambda ks: ks.get("time_q", 0.0))
    
    for i, ks in enumerate(keyswitches):
        if i < len(keyswitches) - 1:
            next_ks = keyswitches[i + 1]
            ks["dur_q"] = max(MIN_NOTE_DUR_Q, next_ks["time_q"] - ks["time_q"])
        else:
            ks["dur_q"] = max(MIN_NOTE_DUR_Q, length_q - ks["time_q"])
    
    return keyswitches


def extract_handoff(
    raw: Dict[str, Any],
    notes: List[Dict[str, Any]],
    length_q: float,
    role: str = "",
) -> Optional[Dict[str, Any]]:
    raw_handoff = raw.get("handoff")
    if raw_handoff and isinstance(raw_handoff, dict):
        return validate_and_fix_handoff(raw_handoff, notes, length_q)
    return generate_synthetic_handoff(notes, role, length_q)


def build_response(
    raw: Dict[str, Any],
    profile: Dict[str, Any],
    length_q: float,
    free_mode: bool = False,
    allow_tempo_changes: bool = False,
    context: Optional[Any] = None,
    user_prompt: str = "",
    extract_motif: bool = False,
    source_instrument: str = "",
    is_ensemble: bool = False,
    current_role: str = "",
    time_sig: str = "4/4",
    arrangement_mode: bool = False,
    source_sketch: Optional[Dict[str, Any]] = None,
    forced_articulation: Optional[str] = None,
    chord_map: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    midi_cfg = profile.get("midi", {})
    default_chan = int(midi_cfg.get("channel", 1))
    mono = str(midi_cfg.get("polyphony", "poly")).lower() == "mono"
    is_drum = bool(midi_cfg.get("is_drum", False))
    abs_range = parse_range(profile.get("range", {}).get("absolute"))
    fix_policy = profile.get("fix_policy", "octave_shift_to_fit")

    notes_raw = raw.get("notes", [])
    if not isinstance(notes_raw, list):
        notes_raw = []

    pattern_notes = expand_pattern_notes(raw, time_sig)
    if pattern_notes:
        notes_raw = notes_raw + pattern_notes

    if free_mode:
        lock_articulation = detect_context_articulation(profile, context)
        if lock_articulation and not user_requests_articulation_change(user_prompt, profile):
            for note in notes_raw:
                if isinstance(note, dict):
                    note.pop("articulation", None)
            raw["articulation"] = lock_articulation
            raw["articulation_changes"] = [{"time_q": 0.0, "articulation": lock_articulation}]

    articulation_changes = normalize_articulation_changes(raw.get("articulation_changes"), time_sig)
    if articulation_changes:
        if articulation_changes[0]["time_q"] > 0:
            articulation_changes.insert(0, {
                "time_q": 0.0,
                "articulation": articulation_changes[0]["articulation"],
            })
        for note in notes_raw:
            if isinstance(note, dict):
                note.pop("articulation", None)
                note.pop("art", None)

    if notes_raw:
        clamp_short_articulation_durations(notes_raw, profile, raw.get("articulation"))
        if arrangement_mode:
            clamp_arrangement_note_durations(notes_raw, time_sig, source_sketch)

    has_per_note_articulations = any(
        isinstance(n, dict) and (n.get("articulation") or n.get("art")) for n in notes_raw
    )

    logger.info("build_response: normalizing %d notes", len(notes_raw))
    notes = normalize_notes(notes_raw, length_q, default_chan, abs_range, fix_policy, mono, time_sig)
    logger.info("build_response: normalized to %d notes", len(notes))
    
    notes = clamp_wind_brass_durations(notes, profile)
    
    normalized_chord_map = normalize_chord_map_for_validation(chord_map, time_sig)
    if normalized_chord_map and not is_drum:
        notes, harmony_corrections = validate_notes_against_harmony(notes, normalized_chord_map, abs_range)
        if harmony_corrections > 0:
            logger.info("build_response: harmony validation corrected %d notes", harmony_corrections)
    
    if not is_drum:
        logger.info("build_response: resolve_same_pitch_overlaps")
        resolve_same_pitch_overlaps(notes)
        logger.info("build_response: resolve_melodic_overlaps")
        resolve_melodic_overlaps(notes)
    
    if arrangement_mode:
        logger.info("build_response: rearticulate_long_notes")
        notes = rearticulate_long_notes(notes, time_sig, profile, length_q)
        logger.info("build_response: rearticulated to %d notes", len(notes))

    if is_drum:
        drums_raw = raw.get("drums", [])
        drum_map = midi_cfg.get("drum_map", {})
        notes.extend(normalize_drums(drums_raw, drum_map, length_q, default_chan))

    curves_raw = raw.get("curves", {})
    curves_raw = ensure_per_note_dynamics(curves_raw, notes, length_q, time_sig)
    curves_raw = ensure_expression_baseline(curves_raw, length_q)
    cc_events = build_cc_events(curves_raw, profile, length_q, default_chan, time_sig)

    articulation_cc: List[Dict[str, Any]] = []

    if articulation_changes:
        notes, keyswitches, program_changes, articulation_cc, art_name, applied_changes = apply_articulation_changes(
            articulation_changes, profile, notes, default_chan
        )
        articulation_changes = applied_changes
    elif has_per_note_articulations:
        for idx, note_raw in enumerate(notes_raw):
            if isinstance(note_raw, dict) and idx < len(notes):
                art = note_raw.get("articulation") or note_raw.get("art")
                if art:
                    notes[idx]["articulation"] = art
        notes, keyswitches, program_changes, articulation_cc = apply_per_note_articulations(
            notes, profile, default_chan
        )
        art_name = "mixed"
    else:
        articulation = forced_articulation if forced_articulation else raw.get("articulation")
        notes, keyswitches, program_changes, articulation_cc, art_name = apply_articulation(
            articulation, profile, notes, default_chan
        )

    all_cc_events = articulation_cc + cc_events

    keyswitches = make_keyswitches_legato(keyswitches, length_q, profile)

    response = {
        "notes": notes,
        "cc_events": all_cc_events,
        "keyswitches": keyswitches,
        "program_changes": program_changes,
        "articulation": art_name,
        "generation_type": raw.get("generation_type"),
        "generation_style": raw.get("generation_style"),
    }
    if articulation_changes:
        response["articulation_changes"] = articulation_changes

    if allow_tempo_changes:
        tempo_markers = normalize_tempo_markers(raw.get("tempo_markers"), length_q)
        if tempo_markers:
            response["tempo_markers"] = tempo_markers

    if extract_motif and notes and not is_drum:
        motif = extract_motif_from_notes(notes, max_notes=8, source_instrument=source_instrument)
        if motif:
            response["extracted_motif"] = motif

    if is_ensemble:
        handoff = extract_handoff(raw, notes, length_q, current_role)
        if handoff:
            response["handoff"] = handoff

    return response
