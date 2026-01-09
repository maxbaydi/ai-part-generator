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
        build_context_summary,
        build_ensemble_context,
        get_quarters_per_bar,
    )
    from models import GenerateRequest
    from music_theory import get_scale_note_names, get_scale_notes
    from promts import BASE_SYSTEM_PROMPT, COMPOSITION_PLAN_SYSTEM_PROMPT, FREE_MODE_SYSTEM_PROMPT
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
        build_context_summary,
        build_ensemble_context,
        get_quarters_per_bar,
    )
    from .models import GenerateRequest
    from .music_theory import get_scale_note_names, get_scale_notes
    from .promts import BASE_SYSTEM_PROMPT, COMPOSITION_PLAN_SYSTEM_PROMPT, FREE_MODE_SYSTEM_PROMPT
    from .style import DYNAMICS_HINTS, MOOD_HINTS
    from .type import ARTICULATION_HINTS, TYPE_HINTS
    from .utils import safe_format

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
    semantic_to_cc = profile.get("controllers", {}).get("semantic_to_cc", {})
    custom_curves = [k for k in semantic_to_cc.keys() if k not in CUSTOM_CURVE_EXCLUSIONS]
    if not custom_curves:
        return custom_curves, ""
    curves_info = ", ".join([f"curves.{k} (CC{semantic_to_cc[k]})" for k in custom_curves])
    return custom_curves, curves_info


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
        result_parts.append("LONG articulations (dynamics via CC1 curve, use longer dur_q 1.0+):")
        result_parts.extend(long_arts)
    if short_arts:
        result_parts.append("SHORT articulations (dynamics via velocity, use short dur_q as specified):")
        result_parts.extend(short_arts)

    return "\n".join(result_parts)


