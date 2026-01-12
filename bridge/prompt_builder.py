from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import (
        CUSTOM_CURVE_EXCLUSIONS,
        DEFAULT_GENERATION_STYLE,
        DEFAULT_GENERATION_TYPE,
        DEFAULT_PROMPT_PITCH_HIGH,
        DEFAULT_PROMPT_PITCH_LOW,
        PROMPT_PITCH_PREVIEW_LIMIT,
    )
    from context_builder import (
        analyze_harmony_progression,
        build_chord_map_from_sketch,
        build_context_summary,
        build_ensemble_context,
        get_quarters_per_bar,
    )
    from models import ArrangeRequest, GenerateRequest
    from music_theory import detect_key_from_chords, get_scale_note_names, get_scale_notes, pitch_to_note
    from promts import (
        ARRANGEMENT_GENERATION_CONTEXT,
        ARRANGEMENT_PLAN_SYSTEM_PROMPT,
        BASE_SYSTEM_PROMPT,
        COMPOSITION_PLAN_SYSTEM_PROMPT,
        FREE_MODE_SYSTEM_PROMPT,
    )
    from style import DYNAMICS_HINTS, MOOD_HINTS
    from type import ARTICULATION_HINTS, TYPE_HINTS
    from utils import safe_format
except ImportError:
    from .constants import (
        CUSTOM_CURVE_EXCLUSIONS,
        DEFAULT_GENERATION_STYLE,
        DEFAULT_GENERATION_TYPE,
        DEFAULT_PROMPT_PITCH_HIGH,
        DEFAULT_PROMPT_PITCH_LOW,
        PROMPT_PITCH_PREVIEW_LIMIT,
    )
    from .context_builder import (
        analyze_harmony_progression,
        build_chord_map_from_sketch,
        build_context_summary,
        build_ensemble_context,
        get_quarters_per_bar,
    )
    from .models import ArrangeRequest, GenerateRequest
    from .music_theory import detect_key_from_chords, get_scale_note_names, get_scale_notes, pitch_to_note
    from .promts import (
        ARRANGEMENT_GENERATION_CONTEXT,
        ARRANGEMENT_PLAN_SYSTEM_PROMPT,
        BASE_SYSTEM_PROMPT,
        COMPOSITION_PLAN_SYSTEM_PROMPT,
        FREE_MODE_SYSTEM_PROMPT,
    )
    from .style import DYNAMICS_HINTS, MOOD_HINTS
    from .type import ARTICULATION_HINTS, TYPE_HINTS
    from .utils import safe_format

def build_generation_progress(ensemble: Any, current_profile_name: str) -> str:
    if not ensemble or not ensemble.is_sequential:
        return ""
    
    instruments = ensemble.instruments or []
    previously_generated = ensemble.previously_generated or []
    generation_order = ensemble.generation_order or 1
    
    completed_names = [p.get("profile_name") or p.get("track_name") or "?" for p in previously_generated]
    
    remaining = []
    for inst in instruments:
        inst_name = inst.profile_name or inst.track_name or ""
        if inst.index > generation_order and inst_name not in completed_names:
            remaining.append(inst_name)
    
    lines = ["### GENERATION PROGRESS"]
    lines.append(f"Step {generation_order} of {len(instruments)}")
    
    if completed_names:
        lines.append(f"Completed: {', '.join(completed_names)}")
    
    lines.append(f"Current: {current_profile_name}")
    
    if remaining:
        lines.append(f"Remaining: {', '.join(remaining)}")
    
    lines.append("")
    lines.append("You have full context of what was generated above.")
    lines.append("Make musical decisions based on the style/genre and what you see.")
    
    return "\n".join(lines)


def extract_role_from_plan(plan: Optional[Dict[str, Any]], instrument_name: str, track_name: str = "") -> str:
    if not plan or not isinstance(plan, dict):
        return "unknown"
    
    role_guidance = plan.get("role_guidance", [])
    if not isinstance(role_guidance, list):
        return "unknown"
    
    instrument_lower = instrument_name.lower().strip()
    track_lower = track_name.lower().strip()
    
    for entry in role_guidance:
        if not isinstance(entry, dict):
            continue
        entry_instrument = str(entry.get("instrument", "")).lower().strip()
        if not entry_instrument:
            continue
        if entry_instrument == instrument_lower or entry_instrument == track_lower:
            role = entry.get("role", "")
            if role:
                return str(role)
    
    return "unknown"


def extract_key_from_chord_map(chord_map: Optional[List[Dict[str, Any]]]) -> str:
    if not chord_map or not isinstance(chord_map, list) or not chord_map:
        return "unknown"
    
    first_chord = chord_map[0]
    if not isinstance(first_chord, dict):
        return "unknown"
    
    chord_name = first_chord.get("chord", "")
    if not chord_name:
        return "unknown"
    
    chord_str = str(chord_name).strip()
    
    root_map = {
        "C": "C", "C#": "C#", "Db": "Db", "D": "D", "D#": "D#", "Eb": "Eb",
        "E": "E", "F": "F", "F#": "F#", "Gb": "Gb", "G": "G", "G#": "G#",
        "Ab": "Ab", "A": "A", "A#": "A#", "Bb": "Bb", "B": "B",
    }
    
    root = ""
    for r in ["C#", "Db", "D#", "Eb", "F#", "Gb", "G#", "Ab", "A#", "Bb", "C", "D", "E", "F", "G", "A", "B"]:
        if chord_str.startswith(r):
            root = root_map.get(r, r)
            suffix = chord_str[len(r):].lower()
            break
    
    if not root:
        return "unknown"
    
    if "m" in suffix and "maj" not in suffix:
        return f"{root} minor"
    return f"{root} major"


def bar_to_time_q(bar: int, time_sig: str = "4/4") -> float:
    try:
        parts = time_sig.split("/")
        num = int(parts[0])
        denom = int(parts[1])
    except (ValueError, IndexError):
        num, denom = 4, 4
    quarters_per_bar = num * (4.0 / denom)
    return (bar - 1) * quarters_per_bar


def bars_range_to_time_q(bars_str: str, time_sig: str = "4/4") -> Tuple[float, float]:
    try:
        if "-" in bars_str:
            parts = bars_str.split("-")
            start_bar = int(parts[0])
            end_bar = int(parts[1])
        else:
            start_bar = int(bars_str)
            end_bar = start_bar
    except (ValueError, IndexError):
        return 0.0, 0.0
    
    start_q = bar_to_time_q(start_bar, time_sig)
    end_q = bar_to_time_q(end_bar + 1, time_sig)
    return start_q, end_q


def get_chord_tones_from_name(chord_name: str) -> List[int]:
    chord_name = chord_name.strip()
    if not chord_name:
        return []
    
    root_map = {
        "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
        "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
        "A": 9, "A#": 10, "Bb": 10, "B": 11,
    }
    
    root_pc = 0
    suffix = chord_name
    for root in ["C#", "Db", "D#", "Eb", "F#", "Gb", "G#", "Ab", "A#", "Bb", "C", "D", "E", "F", "G", "A", "B"]:
        if chord_name.startswith(root):
            root_pc = root_map[root]
            suffix = chord_name[len(root):]
            break
    
    suffix_lower = suffix.lower()
    
    if "maj7" in suffix_lower or "maj9" in suffix_lower:
        intervals = [0, 4, 7, 11]
    elif "m7b5" in suffix_lower or "ø" in suffix:
        intervals = [0, 3, 6, 10]
    elif "dim7" in suffix_lower or "°7" in suffix:
        intervals = [0, 3, 6, 9]
    elif "dim" in suffix_lower or "°" in suffix:
        intervals = [0, 3, 6]
    elif "aug" in suffix_lower or "+" in suffix:
        intervals = [0, 4, 8]
    elif "sus4" in suffix_lower:
        intervals = [0, 5, 7]
    elif "sus2" in suffix_lower:
        intervals = [0, 2, 7]
    elif "add9" in suffix_lower:
        intervals = [0, 4, 7, 14]
    elif "add" in suffix_lower and "11" in suffix_lower:
        intervals = [0, 4, 7, 17]
    elif "m9" in suffix_lower:
        intervals = [0, 3, 7, 10, 14]
    elif "9" in suffix_lower and "m" not in suffix_lower:
        intervals = [0, 4, 7, 10, 14]
    elif "m7" in suffix_lower or "min7" in suffix_lower:
        intervals = [0, 3, 7, 10]
    elif "7" in suffix_lower:
        intervals = [0, 4, 7, 10]
    elif suffix_lower.startswith("m") or "min" in suffix_lower:
        intervals = [0, 3, 7]
    else:
        intervals = [0, 4, 7]
    
    return [(root_pc + i) % 12 for i in intervals]


