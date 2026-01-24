from __future__ import annotations

import copy
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

try:
    from constants import APP_NAME, BRIDGE_HOST, BRIDGE_PORT, MAX_REPAIR_ATTEMPTS, SECONDS_PER_MINUTE
    from logger_config import logger
    from models import ArrangeRequest, EnhanceRequest, GenerateRequest
    from profile_utils import deep_merge, load_profile, resolve_preset
    from prompt_builder import build_arrange_plan_prompt, build_chat_messages, build_plan_prompt, build_prompt
    from prompt_builder_common import extract_role_from_plan
    from llm_client import call_llm, parse_llm_json, resolve_model
    from prompt_enhancer import ENHANCER_SYSTEM_PROMPT, build_enhancer_prompt, extract_enhanced_prompt
    from promts import (
        OUTPUT_SCHEMA_CURVE_KEYS,
        OUTPUT_SCHEMA_KEYS,
        OUTPUT_SCHEMA_LIST_KEYS,
        OUTPUT_SCHEMA_STRING_KEYS,
        OUTPUT_SCHEMA_TEMPLATE,
        REPAIR_SYSTEM_PROMPT,
        SCHEMA_KEY_ARTICULATION,
        SCHEMA_KEY_ARTICULATION_CHANGES,
        SCHEMA_KEY_CURVES,
        SCHEMA_KEY_GENERATION_STYLE,
        SCHEMA_KEY_GENERATION_TYPE,
        SCHEMA_KEY_HANDOFF,
        SCHEMA_REPAIR_SYSTEM_PROMPT,
    )
    from response_builder import build_response, normalize_articulation_changes
    from utils import summarize_text
except ImportError:
    from .constants import APP_NAME, BRIDGE_HOST, BRIDGE_PORT, MAX_REPAIR_ATTEMPTS, SECONDS_PER_MINUTE
    from .logger_config import logger
    from .models import ArrangeRequest, EnhanceRequest, GenerateRequest
    from .profile_utils import deep_merge, load_profile, resolve_preset
    from .prompt_builder import build_arrange_plan_prompt, build_chat_messages, build_plan_prompt, build_prompt
    from .prompt_builder_common import extract_role_from_plan
    from .llm_client import call_llm, parse_llm_json, resolve_model
    from .prompt_enhancer import ENHANCER_SYSTEM_PROMPT, build_enhancer_prompt, extract_enhanced_prompt
    from .promts import (
        OUTPUT_SCHEMA_CURVE_KEYS,
        OUTPUT_SCHEMA_KEYS,
        OUTPUT_SCHEMA_LIST_KEYS,
        OUTPUT_SCHEMA_STRING_KEYS,
        OUTPUT_SCHEMA_TEMPLATE,
        REPAIR_SYSTEM_PROMPT,
        SCHEMA_KEY_ARTICULATION,
        SCHEMA_KEY_ARTICULATION_CHANGES,
        SCHEMA_KEY_CURVES,
        SCHEMA_KEY_GENERATION_STYLE,
        SCHEMA_KEY_GENERATION_TYPE,
        SCHEMA_KEY_HANDOFF,
        SCHEMA_REPAIR_SYSTEM_PROMPT,
    )
    from .response_builder import build_response, normalize_articulation_changes
    from .utils import summarize_text

app = FastAPI(title=APP_NAME)


def calculate_length_q(time_window, music_info) -> float:
    length_sec = time_window.end_sec - time_window.start_sec
    
    if time_window.length_bars is not None:
        time_sig = music_info.time_sig
        try:
            parts = time_sig.split("/")
            num = int(parts[0])
            denom = int(parts[1])
            quarters_per_bar = num * (4.0 / denom)
        except (ValueError, IndexError):
            quarters_per_bar = 4.0
        return max(0.0, float(time_window.length_bars) * quarters_per_bar)
    
    bpm_for_calc = music_info.original_bpm or music_info.bpm
    return max(0.0, length_sec * float(bpm_for_calc) / SECONDS_PER_MINUTE)


