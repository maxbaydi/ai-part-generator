from __future__ import annotations

import json
import logging
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

APP_NAME = "AI Part Generator Bridge"

PROFILES_DIR = Path(__file__).resolve().parent.parent / "Profiles"

DEFAULT_PROVIDER = "lmstudio"
DEFAULT_LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL_NAME = "local-model"
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.0-flash-001"
DEFAULT_TEMPERATURE = 0.7
HTTP_TIMEOUT_SEC = 300.0

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8000

MAX_REPAIR_ATTEMPTS = 2

MIN_CC_STEP_Q = 0.0625
MIN_NOTE_DUR_Q = 0.0625
MIN_NOTE_GAP_Q = 0.0625
KEYSWITCH_DUR_Q = 0.25
SECONDS_PER_MINUTE = 60.0
QUARTERS_PER_WHOLE = 4.0
LOG_PREVIEW_CHARS = 500

DEFAULT_CC_INTERP = "cubic"
DEFAULT_SMOOTHING_MODE = "fixed"

MIDI_MIN = 0
MIDI_MAX = 127
MIDI_VEL_MIN = 1
MIDI_CHAN_MIN = 1
MIDI_CHAN_MAX = 16
MIDI_CHAN_ZERO_BASE_MAX = MIDI_CHAN_MAX - 1

DEFAULT_PITCH = 60
DEFAULT_VELOCITY = 80
DEFAULT_DRUM_VELOCITY = 90
DEFAULT_KEYSWITCH_VELOCITY = 100

BASE_SYSTEM_PROMPT = """You are an expert composer. Output ONLY valid JSON, no markdown.

CRITICAL RULE - USE ONLY ALLOWED PITCHES:
You will be given a list of ALLOWED PITCHES (MIDI numbers). Use ONLY those exact pitch values.
DO NOT use any pitch that is not in the allowed list. This ensures notes stay in the correct key/scale.

MUSIC THEORY RULES:
1. MELODY: Use stepwise motion (2nds, 3rds) mostly. Leaps (4ths, 5ths) create tension - resolve by step.
2. HARMONY: Play chord tones on strong beats. Use passing tones (from the scale) on weak beats.
3. RHYTHM: Vary note lengths. Longer notes = emphasis. Start phrases on beat 1.
4. PHRASING: Create 2-4 bar phrases. End phrases on stable scale degrees (1, 3, 5).
5. CONTOUR: Melodies should have a shape - build up to a climax, then resolve down.

OUTPUT FORMAT:
{
  "notes": [{"start_q": 0, "dur_q": 2, "pitch": 72, "vel": 90, "chan": 1}, ...],
  "curves": {"dynamics": {"interp": "cubic", "breakpoints": [{"time_q": X, "value": Y}, ...]}},
  "articulation": "legato"
}

TWO-LAYER DYNAMICS SYSTEM:
There are TWO independent dynamics controls - use BOTH for expressive parts:

1. VELOCITY (vel: 1-127) - PER-NOTE dynamics, controls:
   - Attack intensity of each individual note
   - Critical for SHORT articulations (staccato, pizzicato, spiccato) where velocity IS the dynamics
   - Use to create accents, ghost notes, phrase shaping within a passage
   - Vary velocity to avoid mechanical feel: accented notes 100-127, normal 70-90, soft 40-60

2. CC1 CURVE (curves.dynamics) - PHRASE/GLOBAL dynamics, controls:
   - Overall expression/volume envelope over time
   - Critical for LONG articulations (sustain, legato, tremolo) where CC1 shapes the sound
   - Use for crescendos, decrescendos, swells, phrase arcs
   - Values 0-127, include 3-8 breakpoints

DYNAMICS STRATEGIES:
- Melodic lines: Vary velocity per note (phrase peaks louder), CC1 for overall arc
- Chords/Pads: Similar velocity across chord, CC1 for slow swells
- Rhythmic parts: Velocity for accents (beat 1 louder), CC1 relatively flat
- Accented passage: High velocity on accents, lower between, CC1 supports
- Smooth legato: Even velocity, CC1 does all expression work

DO NOT always use crescendo-decrescendo. Match dynamics to the mood:
- Constant intensity: flat CC1 (80-90), even velocities
- Building tension: CC1 crescendo (40→100), velocities increase
- Fading: CC1 decrescendo (100→40), velocities decrease
- Terraced: sudden CC1 jumps, velocity groups at each level
- Accented: spiky velocities (40-50 vs 100-120), CC1 supports

CRITICAL: 
- Use ONLY pitches from the ALLOWED PITCHES list
- Generate enough notes spread across the entire duration
- MUST include 'curves' with 'dynamics' that matches the requested style
- VARY velocity values - do not use same velocity for all notes"""

REPAIR_SYSTEM_PROMPT = (
    "Return valid JSON only. Do not include any extra text or markdown."
)

FREE_MODE_SYSTEM_PROMPT = """You are an expert composer with COMPLETE CREATIVE FREEDOM. Output ONLY valid JSON, no markdown.

CRITICAL PRINCIPLE - MATCH COMPLEXITY TO USER REQUEST:
Read the user's request carefully. Your output complexity should MATCH what they ask for:
- If they ask for "simple chords" or "basic triads" → generate SIMPLE, STRAIGHTFORWARD chords
- If they ask for "Hans Zimmer style pads" → use sustained whole-note chords with slow CC1 swells
- If they ask for "complex melody" or "virtuosic passage" → then be creative and elaborate
- If they ask for "accompanying part" → support, don't dominate
DO NOT over-complicate simple requests. Professional composers know when to be simple.

CRITICAL RULE - USE ONLY ALLOWED PITCHES:
You will be given a list of ALLOWED PITCHES (MIDI numbers). Use ONLY those exact pitch values.
DO NOT use any pitch that is not in the allowed list. This ensures notes stay in the correct key/scale.

ARTICULATION USAGE:
You CAN use multiple articulations, but ONLY when musically justified:
- For SIMPLE PARTS (pads, sustained chords, basic accompaniment): use ONE articulation (usually "sustain")
- For MELODIC/EXPRESSIVE parts: mix articulations tastefully
- For RHYTHMIC parts: consider staccato/spiccato for punch
- NEVER add articulation variety just for variety's sake

TWO-LAYER DYNAMICS SYSTEM:
1. VELOCITY (vel: 1-127) - PER-NOTE dynamics:
   - Attack intensity of each note
   - For SHORT articulations (staccato, pizzicato): velocity IS the dynamics
   - Vary for accents, phrase shaping: strong beats 90-110, weak 60-80, accents 100-127, ghost notes 40-55
   
2. CC1 CURVE (curves.dynamics) - PHRASE dynamics:
   - Overall expression envelope over time
   - For LONG articulations (sustain, legato): CC1 shapes the sound
   - Use for crescendos, swells, phrase arcs

DYNAMICS STRATEGIES BY PART TYPE:
- Sustained pads/chords: FLAT or slow-swell CC1, uniform velocity across chord
- Melodic lines: Varied velocity (phrase peaks), CC1 for overall arc
- Rhythmic parts: Velocity for accents, CC1 relatively flat
- Building intensity: Both velocity and CC1 increase together
- Intimate/soft: Low velocity (50-70), low CC1 (40-60)

OUTPUT FORMAT:
{
  "notes": [
    {"start_q": 0, "dur_q": 4, "pitch": 60, "vel": 85, "chan": 1, "articulation": "sustain"},
    {"start_q": 0, "dur_q": 4, "pitch": 64, "vel": 85, "chan": 1, "articulation": "sustain"},
    {"start_q": 0, "dur_q": 4, "pitch": 67, "vel": 85, "chan": 1, "articulation": "sustain"},
    ...
  ],
  "curves": {"dynamics": {"interp": "cubic", "breakpoints": [{"time_q": 0, "value": 70}, {"time_q": 8, "value": 85}, ...]}},
  "generation_type": "Chords",
  "generation_style": "Cinematic"
}

IMPORTANT:
- Each note CAN have "articulation" field (optional if all notes use same articulation)
- For simple pad/chord parts, you may omit per-note articulation and set global "articulation": "sustain"
- VARY velocity values appropriately - not all notes should have same velocity
- Include 'generation_type' and 'generation_style' in response

CRITICAL: 
- Use ONLY pitches from the ALLOWED PITCHES list
- Generate enough notes to fill the duration musically
- MUST include 'curves' with 'dynamics'
- MATCH the complexity of your output to what the user actually requested"""

NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

logger = logging.getLogger("ai_part_generator")
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
handler.stream.reconfigure(encoding='utf-8')
logger.addHandler(handler)
logger.setLevel(logging.INFO)

app = FastAPI(title=APP_NAME)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


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


class ModelInfo(BaseModel):
    provider: str = DEFAULT_PROVIDER
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class GenerateRequest(BaseModel):
    time: TimeWindow
    music: MusicInfo
    target: TargetInfo
    context: Optional[ContextInfo] = None
    generation_type: str = "Melody"
    generation_style: str = "Heroic"
    free_mode: bool = False
    user_prompt: str = ""
    model: Optional[ModelInfo] = None


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


def safe_format(template: str, values: Dict[str, Any]) -> str:
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(SafeDict(values))


