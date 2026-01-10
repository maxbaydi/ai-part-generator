from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

try:
    from constants import APP_NAME, BRIDGE_HOST, BRIDGE_PORT, MAX_REPAIR_ATTEMPTS, SECONDS_PER_MINUTE
    from logger_config import logger
    from models import ArrangeRequest, EnhanceRequest, GenerateRequest
    from profile_utils import deep_merge, load_profile, resolve_preset
    from prompt_builder import build_arrange_plan_prompt, build_chat_messages, build_plan_prompt, build_prompt
    from llm_client import call_llm, parse_llm_json, resolve_model
    from prompt_enhancer import ENHANCER_SYSTEM_PROMPT, build_enhancer_prompt, extract_enhanced_prompt
    from promts import REPAIR_SYSTEM_PROMPT
    from response_builder import build_response
    from utils import summarize_text
except ImportError:
    from .constants import APP_NAME, BRIDGE_HOST, BRIDGE_PORT, MAX_REPAIR_ATTEMPTS, SECONDS_PER_MINUTE
    from .logger_config import logger
    from .models import ArrangeRequest, EnhanceRequest, GenerateRequest
    from .profile_utils import deep_merge, load_profile, resolve_preset
    from .prompt_builder import build_arrange_plan_prompt, build_chat_messages, build_plan_prompt, build_prompt
    from .llm_client import call_llm, parse_llm_json, resolve_model
    from .prompt_enhancer import ENHANCER_SYSTEM_PROMPT, build_enhancer_prompt, extract_enhanced_prompt
    from .promts import REPAIR_SYSTEM_PROMPT
    from .response_builder import build_response
    from .utils import summarize_text

app = FastAPI(title=APP_NAME)


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
    length_sec = request.time.end_sec - request.time.start_sec
    length_q = length_sec * float(request.music.bpm) / SECONDS_PER_MINUTE
    length_q = max(0.0, length_q)

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

    should_extract_motif = False
    source_instrument = ""
    current_role = ""
    is_ensemble = bool(request.ensemble and request.ensemble.total_instruments > 1)
    if request.free_mode and request.ensemble:
        current_inst = request.ensemble.current_instrument or {}
        current_role = str(current_inst.get("role", "")).lower()
        gen_order = request.ensemble.generation_order or 1
        existing_motif = request.ensemble.generated_motif
        if current_role in ("melody", "lead") and gen_order <= 2 and not existing_motif:
            should_extract_motif = True
            source_instrument = current_inst.get("profile_name") or current_inst.get("track_name") or "melody"

    forced_articulation = None
    if not request.free_mode:
        forced_articulation = preset_settings.get("articulation")

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

    length_sec = request.time.end_sec - request.time.start_sec
    length_q = length_sec * float(request.music.bpm) / SECONDS_PER_MINUTE
    length_q = max(0.0, length_q)

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

    length_sec = request.time.end_sec - request.time.start_sec
    length_q = length_sec * float(request.music.bpm) / SECONDS_PER_MINUTE
    length_q = max(0.0, length_q)

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
