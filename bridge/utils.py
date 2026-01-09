from __future__ import annotations

import re
from typing import Any, Dict

try:
    from constants import LOG_PREVIEW_CHARS
except ImportError:
    from .constants import LOG_PREVIEW_CHARS

PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_format(template: str, values: Dict[str, Any]) -> str:
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        if key in values:
            return str(values[key])
        return match.group(0)

    return PLACEHOLDER_PATTERN.sub(replacer, template)


def summarize_text(text: str, limit: int = LOG_PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"
