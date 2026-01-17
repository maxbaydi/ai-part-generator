from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from constants import (
        ARRANGEMENT_MAX_NOTE_DUR_BARS,
        DEFAULT_PITCH,
        DEFAULT_VELOCITY,
        MIDI_CHAN_MAX,
        MIDI_CHAN_MIN,
        MIDI_MAX,
        MIDI_MIN,
    )
    from context_builder import get_quarters_per_bar
    from music_theory import pitch_to_note
    from prompt_builder_common import UNKNOWN_VALUE
    from promts import ARRANGEMENT_GENERATION_CONTEXT
except ImportError:
    from .constants import (
        ARRANGEMENT_MAX_NOTE_DUR_BARS,
        DEFAULT_PITCH,
        DEFAULT_VELOCITY,
        MIDI_CHAN_MAX,
        MIDI_CHAN_MIN,
        MIDI_MAX,
        MIDI_MIN,
    )
    from .context_builder import get_quarters_per_bar
    from .music_theory import pitch_to_note
    from .prompt_builder_common import UNKNOWN_VALUE
    from .promts import ARRANGEMENT_GENERATION_CONTEXT


SKETCH_NOTES_LIMIT = 1000
SKETCH_NOTES_PREVIEW = 200
SKETCH_CC_EVENTS_LIMIT = 200

DEFAULT_NOTE_DUR_Q = 1.0
DEFAULT_START_Q = 0.0
DEFAULT_CC_CONTROLLER = -1
DEFAULT_CC_VALUE = 0
DEFAULT_BAR_INDEX = 1
DEFAULT_BEAT_OFFSET = 1.0
NOTE_PREVIEW_PRECISION = 1
DEFAULT_TIME_SIGNATURE = "4/4"
DEFAULT_LENGTH_Q = 16.0
DEFAULT_SKETCH_TRACK_NAME = "Sketch"
DEFAULT_ARRANGEMENT_ROLE = UNKNOWN_VALUE
DEFAULT_MATERIAL_SOURCE = "Extract appropriate material from sketch"
DEFAULT_ADAPTATION_NOTES = "Adapt to instrument idiom"
DEFAULT_VERBATIM_LEVEL = "medium"
DEFAULT_REGISTER_ADJUSTMENT = "none"