def build_tempo_change_guidance(request: GenerateRequest, length_q: float) -> List[str]:
    if not request.allow_tempo_changes:
        return []

    if request.ensemble and request.ensemble.is_sequential:
        generation_order = int(request.ensemble.generation_order or 0)
        if generation_order > 1:
            return [
                "### TEMPO CHANGES",
                "Tempo changes are already defined by an earlier part.",
                "DO NOT output tempo_markers for this response.",
            ]

    length_hint = round(float(length_q or 0.0), 2)
    lines = [
        "### TEMPO CHANGES (optional)",
        "You may include tempo changes across the selection.",
        "Use top-level tempo_markers: [{\"time_q\": 0, \"bpm\": 120, \"linear\": false}, ...].",
        f"time_q is in quarter notes from the selection start (0..{length_hint}).",
        "Keep markers in ascending order, 1-4 markers max.",
        "linear=true means a smooth ramp to the next marker; false means an immediate change.",
    ]
    if request.ensemble and request.ensemble.is_sequential:
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

    gen_lower = generation_type.lower()
    type_hint = TYPE_HINTS.get(gen_lower, f"Generate a {generation_type} part.")
    type_hint += " Result must be MUSICAL, easy to perceive, and memorable."
    generation_style = request.generation_style or DEFAULT_GENERATION_STYLE
    style_lower = generation_style.lower()
    mood_hint = MOOD_HINTS.get(style_lower, f"Create in {generation_style} style.")

    articulation = preset_settings.get("articulation", "legato")
    articulation_hint = ARTICULATION_HINTS.get(articulation.lower(), "") if articulation else ""

    dynamics_hint = DYNAMICS_HINTS.get(
        style_lower,
        "EXPRESSION: Match the overall section arc. DYNAMICS: Add local note/phrase breathing.",
    )

    style_hint = f"{type_hint} {mood_hint}"
    if articulation_hint:
        style_hint = f"{style_hint} {articulation_hint}"

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

    context_summary, detected_key, _position = build_context_summary(
        request.context, request.music.time_sig, length_q
    )

    final_key = request.music.key
    if final_key == "unknown" and detected_key != "unknown":
        final_key = detected_key

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(1, int(length_q / quarters_per_bar))
    selection_info = build_selection_info(length_q, quarters_per_bar, bars)

    scale_notes = get_scale_note_names(final_key)
    valid_pitches = get_scale_notes(final_key, pitch_low, pitch_high)
    valid_pitches_str = ", ".join(str(p) for p in valid_pitches[:PROMPT_PITCH_PREVIEW_LIMIT])
    if len(valid_pitches) > PROMPT_PITCH_PREVIEW_LIMIT:
        valid_pitches_str += f"... ({len(valid_pitches)} total)"

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
            f"### MUSICAL CONTEXT",
            f"- Key: {final_key}",
            f"- Scale notes: {scale_notes}",
            f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
            f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
            f"",
            *selection_info,
            f"",
            f"### AVAILABLE ARTICULATIONS:",
            articulation_list_str,
        ])

        user_prompt_parts.extend([
            f"",
            f"Note: Use Expression (CC11) for overall section dynamics, Dynamics (CC1) for note-level shaping. For SHORT articulations, velocity is primary.",
        ])

        is_ensemble = request.ensemble and request.ensemble.total_instruments > 1
        orchestration_hints_prompt = build_orchestration_hints_prompt(profile, is_ensemble)
        if orchestration_hints_prompt:
            user_prompt_parts.append(f"")
            user_prompt_parts.append(orchestration_hints_prompt)
    else:
        user_prompt_parts = [
            f"## COMPOSE: {generation_style.upper()} {generation_type.upper()} for {profile.get('name', 'instrument')}",
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
    )
    if ensemble_context:
        user_prompt_parts.append(f"")
        user_prompt_parts.append(ensemble_context)
    if request.free_mode and request.ensemble:
        plan_summary = (request.ensemble.plan_summary or "").strip()
        plan_data = request.ensemble.plan if isinstance(request.ensemble.plan, dict) else {}
        section_overview = plan_data.get("section_overview") if isinstance(plan_data, dict) else None
        role_guidance = plan_data.get("role_guidance") if isinstance(plan_data, dict) else None
        harmonic_plan = plan_data.get("harmonic_plan") if isinstance(plan_data, dict) else None
        motif_guidance = plan_data.get("motif_guidance") if isinstance(plan_data, dict) else None

        has_plan_content = plan_summary or section_overview or role_guidance or harmonic_plan or motif_guidance
        if has_plan_content:
            user_prompt_parts.append(f"")
            user_prompt_parts.append("### COMPOSITION PLAN (FOLLOW THIS GUIDANCE)")
            if plan_summary:
                user_prompt_parts.append(plan_summary)

            if isinstance(harmonic_plan, dict):
                user_prompt_parts.append("")
                user_prompt_parts.append("**HARMONIC FRAMEWORK:**")
                prog_style = harmonic_plan.get("progression_style", "")
                if prog_style:
                    user_prompt_parts.append(f"- Style: {prog_style}")
                chord_rhythm = harmonic_plan.get("chord_rhythm", "")
                if chord_rhythm:
                    user_prompt_parts.append(f"- Harmonic rhythm: {chord_rhythm}")
                key_chords = harmonic_plan.get("key_chords", [])
                if key_chords:
                    user_prompt_parts.append(f"- Key chords: {', '.join(str(c) for c in key_chords)}")
                harmonic_arc = harmonic_plan.get("harmonic_arc", "")
                if harmonic_arc:
                    user_prompt_parts.append(f"- Arc: {harmonic_arc}")
                user_prompt_parts.append("RULE: All instruments must follow this harmonic framework!")

            if isinstance(motif_guidance, dict):
                user_prompt_parts.append("")
                user_prompt_parts.append("**MOTIF/THEME:**")
                main_idea = motif_guidance.get("main_idea", "")
                if main_idea:
                    user_prompt_parts.append(f"- Main idea: {main_idea}")
                character = motif_guidance.get("character", "")
                if character:
                    user_prompt_parts.append(f"- Character: {character}")
                dev_hints = motif_guidance.get("development_hints", "")
                if dev_hints:
                    user_prompt_parts.append(f"- Development: {dev_hints}")

            if isinstance(section_overview, list) and section_overview:
                user_prompt_parts.append("")
                user_prompt_parts.append("**SECTION STRUCTURE:**")
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
            user_prompt_parts.append("STRUCTURE RULES:")
            user_prompt_parts.append("- Each section should have distinct character matching its type")
            user_prompt_parts.append("- Create smooth transitions between sections")
            user_prompt_parts.append("- Follow the harmonic framework - all instruments play the SAME chords")
            user_prompt_parts.append("- Develop the motif across instruments for unity")
            user_prompt_parts.append("")

    if request.free_mode:
        user_prompt_parts.extend([
            f"",
            f"### COMPOSITION RULES",
            f"- ALLOWED PITCHES (use ONLY these): {valid_pitches_str}",
            f"- Pitch range: MIDI {pitch_low}-{pitch_high}",
            f"- Channel: {midi_channel}",
            f"- Generate appropriate number of notes for the part type",
            f"",
            f"### YOUR CREATIVE CHOICES",
            f"- Choose generation TYPE based on user request or context (Melody, Arpeggio, Chords, Pad, Bass, etc.)",
            f"- Choose STYLE that fits (Heroic, Romantic, Dark, Cinematic, etc.)",
            f"- Articulations: use ONE for simple parts (pads, chords), MULTIPLE only for expressive melodic parts",
            f"",
            f"### THREE-LAYER DYNAMICS",
            f"1. VELOCITY (vel): Note attack intensity. Accent: 100-127, normal: 70-90, soft: 40-60",
            f"2. CC11 EXPRESSION (curves.expression): GLOBAL section dynamics - overall arc of the passage",
            f"   - Sets the macro-level: how loud is this section overall",
            f"3. CC1 DYNAMICS (curves.dynamics): LOCAL note/phrase dynamics - internal movement",
            f"   - For sustained notes: adds swells and fades within each note",
            f"   - For phrases: adds breathing and local detail",
            f"TIP: Choose a dynamic contour that fits the request - steady, gentle waves, build-climax, or any shape that serves the music.",
        ])
    else:
        short_articulations = profile.get("articulations", {}).get("short_articulations", [])
        is_short_art = articulation.lower() in [a.lower() for a in short_articulations]
        velocity_hint = "Use velocity for note-to-note dynamics (accents: 100-120, normal: 75-95, soft: 50-70)" if is_short_art else "Vary velocity for phrase shaping (phrase peaks: 90-100, between: 70-85)"

        user_prompt_parts.extend([
            f"",
            f"### COMPOSITION RULES",
            f"- Style: {style_hint}",
            f"- ALLOWED PITCHES (use ONLY these): {valid_pitches_str}",
            f"- Suggested note range: {min_notes}-{max_notes} (adapt based on musical needs)",
            f"- Pitch range: MIDI {pitch_low}-{pitch_high}",
            f"- Channel: {midi_channel}",
            f"- Articulation: {articulation}",
            f"",
            f"### THREE-LAYER DYNAMICS",
            f"1. VELOCITY: {velocity_hint}",
            f"2. EXPRESSION + DYNAMICS: {dynamics_hint}",
            f"   - Expression (CC11): GLOBAL arc of the section",
            f"   - Dynamics (CC1): LOCAL swells/fades within notes and phrases",
            f"   - TIP: Match dynamic shape to the requested mood and style.",
        ])

    tempo_guidance = build_tempo_change_guidance(request, length_q)
    if tempo_guidance:
        user_prompt_parts.append(f"")
        user_prompt_parts.extend(tempo_guidance)

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

    user_prompt_parts.extend([
        f"",
        f"### OUTPUT (valid JSON only):",
    ])

    user_prompt = "\n".join(user_prompt_parts)
    return system_prompt, user_prompt


def build_plan_prompt(request: GenerateRequest, length_q: float) -> Tuple[str, str]:
    system_prompt = COMPOSITION_PLAN_SYSTEM_PROMPT

    context_summary, detected_key, _ = build_context_summary(request.context, request.music.time_sig, length_q)
    final_key = request.music.key
    if final_key == "unknown" and detected_key != "unknown":
        final_key = detected_key

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(1, int(length_q / quarters_per_bar))

    user_prompt_parts = [
        "## FREE MODE COMPOSITION PLAN",
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