PROFILE_KEY_ARTICULATIONS = "articulations"
PROFILE_KEY_MAP = "map"
PROFILE_KEY_MIDI = "midi"
PROFILE_KEY_MODE = "mode"
PROFILE_KEY_IS_DRUM = "is_drum"
PROFILE_KEY_DEFAULT = "default"
ARTICULATION_MODE_NONE = "none"
CURVE_KEY_BREAKPOINTS = "breakpoints"
CURVE_KEY_INTERP = "interp"
ARTICULATION_TIME_KEY = "time_q"
ARTICULATION_NAME_KEY = "articulation"


def get_profile_articulation_names(profile: dict) -> list[str]:
    art_cfg = profile.get(PROFILE_KEY_ARTICULATIONS, {})
    art_map = art_cfg.get(PROFILE_KEY_MAP, {})
    if not isinstance(art_map, dict):
        return []
    names = [str(name).strip() for name in art_map.keys() if str(name).strip()]
    return sorted(set(names))


def profile_has_articulations(profile: dict) -> bool:
    art_cfg = profile.get(PROFILE_KEY_ARTICULATIONS, {})
    mode = str(art_cfg.get(PROFILE_KEY_MODE, "")).lower()
    art_map = art_cfg.get(PROFILE_KEY_MAP, {})
    return mode != ARTICULATION_MODE_NONE and isinstance(art_map, dict) and len(art_map) > 0


def build_allowed_articulation_map(names: list[str]) -> dict[str, str]:
    return {name.lower(): name for name in names}


def resolve_articulation_name(value: str, allowed_map: dict[str, str]) -> str:
    name = str(value or "").strip()
    if not name:
        return ""
    if not allowed_map:
        return name
    return allowed_map.get(name.lower(), "")


def resolve_default_articulation(profile: dict, allowed_map: dict[str, str], allowed_names: list[str]) -> str:
    art_cfg = profile.get(PROFILE_KEY_ARTICULATIONS, {})
    default_name = str(art_cfg.get(PROFILE_KEY_DEFAULT, "")).strip()
    resolved = resolve_articulation_name(default_name, allowed_map)
    if resolved:
        return resolved
    return allowed_names[0] if allowed_names else ""


def normalize_articulation_changes_list(
    raw_changes: list[dict],
    allowed_map: dict[str, str],
    time_sig: str,
) -> list[dict]:
    normalized = normalize_articulation_changes(raw_changes, time_sig)
    cleaned: list[dict] = []
    for change in normalized:
        art_name = resolve_articulation_name(change.get(ARTICULATION_NAME_KEY, ""), allowed_map)
        if not art_name:
            continue
        cleaned.append({
            ARTICULATION_TIME_KEY: float(change.get(ARTICULATION_TIME_KEY, 0.0)),
            ARTICULATION_NAME_KEY: art_name,
        })
    return cleaned


