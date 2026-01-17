from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import (
        CUSTOM_CURVE_EXCLUSIONS,
        DEFAULT_KEYSWITCH_VELOCITY,
        DEFAULT_PROMPT_PITCH_HIGH,
        DEFAULT_PROMPT_PITCH_LOW,
        MIDI_VEL_MIN,
    )
    from prompt_builder_common import (
        DEFAULT_GENERATION_ORDER,
        RANGE_BOUND_COUNT,
        normalize_lower,
        normalize_text,
        import_note_to_midi,
    )
    from utils import safe_format
except ImportError:
    from .constants import (
        CUSTOM_CURVE_EXCLUSIONS,
        DEFAULT_KEYSWITCH_VELOCITY,
        DEFAULT_PROMPT_PITCH_HIGH,
        DEFAULT_PROMPT_PITCH_LOW,
        MIDI_VEL_MIN,
    )
    from .prompt_builder_common import (
        DEFAULT_GENERATION_ORDER,
        RANGE_BOUND_COUNT,
        normalize_lower,
        normalize_text,
        import_note_to_midi,
    )
    from .utils import safe_format


DEFAULT_PROFILE_NAME = "Unknown"
DEFAULT_POLYPHONY = "poly"
ARTICULATION_MODE_CC = "cc"
ARTICULATION_MODE_KEYSWITCH = "keyswitch"
ARTICULATION_MODE_NONE = "none"
LEGATO_KEY = "legato"
DYNAMICS_TYPE_VELOCITY = "velocity"
DEFAULT_DYNAMICS_TYPE = "cc1"
ORCHESTRATION_LIST_LIMIT = 5
UNKNOWN_PROFILE_PLACEHOLDER = "?"

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


def build_generation_progress(ensemble: Any, current_profile_name: str) -> str:
    if not ensemble or not ensemble.is_sequential:
        return ""

    instruments = ensemble.instruments or []
    previously_generated = ensemble.previously_generated or []
    generation_order = ensemble.generation_order or DEFAULT_GENERATION_ORDER

    completed_names = [
        p.get("profile_name") or p.get("track_name") or UNKNOWN_PROFILE_PLACEHOLDER
        for p in previously_generated
    ]

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


def format_profile_user_template(template: str, values: Dict[str, Any]) -> str:
    if not template:
        return ""
    return safe_format(template, values)


def get_custom_curves_info(profile: Dict[str, Any]) -> Tuple[List[str], str]:
    controllers = profile.get("controllers", {})
    semantic_to_cc = controllers.get("semantic_to_cc", controllers)
    custom_curves = [
        k for k in semantic_to_cc.keys()
        if k not in CUSTOM_CURVE_EXCLUSIONS and isinstance(semantic_to_cc[k], int)
    ]
    if not custom_curves:
        return custom_curves, ""
    curves_info = ", ".join([f"curves.{k} (CC{semantic_to_cc[k]})" for k in custom_curves])
    return custom_curves, curves_info


def format_profile_for_prompt(profile: Dict[str, Any]) -> str:
    lines = []

    name = profile.get("name", DEFAULT_PROFILE_NAME)
    range_info = profile.get("range", {})
    preferred = range_info.get("preferred", [])
    lines.append(f"INSTRUMENT: {name}")
    if preferred:
        lines.append(f"RANGE: {preferred[0]} - {preferred[1]}")

    midi = profile.get("midi", {})
    polyphony = midi.get("polyphony", DEFAULT_POLYPHONY)
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
    mode = art.get("mode", ARTICULATION_MODE_NONE)
    art_map = art.get("map", {})

    legato = profile.get("legato", {})
    if legato and not art_map.get(LEGATO_KEY):
        art_map = dict(art_map)
        art_map[LEGATO_KEY] = legato

    if mode == ARTICULATION_MODE_CC and art_map:
        cc_num = art.get("cc_number")
        lines.append(f"ARTICULATIONS (CC{cc_num}, use articulation_changes list):")
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
                lines.append(
                    f"  {art_name}: keyswitch {ks} (vel_on={data['velocity_on']}, vel_off={data.get('velocity_off', MIDI_VEL_MIN)})"
                )

    elif mode == ARTICULATION_MODE_KEYSWITCH and art_map:
        lines.append("ARTICULATIONS (use articulation_changes list, keyswitches added automatically):")
        for art_name, data in art_map.items():
            if not isinstance(data, dict):
                continue
            desc = data.get("description", art_name)
            dynamics = data.get("dynamics", DEFAULT_DYNAMICS_TYPE)
            dyn_str = " [velocity]" if dynamics == DYNAMICS_TYPE_VELOCITY else ""
            lines.append(f"  {art_name}: {desc}{dyn_str}")

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
        vel_on = legato.get("velocity_on", DEFAULT_KEYSWITCH_VELOCITY)
        vel_off = legato.get("velocity_off", MIDI_VEL_MIN)
        lines.append(f"LEGATO: keyswitch {ks} (vel_on={vel_on}, vel_off={vel_off})")

    return "\n".join(lines)


def resolve_prompt_pitch_range(pref_range: Any) -> Tuple[int, int]:
    pitch_low = DEFAULT_PROMPT_PITCH_LOW
    pitch_high = DEFAULT_PROMPT_PITCH_HIGH
    if pref_range and isinstance(pref_range, list) and len(pref_range) == RANGE_BOUND_COUNT:
        note_to_midi = import_note_to_midi()
        try:
            pitch_low = note_to_midi(pref_range[0])
            pitch_high = note_to_midi(pref_range[1])
        except ValueError:
            pass
    return pitch_low, pitch_high


def get_profile_articulation_names(profile: Dict[str, Any]) -> List[str]:
    art_cfg = profile.get("articulations", {})
    art_map = art_cfg.get("map", {})
    if not isinstance(art_map, dict):
        return []
    names = [normalize_text(name) for name in art_map.keys() if normalize_text(name)]
    return sorted(set(names))


def resolve_profile_default_articulation(
    profile: Dict[str, Any],
    allowed_map: Dict[str, str],
    allowed_names: List[str],
) -> str:
    art_cfg = profile.get("articulations", {})
    default_name = normalize_text(art_cfg.get("default", ""))
    if default_name:
        resolved = allowed_map.get(default_name.lower(), "")
        if resolved:
            return resolved
    return allowed_names[0] if allowed_names else ""


def resolve_prompt_articulation(profile: Dict[str, Any], preset_settings: Dict[str, Any]) -> str:
    allowed_names = get_profile_articulation_names(profile)
    allowed_map = {name.lower(): name for name in allowed_names}
    preset_value = preset_settings.get("articulation") if isinstance(preset_settings, dict) else None
    if preset_value:
        resolved = allowed_map.get(normalize_lower(preset_value), "")
        if resolved:
            return resolved
    return resolve_profile_default_articulation(profile, allowed_map, allowed_names)


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
        for item in best_for[:ORCHESTRATION_LIST_LIMIT]:
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
            for tip in ensemble_tips[:ORCHESTRATION_LIST_LIMIT]:
                lines.append(f"  - {tip}")

    texture_options = hints.get("texture_options", [])
    if texture_options:
        lines.append("**Texture options:**")
        for option in texture_options[:ORCHESTRATION_LIST_LIMIT]:
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
        dynamics_type = data.get("dynamics", DEFAULT_DYNAMICS_TYPE)
        dur_hint = ARTICULATION_DURATION_HINTS.get(name, "")
        if dynamics_type == DYNAMICS_TYPE_VELOCITY:
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
