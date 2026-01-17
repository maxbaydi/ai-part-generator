from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from constants import DEFAULT_PITCH, DEFAULT_VELOCITY
    from prompt_builder_utils import (
        UNKNOWN_VALUE,
        get_chord_tones_from_name,
        import_music_notation,
        import_note_to_midi,
        is_non_empty_list,
        normalize_lower,
        normalize_text,
    )
except ImportError:
    from .constants import DEFAULT_PITCH, DEFAULT_VELOCITY
    from .prompt_builder_utils import (
        UNKNOWN_VALUE,
        get_chord_tones_from_name,
        import_music_notation,
        import_note_to_midi,
        is_non_empty_list,
        normalize_lower,
        normalize_text,
    )


TREND_SYMBOLS = {
    "building": "↗",
    "climax": "★",
    "fading": "↘",
    "resolving": "↓",
    "stable": "→",
}
STRONG_ACCENT = "strong"
MEDIUM_ACCENT = "medium"
ACCENT_STRONG_LIMIT = 12
ACCENT_MEDIUM_LIMIT = 8
MOTIF_NOTES_LIMIT = 12
NOTES_PREVIEW_LIMIT = 6
OCTAVE_MIN = 1
OCTAVE_MAX_EXCLUSIVE = 8
OCTAVE_BASE_OFFSET = 1
SEMITONES_PER_OCTAVE = 12
INTERVAL_ARROW = " → "

ROLE_MELODY = "melody"
ROLE_BASS = "bass"
ROLE_HARMONY = "harmony"
ROLE_PAD = "pad"
ROLE_COUNTERMELODY = "countermelody"
DEFAULT_BAR = 1
DEFAULT_BEAT = 1
DEFAULT_DYNAMIC_LEVEL = "mf"
DEFAULT_TREND = "stable"
DEFAULT_TEXTURE_DENSITY = "medium"
DEFAULT_PHRASE_NAME = "phrase"
DEFAULT_MOTIF_SOURCE = "melody"
DEFAULT_START_Q = 0
DEFAULT_NOTE_DUR_Q = 1.0
MIN_INTERVAL_NOTES = 2
INTERVAL_START_INDEX = 1


def format_interval_list(intervals: List[Any]) -> str:
    int_vals = []
    for i in intervals:
        try:
            int_vals.append(int(i))
        except (TypeError, ValueError):
            continue
    if not int_vals:
        return ""
    return ", ".join(f"{v:+d}" for v in int_vals)


def format_rhythm_pattern(rhythm: List[Any], dur_q_to_name) -> str:
    try:
        rhythm_names = [dur_q_to_name(float(r), abbrev=False) for r in rhythm]
    except (TypeError, ValueError):
        return ""
    return INTERVAL_ARROW.join(rhythm_names)