def estimate_note_count(length_q: float, bpm: float, time_sig: str, generation_type: str) -> Tuple[int, int, str]:
    """Estimate recommended note count based on musical context."""
    try:
        sig_parts = time_sig.split("/")
        beats_per_bar = int(sig_parts[0])
        beat_unit = int(sig_parts[1])
    except (ValueError, IndexError):
        beats_per_bar = 4
        beat_unit = 4

    quarters_per_bar = beats_per_bar * (4.0 / beat_unit)
    bars = length_q / quarters_per_bar if quarters_per_bar > 0 else length_q / 4
    bars = max(1, bars)

    gen_type_lower = generation_type.lower()

    if "melody" in gen_type_lower:
        notes_per_bar_min = 2
        notes_per_bar_max = 8
        density_desc = "moderate melodic density with varied rhythms"
    elif "arpeggio" in gen_type_lower:
        notes_per_bar_min = 8
        notes_per_bar_max = 16
        density_desc = "continuous arpeggiated pattern"
    elif "bass" in gen_type_lower:
        notes_per_bar_min = 1
        notes_per_bar_max = 4
        density_desc = "sparse but rhythmically strong bass notes"
    elif "chord" in gen_type_lower:
        notes_per_bar_min = 1
        notes_per_bar_max = 4
        density_desc = "chord changes, multiple simultaneous notes per chord"
    elif "pad" in gen_type_lower or "sustain" in gen_type_lower:
        notes_per_bar_min = 0.5
        notes_per_bar_max = 2
        density_desc = "long sustained notes with smooth transitions"
    elif "rhythm" in gen_type_lower:
        notes_per_bar_min = 4
        notes_per_bar_max = 16
        density_desc = "rhythmic pattern with clear pulse"
    elif "counter" in gen_type_lower:
        notes_per_bar_min = 2
        notes_per_bar_max = 6
        density_desc = "independent melodic line that complements the main melody"
    elif "accomp" in gen_type_lower:
        notes_per_bar_min = 2
        notes_per_bar_max = 8
        density_desc = "supportive accompaniment pattern"
    else:
        notes_per_bar_min = 2
        notes_per_bar_max = 8
        density_desc = "appropriate musical content"

    min_notes = max(1, int(bars * notes_per_bar_min))
    max_notes = max(min_notes + 1, int(bars * notes_per_bar_max))

    return min_notes, max_notes, density_desc


def format_profile_user_template(template: str, values: Dict[str, Any]) -> str:
    if not template:
        return ""
    return safe_format(template, values)


def get_custom_curves_info(profile: Dict[str, Any]) -> Tuple[List[str], str]:
    controllers = profile.get("controllers", {})
    semantic_to_cc = controllers.get("semantic_to_cc", controllers)
    custom_curves = [k for k in semantic_to_cc.keys() if k not in CUSTOM_CURVE_EXCLUSIONS and isinstance(semantic_to_cc[k], int)]
    if not custom_curves:
        return custom_curves, ""
    curves_info = ", ".join([f"curves.{k} (CC{semantic_to_cc[k]})" for k in custom_curves])
    return custom_curves, curves_info


def format_profile_for_prompt(profile: Dict[str, Any]) -> str:
    lines = []
    
    name = profile.get("name", "Unknown")
    range_info = profile.get("range", {})
    preferred = range_info.get("preferred", [])
    lines.append(f"INSTRUMENT: {name}")
    if preferred:
        lines.append(f"RANGE: {preferred[0]} - {preferred[1]}")
    
    midi = profile.get("midi", {})
    polyphony = midi.get("polyphony", "poly")
    lines.append(f"POLYPHONY: {polyphony}")
    
    controllers = profile.get("controllers", {})
    semantic_to_cc = controllers.get("semantic_to_cc", controllers)
    cc_list = []
    for k, v in semantic_to_cc.items():
        if isinstance(v, int):
            cc_list.append(f"{k}=CC{v}")
    if cc_list:
        lines.append(f"CONTROLLERS: {', '.join(cc_list)}")
    
    art = profile.get("articulations", {})
    mode = art.get("mode", "none")
    art_map = art.get("map", {})
    
    legato = profile.get("legato", {})
    if legato and not art_map.get("legato"):
        art_map = dict(art_map)
        art_map["legato"] = legato
    
    if mode == "cc" and art_map:
        cc_num = art.get("cc_number")
        lines.append(f"ARTICULATIONS (CC{cc_num}):")
        for art_name, data in art_map.items():
            if not isinstance(data, dict):
                continue
            cc_val = data.get("cc_value")
            if cc_val is not None:
                desc = data.get("description", art_name)
                dynamics = data.get("dynamics", "")
                dyn_str = f" [{dynamics}]" if dynamics else ""
                lines.append(f"  {art_name}: {cc_val} - {desc}{dyn_str}")
            elif data.get("velocity_on"):
                ks = data.get("keyswitch", "")
                lines.append(f"  {art_name}: keyswitch {ks} (vel_on={data['velocity_on']}, vel_off={data.get('velocity_off', 1)})")
    
    elif mode == "keyswitch" and art_map:
        lines.append("ARTICULATIONS (keyswitch):")
        for art_name, data in art_map.items():
            if not isinstance(data, dict):
                continue
            ks = data.get("keyswitch") or data.get("pitch")
            desc = data.get("description", art_name)
            if data.get("velocity_on"):
                lines.append(f"  {art_name}: {ks} (vel_on={data['velocity_on']}, vel_off={data.get('velocity_off', 1)})")
            else:
                lines.append(f"  {art_name}: {ks} - {desc}")
    
    elif midi.get("is_drum"):
        drum_map = midi.get("drum_map", {})
        if drum_map or art_map:
            lines.append("DRUM MAP:")
            source = art_map if art_map else drum_map
            for drum_name, data in source.items():
                if isinstance(data, dict):
                    pitch = data.get("pitch")
                else:
                    pitch = data
                lines.append(f"  {drum_name}: {pitch}")
    
    elif legato:
        ks = legato.get("keyswitch", "")
        vel_on = legato.get("velocity_on", 100)
        vel_off = legato.get("velocity_off", 1)
        lines.append(f"LEGATO: keyswitch {ks} (vel_on={vel_on}, vel_off={vel_off})")
    
    return "\n".join(lines)


def resolve_prompt_pitch_range(pref_range: Any) -> Tuple[int, int]:
    pitch_low = DEFAULT_PROMPT_PITCH_LOW
    pitch_high = DEFAULT_PROMPT_PITCH_HIGH
    if pref_range and isinstance(pref_range, list) and len(pref_range) == 2:
        try:
            from midi_utils import note_to_midi
        except ImportError:
            from .midi_utils import note_to_midi
        try:
            pitch_low = note_to_midi(pref_range[0])
            pitch_high = note_to_midi(pref_range[1])
        except ValueError:
            pass
    return pitch_low, pitch_high


ARTICULATION_DURATION_HINTS = {
    "spiccato": "dur_q: 0.25-0.5, bouncy detached",
    "staccatissimo": "dur_q: 0.125-0.25, very short crisp",
    "staccato": "dur_q: 0.25-0.5, short separated",
    "pizzicato": "dur_q: 0.25-0.5, plucked short",
    "col_legno": "dur_q: 0.25-0.5, short wooden",
    "bartok_snap": "dur_q: 0.25, percussive snap",
    "sforzando": "dur_q: 0.5-1.0, accented attack",
    "marcato": "dur_q: 0.5-1.0, marked accent",
}

DEFAULT_QUARTERS_PER_BAR = 4.0

def infer_key_from_plan_chord_map(chord_map: Any) -> str:
    if not isinstance(chord_map, list) or not chord_map:
        return "unknown"
    roots: List[int] = []
    for entry in chord_map:
        if not isinstance(entry, dict):
            continue
        tones = entry.get("chord_tones")
        if not isinstance(tones, list) or not tones:
            continue
        try:
            root_pc = int(tones[0]) % 12
        except (TypeError, ValueError):
            continue
        roots.append(root_pc)
    return detect_key_from_chords(roots)


def build_orchestration_hints_prompt(profile: Dict[str, Any], is_ensemble: bool = False) -> str:
    hints = profile.get("orchestration_hints", {})
    if not hints:
        return ""

    lines = ["### ORCHESTRATION GUIDANCE (recommendations for this instrument)"]

    character = hints.get("character", "")
    if character:
        lines.append(f"**Character:** {character}")

    typical_roles = hints.get("typical_roles", [])
    if typical_roles:
        lines.append(f"**Typical roles:** {', '.join(typical_roles)}")

    best_for = hints.get("best_for", [])
    if best_for:
        lines.append("**Best suited for:**")
        for item in best_for[:5]:
            lines.append(f"  - {item}")

    register_char = hints.get("register_character", {})
    if register_char:
        lines.append("**Register characteristics:**")
        for reg, desc in register_char.items():
            lines.append(f"  - {reg}: {desc}")

    if is_ensemble:
        ensemble_tips = hints.get("ensemble_tips", [])
        if ensemble_tips:
            lines.append("**Ensemble tips:**")
            for tip in ensemble_tips[:5]:
                lines.append(f"  - {tip}")

    texture_options = hints.get("texture_options", [])
    if texture_options:
        lines.append("**Texture options:**")
        for option in texture_options[:5]:
            lines.append(f"  - {option}")

    avoid = hints.get("avoid", [])
    if avoid:
        lines.append("**Avoid:**")
        for item in avoid:
            lines.append(f"  - {item}")

    solo_mode = hints.get("solo_mode", {})
    if solo_mode and not is_ensemble:
        lines.append("**Solo mode guidance:**")
        if solo_mode.get("description"):
            lines.append(f"  {solo_mode['description']}")
        if solo_mode.get("left_hand"):
            lines.append(f"  LEFT HAND: {solo_mode['left_hand']}")
        if solo_mode.get("right_hand"):
            lines.append(f"  RIGHT HAND: {solo_mode['right_hand']}")

    lines.append("")
    lines.append("Note: These are recommendations. User prompt may override these suggestions.")

    return "\n".join(lines)


