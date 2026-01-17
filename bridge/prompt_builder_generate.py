from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

try:
    from constants import (
        DEFAULT_GENERATION_STYLE,
        DEFAULT_GENERATION_TYPE,
        MIDI_CHAN_MIN,
        WIND_BRASS_FAMILIES,
        WIND_BRASS_MAX_NOTE_DUR_Q,
    )
    from context_builder import (
        build_chord_map_from_sketch,
        build_context_summary,
        build_ensemble_context,
        get_quarters_per_bar,
    )
    from models import GenerateRequest
    from music_theory import get_scale_note_names
    from promts import BASE_SYSTEM_PROMPT, FREE_MODE_SYSTEM_PROMPT
    from prompt_builder_plan_sections import append_generated_motif_section, append_plan_sections
    from prompt_builder_sketch import build_arrangement_context
    from prompt_builder_utils import (
        MIN_BARS_COUNT,
        UNKNOWN_VALUE,
        build_generation_progress,
        build_orchestration_hints_prompt,
        estimate_note_count,
        extract_key_from_chord_map,
        extract_role_from_plan,
        format_profile_for_prompt,
        format_profile_user_template,
        get_custom_curves_info,
        import_music_notation,
        infer_key_from_plan_chord_map,
        is_non_empty_list,
        normalize_lower,
        normalize_text,
        resolve_prompt_articulation,
        resolve_prompt_pitch_range,
    )
    from style import DYNAMICS_HINTS, MOOD_HINTS
    from type import TYPE_HINTS
    from utils import safe_format
except ImportError:
    from .constants import (
        DEFAULT_GENERATION_STYLE,
        DEFAULT_GENERATION_TYPE,
        MIDI_CHAN_MIN,
        WIND_BRASS_FAMILIES,
        WIND_BRASS_MAX_NOTE_DUR_Q,
    )
    from .context_builder import (
        build_chord_map_from_sketch,
        build_context_summary,
        build_ensemble_context,
        get_quarters_per_bar,
    )
    from .models import GenerateRequest
    from .music_theory import get_scale_note_names
    from .promts import BASE_SYSTEM_PROMPT, FREE_MODE_SYSTEM_PROMPT
    from .prompt_builder_plan_sections import append_generated_motif_section, append_plan_sections
    from .prompt_builder_sketch import build_arrangement_context
    from .prompt_builder_utils import (
        MIN_BARS_COUNT,
        UNKNOWN_VALUE,
        build_generation_progress,
        build_orchestration_hints_prompt,
        estimate_note_count,
        extract_key_from_chord_map,
        extract_role_from_plan,
        format_profile_for_prompt,
        format_profile_user_template,
        get_custom_curves_info,
        import_music_notation,
        infer_key_from_plan_chord_map,
        is_non_empty_list,
        normalize_lower,
        normalize_text,
        resolve_prompt_articulation,
        resolve_prompt_pitch_range,
    )
    from .style import DYNAMICS_HINTS, MOOD_HINTS
    from .type import TYPE_HINTS
    from .utils import safe_format


FREE_MODE_MIN_NOTES = 1
FREE_MODE_MAX_NOTES = 999
UNKNOWN_ROLE_LABEL = "UNKNOWN"
ZERO_FLOAT = 0.0
ZERO_INT = 0
SELECTION_QUARTERS_PRECISION = 4
SELECTION_LENGTH_PRECISION = 3
MUSICAL_LENGTH_PRECISION = 1
TEMPO_LENGTH_PRECISION = 2
GENERATION_ORDER_DEFAULT = 0
GENERATION_ORDER_FIRST = 1
PATTERN_BARS_THRESHOLD = 4
REPETITIVE_TYPES = ("ostinato", "rhythm", "accomp", "arpeggio", "bass")
PERCUSSION_FAMILIES = ("drums", "percussion", "perc")
DEFAULT_MOOD_HINT_TEMPLATE = "STYLE: {style}. CHARACTER: Create a part in this style."
DEFAULT_DYNAMICS_HINT = "EXPRESSION: Follow phrase shape. DYNAMICS: Natural breathing."
DEFAULT_TYPE_HINT_TEMPLATE = "ROLE: Generate a {generation_type} part. OBJECTIVE: Musical, memorable, fitting."