def append_plan_sections(
    user_prompt_parts: List[str],
    plan_data: Dict[str, Any],
    plan_summary: str,
    is_arrangement_mode: bool,
    sketch_chord_map_str: str,
    chord_map: Optional[List[Dict[str, Any]]],
    pitch_low: int,
    pitch_high: int,
    current_family: str,
) -> None:
    section_overview = plan_data.get("section_overview") if isinstance(plan_data, dict) else None
    role_guidance = plan_data.get("role_guidance") if isinstance(plan_data, dict) else None
    phrase_structure = plan_data.get("phrase_structure") if isinstance(plan_data, dict) else None
    accent_map = plan_data.get("accent_map") if isinstance(plan_data, dict) else None
    motif_blueprint = plan_data.get("motif_blueprint") if isinstance(plan_data, dict) else None

    has_plan_content = plan_summary or section_overview or role_guidance or phrase_structure
    if not (has_plan_content or sketch_chord_map_str):
        return

    user_prompt_parts.append("")
    user_prompt_parts.append("### COMPOSITION PLAN (MANDATORY - FOLLOW EXACTLY)")
    if plan_summary:
        user_prompt_parts.append(plan_summary)

    if is_arrangement_mode and sketch_chord_map_str:
        user_prompt_parts.append("")
        user_prompt_parts.append("**CHORD MAP (AUTO-DETECTED FROM SKETCH - MANDATORY):**")
        user_prompt_parts.append(sketch_chord_map_str)
        user_prompt_parts.append("This harmonic structure was detected from the source sketch.")
        user_prompt_parts.append("Use it as the harmonic foundation for your arrangement.")
    elif is_non_empty_list(chord_map):
        midi_to_note, _dur_q_to_name, _velocity_to_dynamic = import_music_notation()

        user_prompt_parts.append("")
        user_prompt_parts.append("**CHORD MAP (MANDATORY - USE THESE EXACT NOTES):**")
        user_prompt_parts.append("```")
        user_prompt_parts.append("Bar.Beat | Chord        | Notes for YOUR range")
        user_prompt_parts.append("---------|--------------|---------------------")
        for chord_entry in chord_map:
            if not isinstance(chord_entry, dict):
                continue
            bar = chord_entry.get("bar", DEFAULT_BAR)
            beat = chord_entry.get("beat", DEFAULT_BEAT)
            chord = chord_entry.get("chord", "?")
            roman = chord_entry.get("roman", "")
            chord_tones = chord_entry.get("chord_tones", [])

            if not chord_tones and chord != "?":
                chord_tones = get_chord_tones_from_name(chord)

            notes_in_range = []
            for pc in chord_tones:
                try:
                    pc_int = int(pc) % SEMITONES_PER_OCTAVE
                except (TypeError, ValueError):
                    continue
                for octave in range(OCTAVE_MIN, OCTAVE_MAX_EXCLUSIVE):
                    midi_pitch = pc_int + (octave + OCTAVE_BASE_OFFSET) * SEMITONES_PER_OCTAVE
                    if pitch_low <= midi_pitch <= pitch_high:
                        notes_in_range.append(midi_to_note(midi_pitch))
                        break

            notes_str = ", ".join(notes_in_range[:NOTES_PREVIEW_LIMIT]) if notes_in_range else chord
            chord_label = f"{chord} ({roman})" if roman else chord
            user_prompt_parts.append(f"{bar}.{beat:<4}    | {chord_label:<12} | {notes_str}")
        user_prompt_parts.append("```")
        user_prompt_parts.append("")
        user_prompt_parts.append("Use this harmonic structure. How you use it depends on the musical context and style.")

    dynamic_arc = plan_data.get("dynamic_arc") if isinstance(plan_data, dict) else None
    if is_non_empty_list(dynamic_arc):
        user_prompt_parts.append("")
        user_prompt_parts.append("**DYNAMIC ARC (MANDATORY - FOLLOW THIS INTENSITY CURVE):**")
        user_prompt_parts.append("```")
        user_prompt_parts.append("Bar   | Dynamics | Trend")
        user_prompt_parts.append("------|----------|-------")
        for dyn_entry in dynamic_arc:
            if not isinstance(dyn_entry, dict):
                continue
            bar = dyn_entry.get("bar", DEFAULT_BAR)
            level = dyn_entry.get("level", DEFAULT_DYNAMIC_LEVEL)
            trend = dyn_entry.get("trend", DEFAULT_TREND)
            trend_arrow = TREND_SYMBOLS.get(trend, TREND_SYMBOLS[DEFAULT_TREND])
            user_prompt_parts.append(f"Bar {bar:<2} | {level:<8} | {trend_arrow} {trend}")
        user_prompt_parts.append("```")
        user_prompt_parts.append("DYNAMIC ARC RULES:")
        user_prompt_parts.append("- Match the dynamics level at each bar")
        user_prompt_parts.append("- 'building': gradually increase intensity toward next point")
        user_prompt_parts.append("- 'climax': peak intensity, strongest notes")
        user_prompt_parts.append("- 'fading'/'resolving': decrease intensity")

    texture_map = plan_data.get("texture_map") if isinstance(plan_data, dict) else None
    current_family_lower = normalize_lower(current_family)
    if is_non_empty_list(texture_map):
        user_prompt_parts.append("")
        user_prompt_parts.append("**TEXTURE MAP (WHEN TO PLAY/REST):**")
        for tex_entry in texture_map:
            if not isinstance(tex_entry, dict):
                continue
            tex_bars = tex_entry.get("bars", "")
            density = tex_entry.get("density", DEFAULT_TEXTURE_DENSITY)
            active_fam = tex_entry.get("active_families", [])
            tacet_fam = tex_entry.get("tacet_families", [])
            tex_type = tex_entry.get("texture_type", "")
            notes_hint = tex_entry.get("notes_per_bar_hint", "")

            active_fam_lower = [normalize_lower(f) for f in active_fam]
            tacet_fam_lower = [normalize_lower(f) for f in tacet_fam]
            is_active = not active_fam_lower or current_family_lower in active_fam_lower
            is_tacet = current_family_lower in tacet_fam_lower

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

    if is_non_empty_list(phrase_structure):
        user_prompt_parts.append("")
        user_prompt_parts.append("**PHRASE STRUCTURE (BREATHING & CADENCES):**")
        for phrase in phrase_structure:
            if not isinstance(phrase, dict):
                continue
            name = phrase.get("name", DEFAULT_PHRASE_NAME)
            bars = phrase.get("bars", "")
            function = phrase.get("function", "")
            cadence = phrase.get("cadence", {})
            breathing = phrase.get("breathing_points", [])
            breathe_at = phrase.get("breathe_at", [])
            climax = phrase.get("climax_point", phrase.get("climax", {}))

            user_prompt_parts.append(f"- **{normalize_text(name).upper()}** (Bars {bars})")
            if function:
                user_prompt_parts.append(f"    Function: {function}")
            if isinstance(cadence, dict) and cadence:
                cad_type = cadence.get("type", "")
                cad_bar = cadence.get("bar", "")
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

    if is_non_empty_list(accent_map):
        user_prompt_parts.append("")
        user_prompt_parts.append("**ACCENT MAP (RHYTHMIC SYNC):**")
        strong_accents = [
            a for a in accent_map
            if isinstance(a, dict) and a.get("strength") == STRONG_ACCENT
        ]
        if strong_accents:
            accent_strs = []
            for a in strong_accents[:ACCENT_STRONG_LIMIT]:
                bar = a.get("bar", DEFAULT_BAR)
                beat = a.get("beat", DEFAULT_BEAT)
                accent_strs.append(f"Bar {bar}.{beat}")
            user_prompt_parts.append(f"- STRONG accents (all instruments): {', '.join(accent_strs)}")
            user_prompt_parts.append("  → Place notes ON these beats, use f-ff dynamics")
        medium_accents = [
            a for a in accent_map
            if isinstance(a, dict) and a.get("strength") == MEDIUM_ACCENT
        ]
        if medium_accents:
            accent_strs = []
            for a in medium_accents[:ACCENT_MEDIUM_LIMIT]:
                bar = a.get("bar", DEFAULT_BAR)
                beat = a.get("beat", DEFAULT_BEAT)
                accent_strs.append(f"Bar {bar}.{beat}")
            user_prompt_parts.append(f"- MEDIUM accents (optional): {', '.join(accent_strs)}")

    if isinstance(motif_blueprint, dict) and motif_blueprint:
        midi_to_note, dur_q_to_name, _velocity_to_dynamic = import_music_notation()
        note_to_midi = import_note_to_midi()

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
            note_parts = [
                n.strip() for n in notes_str.replace("→", ",").replace("->", ",").split(",") if n.strip()
            ]
            if len(note_parts) >= MIN_INTERVAL_NOTES:
                try:
                    midi_notes = [note_to_midi(n) for n in note_parts]
                    for i in range(INTERVAL_START_INDEX, len(midi_notes)):
                        computed_intervals.append(midi_notes[i] - midi_notes[i - INTERVAL_START_INDEX])
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
                user_prompt_parts.append(f"- Notes: {INTERVAL_ARROW.join(motif_notes)}")
            except (TypeError, ValueError):
                pass
        elif start_pitch:
            try:
                user_prompt_parts.append(f"- Start note: {midi_to_note(int(start_pitch))}")
            except (TypeError, ValueError):
                pass

        if rhythm:
            rhythm_str = format_rhythm_pattern(rhythm, dur_q_to_name)
            if rhythm_str:
                user_prompt_parts.append(f"- Rhythm: {rhythm_str}")

        final_intervals = computed_intervals if computed_intervals else intervals
        interval_str = format_interval_list(final_intervals) if final_intervals else ""
        if interval_str:
            user_prompt_parts.append(f"- Intervals: [{interval_str}] semitones")

        if techniques:
            user_prompt_parts.append(f"- Development: {', '.join(techniques)}")

        user_prompt_parts.append("")
        user_prompt_parts.append("MOTIF RULE: MELODY role should establish this motif, others respond/develop it")

    if is_non_empty_list(section_overview):
        user_prompt_parts.append("")
        user_prompt_parts.append("**SECTION OVERVIEW:**")
        for entry in section_overview:
            if not isinstance(entry, dict):
                continue
            section_bars = normalize_text(entry.get("bars"))
            section_type = normalize_text(entry.get("type"))
            texture = normalize_text(entry.get("texture"))
            dynamics = normalize_text(entry.get("dynamics"))
            energy = normalize_text(entry.get("energy"))
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

    if is_non_empty_list(role_guidance):
        user_prompt_parts.append("")
        user_prompt_parts.append("**ROLE ASSIGNMENTS:**")
        for entry in role_guidance:
            if not isinstance(entry, dict):
                continue
            instrument = normalize_text(entry.get("instrument"))
            role = normalize_text(entry.get("role"))
            register = normalize_text(entry.get("register"))
            guidance = normalize_text(entry.get("guidance"))
            relationship = normalize_text(entry.get("relationship"))

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