def note_to_midi(note: Any) -> int:
    if isinstance(note, int):
        return note
    if isinstance(note, float) and note.is_integer():
        return int(note)
    if isinstance(note, str):
        if note.isdigit() or (note.startswith("-") and note[1:].isdigit()):
            return int(note)
        match = NOTE_RE.match(note.strip())
        if not match:
            raise ValueError(f"Invalid note format: {note}")
        letter, accidental, octave_str = match.groups()
        octave = int(octave_str)
        base_map = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        semitone = base_map[letter.upper()]
        if accidental == "#":
            semitone += 1
        elif accidental == "b":
            semitone -= 1
        midi = (octave + 1) * 12 + semitone
        return int(midi)
    raise ValueError(f"Unsupported note value: {note}")


def parse_range(range_data: Any) -> Optional[Tuple[int, int]]:
    if not range_data or not isinstance(range_data, list) or len(range_data) != 2:
        return None
    low = note_to_midi(range_data[0])
    high = note_to_midi(range_data[1])
    low = max(MIDI_MIN, min(MIDI_MAX, low))
    high = max(MIDI_MIN, min(MIDI_MAX, high))
    return (min(low, high), max(low, high))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fit_pitch_to_range(pitch: int, abs_range: Optional[Tuple[int, int]], policy: str) -> int:
    if not abs_range:
        return pitch
    low, high = abs_range
    if low <= pitch <= high:
        return pitch
    if policy == "octave_shift_to_fit":
        shifted = pitch
        if shifted < low:
            while shifted < low:
                shifted += 12
        elif shifted > high:
            while shifted > high:
                shifted -= 12
        if low <= shifted <= high:
            return shifted
    return int(clamp(pitch, low, high))


def normalize_channel(value: Optional[Any], default_chan: int) -> int:
    if value is None:
        return default_chan
    try:
        chan = int(value)
    except (TypeError, ValueError):
        return default_chan
    if 0 <= chan <= MIDI_CHAN_ZERO_BASE_MAX:
        return chan + 1
    if MIDI_CHAN_MIN <= chan <= MIDI_CHAN_MAX:
        return chan
    return default_chan


def deduplicate_notes(notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not notes:
        return notes
    best: Dict[Tuple[float, int, int], Dict[str, Any]] = {}
    for note in notes:
        key = (round(note["start_q"], 4), note["pitch"], note["chan"])
        existing = best.get(key)
        if existing is None or note["dur_q"] > existing["dur_q"]:
            best[key] = note
    return list(best.values())


def normalize_notes(
    notes: List[Dict[str, Any]],
    length_q: float,
    default_chan: int,
    abs_range: Optional[Tuple[int, int]],
    fix_policy: str,
    mono: bool,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for note in notes:
        try:
            start_q = float(note.get("start_q", 0.0))
            dur_q = float(note.get("dur_q", MIN_NOTE_DUR_Q))
            pitch = int(note.get("pitch", DEFAULT_PITCH))
            vel = int(note.get("vel", DEFAULT_VELOCITY))
            chan = normalize_channel(note.get("chan"), default_chan)
        except (TypeError, ValueError):
            continue

        start_q = clamp(start_q, 0.0, max(0.0, length_q))
        dur_q = max(MIN_NOTE_DUR_Q, dur_q)
        if start_q + dur_q > length_q:
            dur_q = max(0.0, length_q - start_q)
        if dur_q <= 0:
            continue

        pitch = fit_pitch_to_range(pitch, abs_range, fix_policy)
        pitch = int(clamp(pitch, MIDI_MIN, MIDI_MAX))
        vel = int(clamp(vel, MIDI_VEL_MIN, MIDI_MAX))

        normalized.append(
            {
                "start_q": start_q,
                "dur_q": dur_q,
                "pitch": pitch,
                "vel": vel,
                "chan": chan,
            }
        )

    normalized = deduplicate_notes(normalized)

    if not mono:
        return normalized

    normalized.sort(key=lambda n: (n["start_q"], n["pitch"]))
    mono_notes: List[Dict[str, Any]] = []
    for note in normalized:
        if not mono_notes:
            mono_notes.append(note)
            continue
        prev = mono_notes[-1]
        prev_end = prev["start_q"] + prev["dur_q"]
        if prev_end > note["start_q"]:
            new_dur = note["start_q"] - prev["start_q"] - MIN_NOTE_GAP_Q
            if new_dur < MIN_NOTE_DUR_Q:
                mono_notes.pop()
            else:
                prev["dur_q"] = new_dur
        mono_notes.append(note)
    return mono_notes


def normalize_drums(
    drums: List[Dict[str, Any]],
    drum_map: Dict[str, Any],
    length_q: float,
    default_chan: int,
) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    for hit in drums:
        name = hit.get("drum") or hit.get("name")
        if not name:
            continue
        pitch_raw = drum_map.get(str(name).lower()) or drum_map.get(name)
        if pitch_raw is None:
            continue
        try:
            pitch = note_to_midi(pitch_raw)
        except ValueError:
            continue
        start_q = float(hit.get("time_q", 0.0))
        dur_q = float(hit.get("dur_q", MIN_NOTE_DUR_Q))
        vel = int(hit.get("vel", DEFAULT_DRUM_VELOCITY))
        chan = normalize_channel(hit.get("chan"), default_chan)
        start_q = clamp(start_q, 0.0, max(0.0, length_q))
        dur_q = max(MIN_NOTE_DUR_Q, dur_q)
        if start_q + dur_q > length_q:
            dur_q = max(0.0, length_q - start_q)
        if dur_q <= 0:
            continue
        vel = int(clamp(vel, MIDI_VEL_MIN, MIDI_MAX))
        notes.append(
            {
                "start_q": start_q,
                "dur_q": dur_q,
                "pitch": int(clamp(pitch, MIDI_MIN, MIDI_MAX)),
                "vel": vel,
                "chan": chan,
            }
        )
    return notes


def catmull_rom(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2 * p1)
        + (-p0 + p2) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
    )


def eval_curve_at(
    breakpoints: List[Dict[str, float]],
    interp: str,
    t: float,
) -> float:
    if not breakpoints:
        return 0.0
    if len(breakpoints) == 1:
        return breakpoints[0]["value"]
    idx = 0
    while idx < len(breakpoints) - 1 and breakpoints[idx + 1]["time_q"] <= t:
        idx += 1
    if idx >= len(breakpoints) - 1:
        return breakpoints[-1]["value"]
    p1 = breakpoints[idx]
    p2 = breakpoints[idx + 1]
    if interp == "hold":
        return p1["value"]
    if p2["time_q"] <= p1["time_q"]:
        return p2["value"]
    u = (t - p1["time_q"]) / (p2["time_q"] - p1["time_q"])
    if interp == "linear":
        return p1["value"] + (p2["value"] - p1["value"]) * u
    p0 = breakpoints[idx - 1] if idx - 1 >= 0 else p1
    p3 = breakpoints[idx + 2] if idx + 2 < len(breakpoints) else p2
    return catmull_rom(p0["value"], p1["value"], p2["value"], p3["value"], u)


def build_cc_events(
    curves: Dict[str, Any],
    profile: Dict[str, Any],
    length_q: float,
    default_chan: int,
) -> List[Dict[str, Any]]:
    controller_cfg = profile.get("controllers", {})
    semantic_to_cc = controller_cfg.get("semantic_to_cc", {})
    smoothing = controller_cfg.get("smoothing", {})
    step_q = parse_step_q(smoothing.get("min_step", "1/64"))
    interp_default = smoothing.get("interp", DEFAULT_CC_INTERP)
    mode = smoothing.get("mode", DEFAULT_SMOOTHING_MODE)
    write_every_step = bool(smoothing.get("write_every_step", True))

    events: List[Dict[str, Any]] = []
    if not curves:
        return events

    for semantic, curve in curves.items():
        if semantic not in semantic_to_cc:
            continue
        cc_num = int(semantic_to_cc[semantic])
        if cc_num < MIDI_MIN or cc_num > MIDI_MAX:
            continue
        interp = str(curve.get("interp") or interp_default).lower()
        raw_points = curve.get("breakpoints", [])
        points: List[Dict[str, float]] = []
        for point in raw_points:
            try:
                time_q = float(point.get("time_q", 0.0))
                value = float(point.get("value", 0.0))
            except (TypeError, ValueError):
                continue
            time_q = clamp(time_q, 0.0, max(0.0, length_q))
            value = clamp(value, float(MIDI_MIN), float(MIDI_MAX))
            points.append({"time_q": time_q, "value": value})
        if not points:
            continue
        points.sort(key=lambda p: p["time_q"])
        time_q = 0.0
        last_val: Optional[int] = None
        while time_q <= length_q + 1e-6:
            value = eval_curve_at(points, interp, time_q)
            value_int = int(round(clamp(value, float(MIDI_MIN), float(MIDI_MAX))))
            if mode == "fixed" or write_every_step:
                events.append(
                    {
                        "time_q": time_q,
                        "cc": cc_num,
                        "value": value_int,
                        "chan": default_chan,
                    }
                )
            else:
                if last_val is None or value_int != last_val:
                    events.append(
                        {
                            "time_q": time_q,
                            "cc": cc_num,
                            "value": value_int,
                            "chan": default_chan,
                        }
                    )
            last_val = value_int
            time_q += step_q
    return events


def parse_step_q(step: Any) -> float:
    if isinstance(step, (int, float)):
        return max(MIN_CC_STEP_Q, float(step))
    if isinstance(step, str) and "/" in step:
        parts = step.split("/", 1)
        try:
            num = float(parts[0])
            den = float(parts[1])
            if den > 0:
                return max(MIN_CC_STEP_Q, (QUARTERS_PER_WHOLE * num) / den)
        except (ValueError, ZeroDivisionError):
            return MIN_CC_STEP_Q
    return MIN_CC_STEP_Q


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CHORD_TYPES = {
    frozenset([0, 4, 7]): "",
    frozenset([0, 3, 7]): "m",
    frozenset([0, 4, 7, 11]): "maj7",
    frozenset([0, 3, 7, 10]): "m7",
    frozenset([0, 4, 7, 10]): "7",
    frozenset([0, 3, 6]): "dim",
    frozenset([0, 3, 6, 9]): "dim7",
    frozenset([0, 3, 6, 10]): "m7b5",
    frozenset([0, 4, 8]): "aug",
    frozenset([0, 4, 8, 10]): "aug7",
    frozenset([0, 4, 8, 11]): "augmaj7",
    frozenset([0, 5, 7]): "sus4",
    frozenset([0, 2, 7]): "sus2",
    frozenset([0, 2, 5, 7]): "sus2sus4",
    frozenset([0, 7]): "5",
    frozenset([0, 4]): "(no5)",
    frozenset([0, 3]): "m(no5)",
    frozenset([0, 4, 7, 9]): "6",
    frozenset([0, 3, 7, 9]): "m6",
    frozenset([0, 4, 7, 10, 14]): "9",
    frozenset([0, 3, 7, 10, 14]): "m9",
    frozenset([0, 4, 7, 11, 14]): "maj9",
    frozenset([0, 4, 7, 10, 13]): "7b9",
    frozenset([0, 4, 7, 10, 15]): "7#9",
    frozenset([0, 4, 7, 10, 14, 17]): "11",
    frozenset([0, 3, 7, 10, 14, 17]): "m11",
    frozenset([0, 4, 7, 11, 14, 17]): "maj11",
    frozenset([0, 4, 7, 10, 14, 21]): "13",
    frozenset([0, 3, 7, 10, 14, 21]): "m13",
    frozenset([0, 4, 7, 11, 14, 21]): "maj13",
    frozenset([0, 5, 7, 10]): "7sus4",
    frozenset([0, 2, 7, 10]): "7sus2",
    frozenset([0, 5, 7, 10, 14]): "9sus4",
    frozenset([0, 5, 7, 11]): "maj7sus4",
    frozenset([0, 2, 7, 11]): "maj7sus2",
    frozenset([0, 2, 4, 7]): "add2",
    frozenset([0, 4, 5, 7]): "add4",
    frozenset([0, 4, 7, 14]): "add9",
    frozenset([0, 3, 7, 14]): "madd9",
    frozenset([0, 4, 7, 17]): "add11",
    frozenset([0, 3, 7, 17]): "madd11",
    frozenset([0, 4, 10]): "7(no5)",
    frozenset([0, 3, 10]): "m7(no5)",
    frozenset([0, 4, 11]): "maj7(no5)",
    frozenset([0, 3, 11]): "mM7(no5)",
    frozenset([0, 3, 7, 11]): "mM7",
    frozenset([0, 4, 6, 10]): "7b5",
    frozenset([0, 4, 8, 10]): "7#5",
    frozenset([0, 4, 6, 11]): "maj7b5",
    frozenset([0, 4, 8, 11]): "maj7#5",
    frozenset([0, 4, 6, 7]): "add#11",
    frozenset([0, 4, 7, 18]): "add#11",
    frozenset([0, 1, 7]): "addb9",
    frozenset([0, 3, 8]): "m#5",
    frozenset([0, 4, 6]): "b5",
    frozenset([0, 1, 4, 7]): "addb2",
    frozenset([0, 4, 7, 10, 14, 18]): "11#11",
    frozenset([0, 2]): "sus2(no5)",
    frozenset([0, 5]): "sus4(no5)",
    frozenset([0, 4, 9]): "6(no5)",
    frozenset([0, 3, 9]): "m6(no5)",
    frozenset([0, 7, 10]): "m7(no3)",
    frozenset([0, 7, 11]): "maj7(no3)",
    frozenset([0, 4, 7, 9, 14]): "6/9",
    frozenset([0, 3, 7, 9, 14]): "m6/9",
}


def pitch_to_note(pitch: int) -> str:
    return NOTE_NAMES[pitch % 12] + str(pitch // 12 - 1)


SCALE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "natural minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic minor": [0, 2, 3, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "pentatonic major": [0, 2, 4, 7, 9],
    "pentatonic minor": [0, 3, 5, 7, 10],
}

NOTE_TO_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5, "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11, "B#": 0,
}


def parse_key(key_str: str) -> Tuple[int, str]:
    if not key_str or key_str.lower() == "unknown":
        return 0, "major"

    key_str = key_str.strip()
    key_lower = key_str.lower()

    is_minor = "minor" in key_lower or "min" in key_lower or key_str.endswith("m")
    scale_type = "minor" if is_minor else "major"

    root_str = key_str.replace("minor", "").replace("Minor", "").replace("major", "").replace("Major", "")
    root_str = root_str.replace("min", "").replace("Min", "").replace("maj", "").replace("Maj", "")
    root_str = root_str.strip()

    if root_str.endswith("m") and len(root_str) > 1:
        root_str = root_str[:-1]

    root_str = root_str.strip()
    if not root_str:
        return 0, scale_type

    root_pc = NOTE_TO_PC.get(root_str, NOTE_TO_PC.get(root_str.capitalize(), 0))
    return root_pc, scale_type


def get_scale_notes(key_str: str, pitch_low: int, pitch_high: int) -> List[int]:
    root_pc, scale_type = parse_key(key_str)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])

    scale_pcs = set((root_pc + i) % 12 for i in intervals)

    valid_pitches = []
    for pitch in range(pitch_low, pitch_high + 1):
        if pitch % 12 in scale_pcs:
            valid_pitches.append(pitch)

    return valid_pitches


