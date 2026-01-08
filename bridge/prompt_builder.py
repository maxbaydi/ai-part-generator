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
        detect_continuation_intent,
        get_quarters_per_bar,
        parse_composition_structure,
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
        detect_continuation_intent,
        get_quarters_per_bar,
        parse_composition_structure,
    )
    from .models import GenerateRequest
    from .music_theory import get_scale_note_names, get_scale_notes
    from .promts import BASE_SYSTEM_PROMPT, COMPOSITION_PLAN_SYSTEM_PROMPT, FREE_MODE_SYSTEM_PROMPT
    from .style import DYNAMICS_HINTS, MOOD_HINTS
    from .type import ARTICULATION_HINTS, TYPE_HINTS
    from .utils import safe_format

CONTINUATION_INTENT_INSTRUCTIONS = {
    "continue": """### CONTINUATION TASK
You must CONTINUE the existing musical material. Study the notes BEFORE the target area carefully.
- Maintain the same melodic direction and momentum
- Use similar rhythmic patterns
- Keep the same register and style
- Create a seamless connection from the preceding material""",
    "continue_progression": """### CHORD PROGRESSION CONTINUATION TASK
You must CONTINUE the chord progression. Analyze the existing harmony carefully.
- Follow the harmonic direction established before
- Use appropriate voice leading
- Maintain the same harmonic rhythm
- Create a natural extension of the progression""",
    "complete": """### COMPLETION TASK
You must COMPLETE/FINISH the musical phrase or section. The material should feel like a natural ending.
- Create a sense of resolution and finality
- Use cadential patterns (V-I, IV-I, etc.)
- Gradually reduce activity toward the end
- End on stable scale degrees (1, 3, 5)
- Consider using ritardando effect (longer notes toward the end)""",
    "complete_progression": """### CHORD PROGRESSION COMPLETION TASK
You must COMPLETE the chord progression with a satisfying cadence.
- Analyze the preceding chords to determine the key
- Use appropriate cadential formulas (V-I, IV-V-I, ii-V-I, etc.)
- Create harmonic resolution
- The final chord should provide closure""",
    "fill": """### FILL/BRIDGE TASK
You must FILL the gap between existing material BEFORE and AFTER the target area.
- Study both the preceding and following notes
- Create a smooth transition that connects both sections
- Match the starting point of what comes after
- Gradually transform from where the before section ends""",
    "fill_progression": """### HARMONIC FILL TASK
You must FILL the harmonic gap between existing chord progressions.
- Analyze chords before AND after the target area
- Create a smooth harmonic bridge
- Use passing chords and voice leading
- Ensure the connection sounds natural""",
}

POSITION_INSTRUCTIONS = {
    "start": """### POSITION: START OF SECTION
This is the beginning. The generated material should:
- Establish the theme/motif clearly
- Create memorable opening phrase
- Set up the musical direction for what follows""",
    "middle": """### POSITION: MIDDLE OF SECTION  
This fills a gap between existing material. The generated material should:
- Connect naturally with preceding notes
- Prepare for the following notes
- Maintain continuity of style and register""",
    "end": """### POSITION: END OF SECTION
This is the ending. The generated material should:
- Bring the phrase to a natural conclusion
- Consider using cadential patterns
- Create a sense of completion""",
}

