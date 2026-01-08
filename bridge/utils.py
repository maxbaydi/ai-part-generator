from __future__ import annotations

from typing import Any, Dict

try:
    from constants import LOG_PREVIEW_CHARS
except ImportError:
    from .constants import LOG_PREVIEW_CHARS


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_format(template: str, values: Dict[str, Any]) -> str:
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(SafeDict(values))


def summarize_text(text: str, limit: int = LOG_PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"