def build_articulation_list_for_prompt(profile: Dict[str, Any]) -> str:
    art_cfg = profile.get("articulations", {})
    art_map = art_cfg.get("map", {})
    if not art_map:
        return "No articulations available"

    short_arts = []
    long_arts = []

    for name, data in sorted(art_map.items()):
        desc = data.get("description", name)
        dynamics_type = data.get("dynamics", "cc1")
        dur_hint = ARTICULATION_DURATION_HINTS.get(name, "")
        if dynamics_type == "velocity":
            if dur_hint:
                short_arts.append(f"  - {name}: {desc} ({dur_hint})")
            else:
                short_arts.append(f"  - {name}: {desc}")
        else:
            long_arts.append(f"  - {name}: {desc}")

    result_parts = []
    if long_arts:
        result_parts.append("LONG articulations (dynamics via Dynamics curve, use longer dur_q 1.0+):")
        result_parts.extend(long_arts)
    if short_arts:
        result_parts.append("SHORT articulations (dynamics via velocity, use short dur_q as specified):")
        result_parts.extend(short_arts)

    return "\n".join(result_parts)


def build_pattern_guidance(profile: Dict[str, Any], generation_type: str, bars: int) -> List[str]:
    is_drum = bool(profile.get("midi", {}).get("is_drum", False))
    family = str(profile.get("family", "")).lower()
    gen_lower = str(generation_type or "").lower()

    is_percussion_family = family in ("drums", "percussion", "perc")
    is_repetitive_type = any(t in gen_lower for t in ("ostinato", "rhythm", "accomp", "arpeggio", "bass"))

    try:
        bars_int = int(bars)
    except (TypeError, ValueError):
        bars_int = 0

    if not (is_drum or is_percussion_family or is_repetitive_type or bars_int >= 4):
        return []

    lines = ["### PATTERN CLONING (use for repetitive content)"]

    if is_drum or is_percussion_family:
        lines.extend([
            "⚠️ DRUMS/PERCUSSION: You MUST use patterns/repeats for grooves!",
            "DO NOT duplicate the same notes bar after bar manually.",
            "",
            "EXAMPLE for drum groove:",
            '  "patterns": [{"id": "groove", "length_q": 4, "notes": [...one bar of notes...]}],',
            '  "repeats": [{"pattern": "groove", "start_q": 0, "times": N, "step_q": 4}],',
            '  "notes": []  // empty - all notes come from patterns',
        ])
    elif is_repetitive_type:
        lines.extend([
            "For repetitive figures (ostinatos, arpeggios, bass lines) - USE patterns/repeats!",
            "Define the pattern once, then repeat it. Much more efficient than duplicating notes.",
            "",
            'EXAMPLE: "patterns": [{"id": "ost", "length_q": 2, "notes": [...]}],',
            '         "repeats": [{"pattern": "ost", "start_q": 0, "times": 16, "step_q": 2}]',
        ])
    else:
        lines.extend([
            f"For {bars_int} bars - consider using patterns/repeats if your figure repeats.",
            "This keeps JSON compact and ensures consistent timing.",
        ])

    return lines


def build_tempo_change_guidance(request: GenerateRequest, length_q: float) -> List[str]:
    if not request.allow_tempo_changes:
        return []

    if request.ensemble and request.ensemble.is_sequential:
        plan = request.ensemble.plan or {}
        initial_bpm = plan.get("initial_bpm")
        
        if initial_bpm:
            return [
                "### TEMPO/TIME SIGNATURE",
                f"Tempo is set by the composition plan: {initial_bpm} BPM",
                "DO NOT output tempo_markers - tempo changes are controlled by the plan.",
            ]
        
        generation_order = int(request.ensemble.generation_order or 0)
        if generation_order > 1:
            return [
                "### TEMPO/TIME SIGNATURE CHANGES",
                "Tempo and time signature changes are already defined by an earlier part.",
                "DO NOT output tempo_markers for this response.",
            ]

    length_hint = round(float(length_q or 0.0), 2)
    current_bpm = request.music.bpm
    current_time_sig = request.music.time_sig
    lines = [
        "### TEMPO & TIME SIGNATURE CONTROL (YOUR CREATIVE CHOICE)",
        f"Project default: {current_bpm} BPM, {current_time_sig}",
        "",
        "YOU MAY CHANGE the initial tempo if it doesn't fit the style/mood you're creating.",
        "The project tempo is just a starting point - override it if musically appropriate.",
        "",
        "YOUR OPTIONS:",
        "- OVERRIDE initial tempo (time_q: 0) - set what fits the mood/genre",
        "- ADD tempo changes for dramatic effect (accelerando, ritardando)",
        "- CHANGE time signature when needed (3/4 waltz, 6/8 compound, mixed meter)",
        "",
        "FORMAT: tempo_markers: [{\"time_q\": 0, \"bpm\": 85, \"num\": 3, \"denom\": 4}, ...]",
        "",
        "FIELDS:",
        f"- time_q: position in quarter notes (0..{length_hint})",
        "- bpm: tempo in beats per minute (REQUIRED at time_q=0 to set initial tempo)",
        "- num/denom: time signature (e.g. num:6, denom:8 for 6/8)",
        "- linear: true for gradual tempo ramp, false for instant change",
        "",
        "EXAMPLES:",
        "- Set tempo: [{\"time_q\": 0, \"bpm\": 72}]",
        "- Set tempo + time sig: [{\"time_q\": 0, \"bpm\": 90, \"num\": 6, \"denom\": 8}]",
        "- Accelerando: [{\"time_q\": 0, \"bpm\": 60}, {\"time_q\": 24, \"bpm\": 100, \"linear\": true}]",
        "- Ritardando at end: [{\"time_q\": 0, \"bpm\": 120}, {\"time_q\": 48, \"bpm\": 80, \"linear\": true}]",
        "",
        "COMMON TIME SIGNATURES: 4/4, 3/4, 2/4, 6/8, 12/8, 5/4, 7/8",
        "Keep markers in ascending order. Max 4-6 markers.",
    ]
    if request.ensemble and request.ensemble.is_sequential:
        lines.append("")
        lines.append("IMPORTANT: Only output tempo_markers for the FIRST instrument in sequential generation.")
    return lines


def build_selection_info(length_q: float, quarters_per_bar: float, bars: int) -> List[str]:
    length_q = max(0.0, float(length_q or 0.0))
    length_hint = round(length_q, 3)

    return [
        "### SELECTION (working area)",
        f"- Available range: {bars} bars (start_q 0 to {length_hint} quarter notes)",
        "- Time axis: notes use start_q, curves use time_q (quarter notes from selection start)",
        "- How much of this range to fill is YOUR creative decision based on user request and context",
        "- RECOMMENDATION: Plan the musical development (intro, theme, resolution) to fit within the available range",
        "- Consider using the full selection for complete compositions; shorter portions for fragments or phrases",
        "- Patterns/repeats can help keep JSON concise for repeating figures",
    ]


