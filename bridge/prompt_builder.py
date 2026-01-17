from __future__ import annotations

try:
    from prompt_builder_generate import (
        build_chat_messages,
        build_pattern_guidance,
        build_prompt,
        build_selection_info,
        build_tempo_change_guidance,
    )
    from prompt_builder_plans import build_arrange_plan_prompt, build_plan_prompt
    from prompt_builder_sketch import (
        SKETCH_CC_EVENTS_LIMIT,
        SKETCH_NOTES_LIMIT,
        SKETCH_NOTES_PREVIEW,
        build_arrangement_context,
        format_sketch_cc_segments,
        format_sketch_notes,
        format_sketch_notes_compact,
    )
    from prompt_builder_utils import (
        ARTICULATION_DURATION_HINTS,
        bar_to_time_q,
        bars_range_to_time_q,
        build_articulation_list_for_prompt,
        build_generation_progress,
        build_orchestration_hints_prompt,
        estimate_note_count,
        extract_key_from_chord_map,
        extract_role_from_plan,
        format_profile_for_prompt,
        format_profile_user_template,
        get_chord_tones_from_name,
        get_custom_curves_info,
        get_profile_articulation_names,
        infer_key_from_plan_chord_map,
        resolve_profile_default_articulation,
        resolve_prompt_articulation,
        resolve_prompt_pitch_range,
    )
except ImportError:
    from .prompt_builder_generate import (
        build_chat_messages,
        build_pattern_guidance,
        build_prompt,
        build_selection_info,
        build_tempo_change_guidance,
    )
    from .prompt_builder_plans import build_arrange_plan_prompt, build_plan_prompt
    from .prompt_builder_sketch import (
        SKETCH_CC_EVENTS_LIMIT,
        SKETCH_NOTES_LIMIT,
        SKETCH_NOTES_PREVIEW,
        build_arrangement_context,
        format_sketch_cc_segments,
        format_sketch_notes,
        format_sketch_notes_compact,
    )
    from .prompt_builder_utils import (
        ARTICULATION_DURATION_HINTS,
        bar_to_time_q,
        bars_range_to_time_q,
        build_articulation_list_for_prompt,
        build_generation_progress,
        build_orchestration_hints_prompt,
        estimate_note_count,
        extract_key_from_chord_map,
        extract_role_from_plan,
        format_profile_for_prompt,
        format_profile_user_template,
        get_chord_tones_from_name,
        get_custom_curves_info,
        get_profile_articulation_names,
        infer_key_from_plan_chord_map,
        resolve_profile_default_articulation,
        resolve_prompt_articulation,
        resolve_prompt_pitch_range,
    )
