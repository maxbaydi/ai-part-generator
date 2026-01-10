from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
        normalize_channel,
        normalize_drums,
        normalize_notes,
        note_to_midi,
        parse_range,
    )
    from music_analysis import extract_motif_from_notes
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
        normalize_channel,
        normalize_drums,
        normalize_notes,
        note_to_midi,
        parse_range,
    )
    from .music_analysis import extract_motif_from_notes
    from .utils import clamp


MIN_NOTE_DUR_FOR_DYNAMICS = 1.0
SWELL_PEAK_RATIO = 0.35
DYNAMICS_BASE_VALUE = 60
DYNAMICS_SWELL_AMOUNT = 25


def ensure_per_note_dynamics(
    curves: Dict[str, Any],
    notes: List[Dict[str, Any]],
    length_q: float,
) -> Dict[str, Any]:
    if not notes:
        return curves

    curves = dict(curves) if curves else {}
    dynamics_curve = curves.get("dynamics", {})
    existing_breakpoints = dynamics_curve.get("breakpoints", [])

    sustained_notes = [
        n for n in notes
        if isinstance(n, dict) and float(n.get("dur_q", 0)) >= MIN_NOTE_DUR_FOR_DYNAMICS
    ]

    if not sustained_notes:
        return curves

    def count_breakpoints_in_range(start: float, end: float) -> int:
        count = 0
        for bp in existing_breakpoints:
            t = float(bp.get("time_q", 0))
            if start <= t <= end:
                count += 1
        return count

    def get_value_at_time(t: float) -> float:
        if not existing_breakpoints:
            return DYNAMICS_BASE_VALUE
        sorted_bps = sorted(existing_breakpoints, key=lambda x: float(x.get("time_q", 0)))
        for i, bp in enumerate(sorted_bps):
            bp_time = float(bp.get("time_q", 0))
            if bp_time >= t:
                if i == 0:
                    return float(bp.get("value", DYNAMICS_BASE_VALUE))
                prev_bp = sorted_bps[i - 1]
                prev_t = float(prev_bp.get("time_q", 0))
                prev_v = float(prev_bp.get("value", DYNAMICS_BASE_VALUE))
                curr_v = float(bp.get("value", DYNAMICS_BASE_VALUE))
                if bp_time == prev_t:
                    return curr_v
                ratio = (t - prev_t) / (bp_time - prev_t)
                return prev_v + (curr_v - prev_v) * ratio
        if sorted_bps:
            return float(sorted_bps[-1].get("value", DYNAMICS_BASE_VALUE))
        return DYNAMICS_BASE_VALUE

    new_breakpoints = list(existing_breakpoints)
    
    for note in sustained_notes:
        start_q = float(note.get("start_q", 0))
        dur_q = float(note.get("dur_q", 1))
        end_q = min(start_q + dur_q, length_q)
        vel = int(note.get("vel", 80))
        
        bp_count = count_breakpoints_in_range(start_q, end_q)
        min_required = 2 if dur_q < 2.0 else (3 if dur_q < 4.0 else 4)
        
        if bp_count >= min_required:
            continue
        
        base_value = get_value_at_time(start_q)
        vel_factor = vel / 80.0
        swell_amount = int(DYNAMICS_SWELL_AMOUNT * vel_factor)
        
        peak_time = start_q + dur_q * SWELL_PEAK_RATIO
        settle_time = start_q + dur_q * 0.6
        
        start_value = int(clamp(base_value - 5, MIDI_MIN, MIDI_MAX))
        peak_value = int(clamp(base_value + swell_amount, MIDI_MIN, MIDI_MAX))
        settle_value = int(clamp(base_value + swell_amount * 0.6, MIDI_MIN, MIDI_MAX))
        end_value = int(clamp(base_value - 2, MIDI_MIN, MIDI_MAX))
        
        new_breakpoints.append({"time_q": round(start_q, 4), "value": start_value})
        new_breakpoints.append({"time_q": round(peak_time, 4), "value": peak_value})
        
        if dur_q >= 2.0:
            new_breakpoints.append({"time_q": round(settle_time, 4), "value": settle_value})
        
        if dur_q >= 3.0:
            new_breakpoints.append({"time_q": round(end_q - 0.1, 4), "value": end_value})

    new_breakpoints.sort(key=lambda x: float(x.get("time_q", 0)))
    
    curves["dynamics"] = {
        "interp": dynamics_curve.get("interp", "cubic"),
        "breakpoints": new_breakpoints,
    }
    
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