def build_selection_info(length_q: float, quarters_per_bar: float, bars: int) -> List[str]:
    length_q = max(ZERO_FLOAT, float(length_q or ZERO_FLOAT))
    length_hint = round(length_q, SELECTION_LENGTH_PRECISION)

    return [
        "### SELECTION (working area)",
        f"- Available range: {bars} bars (start_q 0 to {length_hint} quarter notes)",
        "- Time axis: notes use start_q, curves use time_q (quarter notes from selection start)",
        "- How much of this range to fill is YOUR creative decision based on user request and context",
        "- RECOMMENDATION: Plan the musical development (intro, theme, resolution) to fit within the available range",
        "- Consider using the full selection for complete compositions; shorter portions for fragments or phrases",
        "- Patterns/repeats can help keep JSON concise for repeating figures",
    ]


def build_pattern_guidance(profile: Dict[str, Any], generation_type: str, bars: int) -> List[str]:
    is_drum = bool(profile.get("midi", {}).get("is_drum", False))
    family = normalize_lower(profile.get("family", ""))
    gen_lower = normalize_lower(generation_type or "")

    is_percussion_family = family in PERCUSSION_FAMILIES
    is_repetitive_type = any(t in gen_lower for t in REPETITIVE_TYPES)

    try:
        bars_int = int(bars)
    except (TypeError, ValueError):
        bars_int = ZERO_INT

    if not (is_drum or is_percussion_family or is_repetitive_type or bars_int >= PATTERN_BARS_THRESHOLD):
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

        generation_order = int(request.ensemble.generation_order or GENERATION_ORDER_DEFAULT)
        if generation_order > GENERATION_ORDER_FIRST:
            return [
                "### TEMPO/TIME SIGNATURE CHANGES",
                "Tempo and time signature changes are already defined by an earlier part.",
                "DO NOT output tempo_markers for this response.",
            ]

    length_hint = round(float(length_q or ZERO_FLOAT), TEMPO_LENGTH_PRECISION)
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
        'FORMAT: tempo_markers: [{"time_q": 0, "bpm": 85, "num": 3, "denom": 4}, ...]',
        "",
        "FIELDS:",
        f"- time_q: position in quarter notes (0..{length_hint})",
        "- bpm: tempo in beats per minute (REQUIRED at time_q=0 to set initial tempo)",
        "- num/denom: time signature (e.g. num:6, denom:8 for 6/8)",
        "- linear: true for gradual tempo ramp, false for instant change",
        "",
        "EXAMPLES:",
        '- Set tempo: [{"time_q": 0, "bpm": 72}]',
        '- Set tempo + time sig: [{"time_q": 0, "bpm": 90, "num": 6, "denom": 8}]',
        '- Accelerando: [{"time_q": 0, "bpm": 60}, {"time_q": 24, "bpm": 100, "linear": true}]',
        '- Ritardando at end: [{"time_q": 0, "bpm": 120}, {"time_q": 48, "bpm": 80, "linear": true}]',
        "",
        "COMMON TIME SIGNATURES: 4/4, 3/4, 2/4, 6/8, 12/8, 5/4, 7/8",
        "Keep markers in ascending order. Max 4-6 markers.",
    ]
    if request.ensemble and request.ensemble.is_sequential:
        lines.append("")
        lines.append("IMPORTANT: Only output tempo_markers for the FIRST instrument in sequential generation.")
    return lines


def build_musical_context_lines(
    final_key: str,
    scale_notes: str,
    bpm: float,
    time_sig: str,
    bars: int,
    length_q: float,
    selection_info: List[str],
    include_scale_notes: bool,
) -> List[str]:
    lines = [
        "### MUSICAL CONTEXT",
        f"- Key: {final_key}",
    ]
    if include_scale_notes:
        lines.append(f"- Scale notes: {scale_notes}")
    lines.extend([
        f"- Tempo: {bpm} BPM, Time: {time_sig}",
        f"- Length: {bars} bars ({round(length_q, MUSICAL_LENGTH_PRECISION)} quarter notes)",
        "",
        *selection_info,
    ])
    return lines


def build_instrument_profile_lines(profile_info: str) -> List[str]:
    return [
        "### INSTRUMENT PROFILE",
        profile_info,
    ]