def build_prompt(
    request: GenerateRequest,
    profile: Dict[str, Any],
    preset_name: Optional[str],
    preset_settings: Dict[str, Any],
    length_q: float,
) -> Tuple[str, str]:
    profile_ai = profile.get("ai", {})
    profile_system = profile_ai.get("system_prompt_template", "")
    profile_user = profile_ai.get("user_prompt_template", "")
    profile_range = profile.get("range", {})
    abs_range = profile_range.get("absolute")
    pref_range = profile_range.get("preferred")

    ensemble = request.ensemble
    is_arrangement_mode = bool(ensemble and ensemble.arrangement_mode)
    plan_data = ensemble.plan if (ensemble and isinstance(ensemble.plan, dict)) else {}
    plan_chord_map = plan_data.get("chord_map") if isinstance(plan_data, dict) else None
    has_plan_chord_map = isinstance(plan_chord_map, list) and len(plan_chord_map) > 0
    is_compose_ensemble = bool(
        ensemble
        and not is_arrangement_mode
        and ((ensemble.plan_summary or "").strip() or has_plan_chord_map)
    )

    if request.free_mode:
        generation_type = ""
        min_notes, max_notes = 1, 999
    else:
        generation_type = request.generation_type or DEFAULT_GENERATION_TYPE
        min_notes, max_notes, _ = estimate_note_count(
            length_q, request.music.bpm, request.music.time_sig, generation_type
        )

    values = {
        "profile_name": profile.get("name", ""),
        "profile_id": profile.get("id", ""),
        "family": profile.get("family", ""),
        "bpm": request.music.bpm,
        "time_sig": request.music.time_sig,
        "key": request.music.key,
        "selection_quarters": round(length_q, 4),
        "range_absolute": abs_range,
        "range_preferred": pref_range,
        "preset_name": preset_name or "",
        "preset_settings": json.dumps(preset_settings, ensure_ascii=False),
        "polyphony": profile.get("midi", {}).get("polyphony", ""),
        "is_drum": profile.get("midi", {}).get("is_drum", False),
        "channel": profile.get("midi", {}).get("channel", 1),
        "generation_type": generation_type,
        "min_notes": min_notes,
        "max_notes": max_notes,
    }

    profile_user_formatted = format_profile_user_template(profile_user, values)
    custom_curves, custom_curves_info = get_custom_curves_info(profile)

    midi_channel = profile.get("midi", {}).get("channel", 1)
    pitch_low, pitch_high = resolve_prompt_pitch_range(pref_range)

    articulation = preset_settings.get("articulation", "legato")
    articulation_hint = ARTICULATION_HINTS.get(articulation.lower(), "") if articulation else ""

    if request.free_mode:
        generation_style = ""
        type_hint = ""
        mood_hint = ""
        dynamics_hint = ""
    else:
        generation_style = request.generation_style or DEFAULT_GENERATION_STYLE
        style_lower = generation_style.lower()
        # Default if not found in dictionary
        mood_hint = MOOD_HINTS.get(style_lower, f"STYLE: {generation_style}. CHARACTER: Create a part in this style.")

        # Check if DYNAMICS_HINTS has specific entry, otherwise use default
        dynamics_hint = DYNAMICS_HINTS.get(
            style_lower,
            DYNAMICS_HINTS.get("default", "EXPRESSION: Follow phrase shape. DYNAMICS: Natural breathing.")
        )

    if request.free_mode:
        system_parts = [
            FREE_MODE_SYSTEM_PROMPT,
            safe_format(profile_system, values),
        ]
    else:
        system_parts = [
            BASE_SYSTEM_PROMPT,
            safe_format(profile_system, values),
        ]
    system_prompt = "\n\n".join([p for p in system_parts if p])

    skip_auto_harmony = is_arrangement_mode or has_plan_chord_map

    context_summary, detected_key, _position = build_context_summary(
        request.context, request.music.time_sig, length_q, request.music.key,
        skip_auto_harmony=skip_auto_harmony,
    )

    final_key = request.music.key
    if final_key == "unknown" and detected_key != "unknown":
        final_key = detected_key
    if final_key == "unknown" and has_plan_chord_map:
        inferred_key = extract_key_from_chord_map(plan_chord_map)
        if inferred_key == "unknown":
            inferred_key = infer_key_from_plan_chord_map(plan_chord_map)
        if inferred_key != "unknown":
            final_key = inferred_key

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(1, int(length_q / quarters_per_bar))
    selection_info = build_selection_info(length_q, quarters_per_bar, bars)

    if has_plan_chord_map:
        valid_pitches = list(range(pitch_low, pitch_high + 1))
        valid_pitches_str = f"MIDI {pitch_low}-{pitch_high} (follow chord_tones from CHORD MAP)"
    else:
        valid_pitches = get_scale_notes(final_key, pitch_low, pitch_high)
        valid_pitches_str = ", ".join(str(p) for p in valid_pitches[:PROMPT_PITCH_PREVIEW_LIMIT])
        if len(valid_pitches) > PROMPT_PITCH_PREVIEW_LIMIT:
            valid_pitches_str += f"... ({len(valid_pitches)} total)"

    scale_notes = get_scale_note_names(final_key)
    profile_info = format_profile_for_prompt(profile)

    if request.free_mode:
        articulation_list_str = build_articulation_list_for_prompt(profile)

        user_prompt_parts = [
            f"## FREE MODE COMPOSITION for {profile.get('name', 'instrument')}",
        ]

        if profile_user_formatted:
            user_prompt_parts.extend([
                f"",
                f"### !!! CRITICAL INSTRUMENT RULES - READ FIRST !!!",
                profile_user_formatted,
            ])
        if custom_curves_info:
            if not profile_user_formatted:
                user_prompt_parts.extend([
                    f"",
                    f"### INSTRUMENT CURVES",
                ])
            user_prompt_parts.append(
                f"Additional curves (optional unless instrument rules say otherwise): {custom_curves_info}"
            )

        user_prompt_parts.extend([
            f"",
            f"YOU DECIDE: Choose the best generation type, style, and articulations for this context.",
            f"IMPORTANT: Match your output complexity to what the user requests. Simple request = simple output.",
            f"",
            f"### INSTRUMENT PROFILE",
            profile_info,
            f"",
            f"### MUSICAL CONTEXT",
            f"- Key: {final_key}",
            f"- Scale notes: {scale_notes}",
            f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
            f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
            f"",
            *selection_info,
        ])

        user_prompt_parts.extend([
            f"",
            f"Note: Use Expression curve for overall section dynamics, Dynamics curve for note-level shaping. For SHORT articulations, velocity is primary.",
        ])

        is_ensemble = request.ensemble and request.ensemble.total_instruments > 1
        orchestration_hints_prompt = build_orchestration_hints_prompt(profile, is_ensemble)
        if orchestration_hints_prompt:
            user_prompt_parts.append(f"")
            user_prompt_parts.append(orchestration_hints_prompt)
    else:
        is_compose_or_arrange = is_compose_ensemble or is_arrangement_mode

        if is_compose_or_arrange and ensemble and isinstance(ensemble.current_instrument, dict):
            current_track = str(ensemble.current_instrument.get("track_name") or "").strip()
            current_profile_name_str = str(ensemble.current_instrument.get("profile_name") or "").strip()
            
            current_role = str(ensemble.current_instrument.get("role") or "").strip()
            if not current_role or current_role.lower() == "unknown":
                current_role = extract_role_from_plan(plan_data, current_profile_name_str, current_track)
            
            current_role_upper = current_role.upper() if current_role and current_role.lower() != "unknown" else "UNKNOWN"

            current_track = current_track.lower()
            current_profile_name = current_profile_name_str.lower()
            role_guidance_list = plan_data.get("role_guidance") if isinstance(plan_data, dict) else None
            role_detail = ""
            if isinstance(role_guidance_list, list) and role_guidance_list:
                for entry in role_guidance_list:
                    if not isinstance(entry, dict):
                        continue
                    inst_name = str(entry.get("instrument") or "").strip().lower()
                    if not inst_name:
                        continue
                    if inst_name in (current_track, current_profile_name) or inst_name == profile.get("name", "").strip().lower():
                        guidance = str(entry.get("guidance") or "").strip()
                        relationship = str(entry.get("relationship") or "").strip()
                        register = str(entry.get("register") or "").strip()
                        details = []
                        if register:
                            details.append(f"Register: {register}")
                        if guidance:
                            details.append(guidance)
                        if relationship:
                            details.append(f"Relationship: {relationship}")
                        role_detail = "\n".join(details).strip()
                        break

            user_prompt_parts = [
                f"## COMPOSE: {current_role_upper} for {profile.get('name', 'instrument')}",
                f"",
                f"### YOUR ROLE (from plan): {current_role_upper}",
            ]
            if role_detail:
                user_prompt_parts.append(role_detail)
            user_prompt_parts.extend([
                f"",
                f"### INSTRUMENT PROFILE",
                profile_info,
                f"",
                f"### MUSICAL CONTEXT",
                f"- Key: {final_key}",
                f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
                f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
                f"",
                *selection_info,
            ])
        else:
            gen_lower = generation_type.lower()
            type_hint = TYPE_HINTS.get(gen_lower, f"ROLE: Generate a {generation_type} part. OBJECTIVE: Musical, memorable, fitting.")
            user_prompt_parts = [
                f"## COMPOSE: {generation_style.upper()} {generation_type.upper()} for {profile.get('name', 'instrument')}",
                f"",
                f"### INSTRUMENT PROFILE",
                profile_info,
                f"",
                f"### GENERATION TARGET (WHAT TO BUILD)",
                f"1. PART TYPE ({generation_type}):",
                f"{type_hint}",
                f"",
                f"2. STYLE ({generation_style}):",
                f"{mood_hint}",
                f"",
                f"3. DYNAMICS GOAL:",
                f"{dynamics_hint}",
                f"",
                f"### MUSICAL CONTEXT",
                f"- Key: {final_key}",
                f"- Scale notes: {scale_notes}",
                f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
                f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
                f"",
                *selection_info,
            ]

    if context_summary:
        user_prompt_parts.append(f"")
        user_prompt_parts.append(context_summary)

    ensemble_context = build_ensemble_context(
        request.ensemble,
        profile.get("name", ""),
        request.music.time_sig,
        length_q,
        has_plan_chord_map=has_plan_chord_map,
    )
    if ensemble_context:
        user_prompt_parts.append(f"")
        user_prompt_parts.append(ensemble_context)

    if is_arrangement_mode:
        arrangement_context = build_arrangement_context(
            request.ensemble,
            profile.get("name", ""),
            request.music.time_sig,
            length_q,
        )
        if arrangement_context:
            user_prompt_parts.append(f"")
            user_prompt_parts.append(arrangement_context)

    sketch_chord_map_str = ""
    if is_arrangement_mode and request.ensemble.source_sketch:
        sketch_notes = request.ensemble.source_sketch.get("notes", [])
        if sketch_notes:
            sketch_chord_map_str, _ = build_chord_map_from_sketch(
                sketch_notes,
                request.music.time_sig,
                length_q,
            )

    if request.ensemble:
        generation_progress = build_generation_progress(request.ensemble, profile.get("name", ""))
        if generation_progress:
            user_prompt_parts.append("")
            user_prompt_parts.append(generation_progress)
        
        plan_summary = (request.ensemble.plan_summary or "").strip()
        section_overview = plan_data.get("section_overview") if isinstance(plan_data, dict) else None
        role_guidance = plan_data.get("role_guidance") if isinstance(plan_data, dict) else None
        chord_map = plan_chord_map
        phrase_structure = plan_data.get("phrase_structure") if isinstance(plan_data, dict) else None
        accent_map = plan_data.get("accent_map") if isinstance(plan_data, dict) else None
        motif_blueprint = plan_data.get("motif_blueprint") if isinstance(plan_data, dict) else None

        has_plan_content = plan_summary or section_overview or role_guidance or phrase_structure
        if has_plan_content or sketch_chord_map_str:
            user_prompt_parts.append(f"")
            user_prompt_parts.append("### COMPOSITION PLAN (MANDATORY - FOLLOW EXACTLY)")
            if plan_summary:
                user_prompt_parts.append(plan_summary)

            if is_arrangement_mode and sketch_chord_map_str:
                user_prompt_parts.append("")
                user_prompt_parts.append("**CHORD MAP (AUTO-DETECTED FROM SKETCH - MANDATORY):**")
                user_prompt_parts.append(sketch_chord_map_str)
                user_prompt_parts.append("This harmonic structure was detected from the source sketch.")
                user_prompt_parts.append("Use it as the harmonic foundation for your arrangement.")
            elif isinstance(chord_map, list) and chord_map:
                try:
                    from music_notation import midi_to_note
                except ImportError:
                    from .music_notation import midi_to_note
                
                user_prompt_parts.append("")
                user_prompt_parts.append("**CHORD MAP (MANDATORY - USE THESE EXACT NOTES):**")
                user_prompt_parts.append("```")
                user_prompt_parts.append("Bar.Beat | Chord        | Notes for YOUR range")
                user_prompt_parts.append("---------|--------------|---------------------")
                for chord_entry in chord_map:
                    if not isinstance(chord_entry, dict):
                        continue
                    bar = chord_entry.get("bar", 1)
                    beat = chord_entry.get("beat", 1)
                    chord = chord_entry.get("chord", "?")
                    roman = chord_entry.get("roman", "")
                    chord_tones = chord_entry.get("chord_tones", [])
                    
                    if not chord_tones and chord != "?":
                        chord_tones = get_chord_tones_from_name(chord)
                    
                    notes_in_range = []
                    for pc in chord_tones:
                        try:
                            pc_int = int(pc) % 12
                        except (TypeError, ValueError):
                            continue
                        for octave in range(1, 8):
                            midi_pitch = pc_int + (octave + 1) * 12
                            if pitch_low <= midi_pitch <= pitch_high:
                                notes_in_range.append(midi_to_note(midi_pitch))
                                break
                    
                    notes_str = ", ".join(notes_in_range[:6]) if notes_in_range else chord
                    chord_label = f"{chord} ({roman})" if roman else chord
                    user_prompt_parts.append(f"{bar}.{beat:<4}    | {chord_label:<12} | {notes_str}")
                user_prompt_parts.append("```")
                user_prompt_parts.append("")
                user_prompt_parts.append("Use this harmonic structure. How you use it depends on the musical context and style.")
            
            dynamic_arc = plan_data.get("dynamic_arc") if isinstance(plan_data, dict) else None
            if isinstance(dynamic_arc, list) and dynamic_arc:
                user_prompt_parts.append("")
                user_prompt_parts.append("**DYNAMIC ARC (MANDATORY - FOLLOW THIS INTENSITY CURVE):**")
                user_prompt_parts.append("```")
                user_prompt_parts.append("Bar   | Dynamics | Trend")
                user_prompt_parts.append("------|----------|-------")
                for dyn_entry in dynamic_arc:
                    if not isinstance(dyn_entry, dict):
                        continue
                    bar = dyn_entry.get("bar", 1)
                    level = dyn_entry.get("level", "mf")
                    trend = dyn_entry.get("trend", "stable")
                    trend_arrow = {"building": "↗", "climax": "★", "fading": "↘", "resolving": "↓", "stable": "→"}.get(trend, "→")
                    user_prompt_parts.append(f"Bar {bar:<2} | {level:<8} | {trend_arrow} {trend}")
                user_prompt_parts.append("```")
                user_prompt_parts.append("DYNAMIC ARC RULES:")
                user_prompt_parts.append("- Match the dynamics level at each bar")
                user_prompt_parts.append("- 'building': gradually increase intensity toward next point")
                user_prompt_parts.append("- 'climax': peak intensity, strongest notes")
                user_prompt_parts.append("- 'fading'/'resolving': decrease intensity")

            texture_map = plan_data.get("texture_map") if isinstance(plan_data, dict) else None
            current_inst = request.ensemble.current_instrument if request.ensemble else None
            current_family = (current_inst.get("family", "") if current_inst else "").lower()
            time_sig = request.music.time_sig if request.music else "4/4"
            if isinstance(texture_map, list) and texture_map:
                user_prompt_parts.append("")
                user_prompt_parts.append("**TEXTURE MAP (WHEN TO PLAY/REST):**")
                for tex_entry in texture_map:
                    if not isinstance(tex_entry, dict):
                        continue
                    tex_bars = tex_entry.get("bars", "")
                    density = tex_entry.get("density", "medium")
                    active_fam = tex_entry.get("active_families", [])
                    tacet_fam = tex_entry.get("tacet_families", [])
                    tex_type = tex_entry.get("texture_type", "")
                    notes_hint = tex_entry.get("notes_per_bar_hint", "")

                    is_active = not active_fam or current_family in [f.lower() for f in active_fam]
                    is_tacet = current_family in [f.lower() for f in tacet_fam]

                    status = "→ YOU PLAY" if is_active and not is_tacet else "→ TACET (rest)"
                    user_prompt_parts.append(f"- Bars {tex_bars}: {density} density {status}")
                    if tex_type:
                        user_prompt_parts.append(f"    Texture: {tex_type}")
                    if notes_hint and is_active and not is_tacet:
                        user_prompt_parts.append(f"    Notes per bar: ~{notes_hint}")
                    if is_tacet:
                        user_prompt_parts.append(f"    → Generate NO NOTES for bars {tex_bars}!")

                user_prompt_parts.append("")
                user_prompt_parts.append("TEXTURE RULES:")
                user_prompt_parts.append("- TACET sections: output empty notes array for those bars")
                user_prompt_parts.append("- 'sparse': leave lots of space, few notes")
                user_prompt_parts.append("- 'full'/'tutti': all instruments active, denser writing")

            if isinstance(phrase_structure, list) and phrase_structure:
                user_prompt_parts.append("")
                user_prompt_parts.append("**PHRASE STRUCTURE (BREATHING & CADENCES):**")
                for phrase in phrase_structure:
                    if not isinstance(phrase, dict):
                        continue
                    name = phrase.get("name", "phrase")
                    bars = phrase.get("bars", "")
                    function = phrase.get("function", "")
                    cadence = phrase.get("cadence", {})
                    breathing = phrase.get("breathing_points", [])
                    breathe_at = phrase.get("breathe_at", [])
                    climax = phrase.get("climax_point", phrase.get("climax", {}))

                    user_prompt_parts.append(f"- **{name.upper()}** (Bars {bars})")
                    if function:
                        user_prompt_parts.append(f"    Function: {function}")
                    if isinstance(cadence, dict) and cadence:
                        cad_type = cadence.get("type", "")
                        cad_bar = cadence.get("bar", "")
                        target = cadence.get("target_degree", "")
                        if cad_type and cad_bar:
                            user_prompt_parts.append(f"    Cadence: {cad_type} at bar {cad_bar}")
                    if breathe_at:
                        breath_str = ", ".join(str(b) for b in breathe_at)
                        user_prompt_parts.append(f"    Breathe at: {breath_str}")
                    elif breathing:
                        breath_str = ", ".join(str(b) for b in breathing)
                        user_prompt_parts.append(f"    Breathe at: {breath_str}")
                    if isinstance(climax, dict) and climax:
                        climax_bar = climax.get("bar", "")
                        intensity = climax.get("intensity", "")
                        if climax_bar:
                            user_prompt_parts.append(f"    Climax: Bar {climax_bar} ({intensity})")

            if isinstance(accent_map, list) and accent_map:
                user_prompt_parts.append("")
                user_prompt_parts.append("**ACCENT MAP (RHYTHMIC SYNC):**")
                strong_accents = [a for a in accent_map if isinstance(a, dict) and a.get("strength") == "strong"]
                if strong_accents:
                    accent_strs = []
                    for a in strong_accents[:12]:
                        bar = a.get("bar", 1)
                        beat = a.get("beat", 1)
                        accent_strs.append(f"Bar {bar}.{beat}")
                    user_prompt_parts.append(f"- STRONG accents (all instruments): {', '.join(accent_strs)}")
                    user_prompt_parts.append("  → Place notes ON these beats, use f-ff dynamics")
                medium_accents = [a for a in accent_map if isinstance(a, dict) and a.get("strength") == "medium"]
                if medium_accents:
                    accent_strs = []
                    for a in medium_accents[:8]:
                        bar = a.get("bar", 1)
                        beat = a.get("beat", 1)
                        accent_strs.append(f"Bar {bar}.{beat}")
                    user_prompt_parts.append(f"- MEDIUM accents (optional): {', '.join(accent_strs)}")

            if isinstance(motif_blueprint, dict) and motif_blueprint:
                try:
                    from music_notation import midi_to_note, dur_q_to_name
                    from midi_utils import note_to_midi
                except ImportError:
                    from .music_notation import midi_to_note, dur_q_to_name
                    from .midi_utils import note_to_midi
                
                user_prompt_parts.append("")
                user_prompt_parts.append("**MOTIF BLUEPRINT:**")
                description = motif_blueprint.get("description", "")
                character = motif_blueprint.get("character", "")
                intervals = motif_blueprint.get("intervals", [])
                rhythm = motif_blueprint.get("rhythm_pattern", [])
                start_pitch = motif_blueprint.get("suggested_start_pitch")
                techniques = motif_blueprint.get("development_techniques", [])
                notes_str = motif_blueprint.get("notes", "")

                if description:
                    user_prompt_parts.append(f"- Idea: {description}")
                if character:
                    user_prompt_parts.append(f"- Character: {character}")
                
                computed_intervals = []
                if notes_str:
                    user_prompt_parts.append(f"- Notes: {notes_str}")
                    note_parts = [n.strip() for n in notes_str.replace("→", ",").replace("->", ",").split(",") if n.strip()]
                    if len(note_parts) > 1:
                        try:
                            midi_notes = [note_to_midi(n) for n in note_parts]
                            for i in range(1, len(midi_notes)):
                                computed_intervals.append(midi_notes[i] - midi_notes[i-1])
                        except (ValueError, TypeError):
                            pass
                elif intervals and start_pitch:
                    try:
                        motif_notes = []
                        current_pitch = int(start_pitch)
                        motif_notes.append(midi_to_note(current_pitch))
                        for interval in intervals:
                            current_pitch += int(interval)
                            motif_notes.append(midi_to_note(current_pitch))
                        user_prompt_parts.append(f"- Notes: {' → '.join(motif_notes)}")
                    except (TypeError, ValueError):
                        pass
                elif start_pitch:
                    try:
                        user_prompt_parts.append(f"- Start note: {midi_to_note(int(start_pitch))}")
                    except (TypeError, ValueError):
                        pass
                
                if rhythm:
                    try:
                        rhythm_names = [dur_q_to_name(float(r), abbrev=False) for r in rhythm]
                        user_prompt_parts.append(f"- Rhythm: {' → '.join(rhythm_names)}")
                    except (TypeError, ValueError):
                        pass
                
                final_intervals = computed_intervals if computed_intervals else intervals
                if final_intervals:
                    int_vals = []
                    for i in final_intervals:
                        try:
                            int_vals.append(int(i))
                        except (TypeError, ValueError):
                            continue
                    if int_vals:
                        int_str = ", ".join(f"{v:+d}" for v in int_vals)
                        user_prompt_parts.append(f"- Intervals: [{int_str}] semitones")
                
                if techniques:
                    user_prompt_parts.append(f"- Development: {', '.join(techniques)}")
                
                user_prompt_parts.append("")
                user_prompt_parts.append("MOTIF RULE: MELODY role should establish this motif, others respond/develop it")

            if isinstance(section_overview, list) and section_overview:
                user_prompt_parts.append("")
                user_prompt_parts.append("**SECTION OVERVIEW:**")
                for entry in section_overview:
                    if not isinstance(entry, dict):
                        continue
                    section_bars = str(entry.get("bars") or "").strip()
                    section_type = str(entry.get("type") or "").strip()
                    texture = str(entry.get("texture") or "").strip()
                    dynamics = str(entry.get("dynamics") or "").strip()
                    energy = str(entry.get("energy") or "").strip()
                    active = entry.get("active_instruments", [])
                    tacet = entry.get("tacet_instruments", [])

                    parts_line = []
                    if section_bars:
                        parts_line.append(f"Bars {section_bars}")
                    if section_type:
                        parts_line.append(f"[{section_type.upper()}]")
                    if texture:
                        parts_line.append(f"texture: {texture}")
                    if dynamics:
                        parts_line.append(f"dynamics: {dynamics}")
                    if energy:
                        parts_line.append(f"energy: {energy}")
                    if parts_line:
                        user_prompt_parts.append(f"- " + " | ".join(parts_line))
                    if active:
                        user_prompt_parts.append(f"    Active: {', '.join(str(i) for i in active)}")
                    if tacet:
                        user_prompt_parts.append(f"    Tacet: {', '.join(str(i) for i in tacet)}")

            if isinstance(role_guidance, list) and role_guidance:
                user_prompt_parts.append("")
                user_prompt_parts.append("**ROLE ASSIGNMENTS:**")
                for entry in role_guidance:
                    if not isinstance(entry, dict):
                        continue
                    instrument = str(entry.get("instrument") or "").strip()
                    role = str(entry.get("role") or "").strip()
                    register = str(entry.get("register") or "").strip()
                    guidance = str(entry.get("guidance") or "").strip()
                    relationship = str(entry.get("relationship") or "").strip()

                    if not instrument:
                        continue
                    line = f"- **{instrument}**"
                    if role:
                        line += f" → {role.upper()}"
                    if register:
                        line += f" ({register} register)"
                    user_prompt_parts.append(line)
                    if guidance:
                        user_prompt_parts.append(f"    {guidance}")
                    if relationship:
                        user_prompt_parts.append(f"    Relationship: {relationship}")

            user_prompt_parts.append("")

        generated_motif = request.ensemble.generated_motif if request.ensemble else None
        if isinstance(generated_motif, dict) and generated_motif:
            user_prompt_parts.append("### ESTABLISHED MOTIF (from melody instrument - RESPOND TO THIS)")
            source = generated_motif.get("source_instrument", "melody")
            user_prompt_parts.append(f"**Source:** {source}")
            # ... (motif display code) ...
            motif_notes = generated_motif.get("notes", [])
            if motif_notes:
                try:
                    from music_notation import midi_to_note, dur_q_to_name, velocity_to_dynamic
                except ImportError:
                    from .music_notation import midi_to_note, dur_q_to_name, velocity_to_dynamic
                
                user_prompt_parts.append("**Motif notes:**")
                user_prompt_parts.append("```")
                user_prompt_parts.append("Beat | Note    | Duration  | Dynamics")
                user_prompt_parts.append("-----|---------|-----------|--------")
                for note in motif_notes[:12]:
                    if isinstance(note, dict):
                        start_q = note.get("start_q", 0)
                        dur_q = note.get("dur_q", 1.0)
                        pitch = note.get("pitch", 60)
                        vel = note.get("vel", 80)
                        note_name = midi_to_note(pitch)
                        dur_name = dur_q_to_name(dur_q, abbrev=False)
                        dyn = velocity_to_dynamic(vel)
                        user_prompt_parts.append(f"{start_q:4.1f} | {note_name:<7} | {dur_name:<9} | {dyn}")
                user_prompt_parts.append("```")

            intervals = generated_motif.get("intervals", [])
            if intervals:
                int_vals = []
                for i in intervals:
                    try:
                        int_vals.append(int(i))
                    except (TypeError, ValueError):
                        continue
                if int_vals:
                    int_str = ", ".join(f"{v:+d}" for v in int_vals)
                    user_prompt_parts.append(f"**Intervals:** [{int_str}] semitones")

            rhythm = generated_motif.get("rhythm_pattern", [])
            if rhythm:
                try:
                    from music_notation import dur_q_to_name
                except ImportError:
                    from .music_notation import dur_q_to_name
                try:
                    rhythm_names = [dur_q_to_name(float(r), abbrev=False) for r in rhythm]
                    user_prompt_parts.append(f"**Rhythm:** {' → '.join(rhythm_names)}")
                except (TypeError, ValueError):
                    pass

            character = generated_motif.get("character", "")
            if character:
                user_prompt_parts.append(f"**Character:** {character}")

            current_role = request.ensemble.current_instrument.get("role", "").lower() if request.ensemble.current_instrument else ""
            user_prompt_parts.append("")
            if current_role == "melody":
                user_prompt_parts.append("YOUR TASK: You ARE the motif carrier. Develop/vary this motif.")
            elif current_role == "bass":
                user_prompt_parts.append("YOUR TASK: Support the motif rhythm with root notes on strong beats.")
            elif current_role in ("harmony", "pad"):
                user_prompt_parts.append("YOUR TASK: Provide harmonic backdrop that frames this motif.")
            elif current_role == "countermelody":
                user_prompt_parts.append("YOUR TASK: Create a complementary line that answers this motif.")
            else:
                user_prompt_parts.append("YOUR TASK: Complement this motif - don't duplicate it, respond to it.")
            user_prompt_parts.append("")

    try:
        from music_notation import midi_to_note
    except ImportError:
        from .music_notation import midi_to_note
    
    pitch_low_note = midi_to_note(pitch_low)
    pitch_high_note = midi_to_note(pitch_high)
    
    family = str(profile.get("family", "")).lower()
    is_wind_brass = family in {"woodwinds", "brass", "winds"}
    max_dur_hint = "- MAX NOTE DURATION: 8 beats (~2 bars) for wind/brass - split longer notes with breath rests" if is_wind_brass else ""
    
    if request.free_mode:
        free_mode_rules = [
            f"",
            f"### COMPOSITION RULES",
            f"- ALLOWED RANGE: {pitch_low_note} to {pitch_high_note}",
            f"- Channel: {midi_channel}",
            f"- Generate appropriate number of notes for the part type",
        ]
        if max_dur_hint:
            free_mode_rules.append(max_dur_hint)
        user_prompt_parts.extend(free_mode_rules)
        
        user_prompt_parts.extend([
            f"",
            f"### YOUR CREATIVE CHOICES",
            f"- Choose generation TYPE based on user request or context (Melody, Arpeggio, Chords, Pad, Bass, etc.)",
            f"- Choose STYLE that fits (Heroic, Romantic, Dark, Cinematic, etc.)",
            f"- Articulations: use ONE for simple parts (pads, chords), MULTIPLE only for expressive melodic parts",
            f"",
            f"### THREE-LAYER DYNAMICS",
            f"1. DYNAMICS (dyn): Note attack intensity - p, mp, mf, f, ff",
            f"2. EXPRESSION CURVE: GLOBAL section envelope (CC11)",
            f"3. DYNAMICS CURVE: Section dynamics shape (CC1)",
            f"",
            f"DYNAMICS CURVE (CC1) - CRITICAL:",
            f"- Values: 40-127 (40=pp, 64=mp, 80=mf, 100=f, 120=ff)",
            f"- SMOOTH transitions - max jump 20 between points",
            f"- 4-8 breakpoints covering the full piece length",
            f"- Follow DYNAMIC ARC from composition plan",
        ])
    else:
        short_articulations = profile.get("articulations", {}).get("short_articulations", [])
        is_short_art = articulation.lower() in [a.lower() for a in short_articulations]
        velocity_hint = "Use dyn for note-to-note dynamics (accents: f-fff, normal: mf-f, soft: p-mp)" if is_short_art else "Vary dynamics for phrase shaping (peaks: f-ff, between: mf)"

        composition_rules = [
            f"",
            f"### COMPOSITION RULES",
            f"- ALLOWED RANGE: {pitch_low_note} to {pitch_high_note}",
            f"- Suggested note count: {min_notes}-{max_notes} (adapt based on musical needs)",
            f"- Channel: {midi_channel}",
            f"- Articulation: {articulation}",
        ]
        if max_dur_hint:
            composition_rules.append(max_dur_hint)
        user_prompt_parts.extend(composition_rules)
        
        user_prompt_parts.extend([
            f"",
            f"### THREE-LAYER DYNAMICS",
            f"1. DYNAMICS: {velocity_hint}",
            f"2. EXPRESSION CURVE: GLOBAL section envelope",
            f"3. DYNAMICS CURVE: PER-NOTE breathing (cresc/decresc/swell for each sustained note)",
            f"",
            f"DYNAMICS CURVE (CC1): Provide 4-8 breakpoints with SMOOTH transitions (max jump 20)",
        ])

    tempo_guidance = build_tempo_change_guidance(request, length_q)
    if tempo_guidance:
        user_prompt_parts.append(f"")
        user_prompt_parts.extend(tempo_guidance)

    pattern_guidance = build_pattern_guidance(profile, generation_type, bars)
    if pattern_guidance:
        user_prompt_parts.append(f"")
        user_prompt_parts.extend(pattern_guidance)

    if request.user_prompt and request.user_prompt.strip():
        user_prompt_parts.append(f"")
        user_prompt_parts.append(f"### USER REQUEST (PRIORITY - follow these instructions, they override defaults):")
        user_prompt_parts.append(f"{request.user_prompt}")
        user_prompt_parts.append(f"")
        user_prompt_parts.append(f"INTERPRET USER REQUEST:")
        user_prompt_parts.append(f"- If user asks for 'simple', 'basic', 'straightforward' → create simple, clean output")
        user_prompt_parts.append(f"- If user mentions dynamics (crescendo, forte, soft, etc.) → apply to Expression curve for overall, Dynamics curve for detail")
        user_prompt_parts.append(f"- If user forbids spikes or caps max dynamics (e.g. 'cap at f, no ff') → enforce strictly in velocity/CC (no sfz, no sudden accents, no abrupt jumps)")
        user_prompt_parts.append(f"- If user mentions a composer style (Zimmer, Williams, etc.) → match their typical approach")
        user_prompt_parts.append(f"- If user asks for chords/pads → use sustained notes, minimal articulation changes")

    if not request.free_mode:
        if profile_user_formatted:
            user_prompt_parts.extend([
                f"",
                f"### INSTRUMENT-SPECIFIC RULES:",
                profile_user_formatted,
            ])

        if custom_curves_info:
            user_prompt_parts.extend([
                f"",
                f"### INSTRUMENT CURVES (use these curve names):",
                f"{custom_curves_info}",
            ])

    is_ensemble = request.ensemble and request.ensemble.total_instruments > 1
    if request.free_mode and is_ensemble:
        user_prompt_parts.extend([
            f"",
            f"### HANDOFF REQUIREMENT (MANDATORY for ensemble)",
            f"You MUST include a 'handoff' object in your JSON response.",
            f"This helps the next musician understand your contribution and find their place.",
            f"Focus on: what space you occupied, what you left open, and advice for the next instrument.",
        ])

    user_prompt_parts.extend([
        f"",
        f"### OUTPUT (valid JSON only):",
    ])

    user_prompt = "\n".join(user_prompt_parts)
    return system_prompt, user_prompt