def normalize_llm_output_schema(
    parsed: dict,
    profile: dict,
    time_sig: str,
    generation_type: str | None,
    generation_style: str | None,
) -> dict:
    normalized = dict(parsed) if isinstance(parsed, dict) else {}
    raw_changes_source = normalized.get(SCHEMA_KEY_ARTICULATION_CHANGES)
    defaults = copy.deepcopy(OUTPUT_SCHEMA_TEMPLATE)
    for key, value in defaults.items():
        if key not in normalized or normalized[key] is None:
            normalized[key] = value

    for key in OUTPUT_SCHEMA_LIST_KEYS:
        if not isinstance(normalized.get(key), list):
            normalized[key] = []

    for key in OUTPUT_SCHEMA_STRING_KEYS:
        if not isinstance(normalized.get(key), str):
            normalized[key] = ""

    curves = normalized.get(SCHEMA_KEY_CURVES)
    if not isinstance(curves, dict):
        curves = copy.deepcopy(defaults[SCHEMA_KEY_CURVES])
    for curve_key in OUTPUT_SCHEMA_CURVE_KEYS:
        curve_default = defaults[SCHEMA_KEY_CURVES].get(curve_key, {CURVE_KEY_INTERP: "cubic", CURVE_KEY_BREAKPOINTS: []})
        curve_val = curves.get(curve_key)
        if not isinstance(curve_val, dict):
            curves[curve_key] = copy.deepcopy(curve_default)
        else:
            if not isinstance(curve_val.get(CURVE_KEY_BREAKPOINTS), list):
                curve_val[CURVE_KEY_BREAKPOINTS] = []
            if not isinstance(curve_val.get(CURVE_KEY_INTERP), str):
                curve_val[CURVE_KEY_INTERP] = curve_default.get(CURVE_KEY_INTERP, "cubic")
    normalized[SCHEMA_KEY_CURVES] = curves

    handoff = normalized.get(SCHEMA_KEY_HANDOFF)
    if handoff is not None and not isinstance(handoff, dict):
        normalized[SCHEMA_KEY_HANDOFF] = None

    if not normalized[SCHEMA_KEY_GENERATION_TYPE].strip() and generation_type:
        normalized[SCHEMA_KEY_GENERATION_TYPE] = generation_type
    if not normalized[SCHEMA_KEY_GENERATION_STYLE].strip() and generation_style:
        normalized[SCHEMA_KEY_GENERATION_STYLE] = generation_style

    allowed_names = get_profile_articulation_names(profile)
    allowed_map = build_allowed_articulation_map(allowed_names)
    default_articulation = resolve_default_articulation(profile, allowed_map, allowed_names)

    is_drum = bool(profile.get(PROFILE_KEY_MIDI, {}).get(PROFILE_KEY_IS_DRUM, False))
    has_articulations = profile_has_articulations(profile)

    articulation_value = normalized.get(SCHEMA_KEY_ARTICULATION, "")
    articulation_value = resolve_articulation_name(articulation_value, allowed_map)

    raw_changes = raw_changes_source
    if isinstance(raw_changes, dict):
        raw_changes = [raw_changes]
    elif not isinstance(raw_changes, list):
        raw_changes = []
    changes = normalize_articulation_changes_list(raw_changes, allowed_map, time_sig)

    if is_drum:
        changes = []
        articulation_value = ""
    elif has_articulations:
        if changes:
            first_time = float(changes[0].get(ARTICULATION_TIME_KEY, 0.0))
            if first_time > 0:
                changes.insert(0, {
                    ARTICULATION_TIME_KEY: 0.0,
                    ARTICULATION_NAME_KEY: changes[0][ARTICULATION_NAME_KEY],
                })
        else:
            chosen = articulation_value or default_articulation
            if chosen:
                changes = [{ARTICULATION_TIME_KEY: 0.0, ARTICULATION_NAME_KEY: chosen}]
                articulation_value = chosen
    else:
        changes = []

    normalized[SCHEMA_KEY_ARTICULATION] = articulation_value
    normalized[SCHEMA_KEY_ARTICULATION_CHANGES] = changes

    return normalized


def validate_llm_output_schema(parsed: dict, profile: dict, time_sig: str) -> list[str]:
    if not isinstance(parsed, dict):
        return ["root_not_object"]

    errors: list[str] = []

    for key in OUTPUT_SCHEMA_KEYS:
        if key not in parsed:
            errors.append(f"missing:{key}")

    for key in OUTPUT_SCHEMA_LIST_KEYS:
        if key in parsed and not isinstance(parsed.get(key), list):
            errors.append(f"type:{key}:list")

    for key in OUTPUT_SCHEMA_STRING_KEYS:
        if key in parsed and not isinstance(parsed.get(key), str):
            errors.append(f"type:{key}:string")

    curves = parsed.get(SCHEMA_KEY_CURVES)
    if isinstance(curves, dict):
        for key in OUTPUT_SCHEMA_CURVE_KEYS:
            curve = curves.get(key)
            if not isinstance(curve, dict):
                errors.append(f"type:curves.{key}")
                continue
            breakpoints = curve.get(CURVE_KEY_BREAKPOINTS)
            if not isinstance(breakpoints, list):
                errors.append(f"type:curves.{key}.breakpoints")
    elif SCHEMA_KEY_CURVES in parsed:
        errors.append("type:curves:dict")

    handoff = parsed.get(SCHEMA_KEY_HANDOFF)
    if handoff is not None and not isinstance(handoff, dict):
        errors.append("type:handoff:dict_or_null")

    is_drum = bool(profile.get(PROFILE_KEY_MIDI, {}).get(PROFILE_KEY_IS_DRUM, False))
    raw_changes = parsed.get(SCHEMA_KEY_ARTICULATION_CHANGES)
    normalized_changes = (
        normalize_articulation_changes(raw_changes, time_sig)
        if isinstance(raw_changes, list)
        else []
    )
    allowed_names = get_profile_articulation_names(profile)
    allowed_set = {name.lower() for name in allowed_names}

    if is_drum:
        if normalized_changes:
            errors.append("drum_articulation_changes")
    else:
        has_articulations = profile_has_articulations(profile)
        if has_articulations and not normalized_changes:
            errors.append("missing_articulation_changes")
        if normalized_changes:
            first_time = float(normalized_changes[0].get(ARTICULATION_TIME_KEY, 0.0))
            if first_time > 0:
                errors.append("missing_time_zero_articulation")
            if allowed_set:
                for change in normalized_changes:
                    art_name = str(change.get(ARTICULATION_NAME_KEY, "")).strip()
                    if not art_name or art_name.lower() not in allowed_set:
                        errors.append(f"invalid_articulation:{art_name or 'empty'}")
                        break

    articulation = parsed.get(SCHEMA_KEY_ARTICULATION)
    if isinstance(articulation, str) and articulation.strip() and allowed_set:
        if articulation.lower() not in allowed_set:
            errors.append(f"invalid_articulation:{articulation}")
    elif SCHEMA_KEY_ARTICULATION in parsed and articulation is not None and not isinstance(articulation, str):
        errors.append("type:articulation:string")

    return errors