def get_scale_note_names(key_str: str) -> str:
    root_pc, scale_type = parse_key(key_str)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])

    note_names = []
    for interval in intervals:
        pc = (root_pc + interval) % 12
        note_names.append(NOTE_NAMES[pc])

    return ", ".join(note_names)


def analyze_chord(pitches: List[int]) -> Tuple[str, Optional[int]]:
    if not pitches:
        return "?", None
    if len(pitches) == 1:
        root = pitches[0] % 12
        return NOTE_NAMES[root], root

    pitch_classes = sorted(set(p % 12 for p in pitches))
    bass_pc = min(pitches) % 12

    for root_pc in pitch_classes:
        intervals = frozenset((pc - root_pc) % 12 for pc in pitch_classes)
        if intervals in CHORD_TYPES:
            chord_name = NOTE_NAMES[root_pc] + CHORD_TYPES[intervals]
            if root_pc != bass_pc:
                chord_name += "/" + NOTE_NAMES[bass_pc]
            return chord_name, root_pc

    best_match = _find_best_chord_match(pitch_classes, bass_pc)
    if best_match:
        return best_match

    inferred = _infer_chord_from_intervals(pitch_classes, bass_pc)
    if inferred:
        return inferred

    return NOTE_NAMES[bass_pc] + "(?)", bass_pc


def _find_best_chord_match(
    pitch_classes: List[int], bass_pc: int
) -> Optional[Tuple[str, int]]:
    best_score = 0
    best_result: Optional[Tuple[str, int]] = None
    pc_set = set(pitch_classes)

    for root_pc in pitch_classes:
        intervals = frozenset((pc - root_pc) % 12 for pc in pitch_classes)
        for chord_intervals, chord_suffix in CHORD_TYPES.items():
            common = len(intervals & chord_intervals)
            missing = len(chord_intervals - intervals)
            extra = len(intervals - chord_intervals)

            if common < 2:
                continue

            score = common * 10 - missing * 5 - extra * 2

            has_root = 0 in intervals
            has_third = 3 in intervals or 4 in intervals
            has_fifth = 7 in intervals or 6 in intervals or 8 in intervals

            if has_root:
                score += 5
            if has_third:
                score += 3
            if has_fifth:
                score += 2

            if score > best_score and missing <= 2 and extra <= 2:
                best_score = score
                suffix = chord_suffix
                if extra > 0:
                    extra_intervals = intervals - chord_intervals
                    if extra_intervals:
                        suffix += _describe_extensions(extra_intervals)
                chord_name = NOTE_NAMES[root_pc] + suffix
                if root_pc != bass_pc:
                    chord_name += "/" + NOTE_NAMES[bass_pc]
                best_result = (chord_name, root_pc)

    return best_result


def _describe_extensions(extra_intervals: frozenset) -> str:
    ext_map = {
        1: "b9", 2: "9", 3: "#9", 5: "11", 6: "#11",
        8: "b13", 9: "13", 10: "7", 11: "maj7"
    }
    extensions = []
    for interval in sorted(extra_intervals):
        if interval in ext_map:
            extensions.append(ext_map[interval])
    if extensions:
        return "add(" + ",".join(extensions) + ")"
    return ""


