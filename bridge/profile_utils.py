from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

try:
    from constants import PROFILES_DIR
except ImportError:
    from .constants import PROFILES_DIR


def read_json_file(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Profile file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in profile: {path}") from exc


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def list_profile_files() -> List[Path]:
    if not PROFILES_DIR.exists():
        raise HTTPException(status_code=500, detail=f"Profiles directory missing: {PROFILES_DIR}")
    return sorted([p for p in PROFILES_DIR.glob("*.json") if p.is_file()])


def load_profile(profile_id: str) -> Dict[str, Any]:
    name_match: Optional[Dict[str, Any]] = None
    for path in list_profile_files():
        profile = read_json_file(path)
        if profile.get("id") == profile_id:
            return profile
        if name_match is None and profile.get("name", "").lower() == profile_id.lower():
            name_match = profile
    if name_match:
        return name_match
    raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")


def resolve_preset(profile: Dict[str, Any], preset_name: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    presets = profile.get("ai", {}).get("presets", {})
    if not presets:
        return preset_name, {}
    if preset_name and preset_name in presets:
        return preset_name, presets[preset_name]
    first_name = next(iter(presets.keys()))
    return first_name, presets[first_name]