def build_plan_prompt(request: GenerateRequest, length_q: float) -> Tuple[str, str]:
    system_prompt = COMPOSITION_PLAN_SYSTEM_PROMPT

    context_summary, detected_key, _ = build_context_summary(
        request.context, request.music.time_sig, length_q, request.music.key
    )
    final_key = request.music.key
    if final_key == "unknown" and detected_key != "unknown":
        final_key = detected_key

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(1, int(length_q / quarters_per_bar))

    user_prompt_parts = [
        "## COMPOSITION PLAN",
        "Create a detailed musical blueprint for this multi-instrument piece.",
        "",
        "### MUSICAL CONTEXT",
        f"- Key: {final_key}",
        f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
        f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
    ]

    if context_summary:
        user_prompt_parts.append("")
        user_prompt_parts.append(context_summary)

    if request.ensemble and request.ensemble.instruments:
        user_prompt_parts.append("")
        user_prompt_parts.append("### ENSEMBLE TO ORCHESTRATE")
        user_prompt_parts.append("Assign roles and plan how these instruments will work together:")
        user_prompt_parts.append("")

        for inst in request.ensemble.instruments:
            track = inst.track_name or ""
            profile_name = inst.profile_name or ""
            if track and profile_name and track != profile_name:
                name = f"{track} ({profile_name})"
            else:
                name = track or profile_name or "Unknown"
            family = inst.family or "unknown"
            description = inst.description or ""
            range_info = inst.range or {}
            preferred_range = range_info.get("preferred", [])

            detail_parts = [f"family: {family}"]
            if preferred_range:
                detail_parts.append(f"range: {preferred_range[0]}-{preferred_range[1]}")
            detail = ", ".join(detail_parts)

            user_prompt_parts.append(f"- {inst.index}. **{name}** ({detail})")
            if description:
                user_prompt_parts.append(f"    Description: {description[:100]}")

        user_prompt_parts.append("")
        user_prompt_parts.append("PLANNING TASKS:")
        user_prompt_parts.append("1. Assign ROLE to each instrument (melody/bass/harmony/rhythm/countermelody/pad)")
        user_prompt_parts.append("2. Define REGISTER allocation to avoid clashes")
        user_prompt_parts.append("3. Plan HARMONIC framework (chord progression style)")
        user_prompt_parts.append("4. Describe MOTIF or musical idea to develop")
        user_prompt_parts.append("5. Order instruments by GENERATION PRIORITY (bass/rhythm first, melody second, etc.)")

    if request.user_prompt and request.user_prompt.strip():
        user_prompt_parts.append("")
        user_prompt_parts.append("### USER REQUEST (this is the main creative direction)")
        user_prompt_parts.append(request.user_prompt.strip())
        user_prompt_parts.append("")
        user_prompt_parts.append("Interpret the user's request and plan a composition that fulfills their vision.")

    user_prompt_parts.extend([
        "",
        "### OUTPUT (valid JSON only):",
    ])

    user_prompt = "\n".join(user_prompt_parts)
    return system_prompt, user_prompt


