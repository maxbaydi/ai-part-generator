from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

try:
    from constants import (
        DEFAULT_LMSTUDIO_BASE_URL,
        DEFAULT_MODEL_NAME,
        DEFAULT_OLLAMA_BASE_URL,
        DEFAULT_OPENROUTER_BASE_URL,
        DEFAULT_OPENROUTER_MODEL,
        DEFAULT_PROVIDER,
        DEFAULT_TEMPERATURE,
        HTTP_TIMEOUT_SEC,
        LOCAL_HOSTS,
    )
    from logger_config import logger
    from models import GenerateRequest, ModelInfo
except ImportError:
    from .constants import (
        DEFAULT_LMSTUDIO_BASE_URL,
        DEFAULT_MODEL_NAME,
        DEFAULT_OLLAMA_BASE_URL,
        DEFAULT_OPENROUTER_BASE_URL,
        DEFAULT_OPENROUTER_MODEL,
        DEFAULT_PROVIDER,
        DEFAULT_TEMPERATURE,
        HTTP_TIMEOUT_SEC,
        LOCAL_HOSTS,
    )
    from .logger_config import logger
    from .models import GenerateRequest, ModelInfo


def build_url(base_url: str, path: str) -> str:
    if base_url.endswith("/"):
        base = base_url[:-1]
    else:
        base = base_url
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def is_local_url(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    return host in LOCAL_HOSTS or host.startswith("127.")


def read_json_response(resp: Any) -> Dict[str, Any]:
    raw = resp.read().decode("utf-8")
    return json.loads(raw)


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        if is_local_url(url):
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=timeout) as resp:
                return read_json_response(resp)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return read_json_response(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"LLM HTTP error: {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"LLM connection error: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM returned invalid JSON: {exc}") from exc


def call_lmstudio(model_name: str, base_url: str, temperature: float, messages: List[Dict[str, str]]) -> str:
    url = build_url(base_url, "/chat/completions")
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "stop": ["```"],
    }
    response = post_json(url, payload, HTTP_TIMEOUT_SEC)
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="LM Studio response missing content") from exc


def call_ollama(model_name: str, base_url: str, temperature: float, messages: List[Dict[str, str]]) -> str:
    url = build_url(base_url, "/api/chat")
    payload = {
        "model": model_name,
        "messages": messages,
        "options": {"temperature": temperature},
        "stream": False,
    }
    response = post_json(url, payload, HTTP_TIMEOUT_SEC)
    try:
        return response["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Ollama response missing content") from exc


def call_openrouter(model_name: str, base_url: str, temperature: float, messages: List[Dict[str, str]], api_key: str) -> str:
    url = build_url(base_url, "/chat/completions")
    logger.info("OpenRouter request: url=%s model=%s", url, model_name)
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/AI-Part-Generator",
        "X-Title": "AI Part Generator",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            response = read_json_response(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        logger.error("OpenRouter HTTP error: %s %s", exc.code, body)
        raise HTTPException(status_code=502, detail=f"OpenRouter HTTP error: {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        logger.error("OpenRouter connection error: %s", exc)
        raise HTTPException(status_code=502, detail=f"OpenRouter connection error: {exc}") from exc
    except json.JSONDecodeError as exc:
        logger.error("OpenRouter invalid JSON: %s", exc)
        raise HTTPException(status_code=502, detail=f"OpenRouter returned invalid JSON: {exc}") from exc
    try:
        content = response["choices"][0]["message"]["content"]
        logger.info("OpenRouter response received: %d chars", len(content))
        return content
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("OpenRouter response missing content: %s", response)
        raise HTTPException(status_code=502, detail="OpenRouter response missing content") from exc


def extract_json_block(text: str) -> Optional[str]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    return candidate.strip()


def strip_code_fences(text: str) -> str:
    fence_start = text.find("```")
    if fence_start == -1:
        return text
    fence_end = text.rfind("```")
    if fence_end == fence_start:
        return text
    inner = text[fence_start + 3 : fence_end]
    if inner.lstrip().startswith("json"):
        inner = inner.lstrip()[4:]
    return inner.strip()


def extract_first_json_object(text: str) -> Optional[str]:
    start = None
    depth = 0
    in_str = False
    escape = False
    for idx, ch in enumerate(text):
        if start is None:
            if ch == "{":
                start = idx
                depth = 1
            continue
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def parse_llm_json(content: str) -> Dict[str, Any]:
    sanitized = strip_code_fences(content).strip()
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError:
        first_obj = extract_first_json_object(sanitized)
        if first_obj:
            try:
                return json.loads(first_obj)
            except json.JSONDecodeError:
                pass
        extracted = extract_json_block(sanitized)
        if extracted:
            try:
                return json.loads(extracted)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid JSON from LLM") from exc
    raise ValueError("Invalid JSON from LLM")


def resolve_model(request: GenerateRequest, profile: Dict[str, Any]) -> Tuple[str, str, str, float, Optional[str]]:
    model_info = request.model or ModelInfo()
    profile_ai = profile.get("ai", {})
    provider = model_info.provider or profile_ai.get("default_provider") or DEFAULT_PROVIDER
    model_name = model_info.model_name or profile_ai.get("default_model") or DEFAULT_MODEL_NAME
    temperature = model_info.temperature
    if temperature is None:
        temperature = profile_ai.get("default_temperature", DEFAULT_TEMPERATURE)
    base_url = model_info.base_url or profile_ai.get("base_url")
    api_key = model_info.api_key

    if not base_url:
        if provider == "openrouter":
            base_url = DEFAULT_OPENROUTER_BASE_URL
        elif provider == "ollama":
            base_url = DEFAULT_OLLAMA_BASE_URL
        else:
            base_url = DEFAULT_LMSTUDIO_BASE_URL

    if provider == "openrouter" and not model_name:
        model_name = DEFAULT_OPENROUTER_MODEL

    return provider, model_name, base_url, float(temperature), api_key


def call_llm(
    provider: str,
    model_name: str,
    base_url: str,
    temperature: float,
    messages: List[Dict[str, str]],
    api_key: Optional[str] = None,
) -> str:
    logger.info("call_llm: provider=%s model=%s base_url=%s has_api_key=%s", 
                provider, model_name, base_url, bool(api_key))
    if provider == "openrouter":
        if not api_key:
            logger.error("OpenRouter requires an API key but none provided")
            raise HTTPException(status_code=400, detail="OpenRouter requires an API key")
        return call_openrouter(model_name, base_url, temperature, messages, api_key)
    if provider == "ollama":
        return call_ollama(model_name, base_url, temperature, messages)
    return call_lmstudio(model_name, base_url, temperature, messages)