def build_schema_repair_prompt(parsed: dict, profile: dict, errors: list[str]) -> str:
    allowed = get_profile_articulation_names(profile)
    allowed_str = ", ".join(allowed) if allowed else "none"
    return "\n".join([
        "Fix the JSON to match the required schema. Keep musical content unchanged.",
        f"Allowed articulations: {allowed_str}",
        f"Schema errors: {', '.join(errors)}",
        "JSON:",
        json.dumps(parsed, ensure_ascii=False),
    ])


def attempt_schema_repair(
    parsed: dict,
    profile: dict,
    time_sig: str,
    generation_type: str | None,
    generation_style: str | None,
    provider: str,
    model_name: str,
    base_url: str,
    temperature: float,
    api_key: str | None,
    max_attempts: int,
) -> dict | None:
    errors = validate_llm_output_schema(parsed, profile, time_sig)
    if not errors:
        return parsed
    for attempt in range(max_attempts):
        repair_messages = [
            {"role": "system", "content": SCHEMA_REPAIR_SYSTEM_PROMPT},
            {"role": "user", "content": build_schema_repair_prompt(parsed, profile, errors)},
        ]
        content = call_llm(provider, model_name, base_url, temperature, repair_messages, api_key)
        try:
            candidate = parse_llm_json(content)
        except ValueError:
            errors = ["invalid_json_after_schema_repair"]
            continue
        candidate = normalize_llm_output_schema(candidate, profile, time_sig, generation_type, generation_style)
        errors = validate_llm_output_schema(candidate, profile, time_sig)
        if not errors:
            return candidate
        parsed = candidate
    return None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/generate")