STRUCTURE_SECTION_HINTS = {
    "intro": "Build anticipation, establish the mood, simpler texture",
    "main_theme": "Present the main melodic idea clearly and memorably",
    "main_part": "Establish the core material and maintain the driving texture",
    "theme": "Present the melodic idea clearly",
    "outro": "Wind down, resolve tension, bring to peaceful conclusion",
    "development": "Develop themes, add complexity, build tension",
    "verse": "Lyrical, storytelling section",
    "chorus": "Emotional peak, memorable hook",
    "bridge": "Contrast section, transition between parts",
    "climax": "Highest intensity and energy, bold gestures and strong dynamics",
}


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

    context_summary, detected_key, position = build_context_summary(request.context, request.music.time_sig, length_q)

    final_key = request.music.key
    if final_key == "unknown" and detected_key != "unknown":
        final_key = detected_key

    continuation_intent = detect_continuation_intent(request.user_prompt)

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(1, int(length_q / quarters_per_bar))

    scale_notes = get_scale_note_names(final_key)
    valid_pitches = get_scale_notes(final_key, pitch_low, pitch_high)
    valid_pitches_str = ", ".join(str(p) for p in valid_pitches[:PROMPT_PITCH_PREVIEW_LIMIT])
    if len(valid_pitches) > PROMPT_PITCH_PREVIEW_LIMIT:
        valid_pitches_str += f"... ({len(valid_pitches)} total)"

    continuation_instructions = ""
    if continuation_intent:
        continuation_instructions = CONTINUATION_INTENT_INSTRUCTIONS.get(continuation_intent, "")
    elif position != "isolated":
        continuation_instructions = POSITION_INSTRUCTIONS.get(position, "")

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
            f"### AVAILABLE ARTICULATIONS:",
            articulation_list_str,
        ])

        user_prompt_parts.extend([
            f"",
            f"Note: Use Expression (CC11) for overall section dynamics, Dynamics (CC1) for note-level shaping. For SHORT articulations, velocity is primary.",
        ])
    else:
        user_prompt_parts = [
            f"## COMPOSE: {generation_style.upper()} {generation_type.upper()} for {profile.get('name', 'instrument')}",
            f"",
            f"### MUSICAL CONTEXT",
            f"- Key: {final_key}",
            f"- Scale notes: {scale_notes}",
            f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
            f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
        ]

    if continuation_instructions:
        user_prompt_parts.append(f"")
        user_prompt_parts.append(continuation_instructions)

    if context_summary:
        user_prompt_parts.append(f"")
        user_prompt_parts.append(context_summary)

    ensemble_context = build_ensemble_context(request.ensemble, profile.get("name", ""))
    if ensemble_context:
        user_prompt_parts.append(f"")
        user_prompt_parts.append(ensemble_context)
    if request.free_mode and request.ensemble:
        plan_summary = (request.ensemble.plan_summary or "").strip()
        plan_data = request.ensemble.plan if isinstance(request.ensemble.plan, dict) else {}
        section_overview = plan_data.get("section_overview") if isinstance(plan_data, dict) else None
        role_guidance = plan_data.get("role_guidance") if isinstance(plan_data, dict) else None
        if plan_summary or section_overview or role_guidance:
            user_prompt_parts.append(f"")
            user_prompt_parts.append("### COMPOSITION PLAN (GUIDANCE)")
            if plan_summary:
                user_prompt_parts.append(plan_summary)
            if isinstance(section_overview, list) and section_overview:
                user_prompt_parts.append("")
                user_prompt_parts.append("Plan sections:")
                for entry in section_overview:
                    if not isinstance(entry, dict):
                        continue
                    bars = str(entry.get("bars") or "").strip()
                    focus = str(entry.get("focus") or "").strip()
                    energy = str(entry.get("energy") or "").strip()
                    parts_line = []
                    if bars:
                        parts_line.append(f"bars {bars}")
                    if focus:
                        parts_line.append(f"focus: {focus}")
                    if energy:
                        parts_line.append(f"energy: {energy}")
                    if parts_line:
                        user_prompt_parts.append(f"- " + "; ".join(parts_line))
            if isinstance(role_guidance, list) and role_guidance:
                user_prompt_parts.append("")
                user_prompt_parts.append("Role guidance:")
                for entry in role_guidance:
                    if not isinstance(entry, dict):
                        continue
                    instrument = str(entry.get("instrument") or "").strip()
                    role = str(entry.get("role") or "").strip()
                    guidance = str(entry.get("guidance") or "").strip()
                    parts_line = []
                    if instrument:
                        parts_line.append(instrument)
                    if role:
                        parts_line.append(f"role: {role}")
                    if guidance:
                        parts_line.append(guidance)
                    if parts_line:
                        user_prompt_parts.append(f"- " + "; ".join(parts_line))

    if not request.free_mode:
        composition_structure = parse_composition_structure(request.user_prompt, bars, request.music.time_sig)
        if composition_structure:
            user_prompt_parts.append(f"")
            user_prompt_parts.append("### COMPOSITION STRUCTURE - FOLLOW THIS FORM")
            user_prompt_parts.append("The user has specified a specific structure. Generate according to these sections:")
            user_prompt_parts.append("")

            for section in composition_structure:
                section_type = section["type"].replace("_", " ").title()
                start_bar = section["start_bar"]
                end_bar = section["end_bar"]
                num_bars = section["bars"]
                start_q = start_bar * quarters_per_bar
                end_q = end_bar * quarters_per_bar

                hint = STRUCTURE_SECTION_HINTS.get(section["type"], "")

                user_prompt_parts.append(f"  **{section_type}**: Bars {start_bar + 1}-{end_bar} ({num_bars} bars, quarters {start_q:.0f}-{end_q:.0f})")
                if hint:
                    user_prompt_parts.append(f"    → {hint}")

            user_prompt_parts.append("")
            user_prompt_parts.append("STRUCTURE RULES:")
            user_prompt_parts.append("- Each section should have distinct character matching its type")
            user_prompt_parts.append("- Create smooth transitions between sections")
            user_prompt_parts.append("- The outro should feel like a natural resolution")
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
            f"- Notes: {min_notes}-{max_notes}, evenly distributed across all {bars} bars",
            f"- Pitch range: MIDI {pitch_low}-{pitch_high}",
            f"- Channel: {midi_channel}",
            f"- Articulation: {articulation}",
            f"",
            f"### THREE-LAYER DYNAMICS",
            f"1. VELOCITY: {velocity_hint}",
            f"2. EXPRESSION + DYNAMICS: {dynamics_hint}",
            f"   - Expression (CC11): GLOBAL arc of the section",
            f"   - Dynamics (CC1): LOCAL swells/fades within notes and phrases",
        ])

    if request.user_prompt and request.user_prompt.strip():
        user_prompt_parts.append(f"")
        user_prompt_parts.append(f"### USER REQUEST (PRIORITY - follow these instructions, they override defaults):")
        user_prompt_parts.append(f"{request.user_prompt}")
        user_prompt_parts.append(f"")
        user_prompt_parts.append(f"INTERPRET USER REQUEST:")
        user_prompt_parts.append(f"- If user asks for 'simple', 'basic', 'straightforward' → create simple, clean output")
        user_prompt_parts.append(f"- If user mentions dynamics (crescendo, forte, soft, etc.) → apply to Expression curve for overall, Dynamics curve for detail")
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
        "Create a concise plan to guide multi-instrument generation.",
        "If the user mentions sections with bar counts, include them in section_overview with bar ranges.",
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
        user_prompt_parts.append("### ENSEMBLE")
        for inst in request.ensemble.instruments:
            track = inst.track_name or ""
            profile_name = inst.profile_name or ""
            if track and profile_name and track != profile_name:
                name = f"{track} ({profile_name})"
            else:
                name = track or profile_name or "Unknown"
            role = inst.role or "unknown"
            family = inst.family or "unknown"
            user_prompt_parts.append(f"- {inst.index}. {name} (family: {family}, role: {role})")

    if request.user_prompt and request.user_prompt.strip():
        user_prompt_parts.append("")
        user_prompt_parts.append("### USER REQUEST")
        user_prompt_parts.append(request.user_prompt.strip())

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