def build_free_mode_prompt_parts(
    profile: Dict[str, Any],
    profile_user_formatted: str,
    custom_curves_info: str,
    profile_info: str,
    final_key: str,
    scale_notes: str,
    bpm: float,
    time_sig: str,
    bars: int,
    length_q: float,
    selection_info: List[str],
    is_ensemble: bool,
) -> List[str]:
    user_prompt_parts = [
        f"## FREE MODE COMPOSITION for {profile.get('name', 'instrument')}",
    ]

    if profile_user_formatted:
        user_prompt_parts.extend([
            "",
            "### !!! CRITICAL INSTRUMENT RULES - READ FIRST !!!",
            profile_user_formatted,
        ])
    if custom_curves_info:
        if not profile_user_formatted:
            user_prompt_parts.extend([
                "",
                "### INSTRUMENT CURVES",
            ])
        user_prompt_parts.append(
            f"Additional curves (optional unless instrument rules say otherwise): {custom_curves_info}"
        )

    user_prompt_parts.extend([
        "",
        "YOU DECIDE: Choose the best generation type, style, and articulations for this context.",
        "IMPORTANT: Match your output complexity to what the user requests. Simple request = simple output.",
        "",
        *build_instrument_profile_lines(profile_info),
        "",
        *build_musical_context_lines(
            final_key,
            scale_notes,
            bpm,
            time_sig,
            bars,
            length_q,
            selection_info,
            include_scale_notes=True,
        ),
    ])

    user_prompt_parts.extend([
        "",
        "Note: Use Expression curve for overall section dynamics, Dynamics curve for note-level shaping. For SHORT articulations, velocity is primary.",
    ])

    orchestration_hints_prompt = build_orchestration_hints_prompt(profile, is_ensemble)
    if orchestration_hints_prompt:
        user_prompt_parts.append("")
        user_prompt_parts.append(orchestration_hints_prompt)

    return user_prompt_parts


def build_compose_role_prompt_parts(
    profile: Dict[str, Any],
    role_upper: str,
    role_detail: str,
    profile_info: str,
    final_key: str,
    bpm: float,
    time_sig: str,
    bars: int,
    length_q: float,
    selection_info: List[str],
) -> List[str]:
    user_prompt_parts = [
        f"## COMPOSE: {role_upper} for {profile.get('name', 'instrument')}",
        "",
        f"### YOUR ROLE (from plan): {role_upper}",
    ]
    if role_detail:
        user_prompt_parts.append(role_detail)
    user_prompt_parts.extend([
        "",
        *build_instrument_profile_lines(profile_info),
        "",
        *build_musical_context_lines(
            final_key,
            "",
            bpm,
            time_sig,
            bars,
            length_q,
            selection_info,
            include_scale_notes=False,
        ),
    ])
    return user_prompt_parts