def generate(request: GenerateRequest) -> JSONResponse:
    if request.time.end_sec <= request.time.start_sec:
        raise HTTPException(status_code=400, detail="Invalid time selection")

    profile = load_profile(request.target.profile_id)
    if request.target.profile_overrides:
        profile = deep_merge(profile, request.target.profile_overrides)

    preset_name, preset_settings = resolve_preset(profile, request.target.preset_name)
    length_q = calculate_length_q(request.time, request.music)

    system_prompt, user_prompt = build_prompt(request, profile, preset_name, preset_settings, length_q)
    messages = build_chat_messages(system_prompt, user_prompt)

    provider, model_name, base_url, temperature, api_key = resolve_model(request, profile)

    if request.free_mode:
        logger.info(
            "Generate: profile=%s preset=%s provider=%s model=%s free_mode=True",
            profile.get("id"),
            preset_name,
            provider,
            model_name,
        )
    else:
        logger.info(
            "Generate: profile=%s preset=%s provider=%s model=%s type=%s style=%s",
            profile.get("id"),
            preset_name,
            provider,
            model_name,
            request.generation_type,
            request.generation_style,
        )
    logger.info("User prompt to LLM:\n%s", user_prompt)

    content = call_llm(provider, model_name, base_url, temperature, messages, api_key)
    logger.info("LLM response received: %d chars", len(content))
    logger.info("LLM response preview: %s", summarize_text(content))
    parsed = None
    try:
        parsed = parse_llm_json(content)
    except ValueError:
        logger.warning("LLM JSON parse failed, starting repair attempts")
        for attempt in range(MAX_REPAIR_ATTEMPTS):
            logger.info("Repair attempt %d/%d", attempt + 1, MAX_REPAIR_ATTEMPTS)
            repair_messages = [
                {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ]
            content = call_llm(provider, model_name, base_url, temperature, repair_messages, api_key)
            logger.info("Repair response received: %d chars", len(content))
            logger.info("Repair response preview: %s", summarize_text(content))
            try:
                parsed = parse_llm_json(content)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            logger.error("LLM JSON parse failed after repair attempts")
            raise HTTPException(status_code=502, detail="LLM JSON parse failed after repair attempts")

    parsed = normalize_llm_output_schema(
        parsed,
        profile,
        request.music.time_sig,
        request.generation_type,
        request.generation_style,
    )
    schema_errors = validate_llm_output_schema(parsed, profile, request.music.time_sig)
    if schema_errors:
        logger.warning("LLM output schema validation failed: %s", schema_errors)
        repaired = attempt_schema_repair(
            parsed,
            profile,
            request.music.time_sig,
            request.generation_type,
            request.generation_style,
            provider,
            model_name,
            base_url,
            temperature,
            api_key,
            MAX_REPAIR_ATTEMPTS,
        )
        if repaired is None:
            logger.error("LLM output schema repair failed after attempts")
            schema_errors = validate_llm_output_schema(parsed, profile, request.music.time_sig)
            if schema_errors:
                logger.warning("Proceeding with normalized output despite schema errors: %s", schema_errors)
        else:
            parsed = repaired

    should_extract_motif = False
    source_instrument = ""
    current_role = ""
    is_ensemble = bool(request.ensemble and request.ensemble.total_instruments > 1)
    if request.ensemble:
        current_inst = request.ensemble.current_instrument or {}
        current_role = str(current_inst.get("role", "")).lower()
        if current_role in ("", "unknown"):
            plan_data = request.ensemble.plan if request.ensemble else None
            inst_index = current_inst.get("index") or request.ensemble.current_instrument_index
            profile_name = current_inst.get("profile_name") or ""
            track_name = current_inst.get("track_name") or ""
            family = current_inst.get("family") or ""
            resolved = extract_role_from_plan(plan_data, profile_name, track_name, inst_index, family)
            if resolved and resolved.lower() != "unknown":
                current_role = resolved.lower()
        gen_order = request.ensemble.generation_order or 1
        existing_motif = request.ensemble.generated_motif
        if current_role in ("melody", "lead") and gen_order <= 2 and not existing_motif:
            should_extract_motif = True
            source_instrument = current_inst.get("profile_name") or current_inst.get("track_name") or "melody"

    forced_articulation = None
    if not request.free_mode:
        forced_articulation = preset_settings.get("articulation")

    chord_map = None
    if request.ensemble and request.ensemble.plan:
        chord_map = request.ensemble.plan.get("chord_map")

    response = build_response(
        parsed,
        profile,
        length_q,
        request.free_mode,
        request.allow_tempo_changes,
        request.context,
        request.user_prompt or "",
        extract_motif=should_extract_motif,
        source_instrument=source_instrument,
        is_ensemble=is_ensemble,
        current_role=current_role,
        time_sig=request.music.time_sig,
        arrangement_mode=bool(request.ensemble and request.ensemble.arrangement_mode),
        source_sketch=(request.ensemble.source_sketch if request.ensemble and request.ensemble.arrangement_mode else None),
        forced_articulation=forced_articulation,
        chord_map=chord_map,
    )
    logger.info(
        "Response built: notes=%d cc_events=%d keyswitches=%d program_changes=%d articulation=%s motif=%s handoff=%s",
        len(response.get("notes", [])),
        len(response.get("cc_events", [])),
        len(response.get("keyswitches", [])),
        len(response.get("program_changes", [])),
        response.get("articulation"),
        "yes" if response.get("extracted_motif") else "no",
        "yes" if response.get("handoff") else "no",
    )
    return JSONResponse(content=response)


@app.post("/plan")
def plan(request: GenerateRequest) -> JSONResponse:
    if request.time.end_sec <= request.time.start_sec:
        raise HTTPException(status_code=400, detail="Invalid time selection")

    profile = load_profile(request.target.profile_id)
    if request.target.profile_overrides:
        profile = deep_merge(profile, request.target.profile_overrides)

    length_q = calculate_length_q(request.time, request.music)

    system_prompt, user_prompt = build_plan_prompt(request, length_q)
    messages = build_chat_messages(system_prompt, user_prompt)

    provider, model_name, base_url, temperature, api_key = resolve_model(request, profile)

    logger.info(
        "Plan: profile=%s provider=%s model=%s free_mode=%s",
        profile.get("id"),
        provider,
        model_name,
        request.free_mode,
    )
    logger.info("Plan prompt to LLM:\n%s", user_prompt)

    content = call_llm(provider, model_name, base_url, temperature, messages, api_key)
    logger.info("LLM plan response received: %d chars", len(content))
    logger.info("LLM plan preview: %s", summarize_text(content))
    parsed = None
    try:
        parsed = parse_llm_json(content)
    except ValueError:
        logger.warning("LLM plan JSON parse failed, starting repair attempts")
        for attempt in range(MAX_REPAIR_ATTEMPTS):
            logger.info("Plan repair attempt %d/%d", attempt + 1, MAX_REPAIR_ATTEMPTS)
            repair_messages = [
                {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ]
            content = call_llm(provider, model_name, base_url, temperature, repair_messages, api_key)
            logger.info("Plan repair response received: %d chars", len(content))
            logger.info("Plan repair response preview: %s", summarize_text(content))
            try:
                parsed = parse_llm_json(content)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            logger.error("LLM plan JSON parse failed after repair attempts")
            raise HTTPException(status_code=502, detail="LLM plan JSON parse failed after repair attempts")

    plan_summary = str(parsed.get("plan_summary", "")).strip()
    if not plan_summary:
        plan_summary = summarize_text(json.dumps(parsed, ensure_ascii=False))

    response = {
        "plan_summary": plan_summary,
        "plan": parsed,
    }
    return JSONResponse(content=response)


@app.post("/arrange_plan")
def arrange_plan(request: ArrangeRequest) -> JSONResponse:
    if request.time.end_sec <= request.time.start_sec:
        raise HTTPException(status_code=400, detail="Invalid time selection")

    if not request.source_sketch or not request.source_sketch.notes:
        raise HTTPException(status_code=400, detail="Source sketch with notes is required")

    length_q = calculate_length_q(request.time, request.music)

    system_prompt, user_prompt = build_arrange_plan_prompt(request, length_q)
    messages = build_chat_messages(system_prompt, user_prompt)

    model_info = request.model
    provider = model_info.provider if model_info else "lmstudio"
    base_url = model_info.base_url if model_info else None
    temperature = model_info.temperature if model_info and model_info.temperature else 0.7
    api_key = model_info.api_key if model_info else None

    if not base_url:
        if provider == "openrouter":
            from constants import DEFAULT_OPENROUTER_BASE_URL
            base_url = DEFAULT_OPENROUTER_BASE_URL
        elif provider == "ollama":
            from constants import DEFAULT_OLLAMA_BASE_URL
            base_url = DEFAULT_OLLAMA_BASE_URL
        else:
            from constants import DEFAULT_LMSTUDIO_BASE_URL
            base_url = DEFAULT_LMSTUDIO_BASE_URL

    if provider == "openrouter":
        from constants import DEFAULT_ENHANCER_MODEL
        model_name = DEFAULT_ENHANCER_MODEL
    elif model_info and model_info.model_name:
        model_name = model_info.model_name
    else:
        from constants import DEFAULT_MODEL_NAME
        model_name = DEFAULT_MODEL_NAME

    logger.info(
        "ArrangePlan: provider=%s model=%s sketch_notes=%d target_instruments=%d",
        provider,
        model_name,
        len(request.source_sketch.notes),
        len(request.target_instruments),
    )
    logger.info("ArrangePlan prompt to LLM:\n%s", user_prompt)

    content = call_llm(provider, model_name, base_url, float(temperature), messages, api_key)
    logger.info("LLM arrange plan response received: %d chars", len(content))
    logger.info("LLM arrange plan preview: %s", summarize_text(content))

    parsed = None
    try:
        parsed = parse_llm_json(content)
    except ValueError:
        logger.warning("LLM arrange plan JSON parse failed, starting repair attempts")
        for attempt in range(MAX_REPAIR_ATTEMPTS):
            logger.info("Arrange plan repair attempt %d/%d", attempt + 1, MAX_REPAIR_ATTEMPTS)
            repair_messages = [
                {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ]
            content = call_llm(provider, model_name, base_url, float(temperature), repair_messages, api_key)
            logger.info("Arrange plan repair response received: %d chars", len(content))
            try:
                parsed = parse_llm_json(content)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            logger.error("LLM arrange plan JSON parse failed after repair attempts")
            raise HTTPException(status_code=502, detail="LLM arrange plan JSON parse failed after repair attempts")

    plan_summary = str(parsed.get("plan_summary", "")).strip()
    if not plan_summary:
        analysis_summary = str(parsed.get("analysis_summary", "")).strip()
        plan_summary = analysis_summary if analysis_summary else summarize_text(json.dumps(parsed, ensure_ascii=False))

    response = {
        "plan_summary": plan_summary,
        "plan": parsed,
        "arrangement_assignments": parsed.get("arrangement_assignments", []),
    }
    return JSONResponse(content=response)


@app.post("/enhance")
def enhance(request: EnhanceRequest) -> JSONResponse:
    if not request.user_prompt or not request.user_prompt.strip():
        raise HTTPException(status_code=400, detail="User prompt is required")

    instruments_data = [
        {
            "track_name": inst.track_name,
            "profile_name": inst.profile_name,
            "family": inst.family,
            "role": inst.role,
        }
        for inst in request.instruments
    ]

    context_data = None
    if request.context_notes:
        context_data = {"context_notes": request.context_notes}

    user_prompt = build_enhancer_prompt(
        user_prompt=request.user_prompt,
        instruments=instruments_data,
        key=request.key,
        bpm=request.bpm,
        time_sig=request.time_sig,
        length_bars=request.length_bars,
        length_q=request.length_q,
        context=context_data,
    )

    messages = [
        {"role": "system", "content": ENHANCER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    model_info = request.model
    provider = model_info.provider if model_info else "lmstudio"
    base_url = model_info.base_url if model_info else None
    temperature = model_info.temperature if model_info and model_info.temperature else 0.7
    api_key = model_info.api_key if model_info else None

    if not base_url:
        if provider == "openrouter":
            from constants import DEFAULT_OPENROUTER_BASE_URL
            base_url = DEFAULT_OPENROUTER_BASE_URL
        elif provider == "ollama":
            from constants import DEFAULT_OLLAMA_BASE_URL
            base_url = DEFAULT_OLLAMA_BASE_URL
        else:
            from constants import DEFAULT_LMSTUDIO_BASE_URL
            base_url = DEFAULT_LMSTUDIO_BASE_URL

    if provider == "openrouter":
        from constants import DEFAULT_ENHANCER_MODEL
        model_name = DEFAULT_ENHANCER_MODEL
    elif model_info and model_info.model_name:
        model_name = model_info.model_name
    else:
        from constants import DEFAULT_MODEL_NAME
        model_name = DEFAULT_MODEL_NAME

    logger.info(
        "Enhance: provider=%s model=%s instruments=%d",
        provider,
        model_name,
        len(instruments_data),
    )
    logger.info("Enhance user prompt: %s", summarize_text(request.user_prompt))

    content = call_llm(provider, model_name, base_url, float(temperature), messages, api_key)
    logger.info("Enhance response received: %d chars", len(content))

    enhanced_prompt = extract_enhanced_prompt(content)
    logger.info("Enhanced prompt: %s", summarize_text(enhanced_prompt))

    return JSONResponse(content={"enhanced_prompt": enhanced_prompt})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT, log_level="info")
