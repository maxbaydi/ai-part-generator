from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

try:
    from constants import APP_NAME, BRIDGE_HOST, BRIDGE_PORT, MAX_REPAIR_ATTEMPTS, SECONDS_PER_MINUTE
    from logger_config import logger
    from models import GenerateRequest
    from profile_utils import deep_merge, load_profile, resolve_preset
    from prompt_builder import build_chat_messages, build_prompt
    from llm_client import call_llm, parse_llm_json, resolve_model
    from promts import REPAIR_SYSTEM_PROMPT
    from response_builder import build_response
    from utils import summarize_text
except ImportError:
    from .constants import APP_NAME, BRIDGE_HOST, BRIDGE_PORT, MAX_REPAIR_ATTEMPTS, SECONDS_PER_MINUTE
    from .logger_config import logger
    from .models import GenerateRequest
    from .profile_utils import deep_merge, load_profile, resolve_preset
    from .prompt_builder import build_chat_messages, build_prompt
    from .llm_client import call_llm, parse_llm_json, resolve_model
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

    logger.info(
        "Generate: profile=%s preset=%s provider=%s model=%s type=%s style=%s free_mode=%s",
        profile.get("id"),
        preset_name,
        provider,
        model_name,
        request.generation_type,
        request.generation_style,
        request.free_mode,
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

    response = build_response(parsed, profile, length_q, request.free_mode)
    logger.info(
        "Response built: notes=%d cc_events=%d keyswitches=%d program_changes=%d articulation=%s",
        len(response.get("notes", [])),
        len(response.get("cc_events", [])),
        len(response.get("keyswitches", [])),
        len(response.get("program_changes", [])),
        response.get("articulation"),
    )
    return JSONResponse(content=response)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT, log_level="info")