def clamp_wind_brass_durations(notes: List[Dict[str, Any]], profile: Dict[str, Any]) -> None:
    family = str(profile.get("family", "")).lower()
    if family not in WIND_BRASS_FAMILIES:
        return
    for note in notes:
        if not isinstance(note, dict):
            continue
        try:
            dur_q = float(note.get("dur_q", 0))
        except (TypeError, ValueError):
            continue
        if dur_q > WIND_BRASS_MAX_NOTE_DUR_Q:
            note["dur_q"] = WIND_BRASS_MAX_NOTE_DUR_Q


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


def expand_pattern_notes(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    patterns = raw.get("patterns", [])
    repeats = raw.get("repeats", [])
    if not isinstance(patterns, list) or not isinstance(repeats, list):
        return []

    pattern_map: Dict[str, Dict[str, Any]] = {}
    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue
        pattern_id = str(pattern.get("id") or "").strip()
        notes = pattern.get("notes", [])
        if not pattern_id or not isinstance(notes, list):
            continue
        length_q = None
        if "length_q" in pattern:
            try:
                length_q = float(pattern.get("length_q"))
            except (TypeError, ValueError):
                length_q = None
        if length_q is None:
            max_end = None
            for note in notes:
                if not isinstance(note, dict):
                    continue
                try:
                    start_q = float(note.get("start_q", note.get("time_q", 0.0)))
                    dur_q = float(note.get("dur_q", 0.0))
                except (TypeError, ValueError):
                    continue
                end_q = start_q + dur_q
                if max_end is None or end_q > max_end:
                    max_end = end_q
            if max_end is not None:
                length_q = max_end
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
        try:
            start_q = float(repeat.get("start_q", 0.0))
        except (TypeError, ValueError):
            start_q = 0.0
        step_q = repeat.get("step_q")
        if step_q is None:
            step_q = pattern_data.get("length_q")
        try:
            step_q = float(step_q)
        except (TypeError, ValueError):
            step_q = None
        if step_q is None:
            continue

        for i in range(times):
            offset = start_q + (i * step_q)
            for note in pattern_data.get("notes", []):
                if not isinstance(note, dict):
                    continue
                try:
                    note_start = float(note.get("start_q", note.get("time_q", 0.0)))
                except (TypeError, ValueError):
                    note_start = 0.0
                new_note = dict(note)
                new_note["start_q"] = offset + note_start
                if "time_q" in new_note:
                    new_note.pop("time_q", None)
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
                if mode == "keyswitch":
                    try:
                        pitch = get_keyswitch_pitch(data, art_cfg)
                        vel = int(clamp(int(data.get("vel", DEFAULT_KEYSWITCH_VELOCITY)), MIDI_VEL_MIN, MIDI_MAX))
                        chan = normalize_channel(data.get("chan"), default_chan)
                        ks_time = max(0.0, note["start_q"] - ARTICULATION_PRE_ROLL_Q)
                        keyswitches.append({
                            "time_q": ks_time,
                            "pitch": pitch,
                            "vel": vel,
                            "chan": chan,
                            "dur_q": KEYSWITCH_DUR_Q,
                        })
                    except ValueError:
                        pass
                elif mode == "cc":
                    cc_num = int(art_cfg.get("cc_number", DEFAULT_ARTICULATION_CC))
                    cc_value = get_articulation_cc_value(data)
                    if cc_value is not None:
                        chan = normalize_channel(data.get("chan"), default_chan)
                        cc_time = max(0.0, note["start_q"] - ARTICULATION_PRE_ROLL_Q)
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
                        "time_q": note["start_q"],
                        "program": program,
                        "chan": chan,
                    })
                elif mode == "channel":
                    chan = normalize_channel(data.get("chan") or data.get("channel"), default_chan)
                    note["chan"] = chan
                current_articulation = note_art

    return notes, keyswitches, program_changes, articulation_cc


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

    pattern_notes = expand_pattern_notes(raw)
    if pattern_notes:
        notes_raw = notes_raw + pattern_notes

    if free_mode:
        lock_articulation = detect_context_articulation(profile, context)
        if lock_articulation and not user_requests_articulation_change(user_prompt, profile):
            for note in notes_raw:
                if isinstance(note, dict):
                    note.pop("articulation", None)
            raw["articulation"] = lock_articulation

    if notes_raw:
        clamp_short_articulation_durations(notes_raw, profile, raw.get("articulation"))
        clamp_wind_brass_durations(notes_raw, profile)
        if arrangement_mode:
            clamp_arrangement_note_durations(notes_raw, time_sig, source_sketch)

    has_per_note_articulations = free_mode and any(
        isinstance(n, dict) and n.get("articulation") for n in notes_raw
    )

    logger.info("build_response: normalizing %d notes", len(notes_raw))
    notes = normalize_notes(notes_raw, length_q, default_chan, abs_range, fix_policy, mono)
    logger.info("build_response: normalized to %d notes", len(notes))
    if arrangement_mode:
        logger.info("build_response: resolve_same_pitch_overlaps")
        resolve_same_pitch_overlaps(notes)
        logger.info("build_response: rearticulate_long_notes")
        notes = rearticulate_long_notes(notes, time_sig, profile, length_q)
        logger.info("build_response: rearticulated to %d notes", len(notes))

    if is_drum:
        drums_raw = raw.get("drums", [])
        drum_map = midi_cfg.get("drum_map", {})
        notes.extend(normalize_drums(drums_raw, drum_map, length_q, default_chan))

    curves_raw = raw.get("curves", {})
    curves_raw = ensure_per_note_dynamics(curves_raw, notes, length_q)
    cc_events = build_cc_events(curves_raw, profile, length_q, default_chan)

    articulation_cc: List[Dict[str, Any]] = []

    if has_per_note_articulations:
        for idx, note_raw in enumerate(notes_raw):
            if isinstance(note_raw, dict) and idx < len(notes):
                art = note_raw.get("articulation")
                if art:
                    notes[idx]["articulation"] = art
        notes, keyswitches, program_changes, articulation_cc = apply_per_note_articulations(
            notes, profile, default_chan
        )
        art_name = "mixed"
    else:
        articulation = raw.get("articulation")
        notes, keyswitches, program_changes, articulation_cc, art_name = apply_articulation(
            articulation, profile, notes, default_chan
        )

    all_cc_events = articulation_cc + cc_events

    response = {
        "notes": notes,
        "cc_events": all_cc_events,
        "keyswitches": keyswitches,
        "program_changes": program_changes,
        "articulation": art_name,
        "generation_type": raw.get("generation_type"),
        "generation_style": raw.get("generation_style"),
    }

    if allow_tempo_changes:
        tempo_markers = normalize_tempo_markers(raw.get("tempo_markers"), length_q)
        if tempo_markers:
            response["tempo_markers"] = tempo_markers

    if extract_motif and notes and not is_drum:
        motif = extract_motif_from_notes(notes, max_notes=8, source_instrument=source_instrument)
        if motif:
            response["extracted_motif"] = motif

    if is_ensemble and free_mode:
        handoff = extract_handoff(raw, notes, length_q, current_role)
        if handoff:
            response["handoff"] = handoff

    return response