def build_chat_messages(system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


SKETCH_NOTES_LIMIT = 1000
SKETCH_NOTES_PREVIEW = 200
SKETCH_CC_EVENTS_LIMIT = 200


def format_sketch_notes(notes: List[Dict[str, Any]], time_sig: str = "4/4", limit: int = SKETCH_NOTES_LIMIT) -> str:
    if not notes:
        return "(no notes)"

    sorted_notes = sorted(notes, key=lambda n: (n.get("start_q", 0), -n.get("pitch", 60)))
    limited = sorted_notes[:limit]

    quarters_per_bar = get_quarters_per_bar(time_sig)

    lines = ["```"]
    lines.append("time_q | bar.beat | pitch | note | dur_q | vel | chan")
    lines.append("-------|----------|-------|------|-------|-----|-----")

    for note in limited:
        start_q = note.get("start_q", 0)
        pitch = note.get("pitch", 60)
        dur_q = note.get("dur_q", 1.0)
        vel = note.get("vel", 80)
        chan = note.get("chan", 1)
        note_name = pitch_to_note(pitch)
        bar = int(float(start_q) // quarters_per_bar) + 1 if quarters_per_bar > 0 else 1
        beat_q = (float(start_q) % quarters_per_bar) + 1.0 if quarters_per_bar > 0 else 1.0
        bar_beat = f"{bar}.{beat_q:.2f}"
        lines.append(f"{float(start_q):6.2f} | {bar_beat:8} | {int(pitch):5} | {note_name:4} | {float(dur_q):5.2f} | {int(vel):3} | {int(chan):3}")

    lines.append("```")

    if len(sorted_notes) > limit:
        lines.append(f"... and {len(sorted_notes) - limit} more notes")

    return "\n".join(lines)


def format_sketch_notes_compact(notes: List[Dict[str, Any]], limit: int = SKETCH_NOTES_PREVIEW) -> str:
    if not notes:
        return "(no notes)"

    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    limited = sorted_notes[:limit]

    entries = []
    for note in limited:
        start_q = note.get("start_q", 0)
        pitch = note.get("pitch", 60)
        note_name = pitch_to_note(pitch)
        entries.append(f"{start_q:.1f}:{note_name}")

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
            time_q = float(evt.get("time_q", evt.get("start_q", 0.0)))
            cc = int(evt.get("cc", evt.get("controller", -1)))
            value = int(evt.get("value", evt.get("val", 0)))
            chan = int(evt.get("chan", 1))
        except (TypeError, ValueError):
            continue
        if cc < 0 or cc > 127:
            continue
        controllers.add(cc)
        events.append(
            {
                "time_q": max(0.0, time_q),
                "cc": cc,
                "value": max(0, min(127, value)),
                "chan": max(1, min(16, chan)),
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


def build_arrange_plan_prompt(request: ArrangeRequest, length_q: float) -> Tuple[str, str]:
    system_prompt = ARRANGEMENT_PLAN_SYSTEM_PROMPT

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(1, int(length_q / quarters_per_bar))

    sketch_notes = request.source_sketch.notes if request.source_sketch else []
    sketch_track_name = request.source_sketch.track_name if request.source_sketch else "Unknown"
    sketch_cc_events = request.source_sketch.cc_events if request.source_sketch else []
    cc_formatted, cc_controllers = format_sketch_cc_segments(sketch_cc_events or [], length_q)

    pitches = [n.get("pitch", 60) for n in sketch_notes] if sketch_notes else [60]
    min_pitch = min(pitches)
    max_pitch = max(pitches)

    harmony_progression, detected_key = analyze_harmony_progression(
        sketch_notes,
        request.music.time_sig,
        length_q,
    )
    if not harmony_progression:
        harmony_progression = "(no chord changes detected)"

    user_prompt_parts = [
        "## ARRANGEMENT PLAN",
        "Analyze this piano sketch and create an orchestration plan.",
        "",
        "### SOURCE SKETCH",
        f"Track: {sketch_track_name}",
        f"Total notes: {len(sketch_notes)}",
        f"Pitch range: {pitch_to_note(min_pitch)} to {pitch_to_note(max_pitch)} (MIDI {min_pitch}-{max_pitch})",
        "",
        "**Full sketch content:**",
        format_sketch_notes(sketch_notes, request.music.time_sig),
        "",
        f"**Full sketch CC controllers:** {cc_controllers}",
        cc_formatted,
        "",
        "### DETECTED HARMONY (from sketch analysis)",
        f"Detected key: {detected_key}",
        f"Chord progression: {harmony_progression}",
        "",
        "**NOTE**: CHORD_MAP will be auto-generated from this harmony. You do NOT need to create chord_map.",
        "",
        "### MUSICAL CONTEXT",
        f"- Key: {request.music.key} (project setting) / {detected_key} (detected from sketch)",
        f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
        f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
    ]

    if request.target_instruments:
        user_prompt_parts.append("")
        user_prompt_parts.append("### TARGET INSTRUMENTS (to arrange for)")
        user_prompt_parts.append("Decide how to distribute the sketch material among these instruments:")
        user_prompt_parts.append("")

        for inst in request.target_instruments:
            track = inst.track_name or ""
            profile_name = inst.profile_name or ""
            if track and profile_name and track != profile_name:
                name = f"{track} ({profile_name})"
            else:
                name = track or profile_name or "Unknown"
            family = inst.family or "unknown"
            range_info = inst.range or {}
            preferred_range = range_info.get("preferred", [])

            detail_parts = [f"family: {family}"]
            if preferred_range:
                detail_parts.append(f"range: {preferred_range[0]}-{preferred_range[1]}")
            detail = ", ".join(detail_parts)

            user_prompt_parts.append(f"- {inst.index}. **{name}** ({detail})")

    user_prompt_parts.append("")
    user_prompt_parts.append("### ARRANGEMENT TASKS")
    user_prompt_parts.append("1. ANALYZE the sketch - identify melody, harmony, bass, rhythm layers")
    user_prompt_parts.append("2. ASSIGN each layer to appropriate instrument(s)")
    user_prompt_parts.append("3. Specify VERBATIM LEVEL: how closely each instrument follows the original")
    user_prompt_parts.append("4. Order instruments for GENERATION (melody first, then bass, then harmony...)")

    if request.user_prompt and request.user_prompt.strip():
        user_prompt_parts.append("")
        user_prompt_parts.append("### USER REQUEST (style guidance for the arrangement)")
        user_prompt_parts.append(request.user_prompt.strip())

    user_prompt_parts.extend([
        "",
        "### OUTPUT (valid JSON only):",
    ])

    user_prompt = "\n".join(user_prompt_parts)
    return system_prompt, user_prompt


def build_arrangement_context(
    ensemble: Any,
    current_profile_name: str,
    time_sig: str = "4/4",
    length_q: float = 16.0,
) -> str:
    if not ensemble or not ensemble.arrangement_mode:
        return ""

    source_sketch = ensemble.source_sketch
    if not source_sketch or not isinstance(source_sketch, dict):
        return ""

    sketch_notes = source_sketch.get("notes", [])
    sketch_track_name = source_sketch.get("track_name", "Sketch")
    sketch_cc_events = source_sketch.get("cc_events", [])
    assignment = ensemble.arrangement_assignment or {}

    role = assignment.get("role", "unknown")
    material_source = assignment.get("material_source", "Extract appropriate material from sketch")
    adaptation_notes = assignment.get("adaptation_notes", "Adapt to instrument idiom")
    verbatim_level = assignment.get("verbatim_level", "medium")
    register_adjustment = assignment.get("register_adjustment", "none")

    quarters_per_bar = get_quarters_per_bar(time_sig)
    max_dur_by_bars_q = quarters_per_bar * 2.0
    sketch_max_dur_q = 0.0
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
    arrangement_max_dur_q = min(max_dur_by_bars_q, sketch_max_dur_q) if sketch_max_dur_q > 0 else max_dur_by_bars_q

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
        sketch_max_dur_q=round(sketch_max_dur_q, 3) if sketch_max_dur_q > 0 else "unknown",
        arrangement_max_dur_q=round(arrangement_max_dur_q, 3),
        role=role,
        material_source=material_source,
        adaptation_notes=adaptation_notes,
        verbatim_level=verbatim_level,
        register_adjustment=register_adjustment or "none",
    )

    return context
