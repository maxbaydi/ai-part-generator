from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

try:
    from constants import DEFAULT_GENERATION_STYLE, DEFAULT_GENERATION_TYPE, DEFAULT_PROVIDER
except ImportError:
    from .constants import DEFAULT_GENERATION_STYLE, DEFAULT_GENERATION_TYPE, DEFAULT_PROVIDER


class TimeWindow(BaseModel):
    start_sec: float
    end_sec: float


class MusicInfo(BaseModel):
    bpm: float
    time_sig: str
    key: str = "unknown"


class TargetInfo(BaseModel):
    profile_id: str
    preset_name: Optional[str] = None
    profile_overrides: Optional[Dict[str, Any]] = None


class ContextTrack(BaseModel):
    name: str
    midi_base64: Optional[str] = None


class HorizontalContext(BaseModel):
    before: List[Dict[str, Any]] = Field(default_factory=list)
    after: List[Dict[str, Any]] = Field(default_factory=list)
    position: str = "isolated"


class ContextInfo(BaseModel):
    selected_tracks_midi: List[Any] = Field(default_factory=list)
    context_notes: Optional[str] = None
    existing_notes: Optional[List[Dict[str, Any]]] = None
    pitch_range: Optional[Dict[str, int]] = None
    horizontal: Optional[HorizontalContext] = None
    extended_progression: Optional[List[Dict[str, Any]]] = None
    context_tracks: Optional[List[Dict[str, Any]]] = None
    cc_events: Optional[List[Dict[str, Any]]] = None


class ModelInfo(BaseModel):
    provider: str = DEFAULT_PROVIDER
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class EnsembleInstrument(BaseModel):
    index: int = 0
    track_name: str = ""
    profile_id: str = ""
    profile_name: str = ""
    family: str = "unknown"
    role: str = "unknown"
    range: Optional[Dict[str, Any]] = None
    description: str = ""


class GeneratedPartInfo(BaseModel):
    track_name: str = ""
    profile_name: str = ""
    role: str = "unknown"
    notes: List[Dict[str, Any]] = Field(default_factory=list)
    cc_events: List[Dict[str, Any]] = Field(default_factory=list)


class EnsembleInfo(BaseModel):
    total_instruments: int = 1
    instruments: List[EnsembleInstrument] = Field(default_factory=list)
    generation_style: str = DEFAULT_GENERATION_STYLE
    shared_prompt: str = ""
    plan_summary: str = ""
    plan: Optional[Dict[str, Any]] = None
    current_instrument_index: int = 1
    current_instrument: Optional[Dict[str, Any]] = None
    generation_order: int = 1
    is_sequential: bool = False
    previously_generated: List[Dict[str, Any]] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    time: TimeWindow
    music: MusicInfo
    target: TargetInfo
    context: Optional[ContextInfo] = None
    ensemble: Optional[EnsembleInfo] = None
    generation_type: str = DEFAULT_GENERATION_TYPE
    generation_style: str = DEFAULT_GENERATION_STYLE
    free_mode: bool = False
    allow_tempo_changes: bool = False
    user_prompt: str = ""
    model: Optional[ModelInfo] = None


class EnhanceInstrument(BaseModel):
    track_name: str = ""
    profile_name: str = ""
    family: str = ""
    role: str = ""


class EnhanceRequest(BaseModel):
    user_prompt: str
    instruments: List[EnhanceInstrument] = Field(default_factory=list)
    key: str = "unknown"
    bpm: float = 120.0
    time_sig: str = "4/4"
    length_bars: Optional[int] = None
    length_q: Optional[float] = None
    context_notes: Optional[str] = None
    model: Optional[ModelInfo] = None