def _infer_chord_from_intervals(
    pitch_classes: List[int], bass_pc: int
) -> Optional[Tuple[str, int]]:
    if len(pitch_classes) < 2:
        return None

    for root_pc in pitch_classes:
        intervals = set((pc - root_pc) % 12 for pc in pitch_classes)

        has_major_third = 4 in intervals
        has_minor_third = 3 in intervals
        has_perfect_fifth = 7 in intervals
        has_dim_fifth = 6 in intervals
        has_aug_fifth = 8 in intervals
        has_minor_seventh = 10 in intervals
        has_major_seventh = 11 in intervals
        has_ninth = 2 in intervals or 14 in intervals
        has_fourth = 5 in intervals
        has_sixth = 9 in intervals

        chord_type = ""

        if has_major_third and has_perfect_fifth:
            chord_type = ""
        elif has_minor_third and has_perfect_fifth:
            chord_type = "m"
        elif has_minor_third and has_dim_fifth:
            chord_type = "dim"
        elif has_major_third and has_aug_fifth:
            chord_type = "aug"
        elif has_fourth and has_perfect_fifth:
            chord_type = "sus4"
        elif has_ninth and has_perfect_fifth and not has_major_third and not has_minor_third:
            chord_type = "sus2"
        elif has_major_third and not has_perfect_fifth and not has_dim_fifth and not has_aug_fifth:
            chord_type = "(no5)"
        elif has_minor_third and not has_perfect_fifth and not has_dim_fifth:
            chord_type = "m(no5)"
        elif has_perfect_fifth and not has_major_third and not has_minor_third:
            chord_type = "5"
        else:
            continue

        if has_major_seventh:
            if chord_type == "m":
                chord_type = "mM7"
            elif chord_type == "":
                chord_type = "maj7"
            elif chord_type == "aug":
                chord_type = "augmaj7"
            else:
                chord_type += "maj7"
        elif has_minor_seventh:
            if chord_type == "dim":
                chord_type = "m7b5"
            elif chord_type == "m":
                chord_type = "m7"
            elif chord_type == "":
                chord_type = "7"
            elif chord_type == "sus4":
                chord_type = "7sus4"
            elif chord_type == "sus2":
                chord_type = "7sus2"
            else:
                chord_type += "7"

        if has_sixth and "7" not in chord_type:
            chord_type += "6"

        if has_ninth and "sus2" not in chord_type:
            if "7" in chord_type or "maj7" in chord_type:
                chord_type = chord_type.replace("7", "9").replace("maj9", "maj9")
            else:
                chord_type += "add9"

        chord_name = NOTE_NAMES[root_pc] + chord_type
        if root_pc != bass_pc:
            chord_name += "/" + NOTE_NAMES[bass_pc]
        return chord_name, root_pc

    return None


def detect_key_from_chords(chord_roots: List[int]) -> str:
    if not chord_roots:
        return "unknown"

    root_counts: Dict[int, int] = {}
    for root in chord_roots:
        if root is not None:
            root_counts[root] = root_counts.get(root, 0) + 1

    if not root_counts:
        return "unknown"

    most_common = max(root_counts.keys(), key=lambda r: root_counts[r])

    major_scale = [0, 2, 4, 5, 7, 9, 11]
    minor_scale = [0, 2, 3, 5, 7, 8, 10]

    for tonic in range(12):
        major_notes = set((tonic + i) % 12 for i in major_scale)
        minor_notes = set((tonic + i) % 12 for i in minor_scale)

        if all(r in major_notes for r in root_counts.keys()):
            return f"{NOTE_NAMES[tonic]} major"
        if all(r in minor_notes for r in root_counts.keys()):
            return f"{NOTE_NAMES[tonic]} minor"

    return f"{NOTE_NAMES[most_common]} (estimated)"


def parse_time_sig(time_sig: str) -> Tuple[int, int]:
    try:
        parts = time_sig.split("/")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 4, 4


def get_quarters_per_bar(time_sig: str) -> float:
    num, denom = parse_time_sig(time_sig)
    return num * (4.0 / denom)


