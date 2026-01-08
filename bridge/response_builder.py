from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import (
        ARTICULATION_PRE_ROLL_Q,
        DEFAULT_ARTICULATION_CC,
        DEFAULT_KEYSWITCH_VELOCITY,
        KEYSWITCH_DUR_Q,
        MIDI_MAX,
        MIDI_MIN,
        MIDI_VEL_MIN,
    )
    from curve_utils import build_cc_events
    from midi_utils import (
        normalize_channel,
        normalize_drums,
        normalize_notes,
        note_to_midi,
        parse_range,
    )
    from utils import clamp
except ImportError:
    from .constants import (
        ARTICULATION_PRE_ROLL_Q,
        DEFAULT_ARTICULATION_CC,
        DEFAULT_KEYSWITCH_VELOCITY,
        KEYSWITCH_DUR_Q,
        MIDI_MAX,
        MIDI_MIN,
        MIDI_VEL_MIN,
    )
    from .curve_utils import build_cc_events
    from .midi_utils import (
        normalize_channel,
        normalize_drums,
        normalize_notes,
        note_to_midi,
        parse_range,
    )
    from .utils import clamp


def get_keyswitch_pitch(data: Dict[str, Any], art_cfg: Dict[str, Any]) -> int:
    pitch = note_to_midi(data.get("pitch"))
    octave_offset = art_cfg.get("octave_offset", 0)
    return pitch + (octave_offset * 12)


def get_articulation_cc_value(data: Dict[str, Any]) -> Optional[int]:
    cc_value = data.get("cc_value")
    if cc_value is not None:
        return int(clamp(int(cc_value), MIDI_MIN, MIDI_MAX))
    return None


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


def build_response(
    raw: Dict[str, Any],
    profile: Dict[str, Any],
    length_q: float,
    free_mode: bool = False,
) -> Dict[str, Any]:
    midi_cfg = profile.get("midi", {})
    default_chan = int(midi_cfg.get("channel", 1))
    mono = str(midi_cfg.get("polyphony", "poly")).lower() == "mono"
    is_drum = bool(midi_cfg.get("is_drum", False))
    abs_range = parse_range(profile.get("range", {}).get("absolute"))
    fix_policy = profile.get("fix_policy", "octave_shift_to_fit")

    notes_raw = raw.get("notes", [])

    has_per_note_articulations = free_mode and any(
        isinstance(n, dict) and n.get("articulation") for n in notes_raw
    )

    notes = normalize_notes(notes_raw, length_q, default_chan, abs_range, fix_policy, mono)

    if is_drum:
        drums_raw = raw.get("drums", [])
        drum_map = midi_cfg.get("drum_map", {})
        notes.extend(normalize_drums(drums_raw, drum_map, length_q, default_chan))

    curves_raw = raw.get("curves", {})
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

    return {
        "notes": notes,
        "cc_events": all_cc_events,
        "keyswitches": keyswitches,
        "program_changes": program_changes,
        "articulation": art_name,
        "generation_type": raw.get("generation_type"),
        "generation_style": raw.get("generation_style"),
    }