def build_compose_type_prompt_parts(
    profile: Dict[str, Any],
    generation_style: str,
    generation_type: str,
    type_hint: str,
    mood_hint: str,
    dynamics_hint: str,
    profile_info: str,
    final_key: str,
    scale_notes: str,
    bpm: float,
    time_sig: str,
    bars: int,
    length_q: float,
    selection_info: List[str],
) -> List[str]:
    user_prompt_parts = [
        f"## COMPOSE: {generation_style.upper()} {generation_type.upper()} for {profile.get('name', 'instrument')}",
        "",
        *build_instrument_profile_lines(profile_info),
        "",
        "### GENERATION TARGET (WHAT TO BUILD)",
        f"1. PART TYPE ({generation_type}):",
        type_hint,
        "",
        f"2. STYLE ({generation_style}):",
        mood_hint,
        "",
        "3. DYNAMICS GOAL:",
        dynamics_hint,
        "",
        *build_musical_context_lines(
            final_key,
            scale_notes,
            bpm,
            time_sig,
            bars,
            length_q,
            selection_info,
            include_scale_notes=True,
        ),
    ]
    return user_prompt_parts


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
    is_multi_instrument = bool(request.ensemble and request.ensemble.total_instruments > 1)
    is_arrangement_mode = bool(ensemble and ensemble.arrangement_mode)
    plan_data = ensemble.plan if (ensemble and isinstance(ensemble.plan, dict)) else {}
    plan_chord_map = plan_data.get("chord_map") if isinstance(plan_data, dict) else None
    has_plan_chord_map = is_non_empty_list(plan_chord_map)
    is_compose_ensemble = bool(
        ensemble
        and not is_arrangement_mode
        and ((ensemble.plan_summary or "").strip() or has_plan_chord_map)
    )

    if request.free_mode:
        generation_type = ""
        min_notes, max_notes = FREE_MODE_MIN_NOTES, FREE_MODE_MAX_NOTES
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
        "selection_quarters": round(length_q, SELECTION_QUARTERS_PRECISION),
        "range_absolute": abs_range,
        "range_preferred": pref_range,
        "preset_name": preset_name or "",
        "preset_settings": json.dumps(preset_settings, ensure_ascii=False),
        "polyphony": profile.get("midi", {}).get("polyphony", ""),
        "is_drum": profile.get("midi", {}).get("is_drum", False),
        "channel": profile.get("midi", {}).get("channel", MIDI_CHAN_MIN),
        "generation_type": generation_type,
        "min_notes": min_notes,
        "max_notes": max_notes,
    }

    profile_user_formatted = format_profile_user_template(profile_user, values)
    _custom_curves, custom_curves_info = get_custom_curves_info(profile)

    midi_channel = profile.get("midi", {}).get("channel", MIDI_CHAN_MIN)
    pitch_low, pitch_high = resolve_prompt_pitch_range(pref_range)

    articulation = resolve_prompt_articulation(profile, preset_settings)

    system_base = FREE_MODE_SYSTEM_PROMPT if request.free_mode else BASE_SYSTEM_PROMPT
    system_prompt = "\n\n".join([p for p in (system_base, safe_format(profile_system, values)) if p])

    skip_auto_harmony = is_arrangement_mode or has_plan_chord_map

    context_summary, detected_key, _position = build_context_summary(
        request.context,
        request.music.time_sig,
        length_q,
        request.music.key,
        skip_auto_harmony=skip_auto_harmony,
        target_profile=profile,
    )

    final_key = request.music.key
    if final_key == UNKNOWN_VALUE and detected_key != UNKNOWN_VALUE:
        final_key = detected_key
    if final_key == UNKNOWN_VALUE and has_plan_chord_map:
        inferred_key = extract_key_from_chord_map(plan_chord_map)
        if inferred_key == UNKNOWN_VALUE:
            inferred_key = infer_key_from_plan_chord_map(plan_chord_map)
        if inferred_key != UNKNOWN_VALUE:
            final_key = inferred_key

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(MIN_BARS_COUNT, int(length_q / quarters_per_bar))
    selection_info = build_selection_info(length_q, quarters_per_bar, bars)

    scale_notes = get_scale_note_names(final_key)
    profile_info = format_profile_for_prompt(profile)

    if request.free_mode:
        user_prompt_parts = build_free_mode_prompt_parts(
            profile,
            profile_user_formatted,
            custom_curves_info,
            profile_info,
            final_key,
            scale_notes,
            request.music.bpm,
            request.music.time_sig,
            bars,
            length_q,
            selection_info,
            is_multi_instrument,
        )
    else:
        is_compose_or_arrange = is_compose_ensemble or is_arrangement_mode
        if is_compose_or_arrange and ensemble and isinstance(ensemble.current_instrument, dict):
            current_track = normalize_text(ensemble.current_instrument.get("track_name"))
            current_profile_name_str = normalize_text(ensemble.current_instrument.get("profile_name"))

            current_role = normalize_text(ensemble.current_instrument.get("role"))
            if not current_role or normalize_lower(current_role) == UNKNOWN_VALUE:
                current_role = extract_role_from_plan(plan_data, current_profile_name_str, current_track)

            current_role_upper = (
                current_role.upper() if current_role and normalize_lower(current_role) != UNKNOWN_VALUE else UNKNOWN_ROLE_LABEL
            )

            current_track_lower = normalize_lower(current_track)
            current_profile_name_lower = normalize_lower(current_profile_name_str)
            role_guidance_list = plan_data.get("role_guidance") if isinstance(plan_data, dict) else None
            role_detail = ""
            if is_non_empty_list(role_guidance_list):
                profile_name_lower = normalize_lower(profile.get("name", ""))
                for entry in role_guidance_list:
                    if not isinstance(entry, dict):
                        continue
                    inst_name = normalize_lower(entry.get("instrument"))
                    if not inst_name:
                        continue
                    if inst_name in (current_track_lower, current_profile_name_lower) or inst_name == profile_name_lower:
                        guidance = normalize_text(entry.get("guidance"))
                        relationship = normalize_text(entry.get("relationship"))
                        register = normalize_text(entry.get("register"))
                        details = []
                        if register:
                            details.append(f"Register: {register}")
                        if guidance:
                            details.append(guidance)
                        if relationship:
                            details.append(f"Relationship: {relationship}")
                        role_detail = "\n".join(details).strip()
                        break

            user_prompt_parts = build_compose_role_prompt_parts(
                profile,
                current_role_upper,
                role_detail,
                profile_info,
                final_key,
                request.music.bpm,
                request.music.time_sig,
                bars,
                length_q,
                selection_info,
            )
        else:
            generation_style = request.generation_style or DEFAULT_GENERATION_STYLE
            style_lower = generation_style.lower()
            mood_hint = MOOD_HINTS.get(style_lower, DEFAULT_MOOD_HINT_TEMPLATE.format(style=generation_style))
            dynamics_hint = DYNAMICS_HINTS.get(
                style_lower,
                DYNAMICS_HINTS.get("default", DEFAULT_DYNAMICS_HINT),
            )
            gen_lower = generation_type.lower()
            type_hint = TYPE_HINTS.get(
                gen_lower,
                DEFAULT_TYPE_HINT_TEMPLATE.format(generation_type=generation_type),
            )
            user_prompt_parts = build_compose_type_prompt_parts(
                profile,
                generation_style,
                generation_type,
                type_hint,
                mood_hint,
                dynamics_hint,
                profile_info,
                final_key,
                scale_notes,
                request.music.bpm,
                request.music.time_sig,
                bars,
                length_q,
                selection_info,
            )

    if context_summary:
        user_prompt_parts.append("")
        user_prompt_parts.append(context_summary)

    ensemble_context = build_ensemble_context(
        request.ensemble,
        profile.get("name", ""),
        request.music.time_sig,
        length_q,
        has_plan_chord_map=has_plan_chord_map,
    )
    if ensemble_context:
        user_prompt_parts.append("")
        user_prompt_parts.append(ensemble_context)

    if is_arrangement_mode:
        arrangement_context = build_arrangement_context(
            request.ensemble,
            profile.get("name", ""),
            request.music.time_sig,
            length_q,
        )
        if arrangement_context:
            user_prompt_parts.append("")
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
        current_inst = request.ensemble.current_instrument if request.ensemble else None
        current_family = normalize_lower(current_inst.get("family", "")) if current_inst else ""

        append_plan_sections(
            user_prompt_parts,
            plan_data,
            plan_summary,
            is_arrangement_mode,
            sketch_chord_map_str,
            plan_chord_map,
            pitch_low,
            pitch_high,
            current_family,
        )

        generated_motif = request.ensemble.generated_motif if request.ensemble else None
        current_role = request.ensemble.current_instrument.get("role", "") if request.ensemble.current_instrument else ""
        append_generated_motif_section(user_prompt_parts, generated_motif, current_role)

    midi_to_note, _dur_q_to_name, _velocity_to_dynamic = import_music_notation()

    pitch_low_note = midi_to_note(pitch_low)
    pitch_high_note = midi_to_note(pitch_high)

    family = normalize_lower(profile.get("family", ""))
    is_wind_brass = family in WIND_BRASS_FAMILIES
    wind_brass_max_dur = int(WIND_BRASS_MAX_NOTE_DUR_Q)
    max_dur_hint = (
        f"- MAX NOTE DURATION: {wind_brass_max_dur} beats (~2 bars) for wind/brass - split longer notes with breath rests"
        if is_wind_brass else ""
    )

    if request.free_mode:
        free_mode_rules = [
            "",
            "### COMPOSITION RULES",
            f"- ALLOWED RANGE: {pitch_low_note} to {pitch_high_note}",
            f"- Channel: {midi_channel}",
            "- Generate appropriate number of notes for the part type",
        ]
        if max_dur_hint:
            free_mode_rules.append(max_dur_hint)
        user_prompt_parts.extend(free_mode_rules)

        user_prompt_parts.extend([
            "",
            "### YOUR CREATIVE CHOICES",
            "- Choose generation TYPE based on user request or context (Melody, Arpeggio, Chords, Pad, Bass, etc.)",
            "- Choose STYLE that fits (Heroic, Romantic, Dark, Cinematic, etc.)",
            "- Articulations: use ONE for simple parts (pads, chords), MULTIPLE only for expressive melodic parts",
            "",
            "### THREE-LAYER DYNAMICS",
            "1. DYNAMICS (dyn): Note attack intensity - p, mp, mf, f, ff",
            "2. EXPRESSION CURVE: GLOBAL section envelope (CC11)",
            "3. DYNAMICS CURVE: Section dynamics shape (CC1)",
            "",
            "DYNAMICS CURVE (CC1) - CRITICAL:",
            "- Values: 40-127 (40=pp, 64=mp, 80=mf, 100=f, 120=ff)",
            "- SMOOTH transitions - max jump 20 between points",
            "- 4-8 breakpoints covering the full piece length",
            "- Follow DYNAMIC ARC from composition plan",
        ])
    else:
        short_articulations = profile.get("articulations", {}).get("short_articulations", [])
        is_short_art = bool(articulation) and normalize_lower(articulation) in [normalize_lower(a) for a in short_articulations]
        velocity_hint = (
            "Use dyn for note-to-note dynamics (accents: f-fff, normal: mf-f, soft: p-mp)"
            if is_short_art else
            "Vary dynamics for phrase shaping (peaks: f-ff, between: mf)"
        )

        composition_rules = [
            "",
            "### COMPOSITION RULES",
            f"- ALLOWED RANGE: {pitch_low_note} to {pitch_high_note}",
            f"- Suggested note count: {min_notes}-{max_notes} (adapt based on musical needs)",
            f"- Channel: {midi_channel}",
        ]
        if articulation:
            composition_rules.append(f"- Articulation: {articulation}")
        if max_dur_hint:
            composition_rules.append(max_dur_hint)
        user_prompt_parts.extend(composition_rules)

        user_prompt_parts.extend([
            "",
            "### THREE-LAYER DYNAMICS",
            f"1. DYNAMICS: {velocity_hint}",
            "2. EXPRESSION CURVE: GLOBAL section envelope",
            "3. DYNAMICS CURVE: PER-NOTE breathing (cresc/decresc/swell for each sustained note)",
            "",
            "DYNAMICS CURVE (CC1): Provide 4-8 breakpoints with SMOOTH transitions (max jump 20)",
        ])

    tempo_guidance = build_tempo_change_guidance(request, length_q)
    if tempo_guidance:
        user_prompt_parts.append("")
        user_prompt_parts.extend(tempo_guidance)

    pattern_guidance = build_pattern_guidance(profile, generation_type, bars)
    if pattern_guidance:
        user_prompt_parts.append("")
        user_prompt_parts.extend(pattern_guidance)

    user_prompt_text = normalize_text(request.user_prompt)
    if user_prompt_text:
        user_prompt_parts.append("")
        user_prompt_parts.append("### USER REQUEST (PRIORITY - follow these instructions, they override defaults):")
        user_prompt_parts.append(user_prompt_text)
        user_prompt_parts.append("")
        user_prompt_parts.append("INTERPRET USER REQUEST:")
        user_prompt_parts.append("- If user asks for 'simple', 'basic', 'straightforward' → create simple, clean output")
        user_prompt_parts.append("- If user mentions dynamics (crescendo, forte, soft, etc.) → apply to Expression curve for overall, Dynamics curve for detail")
        user_prompt_parts.append("- If user forbids spikes or caps max dynamics (e.g. 'cap at f, no ff') → enforce strictly in velocity/CC (no sfz, no sudden accents, no abrupt jumps)")
        user_prompt_parts.append("- If user mentions a composer style (Zimmer, Williams, etc.) → match their typical approach")
        user_prompt_parts.append("- If user asks for chords/pads → use sustained notes, minimal articulation changes")

    if not request.free_mode:
        if profile_user_formatted:
            user_prompt_parts.extend([
                "",
                "### INSTRUMENT-SPECIFIC RULES:",
                profile_user_formatted,
            ])

        if custom_curves_info:
            user_prompt_parts.extend([
                "",
                "### INSTRUMENT CURVES (use these curve names):",
                f"{custom_curves_info}",
            ])

    if request.free_mode and is_multi_instrument:
        user_prompt_parts.extend([
            "",
            "### HANDOFF REQUIREMENT (MANDATORY for ensemble)",
            "You MUST include a 'handoff' object in your JSON response.",
            "This helps the next musician understand your contribution and find their place.",
            "Focus on: what space you occupied, what you left open, and advice for the next instrument.",
        ])

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