def format_sketch_notes(
    notes: List[Dict[str, Any]],
    time_sig: str = DEFAULT_TIME_SIGNATURE,
    limit: int = SKETCH_NOTES_LIMIT,
) -> str:
    if not notes:
        return "(no notes)"

    sorted_notes = sorted(notes, key=lambda n: (n.get("start_q", DEFAULT_START_Q), -n.get("pitch", DEFAULT_PITCH)))
    limited = sorted_notes[:limit]

    quarters_per_bar = get_quarters_per_bar(time_sig)

    lines = ["```"]
    lines.append("time_q | bar.beat | pitch | note | dur_q | vel | chan")
    lines.append("-------|----------|-------|------|-------|-----|-----")

    for note in limited:
        start_q = note.get("start_q", DEFAULT_START_Q)
        pitch = note.get("pitch", DEFAULT_PITCH)
        dur_q = note.get("dur_q", DEFAULT_NOTE_DUR_Q)
        vel = note.get("vel", DEFAULT_VELOCITY)
        chan = note.get("chan", MIDI_CHAN_MIN)
        note_name = pitch_to_note(pitch)
        bar = int(float(start_q) // quarters_per_bar) + DEFAULT_BAR_INDEX if quarters_per_bar > 0 else DEFAULT_BAR_INDEX
        beat_q = (float(start_q) % quarters_per_bar) + DEFAULT_BEAT_OFFSET if quarters_per_bar > 0 else DEFAULT_BEAT_OFFSET
        bar_beat = f"{bar}.{beat_q:.2f}"
        lines.append(
            f"{float(start_q):6.2f} | {bar_beat:8} | {int(pitch):5} | {note_name:4} | {float(dur_q):5.2f} | {int(vel):3} | {int(chan):3}"
        )

    lines.append("```")

    if len(sorted_notes) > limit:
        lines.append(f"... and {len(sorted_notes) - limit} more notes")

    return "\n".join(lines)


def format_sketch_notes_compact(notes: List[Dict[str, Any]], limit: int = SKETCH_NOTES_PREVIEW) -> str:
    if not notes:
        return "(no notes)"

    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", DEFAULT_START_Q))
    limited = sorted_notes[:limit]

    entries = []
    for note in limited:
        start_q = note.get("start_q", DEFAULT_START_Q)
        pitch = note.get("pitch", DEFAULT_PITCH)
        note_name = pitch_to_note(pitch)
        entries.append(f"{start_q:.{NOTE_PREVIEW_PRECISION}f}:{note_name}")

    result = ", ".join(entries)
    if len(sorted_notes) > limit:
        result += f" ...({len(sorted_notes)} total)"

    return result


def format_sketch_cc_segments(
    cc_events: List[Dict[str, Any]],
    length_q: float,
    limit: int = SKETCH_CC_EVENTS_LIMIT,
) -> Tuple[str, str]:
    if not cc_events:
        return "(no cc events)", "(none)"

    events: List[Dict[str, Any]] = []
    controllers: set[int] = set()

    for evt in cc_events[:limit]:
        if not isinstance(evt, dict):
            continue
        try:
            time_q = float(evt.get("time_q", evt.get("start_q", DEFAULT_START_Q)))
            cc = int(evt.get("cc", evt.get("controller", DEFAULT_CC_CONTROLLER)))
            value = int(evt.get("value", evt.get("val", DEFAULT_CC_VALUE)))
            chan = int(evt.get("chan", MIDI_CHAN_MIN))
        except (TypeError, ValueError):
            continue
        if cc < MIDI_MIN or cc > MIDI_MAX:
            continue
        controllers.add(cc)
        events.append(
            {
                "time_q": max(DEFAULT_START_Q, time_q),
                "cc": cc,
                "value": max(MIDI_MIN, min(MIDI_MAX, value)),
                "chan": max(MIDI_CHAN_MIN, min(MIDI_CHAN_MAX, chan)),
            }
        )

    if not events:
        return "(no cc events)", "(none)"

    events.sort(key=lambda e: (e["cc"], e["chan"], e["time_q"], e["value"]))

    by_key: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for e in events:
        by_key.setdefault((e["cc"], e["chan"]), []).append(e)

    lines = ["```"]
    for (cc, chan) in sorted(by_key.keys()):
        group = sorted(by_key[(cc, chan)], key=lambda e: e["time_q"])
        lines.append(f"CC{cc} ch{chan}")
        lines.append("start_q | end_q | dur_q | value")
        lines.append("--------|-------|-------|------")
        for idx, e in enumerate(group):
            start_q = float(e["time_q"])
            if idx + 1 < len(group):
                end_q = float(group[idx + 1]["time_q"])
            else:
                end_q = float(length_q)
            if end_q < start_q:
                end_q = start_q
            dur_q = end_q - start_q
            lines.append(f"{start_q:7.3f} | {end_q:5.3f} | {dur_q:5.3f} | {int(e['value']):4}")
        lines.append("")
    lines.append("```")

    controllers_str = ", ".join(f"CC{cc}" for cc in sorted(controllers))
    return "\n".join(lines), controllers_str


def build_arrangement_context(
    ensemble: Any,
    current_profile_name: str,
    time_sig: str = DEFAULT_TIME_SIGNATURE,
    length_q: float = DEFAULT_LENGTH_Q,
) -> str:
    if not ensemble or not ensemble.arrangement_mode:
        return ""

    source_sketch = ensemble.source_sketch
    if not source_sketch or not isinstance(source_sketch, dict):
        return ""

    sketch_notes = source_sketch.get("notes", [])
    sketch_track_name = source_sketch.get("track_name", DEFAULT_SKETCH_TRACK_NAME)
    sketch_cc_events = source_sketch.get("cc_events", [])
    assignment = ensemble.arrangement_assignment or {}

    role = assignment.get("role", DEFAULT_ARRANGEMENT_ROLE)
    material_source = assignment.get("material_source", DEFAULT_MATERIAL_SOURCE)
    adaptation_notes = assignment.get("adaptation_notes", DEFAULT_ADAPTATION_NOTES)
    verbatim_level = assignment.get("verbatim_level", DEFAULT_VERBATIM_LEVEL)
    register_adjustment = assignment.get("register_adjustment", DEFAULT_REGISTER_ADJUSTMENT)

    quarters_per_bar = get_quarters_per_bar(time_sig)
    max_dur_by_bars_q = quarters_per_bar * ARRANGEMENT_MAX_NOTE_DUR_BARS
    sketch_max_dur_q = DEFAULT_START_Q
    if isinstance(sketch_notes, list) and sketch_notes:
        for n in sketch_notes:
            if not isinstance(n, dict):
                continue
            try:
                dur_q = float(n.get("dur_q", DEFAULT_START_Q))
            except (TypeError, ValueError):
                continue
            if dur_q > sketch_max_dur_q:
                sketch_max_dur_q = dur_q
    arrangement_max_dur_q = (
        min(max_dur_by_bars_q, sketch_max_dur_q)
        if sketch_max_dur_q > DEFAULT_START_Q else max_dur_by_bars_q
    )

    cc_formatted, cc_controllers = format_sketch_cc_segments(
        sketch_cc_events if isinstance(sketch_cc_events, list) else [],
        length_q,
    )

    context = ARRANGEMENT_GENERATION_CONTEXT.format(
        source_track_name=sketch_track_name,
        note_count=len(sketch_notes),
        sketch_notes_formatted=format_sketch_notes(sketch_notes, time_sig),
        sketch_cc_formatted=cc_formatted,
        sketch_cc_controllers=cc_controllers,
        sketch_max_dur_q=round(sketch_max_dur_q, 3) if sketch_max_dur_q > DEFAULT_START_Q else UNKNOWN_VALUE,
        arrangement_max_dur_q=round(arrangement_max_dur_q, 3),
        role=role,
        material_source=material_source,
        adaptation_notes=adaptation_notes,
        verbatim_level=verbatim_level,
        register_adjustment=register_adjustment or DEFAULT_REGISTER_ADJUSTMENT,
    )

    return context
