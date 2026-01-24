from __future__ import annotations

from typing import Iterable


MOJIBAKE_MARKERS: Iterable[str] = (
    "\u00d0",  # Ð
    "\u00d1",  # Ñ
    "\u00c3",  # Ã
    "\u00c2",  # Â
    "\u00e2",  # â
    "\u00b0",  # °
    "\u00b5",  # µ
    "\u00bb",  # »
    "\u00ab",  # «
    "\u00a0",  # non-breaking space
    "\u0080",  # control
    "\u009d",  # control
    "\ufffd",  # replacement
)


def _marker_score(text: str) -> int:
    return sum(text.count(marker) for marker in MOJIBAKE_MARKERS)


def _looks_mojibake(text: str) -> bool:
    if not text or text.isascii():
        return False
    if "\ufffd" in text:
        return True
    return _marker_score(text) >= 2


def fix_mojibake(text: str) -> str:
    if not isinstance(text, str):
        return str(text or "")
    if not _looks_mojibake(text):
        return text

    candidates = []
    for source_encoding in ("cp1251", "latin1"):
        try:
            candidate = text.encode(source_encoding).decode("utf-8")
        except (UnicodeError, ValueError):
            continue
        candidates.append(candidate)

    if not candidates:
        return text

    original_score = _marker_score(text)
    best_text = text
    best_score = original_score

    for candidate in candidates:
        score = _marker_score(candidate)
        if score < best_score:
            best_text = candidate
            best_score = score

    return best_text