def analyze_harmony_progression(
    existing_notes: List[Dict],
    time_sig: str = "4/4",
    length_q: float = 16.0
) -> Tuple[str, str]:
    if not existing_notes:
        return "", "unknown"

    quarters_per_bar = get_quarters_per_bar(time_sig)
    num, denom = parse_time_sig(time_sig)

    chord_unit = quarters_per_bar / 2 if quarters_per_bar >= 2 else quarters_per_bar

    segments: Dict[int, List[int]] = {}
    for note in existing_notes:
        start_q = note.get("start_q", 0)
        pitch = note.get("pitch", 60)
        dur_q = note.get("dur_q", 0.5)

        seg_start = int(start_q // chord_unit)
        seg_end = int((start_q + dur_q) // chord_unit)

        for seg_idx in range(seg_start, seg_end + 1):
            if seg_idx not in segments:
                segments[seg_idx] = []
            if pitch not in segments[seg_idx]:
                segments[seg_idx].append(pitch)

    progression = []
    chord_roots = []
    segments_per_bar = max(1, int(quarters_per_bar / chord_unit))

    for seg_idx in sorted(segments.keys()):
        bar_num = (seg_idx // segments_per_bar) + 1
        beat_in_bar = (seg_idx % segments_per_bar) + 1
        chord_name, root = analyze_chord(segments[seg_idx])
        if root is not None:
            chord_roots.append(root)
        if segments_per_bar > 1:
            progression.append(f"B{bar_num}.{beat_in_bar}:{chord_name}")
        else:
            progression.append(f"B{bar_num}:{chord_name}")

    detected_key = detect_key_from_chords(chord_roots)
    return " | ".join(progression), detected_key


def analyze_horizontal_notes(notes: List[Dict[str, Any]], label: str) -> str:
    if not notes:
        return ""
    
    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    
    pitches = [n.get("pitch", 60) for n in sorted_notes]
    min_pitch = min(pitches)
    max_pitch = max(pitches)
    
    unique_pitches = sorted(set(pitches))
    pitch_classes = set(p % 12 for p in unique_pitches)
    
    first_few = sorted_notes[:min(8, len(sorted_notes))]
    last_few = sorted_notes[-min(4, len(sorted_notes)):] if len(sorted_notes) > 8 else []
    
    parts = [f"{label} ({len(notes)} notes, range {pitch_to_note(min_pitch)}-{pitch_to_note(max_pitch)}):"]
    
    note_strs = []
    for n in first_few:
        note_strs.append(f"{pitch_to_note(n['pitch'])}@{n.get('start_q', 0):.2f}")
    
    if last_few and last_few != first_few:
        note_strs.append("...")
        for n in last_few:
            note_strs.append(f"{pitch_to_note(n['pitch'])}@{n.get('start_q', 0):.2f}")
    
    parts.append(" ".join(note_strs))
    
    return " ".join(parts)


def build_horizontal_context_summary(horizontal: Optional[HorizontalContext]) -> Tuple[str, str]:
    if not horizontal:
        return "", "isolated"
    
    parts: List[str] = []
    
    position_descriptions = {
        "start": "This is the BEGINNING of a musical section. There is existing material AFTER the generation area.",
        "middle": "This is the MIDDLE of a musical section. There is existing material BEFORE and AFTER the generation area.",
        "end": "This is the END of a musical section. There is existing material BEFORE the generation area.",
        "isolated": "This is an isolated section with no surrounding context on this track."
    }
    
    position = horizontal.position or "isolated"
    parts.append(f"### TEMPORAL POSITION\n{position_descriptions.get(position, position_descriptions['isolated'])}")
    
    if horizontal.before:
        before_summary = analyze_horizontal_notes(horizontal.before, "BEFORE (preceding notes)")
        if before_summary:
            parts.append(before_summary)
            
        last_notes = sorted(horizontal.before, key=lambda n: n.get("start_q", 0))[-4:]
        if last_notes:
            last_pitches = [n.get("pitch", 60) for n in last_notes]
            parts.append(f"Last notes before target: {', '.join(pitch_to_note(p) for p in last_pitches)}")
    
    if horizontal.after:
        after_summary = analyze_horizontal_notes(horizontal.after, "AFTER (following notes)")
        if after_summary:
            parts.append(after_summary)
            
        first_notes = sorted(horizontal.after, key=lambda n: n.get("start_q", 0))[:4]
        if first_notes:
            first_pitches = [n.get("pitch", 60) for n in first_notes]
            parts.append(f"First notes after target: {', '.join(pitch_to_note(p) for p in first_pitches)}")
    
    return "\n".join(parts), position


def detect_continuation_intent(user_prompt: str) -> Optional[str]:
    if not user_prompt:
        return None
    
    prompt_lower = user_prompt.lower()
    
    continue_keywords = [
        "продолжи", "продолжить", "continue", "extend",
        "развей", "развить", "develop",
        "далее", "дальше",
    ]
    
    complete_keywords = [
        "заверши", "завершить", "завершение",
        "закончи", "закончить", "finish", "complete", "end",
        "финал", "кода", "coda", "outro",
    ]
    
    fill_keywords = [
        "заполни", "заполнить", "fill", "fill in",
        "между", "between", "connect", "bridge",
        "соедини", "соединить",
    ]
    
    progression_keywords = [
        "аккордов", "аккорд", "chord", "progression", "прогрессию", "прогрессия",
        "гармони", "harmon",
    ]
    
    has_progression = any(kw in prompt_lower for kw in progression_keywords)
    
    for kw in continue_keywords:
        if kw in prompt_lower:
            return "continue_progression" if has_progression else "continue"
    
    for kw in complete_keywords:
        if kw in prompt_lower:
            return "complete_progression" if has_progression else "complete"
    
    for kw in fill_keywords:
        if kw in prompt_lower:
            return "fill_progression" if has_progression else "fill"
    
    return None


def build_context_summary(
    context: Optional[ContextInfo],
    time_sig: str = "4/4",
    length_q: float = 16.0
) -> Tuple[str, str, str]:
    if not context:
        return "", "unknown", "isolated"

    parts: List[str] = []
    detected_key = "unknown"
    position = "isolated"

    horizontal_summary, position = build_horizontal_context_summary(context.horizontal)
    if horizontal_summary:
        parts.append(horizontal_summary)

    notes_for_progression = context.extended_progression or context.existing_notes
    if notes_for_progression:
        progression, detected_key = analyze_harmony_progression(notes_for_progression, time_sig, length_q)
        if progression:
            parts.append(f"### HARMONY CONTEXT\nCHORD PROGRESSION: {progression}")

    if context.existing_notes:
        if context.pitch_range:
            min_p = context.pitch_range.get("min", 48)
            max_p = context.pitch_range.get("max", 72)
            parts.append(f"Vertical context range: {pitch_to_note(min_p)} to {pitch_to_note(max_p)} (MIDI {min_p}-{max_p})")
            suggested_low = max_p
            suggested_high = min(max_p + 12, 96)
            parts.append(f"SUGGESTED MELODY RANGE: MIDI {suggested_low}-{suggested_high} (above existing parts)")

    if context.context_notes:
        parts.append(context.context_notes.strip())

    if context.selected_tracks_midi:
        names = []
        for t in context.selected_tracks_midi:
            if isinstance(t, str):
                names.append(t)
            elif hasattr(t, 'name') and t.name:
                names.append(t.name)
            elif isinstance(t, dict) and t.get('name'):
                names.append(t['name'])
        if names:
            parts.append(f"Accompanying tracks: {', '.join(names)}")

    return "\n".join([p for p in parts if p]), detected_key, position


def estimate_note_count(length_q: float, bpm: float, time_sig: str, generation_type: str) -> Tuple[int, int, str]:
    """Estimate recommended note count based on musical context."""
    try:
        sig_parts = time_sig.split("/")
        beats_per_bar = int(sig_parts[0])
        beat_unit = int(sig_parts[1])
    except (ValueError, IndexError):
        beats_per_bar = 4
        beat_unit = 4

    quarters_per_bar = beats_per_bar * (4.0 / beat_unit)
    bars = length_q / quarters_per_bar if quarters_per_bar > 0 else length_q / 4
    bars = max(1, bars)

    gen_type_lower = generation_type.lower()

    if "melody" in gen_type_lower:
        notes_per_bar_min = 2
        notes_per_bar_max = 8
        density_desc = "moderate melodic density with varied rhythms"
    elif "arpeggio" in gen_type_lower:
        notes_per_bar_min = 8
        notes_per_bar_max = 16
        density_desc = "continuous arpeggiated pattern"
    elif "bass" in gen_type_lower:
        notes_per_bar_min = 1
        notes_per_bar_max = 4
        density_desc = "sparse but rhythmically strong bass notes"
    elif "chord" in gen_type_lower:
        notes_per_bar_min = 1
        notes_per_bar_max = 4
        density_desc = "chord changes, multiple simultaneous notes per chord"
    elif "pad" in gen_type_lower or "sustain" in gen_type_lower:
        notes_per_bar_min = 0.5
        notes_per_bar_max = 2
        density_desc = "long sustained notes with smooth transitions"
    elif "rhythm" in gen_type_lower:
        notes_per_bar_min = 4
        notes_per_bar_max = 16
        density_desc = "rhythmic pattern with clear pulse"
    elif "counter" in gen_type_lower:
        notes_per_bar_min = 2
        notes_per_bar_max = 6
        density_desc = "independent melodic line that complements the main melody"
    elif "accomp" in gen_type_lower:
        notes_per_bar_min = 2
        notes_per_bar_max = 8
        density_desc = "supportive accompaniment pattern"
    else:
        notes_per_bar_min = 2
        notes_per_bar_max = 8
        density_desc = "appropriate musical content"

    min_notes = max(1, int(bars * notes_per_bar_min))
    max_notes = max(min_notes + 1, int(bars * notes_per_bar_max))

    return min_notes, max_notes, density_desc


def build_articulation_list_for_prompt(profile: Dict[str, Any]) -> str:
    art_cfg = profile.get("articulations", {})
    art_map = art_cfg.get("map", {})
    if not art_map:
        return "No articulations available"
    
    short_arts = []
    long_arts = []
    
    for name, data in sorted(art_map.items()):
        desc = data.get("description", name)
        dynamics_type = data.get("dynamics", "cc1")
        if dynamics_type == "velocity":
            short_arts.append(f"  - {name}: {desc}")
        else:
            long_arts.append(f"  - {name}: {desc}")
    
    result_parts = []
    if long_arts:
        result_parts.append("LONG articulations (dynamics via CC1 curve):")
        result_parts.extend(long_arts)
    if short_arts:
        result_parts.append("SHORT articulations (dynamics via velocity):")
        result_parts.extend(short_arts)
    
    return "\n".join(result_parts)


def build_prompt(
    request: GenerateRequest,
    profile: Dict[str, Any],
    preset_name: Optional[str],
    preset_settings: Dict[str, Any],
    length_q: float,
) -> Tuple[str, str]:
    profile_ai = profile.get("ai", {})
    profile_system = profile_ai.get("system_prompt_template", "")
    profile_user = profile_ai.get("user_prompt_template", "")
    answer_schema = profile_ai.get("answer_schema", "")
    profile_range = profile.get("range", {})
    abs_range = profile_range.get("absolute")
    pref_range = profile_range.get("preferred")

    generation_type = request.generation_type or "Melody"
    min_notes, max_notes, density_desc = estimate_note_count(
        length_q, request.music.bpm, request.music.time_sig, generation_type
    )

    values = {
        "profile_name": profile.get("name", ""),
        "profile_id": profile.get("id", ""),
        "family": profile.get("family", ""),
        "bpm": request.music.bpm,
        "time_sig": request.music.time_sig,
        "key": request.music.key,
        "selection_quarters": round(length_q, 4),
        "range_absolute": abs_range,
        "range_preferred": pref_range,
        "preset_name": preset_name or "",
        "preset_settings": json.dumps(preset_settings, ensure_ascii=False),
        "polyphony": profile.get("midi", {}).get("polyphony", ""),
        "is_drum": profile.get("midi", {}).get("is_drum", False),
        "channel": profile.get("midi", {}).get("channel", 1),
        "generation_type": generation_type,
        "min_notes": min_notes,
        "max_notes": max_notes,
    }

    midi_channel = profile.get("midi", {}).get("channel", 1)
    pitch_low = 48
    pitch_high = 72
    if pref_range and isinstance(pref_range, list) and len(pref_range) == 2:
        try:
            pitch_low = note_to_midi(pref_range[0])
            pitch_high = note_to_midi(pref_range[1])
        except ValueError:
            pass

    type_hints = {
        "melody": "Generate the MAIN MELODY - the primary musical theme. Must be memorable, singable, and emotionally engaging. Clear phrases with natural breathing points.",
        "arpeggio": "Generate an ARPEGGIO pattern - broken chord notes played sequentially. Flowing, harp-like movement following the harmony.",
        "bass line": "Generate a BASS LINE - the harmonic foundation. Supportive low notes that anchor the rhythm and harmony.",
        "chords": "Generate CHORDS - harmonic accompaniment. Block or broken chords providing harmonic support.",
        "pad": "Generate a PAD - sustained atmospheric background. Long, evolving notes creating harmonic bed.",
        "pad/sustained": "Generate a PAD - sustained atmospheric background. Long, evolving notes creating harmonic bed.",
        "counter-melody": "Generate a COUNTER-MELODY - a secondary melody complementing the main theme. Independent but harmonically related.",
        "accompaniment": "Generate ACCOMPANIMENT - rhythmic/harmonic support. Background pattern that enhances without dominating.",
        "rhythmic": "Generate a RHYTHMIC pattern - percussive, groove-focused. Short notes emphasizing beat and syncopation.",
        "ostinato": "Generate an OSTINATO - a repeating musical figure. Hypnotic, consistent pattern with subtle variations.",
        "fill": "Generate a FILL - transitional ornamental passage. Connects sections with flourishes and runs.",
    }
    gen_lower = generation_type.lower()
    type_hint = type_hints.get(gen_lower, f"Generate a {generation_type} part.")
    type_hint += " Result must be MUSICAL, easy to perceive, and memorable."

    mood_hints = {
        "heroic": "RISING melodic contours, strong intervals (4ths, 5ths, octaves). MAJOR tonality, bold dynamics (mf→ff). Emphasize downbeats. Confident, triumphant.",
        "epic": "GRAND sweeping lines, slow build-up. Wide intervals, unison movements. Long phrases to dramatic peaks. Dynamic swells. Majestic, powerful.",
        "triumphant": "FANFARE-like ascending motifs, bright major. Strong accents on beat 1. Celebratory, victorious. Peak dynamics at phrase ends.",
        "majestic": "SLOW dignified lines. Wide spacing, noble character. Sustained notes with gradual swells. Royal, ceremonial.",
        "adventurous": "ENERGETIC leaps, unexpected turns. Mix stepwise and wide intervals. Syncopation. Bright, forward-moving.",
        "dramatic": "Strong DYNAMIC CONTRASTS (pp↔ff). Unexpected accents. Tension intervals (m2, tritone). Emotional peaks then resolution.",
        "intense": "DRIVING ostinato, relentless motion. Crescendo passages. Dense activity. Urgent, pressing.",
        "suspense": "CHROMATIC movement, unresolved phrases. Quiet with sudden accents. Tremolo effects. Hanging, unresolved endings.",
        "thriller": "SYNCOPATED rhythms, unexpected rests. Dissonant intervals. Irregular phrase lengths. Nervous, unpredictable.",
        "horror": "CHROMATIC clusters, LOW register. Tremolo, wide leaps. Dissonant m2/tritone. Eerie, unsettling. Sudden dynamic changes.",
        "dark": "MINOR tonality, DESCENDING lines. Low-mid register. Heavy, oppressive. Slow harmonic rhythm.",
        "ominous": "SLOW creeping motion. Pedal tones with dissonant upper notes. Growing intensity. Threatening.",
        "romantic": "EXPRESSIVE rubato feel, sweeping arcs. Chromatic passing tones. Wide dynamics. Passionate, yearning.",
        "melancholic": "MINOR tonality, descending tendency. Slower feel. Suspensions, appoggiaturas. Wistful, sad.",
        "tender": "SOFT dynamics (pp-mp), close intervals (2nds, 3rds). Gentle flowing motion. Intimate, delicate.",
        "nostalgic": "SIMPLE memorable melodies. Repetitive motifs. Minor inflections in major. Bittersweet, reflective.",
        "passionate": "WIDE dynamic swings, expressive leaps. Building intensity. Emotional peaks. Heartfelt, fervent.",
        "longing": "SUSTAINED notes, yearning intervals (6ths, 7ths). Unresolved phrases. Reaching upward then falling. Aching.",
        "hopeful": "MAJOR tonality, RISING phrases. Gradual crescendo. Resolution on bright notes. Optimistic, uplifting.",
        "energetic": "FAST rhythmic activity, accented staccato. Syncopation for drive. Loud dynamics. Vigorous, lively.",
        "playful": "LIGHT staccato, melodic leaps. Major tonality. Dance-like rhythms. Cheerful, whimsical.",
        "action": "DRIVING ostinato, rapid passages. Accents on weak beats. Relentless motion. Exciting, tense.",
        "aggressive": "SHARP accents, marcato. Dissonant intervals. Strong dynamics. Forceful, attacking.",
        "fierce": "RAPID aggressive motion. Wide leaps, sforzando accents. Intense dynamics. Wild, untamed.",
        "peaceful": "SIMPLE consonant intervals (3rds, 6ths). Slow harmonic rhythm. Soft dynamics. Calm, serene.",
        "dreamy": "FLOWING arpeggiated figures, blurred phrase boundaries. High register. Soft. Floating, ethereal.",
        "ethereal": "HIGH register, sustained tones. Open intervals (4ths, 5ths). Sparse texture. Otherworldly, celestial.",
        "mysterious": "UNUSUAL intervals, ambiguous tonality. Quiet dynamics. Unexpected melodic turns. Enigmatic.",
        "meditative": "MINIMAL motion, repeated patterns. Consonant intervals. Very slow feel. Contemplative, zen.",
        "ambient": "LONG sustained notes, slow evolution. Minimal melodic activity. Atmospheric, spatial.",
        "celtic": "PENTATONIC scale, characteristic 4th/5th leaps. Ornamental grace notes. Dance-like. Folk, earthy.",
        "middle eastern": "PHRYGIAN/harmonic minor. Ornamental melismas. Augmented 2nd intervals. Exotic, mystical.",
        "asian": "PENTATONIC scale. Sparse texture. Contemplative pauses. Elegant, refined.",
        "latin": "SYNCOPATED rhythms, major tonality. Dance patterns. Warm, rhythmic.",
        "nordic": "OPEN 5ths, folk simplicity. Haunting minor melodies. Vast, cold, ancient.",
        "slavic": "MINOR tonality, characteristic intervals. Melancholic yet powerful. Folk dance elements.",
        "baroque": "SEQUENCES, ornaments (trills). Continuous motion. Contrapuntal. Elegant, formal.",
        "classical": "BALANCED 4+4 bar phrases. Clear periodic structure. Symmetric melodic shapes. Elegant.",
        "impressionist": "WHOLE-TONE and modal inflections. Blurred phrase boundaries. Coloristic, atmospheric.",
        "minimalist": "REPETITIVE patterns with subtle variations. Phase shifting. Hypnotic, evolving.",
        "victorious": "ASCENDING fanfare figures. Bright major. Strong downbeat accents. Celebrating, conquering.",
        "tragic": "DESCENDING minor lines. Slow, heavy rhythm. Lamenting intervals. Sorrowful, devastating.",
        "whimsical": "UNEXPECTED leaps, playful rhythms. Light articulation. Quirky, fantastical.",
        "serene": "CONSONANT intervals, gentle motion. Soft throughout. Tranquil, undisturbed.",
        "foreboding": "LOW register, slow chromatic motion. Building tension. Warning, threatening.",
        "magical": "SPARKLING high notes, arpeggiated figures. Whole-tone touches. Enchanting, wondrous.",
        "solemn": "SLOW hymn-like motion. Dignified intervals. Reverent, grave.",
    }
    generation_style = request.generation_style or "Heroic"
    style_lower = generation_style.lower()
    mood_hint = mood_hints.get(style_lower, f"Create in {generation_style} style.")

    articulation = preset_settings.get("articulation", "legato")
    articulation_hints = {
        "spiccato": "Use SHORT notes (dur_q: 0.25-0.5). Bouncy, detached.",
        "staccato": "Use VERY SHORT notes (dur_q: 0.125-0.25). Crisp, separated.",
        "legato": "Use CONNECTED notes. Smooth, flowing lines.",
        "pizzicato": "Use SHORT plucked notes (dur_q: 0.25-0.5).",
        "tremolo": "Use SUSTAINED notes with trembling effect.",
    }
    articulation_hint = articulation_hints.get(articulation.lower(), "") if articulation else ""

    dynamics_hints = {
        "heroic": "DYNAMICS: Strong and bold. Start mf (70-80), build to ff (100-120) at climax. Maintain high energy.",
        "epic": "DYNAMICS: Grand sweeping crescendo. Start mp (50-60), massive build to fff (120-127) at peak, then gradual descent.",
        "triumphant": "DYNAMICS: Victorious forte throughout. Start f (90), peak ff (110-120) at fanfare moments. Keep intensity high.",
        "majestic": "DYNAMICS: Dignified and steady. Moderate f (80-95) with slow subtle swells. No sudden changes.",
        "adventurous": "DYNAMICS: Dynamic variety. Mix mf (70) passages with sudden f (100) bursts. Energetic variation.",
        "dramatic": "DYNAMICS: Extreme contrasts. Sudden jumps: pp (30) to ff (110) and back. Terraced, not gradual.",
        "intense": "DYNAMICS: Relentless drive. Start mf (70), continuous crescendo to fff (120-127). No backing off.",
        "suspense": "DYNAMICS: Quiet tension. Mostly pp-p (25-50) with occasional sudden sfz spikes (100+) then back to quiet.",
        "thriller": "DYNAMICS: Nervous energy. Unpredictable jumps between p (40) and f (100). Irregular accents.",
        "horror": "DYNAMICS: Eerie quiet with shocks. Very soft pp (20-35) with sudden terrifying sfz (110-127) accents.",
        "dark": "DYNAMICS: Heavy and oppressive. Steady mf-f (70-90), slow downward trend. No bright moments.",
        "ominous": "DYNAMICS: Growing threat. Start ppp (15-25), inexorable crescendo. Never fully loud, always building.",
        "romantic": "DYNAMICS: Expressive swells. Wave-like motion mp→f→mp (50-100-50). Breathe with phrases.",
        "melancholic": "DYNAMICS: Soft and fading. Mostly p-mp (35-60). Gentle decrescendos at phrase ends.",
        "tender": "DYNAMICS: Intimate and soft. Stay pp-p (25-50). Minimal variation, delicate throughout.",
        "nostalgic": "DYNAMICS: Bittersweet waves. mp (55) with gentle swells to mf (75), always returning softer.",
        "passionate": "DYNAMICS: Intense expression. Wide swings mp→ff→mp (50-110-50). Follow emotional contour.",
        "longing": "DYNAMICS: Yearning crescendos. Start p (40), reach toward f (90-100), then fade back unfulfilled.",
        "hopeful": "DYNAMICS: Gradual brightening. Start mp (55), steady crescendo to f (95-105). Uplifting arc.",
        "energetic": "DYNAMICS: High and driving. Constant f-ff (90-110). Punchy accents on strong beats.",
        "playful": "DYNAMICS: Light and bouncy. mf (70-80) with playful accent variety. Never too heavy.",
        "action": "DYNAMICS: Driving intensity. f (90-100) throughout with sfz (110+) on action beats.",
        "aggressive": "DYNAMICS: Forceful attack. ff (100-115) with marcato accents (120+). Powerful and relentless.",
        "fierce": "DYNAMICS: Wild and untamed. ff-fff (110-127) with explosive sfz peaks. Maximum intensity.",
        "peaceful": "DYNAMICS: Calm and constant. pp-p (30-50). Barely any variation. Serene stillness.",
        "dreamy": "DYNAMICS: Floating softness. p-mp (35-60). Slow gentle waves like breathing.",
        "ethereal": "DYNAMICS: Distant and soft. ppp-pp (15-35). Barely there, celestial whispers.",
        "mysterious": "DYNAMICS: Unpredictable quiet. p (40-55) with occasional unexpected swells or drops.",
        "meditative": "DYNAMICS: Still and constant. pp (30-40). Minimal movement. Zen-like stability.",
        "ambient": "DYNAMICS: Atmospheric and static. Very slow, almost imperceptible changes. pp-mp (30-60).",
        "celtic": "DYNAMICS: Dance-like energy. mf (70-85) with accent patterns following the rhythm.",
        "middle eastern": "DYNAMICS: Ornamental expression. mp-mf (55-80) with melodic phrase swells.",
        "asian": "DYNAMICS: Refined and sparse. p-mf (40-75). Thoughtful pauses at phrase endings.",
        "latin": "DYNAMICS: Rhythmic warmth. mf-f (75-95). Accent syncopation with dynamic punches.",
        "nordic": "DYNAMICS: Vast and cold. mp-mf (55-80). Sparse, austere, wide open spaces.",
        "slavic": "DYNAMICS: Melancholic power. mp→f→mp (50-95-50). Emotional folk intensity.",
        "baroque": "DYNAMICS: Terraced contrasts. Sudden p→f jumps (45→90). No gradual transitions.",
        "classical": "DYNAMICS: Balanced phrasing. mp-mf (55-80). Gradual crescendo/decrescendo per phrase.",
        "impressionist": "DYNAMICS: Coloristic washes. p-mf (40-75). Blurred, overlapping dynamic shapes.",
        "minimalist": "DYNAMICS: Subtle evolution. Nearly constant mp (60-70). Hypnotic sameness with micro-shifts.",
        "victorious": "DYNAMICS: Triumphant forte. f-ff (95-115) with fanfare peaks (120+). Celebratory.",
        "tragic": "DYNAMICS: Heavy descent. Start mf (70), slow decrescendo to pp (25-35). Lamenting fade.",
        "whimsical": "DYNAMICS: Quirky variety. Random mf (70-85) with unexpected p (45) or f (100) surprises.",
        "serene": "DYNAMICS: Undisturbed calm. pp-p (30-50). Flat, peaceful, no disturbance.",
        "foreboding": "DYNAMICS: Creeping dread. Start ppp (15), inexorable slow crescendo. Never resolve.",
        "magical": "DYNAMICS: Sparkling accents. p (45) base with bright mf (80-90) sparkle moments.",
        "solemn": "DYNAMICS: Reverent steadiness. mp-mf (55-80). Dignified, no sudden changes.",
    }
    dynamics_hint = dynamics_hints.get(style_lower, "DYNAMICS: Match the musical style appropriately.")

    style_hint = f"{type_hint} {mood_hint}"
    if articulation_hint:
        style_hint = f"{style_hint} {articulation_hint}"

    if request.free_mode:
        system_parts = [
            FREE_MODE_SYSTEM_PROMPT,
            safe_format(profile_system, values),
        ]
    else:
        system_parts = [
            BASE_SYSTEM_PROMPT,
            safe_format(profile_system, values),
        ]
    system_prompt = "\n\n".join([p for p in system_parts if p])

    context_summary, detected_key, position = build_context_summary(request.context, request.music.time_sig, length_q)

    final_key = request.music.key
    if final_key == "unknown" and detected_key != "unknown":
        final_key = detected_key

    continuation_intent = detect_continuation_intent(request.user_prompt)

    quarters_per_bar = get_quarters_per_bar(request.music.time_sig)
    bars = max(1, int(length_q / quarters_per_bar))

    scale_notes = get_scale_note_names(final_key)
    valid_pitches = get_scale_notes(final_key, pitch_low, pitch_high)
    valid_pitches_str = ", ".join(str(p) for p in valid_pitches[:20])
    if len(valid_pitches) > 20:
        valid_pitches_str += f"... ({len(valid_pitches)} total)"

    continuation_instructions = ""
    if continuation_intent:
        intent_instructions = {
            "continue": """### CONTINUATION TASK
You must CONTINUE the existing musical material. Study the notes BEFORE the target area carefully.
- Maintain the same melodic direction and momentum
- Use similar rhythmic patterns
- Keep the same register and style
- Create a seamless connection from the preceding material""",
            
            "continue_progression": """### CHORD PROGRESSION CONTINUATION TASK
You must CONTINUE the chord progression. Analyze the existing harmony carefully.
- Follow the harmonic direction established before
- Use appropriate voice leading
- Maintain the same harmonic rhythm
- Create a natural extension of the progression""",
            
            "complete": """### COMPLETION TASK
You must COMPLETE/FINISH the musical phrase or section. The material should feel like a natural ending.
- Create a sense of resolution and finality
- Use cadential patterns (V-I, IV-I, etc.)
- Gradually reduce activity toward the end
- End on stable scale degrees (1, 3, 5)
- Consider using ritardando effect (longer notes toward the end)""",
            
            "complete_progression": """### CHORD PROGRESSION COMPLETION TASK
You must COMPLETE the chord progression with a satisfying cadence.
- Analyze the preceding chords to determine the key
- Use appropriate cadential formulas (V-I, IV-V-I, ii-V-I, etc.)
- Create harmonic resolution
- The final chord should provide closure""",
            
            "fill": """### FILL/BRIDGE TASK
You must FILL the gap between existing material BEFORE and AFTER the target area.
- Study both the preceding and following notes
- Create a smooth transition that connects both sections
- Match the starting point of what comes after
- Gradually transform from where the before section ends""",
            
            "fill_progression": """### HARMONIC FILL TASK
You must FILL the harmonic gap between existing chord progressions.
- Analyze chords before AND after the target area
- Create a smooth harmonic bridge
- Use passing chords and voice leading
- Ensure the connection sounds natural""",
        }
        continuation_instructions = intent_instructions.get(continuation_intent, "")
    elif position != "isolated":
        position_instructions = {
            "start": """### POSITION: START OF SECTION
This is the beginning. The generated material should:
- Establish the theme/motif clearly
- Create memorable opening phrase
- Set up the musical direction for what follows""",
            
            "middle": """### POSITION: MIDDLE OF SECTION  
This fills a gap between existing material. The generated material should:
- Connect naturally with preceding notes
- Prepare for the following notes
- Maintain continuity of style and register""",
            
            "end": """### POSITION: END OF SECTION
This is the ending. The generated material should:
- Bring the phrase to a natural conclusion
- Consider using cadential patterns
- Create a sense of completion""",
        }
        continuation_instructions = position_instructions.get(position, "")

    if request.free_mode:
        articulation_list_str = build_articulation_list_for_prompt(profile)
        user_prompt_parts = [
            f"## FREE MODE COMPOSITION for {profile.get('name', 'instrument')}",
            f"",
            f"YOU DECIDE: Choose the best generation type, style, and articulations for this context.",
            f"IMPORTANT: Match your output complexity to what the user requests. Simple request = simple output.",
            f"",
            f"### MUSICAL CONTEXT",
            f"- Key: {final_key}",
            f"- Scale notes: {scale_notes}",
            f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
            f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
            f"",
            f"### AVAILABLE ARTICULATIONS:",
            articulation_list_str,
            f"",
            f"Note: For LONG articulations, use CC1 curve for dynamics. For SHORT articulations, use velocity.",
        ]
    else:
        user_prompt_parts = [
            f"## COMPOSE: {generation_style.upper()} {generation_type.upper()} for {profile.get('name', 'instrument')}",
            f"",
            f"### MUSICAL CONTEXT",
            f"- Key: {final_key}",
            f"- Scale notes: {scale_notes}",
            f"- Tempo: {request.music.bpm} BPM, Time: {request.music.time_sig}",
            f"- Length: {bars} bars ({round(length_q, 1)} quarter notes)",
        ]

    if continuation_instructions:
        user_prompt_parts.append(f"")
        user_prompt_parts.append(continuation_instructions)

    if context_summary:
        user_prompt_parts.append(f"")
        user_prompt_parts.append(context_summary)

    if request.free_mode:
        user_prompt_parts.extend([
            f"",
            f"### COMPOSITION RULES",
            f"- ALLOWED PITCHES (use ONLY these): {valid_pitches_str}",
            f"- Pitch range: MIDI {pitch_low}-{pitch_high}",
            f"- Channel: {midi_channel}",
            f"- Generate appropriate number of notes for the part type",
            f"",
            f"### YOUR CREATIVE CHOICES",
            f"- Choose generation TYPE based on user request or context (Melody, Arpeggio, Chords, Pad, Bass, etc.)",
            f"- Choose STYLE that fits (Heroic, Romantic, Dark, Cinematic, etc.)",
            f"- Articulations: use ONE for simple parts (pads, chords), MULTIPLE only for expressive melodic parts",
            f"",
            f"### TWO-LAYER DYNAMICS",
            f"1. VELOCITY (vel): Individual note dynamics. Vary for accents and phrase shaping.",
            f"   - For SHORT articulations (staccato, pizzicato): velocity IS the main dynamics control",
            f"   - Accent notes: 100-127, normal: 70-90, soft: 40-60",
            f"2. CC1 CURVE (curves.dynamics): Overall phrase/expression envelope.",
            f"   - For LONG articulations (sustain, legato): CC1 shapes the dynamics over time",
            f"   - For simple pads: use flat or slow-swell curve",
            f"   - For melodic lines: create phrase-shaped arcs",
        ])
    else:
        short_articulations = profile.get("articulations", {}).get("short_articulations", [])
        is_short_art = articulation.lower() in [a.lower() for a in short_articulations]
        velocity_hint = "Use velocity for note-to-note dynamics (accents: 100-120, normal: 75-95, soft: 50-70)" if is_short_art else "Vary velocity for phrase shaping (phrase peaks: 90-100, between: 70-85)"
        
        user_prompt_parts.extend([
            f"",
            f"### COMPOSITION RULES",
            f"- Style: {style_hint}",
            f"- ALLOWED PITCHES (use ONLY these): {valid_pitches_str}",
            f"- Notes: {min_notes}-{max_notes}, evenly distributed across all {bars} bars",
            f"- Pitch range: MIDI {pitch_low}-{pitch_high}",
            f"- Channel: {midi_channel}",
            f"- Articulation: {articulation}",
            f"",
            f"### TWO-LAYER DYNAMICS",
            f"1. VELOCITY (vel): {velocity_hint}",
            f"2. CC1 CURVE: {dynamics_hint}",
        ])

    if request.user_prompt and request.user_prompt.strip():
        user_prompt_parts.append(f"")
        user_prompt_parts.append(f"### USER REQUEST (PRIORITY - follow these instructions, they override defaults):")
        user_prompt_parts.append(f"{request.user_prompt}")
        user_prompt_parts.append(f"")
        user_prompt_parts.append(f"INTERPRET USER REQUEST:")
        user_prompt_parts.append(f"- If user asks for 'simple', 'basic', 'straightforward' → create simple, clean output")
        user_prompt_parts.append(f"- If user mentions dynamics (crescendo, forte, soft, etc.) → apply to CC1 curve AND velocity")
        user_prompt_parts.append(f"- If user mentions a composer style (Zimmer, Williams, etc.) → match their typical approach")
        user_prompt_parts.append(f"- If user asks for chords/pads → use sustained notes, minimal articulation changes")

    user_prompt_parts.extend([
        f"",
        f"### OUTPUT (valid JSON only):",
    ])

    user_prompt = "\n".join(user_prompt_parts)
    return system_prompt, user_prompt


def build_chat_messages(system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


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
    if host in LOCAL_HOSTS:
        return True
    return host.startswith("127.")


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


def summarize_text(text: str, limit: int = LOG_PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


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


def resolve_preset(profile: Dict[str, Any], preset_name: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    presets = profile.get("ai", {}).get("presets", {})
    if not presets:
        return preset_name, {}
    if preset_name and preset_name in presets:
        return preset_name, presets[preset_name]
    first_name = next(iter(presets.keys()))
    return first_name, presets[first_name]


def get_keyswitch_pitch(data: Dict[str, Any], art_cfg: Dict[str, Any]) -> int:
    pitch = note_to_midi(data.get("pitch"))
    octave_offset = art_cfg.get("octave_offset", 0)
    return pitch + (octave_offset * 12)


def get_articulation_cc_value(data: Dict[str, Any]) -> Optional[int]:
    cc_value = data.get("cc_value")
    if cc_value is not None:
        return int(clamp(int(cc_value), MIDI_MIN, MIDI_MAX))
    return None


def apply_articulation(
    articulation: Optional[str],
    profile: Dict[str, Any],
    notes: List[Dict[str, Any]],
    default_chan: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    if not articulation:
        return notes, [], [], [], None
    art_cfg = profile.get("articulations", {})
    mode = art_cfg.get("mode", "none")
    art_map = art_cfg.get("map", {})
    data = art_map.get(articulation)
    if not data:
        return notes, [], [], [], articulation

    if mode == "keyswitch":
        try:
            pitch = get_keyswitch_pitch(data, art_cfg)
        except ValueError:
            return notes, [], [], [], articulation
        vel = int(clamp(int(data.get("vel", DEFAULT_KEYSWITCH_VELOCITY)), MIDI_VEL_MIN, MIDI_MAX))
        chan = normalize_channel(data.get("chan"), default_chan)
        return (
            notes,
            [{"time_q": 0.0, "pitch": pitch, "vel": vel, "chan": chan, "dur_q": KEYSWITCH_DUR_Q}],
            [],
            [],
            articulation,
        )
    if mode == "cc":
        cc_num = int(art_cfg.get("cc_number", 58))
        cc_value = get_articulation_cc_value(data)
        if cc_value is not None:
            chan = normalize_channel(data.get("chan"), default_chan)
            cc_event = {"time_q": 0.0, "cc": cc_num, "value": cc_value, "chan": chan}
            return notes, [], [], [cc_event], articulation
        return notes, [], [], [], articulation
    if mode == "program_change":
        program = int(clamp(int(data.get("program", 0)), MIDI_MIN, MIDI_MAX))
        chan = normalize_channel(data.get("chan"), default_chan)
        return notes, [], [{"time_q": 0.0, "program": program, "chan": chan}], [], articulation
    if mode == "channel":
        chan = normalize_channel(data.get("chan") or data.get("channel"), default_chan)
        for note in notes:
            note["chan"] = chan
        return notes, [], [], [], articulation
    return notes, [], [], [], articulation


def apply_per_note_articulations(
    notes: List[Dict[str, Any]],
    profile: Dict[str, Any],
    default_chan: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    art_cfg = profile.get("articulations", {})
    mode = art_cfg.get("mode", "none")
    art_map = art_cfg.get("map", {})
    
    if mode == "none" or not art_map:
        return notes, [], [], []
    
    notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    keyswitches: List[Dict[str, Any]] = []
    program_changes: List[Dict[str, Any]] = []
    articulation_cc: List[Dict[str, Any]] = []
    current_articulation: Optional[str] = None
    
    for note in notes:
        note_art = note.pop("articulation", None)
        if note_art and note_art != current_articulation:
            data = art_map.get(note_art)
            if data:
                if mode == "keyswitch":
                    try:
                        pitch = get_keyswitch_pitch(data, art_cfg)
                        vel = int(clamp(int(data.get("vel", DEFAULT_KEYSWITCH_VELOCITY)), MIDI_VEL_MIN, MIDI_MAX))
                        chan = normalize_channel(data.get("chan"), default_chan)
                        ks_time = max(0.0, note["start_q"] - 0.01)
                        keyswitches.append({
                            "time_q": ks_time,
                            "pitch": pitch,
                            "vel": vel,
                            "chan": chan,
                            "dur_q": KEYSWITCH_DUR_Q,
                        })
                    except ValueError:
                        pass
                elif mode == "cc":
                    cc_num = int(art_cfg.get("cc_number", 58))
                    cc_value = get_articulation_cc_value(data)
                    if cc_value is not None:
                        chan = normalize_channel(data.get("chan"), default_chan)
                        cc_time = max(0.0, note["start_q"] - 0.01)
                        articulation_cc.append({
                            "time_q": cc_time,
                            "cc": cc_num,
                            "value": cc_value,
                            "chan": chan,
                        })
                elif mode == "program_change":
                    program = int(clamp(int(data.get("program", 0)), MIDI_MIN, MIDI_MAX))
                    chan = normalize_channel(data.get("chan"), default_chan)
                    program_changes.append({
                        "time_q": note["start_q"],
                        "program": program,
                        "chan": chan,
                    })
                elif mode == "channel":
                    chan = normalize_channel(data.get("chan") or data.get("channel"), default_chan)
                    note["chan"] = chan
                current_articulation = note_art
    
    return notes, keyswitches, program_changes, articulation_cc


def build_response(
    raw: Dict[str, Any],
    profile: Dict[str, Any],
    length_q: float,
    free_mode: bool = False,
) -> Dict[str, Any]:
    midi_cfg = profile.get("midi", {})
    default_chan = int(midi_cfg.get("channel", 1))
    mono = str(midi_cfg.get("polyphony", "poly")).lower() == "mono"
    is_drum = bool(midi_cfg.get("is_drum", False))
    abs_range = parse_range(profile.get("range", {}).get("absolute"))
    fix_policy = profile.get("fix_policy", "octave_shift_to_fit")

    notes_raw = raw.get("notes", [])
    
    has_per_note_articulations = free_mode and any(
        isinstance(n, dict) and n.get("articulation") for n in notes_raw
    )
    
    notes = normalize_notes(notes_raw, length_q, default_chan, abs_range, fix_policy, mono)

    if is_drum:
        drums_raw = raw.get("drums", [])
        drum_map = midi_cfg.get("drum_map", {})
        notes.extend(normalize_drums(drums_raw, drum_map, length_q, default_chan))

    curves_raw = raw.get("curves", {})
    cc_events = build_cc_events(curves_raw, profile, length_q, default_chan)

    articulation_cc: List[Dict[str, Any]] = []
    
    if has_per_note_articulations:
        for i, note_raw in enumerate(notes_raw):
            if isinstance(note_raw, dict) and i < len(notes):
                art = note_raw.get("articulation")
                if art:
                    notes[i]["articulation"] = art
        notes, keyswitches, program_changes, articulation_cc = apply_per_note_articulations(
            notes, profile, default_chan
        )
        art_name = "mixed"
    else:
        articulation = raw.get("articulation")
        notes, keyswitches, program_changes, articulation_cc, art_name = apply_articulation(
            articulation, profile, notes, default_chan
        )

    all_cc_events = articulation_cc + cc_events

    return {
        "notes": notes,
        "cc_events": all_cc_events,
        "keyswitches": keyswitches,
        "program_changes": program_changes,
        "articulation": art_name,
        "generation_type": raw.get("generation_type"),
        "generation_style": raw.get("generation_style"),
    }


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

    logger.info("Generate: profile=%s preset=%s provider=%s model=%s type=%s style=%s free_mode=%s",
                profile.get("id"), preset_name, provider, model_name, request.generation_type, request.generation_style, request.free_mode)
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
