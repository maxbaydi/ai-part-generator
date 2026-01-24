from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from constants import DEFAULT_PITCH
    from context_builder import analyze_harmony_progression, build_context_summary, get_quarters_per_bar
    from models import ArrangeRequest, GenerateRequest
    from music_theory import pitch_to_note
    from prompt_builder_sketch import format_sketch_cc_segments, format_sketch_notes
    from prompt_builder_utils import MIN_BARS_COUNT, UNKNOWN_VALUE, normalize_text
    from promts import ARRANGEMENT_PLAN_SYSTEM_PROMPT, COMPOSITION_PLAN_SYSTEM_PROMPT
    from text_utils import fix_mojibake
except ImportError:
    from .constants import DEFAULT_PITCH
    from .context_builder import analyze_harmony_progression, build_context_summary, get_quarters_per_bar
    from .models import ArrangeRequest, GenerateRequest
    from .music_theory import pitch_to_note
    from .prompt_builder_sketch import format_sketch_cc_segments, format_sketch_notes
    from .prompt_builder_utils import MIN_BARS_COUNT, UNKNOWN_VALUE, normalize_text
    from .promts import ARRANGEMENT_PLAN_SYSTEM_PROMPT, COMPOSITION_PLAN_SYSTEM_PROMPT
    from .text_utils import fix_mojibake

UNKNOWN_LABEL = "Unknown"
DESCRIPTION_MAX_LEN = 100
MUSICAL_LENGTH_PRECISION = 1


def build_plan_prompt(request: GenerateRequest, length_q: float) -> Tuple[str, str]:
    system_prompt = COMPOSITION_PLAN_SYSTEM_PROMPT

    context_summary, detected_key, _ = build_context_summary(
        request.context, request.music.time_sig, length_q, request.music.key
    )
    final_key = request.music.key
    if final_key == UNKNOWN_VALUE and detected_key != UNKNOWN_VALUE:
        final_key = detected_key

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(MIN_BARS_COUNT, int(length_q / quarters_per_bar))

    user_prompt_parts = [
        "## COMPOSITION PLAN",
        "Create a detailed musical blueprint for this multi-instrument piece.",
        "",
        "### MUSICAL CONTEXT",
        f"- Key: {final_key}",
        f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
        f"- Length: {bars} bars ({round(length_q, MUSICAL_LENGTH_PRECISION)} quarter notes)",
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
                name = track or profile_name or UNKNOWN_LABEL
            family = inst.family or UNKNOWN_VALUE
            description = inst.description or ""
            range_info = inst.range or {}
            preferred_range = range_info.get("preferred", [])

            detail_parts = [f"family: {family}"]
            if preferred_range:
                detail_parts.append(f"range: {preferred_range[0]}-{preferred_range[1]}")
            detail = ", ".join(detail_parts)

            user_prompt_parts.append(f"- {inst.index}. **{name}** ({detail})")
            if description:
                user_prompt_parts.append(f"    Description: {description[:DESCRIPTION_MAX_LEN]}")

        user_prompt_parts.append("")
        user_prompt_parts.append("PLANNING TASKS:")
        user_prompt_parts.append("1. Assign ROLE to each instrument (melody/bass/harmony/rhythm/countermelody/pad)")
        user_prompt_parts.append("   - Include instrument_index and instrument name in role_guidance")
        user_prompt_parts.append("   - Provide register + guidance + relationship for each instrument")
        user_prompt_parts.append("2. Define REGISTER allocation to avoid clashes")
        user_prompt_parts.append("3. Plan HARMONIC framework (chord progression style)")
        user_prompt_parts.append("4. Describe MOTIF or musical idea to develop")
        user_prompt_parts.append("5. Order instruments by GENERATION PRIORITY (bass/rhythm first, melody second, etc.)")

        if request.allow_tempo_changes:
            user_prompt_parts.append("")
            user_prompt_parts.append("### TEMPO/TIME SIGNATURE CONTROL")
            user_prompt_parts.append("You have FULL control over tempo and time signature if the user request implies it.")
            user_prompt_parts.append("Set initial_bpm and time_sig accordingly. These will be applied after all parts.")

    user_prompt_text = normalize_text(fix_mojibake(request.user_prompt))
    if user_prompt_text:
        user_prompt_parts.append("")
        user_prompt_parts.append("### USER REQUEST (this is the main creative direction)")
        user_prompt_parts.append(user_prompt_text)
        user_prompt_parts.append("")
        user_prompt_parts.append("Interpret the user's request and plan a composition that fulfills their vision.")

    user_prompt_parts.extend([
        "",
        "### OUTPUT (valid JSON only):",
    ])

    user_prompt = "\n".join(user_prompt_parts)
    return system_prompt, user_prompt


def build_arrange_plan_prompt(request: ArrangeRequest, length_q: float) -> Tuple[str, str]:
    system_prompt = ARRANGEMENT_PLAN_SYSTEM_PROMPT

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(MIN_BARS_COUNT, int(length_q / quarters_per_bar))

    sketch_notes = request.source_sketch.notes if request.source_sketch else []
    sketch_track_name = request.source_sketch.track_name if request.source_sketch else UNKNOWN_LABEL
    sketch_cc_events = request.source_sketch.cc_events if request.source_sketch else []
    cc_formatted, cc_controllers = format_sketch_cc_segments(sketch_cc_events or [], length_q)

    pitches = [n.get("pitch", DEFAULT_PITCH) for n in sketch_notes] if sketch_notes else [DEFAULT_PITCH]
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
        f"- Length: {bars} bars ({round(length_q, MUSICAL_LENGTH_PRECISION)} quarter notes)",
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
                name = track or profile_name or UNKNOWN_LABEL
            family = inst.family or UNKNOWN_VALUE
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

    user_prompt_text = normalize_text(request.user_prompt)
    if user_prompt_text:
        user_prompt_parts.append("")
        user_prompt_parts.append("### USER REQUEST (style guidance for the arrangement)")
        user_prompt_parts.append(user_prompt_text)

    user_prompt_parts.extend([
        "",
        "### OUTPUT (valid JSON only):",
    ])

    user_prompt = "\n".join(user_prompt_parts)
    return system_prompt, user_prompt