def append_generated_motif_section(
    user_prompt_parts: List[str],
    generated_motif: Dict[str, Any],
    current_role: str,
) -> None:
    if not isinstance(generated_motif, dict) or not generated_motif:
        return

    user_prompt_parts.append("### ESTABLISHED MOTIF (from melody instrument - RESPOND TO THIS)")
    source = generated_motif.get("source_instrument", DEFAULT_MOTIF_SOURCE)
    user_prompt_parts.append(f"**Source:** {source}")

    motif_notes = generated_motif.get("notes", [])
    if motif_notes:
        midi_to_note, dur_q_to_name, velocity_to_dynamic = import_music_notation()

        user_prompt_parts.append("**Motif notes:**")
        user_prompt_parts.append("```")
        user_prompt_parts.append("Beat | Note    | Duration  | Dynamics")
        user_prompt_parts.append("-----|---------|-----------|--------")
        for note in motif_notes[:MOTIF_NOTES_LIMIT]:
            if isinstance(note, dict):
                start_q = note.get("start_q", DEFAULT_START_Q)
                dur_q = note.get("dur_q", DEFAULT_NOTE_DUR_Q)
                pitch = note.get("pitch", DEFAULT_PITCH)
                vel = note.get("vel", DEFAULT_VELOCITY)
                note_name = midi_to_note(pitch)
                dur_name = dur_q_to_name(dur_q, abbrev=False)
                dyn = velocity_to_dynamic(vel)
                user_prompt_parts.append(f"{start_q:4.1f} | {note_name:<7} | {dur_name:<9} | {dyn}")
        user_prompt_parts.append("```")

    intervals = generated_motif.get("intervals", [])
    interval_str = format_interval_list(intervals) if intervals else ""
    if interval_str:
        user_prompt_parts.append(f"**Intervals:** [{interval_str}] semitones")

    rhythm = generated_motif.get("rhythm_pattern", [])
    if rhythm:
        _midi_to_note, dur_q_to_name, _velocity_to_dynamic = import_music_notation()
        rhythm_str = format_rhythm_pattern(rhythm, dur_q_to_name)
        if rhythm_str:
            user_prompt_parts.append(f"**Rhythm:** {rhythm_str}")

    character = generated_motif.get("character", "")
    if character:
        user_prompt_parts.append(f"**Character:** {character}")

    current_role_lower = normalize_lower(current_role) if current_role else UNKNOWN_VALUE
    user_prompt_parts.append("")
    if current_role_lower == ROLE_MELODY:
        user_prompt_parts.append("YOUR TASK: You ARE the motif carrier. Develop/vary this motif.")
    elif current_role_lower == ROLE_BASS:
        user_prompt_parts.append("YOUR TASK: Support the motif rhythm with root notes on strong beats.")
    elif current_role_lower in {ROLE_HARMONY, ROLE_PAD}:
        user_prompt_parts.append("YOUR TASK: Provide harmonic backdrop that frames this motif.")
    elif current_role_lower == ROLE_COUNTERMELODY:
        user_prompt_parts.append("YOUR TASK: Create a complementary line that answers this motif.")
    else:
        user_prompt_parts.append("YOUR TASK: Complement this motif - don't duplicate it, respond to it.")
    user_prompt_parts.append("")
