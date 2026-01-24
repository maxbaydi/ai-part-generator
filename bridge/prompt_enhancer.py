from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from logger_config import logger
    from text_utils import fix_mojibake
except ImportError:
    from .logger_config import logger
    from .text_utils import fix_mojibake


ENHANCER_SYSTEM_PROMPT = """You are an expert music composition consultant. Transform brief user requests into HIGH-LEVEL creative direction for AI music generation.

=== CRITICAL: LANGUAGE REQUIREMENT ===
ALWAYS respond in ENGLISH regardless of input language.
User may write in Russian, German, Chinese, or any other language — your output MUST be in English.
This is mandatory because the music generation system only processes English prompts.

=== CRITICAL: YOUR ROLE ===
Generate ARTISTIC VISION and CHARACTER guidance, NOT bar-by-bar structure.
The composition PLAN will handle specific structure (chord progressions, bar numbers, instrument entries).
Your job is to define the SOUL of the music: style, mood, emotional arc, sonic qualities.

=== INPUT CONTEXT ===
You will receive:
1. User's brief request
2. List of available instruments/tracks
3. Selection length in bars
4. Musical context (key, tempo, time signature)
5. Optional: existing musical material

=== OUTPUT FORMAT ===
Generate a focused creative brief with these sections:

**STYLE & CHARACTER**
- Genre/style references (composers, soundtracks, genres)
- Core mood and emotional qualities (2-3 key adjectives)
- Sonic character (warm, bright, dark, ethereal, powerful, etc.)

**NARRATIVE ARC**
- Emotional journey in 3-4 phases (NOT bar numbers, just progression)
- Example: "Begin with mystery → build anticipation → reach triumph → resolve nobly"
- Climax placement (early/middle/late)
- Energy flow (building/sustaining/releasing)

**HARMONIC CHARACTER**
- Harmonic language style (not specific chords, the PLAN will create those)
- Modal/tonal feel (major heroic, minor brooding, modal mystical, etc.)
- Cadence style (strong resolutions, open endings, deceptive, etc.)

**DYNAMIC PALETTE**
- Overall dynamic range (pp-ff, or narrower)
- Dynamic arc shape (crescendo throughout, peak-and-resolve, waves, etc.)
- Textural density progression (sparse→full, or layered entries, etc.)

**ORCHESTRATION GUIDANCE**
- Family characters (how strings should feel, how brass should sound, etc.)
- Textural approach (homophonic, polyphonic, melody+accompaniment, etc.)
- Color notes (any special effects, articulations, or textures to emphasize)

**PERFORMANCE FEEL**
- Tempo feel (strict/rubato, driving/relaxed)
- Articulation tendency (legato-dominant, marcato accents, mixed)
- Human elements (breaths, swells, slight timing variations)

=== WHAT NOT TO INCLUDE ===
DO NOT specify:
- Bar numbers or specific timing (e.g., "bars 1-8", "at bar 12")
- Which instrument plays when (the PLAN decides this)
- Specific chord progressions (the PLAN creates chord_map)
- Exact dynamic markings at specific points
- Detailed instrument entries/exits

=== EXAMPLE TRANSFORMATION ===

INPUT: "Сделай трек в стиле Jeremy Soule's Far Horizons"
INSTRUMENTS: French Horn, Strings, Piano, Flute, Tuba

OUTPUT:
**STYLE & CHARACTER**
- Style: Atmospheric fantasy orchestral in the tradition of Jeremy Soule (Elder Scrolls), evoking vast frozen landscapes and distant horizons
- Mood: Serene, nostalgic, gently hopeful with underlying melancholy
- Sonic character: Warm yet distant, shimmering, spacious with reverb depth

**NARRATIVE ARC**
- Begin in stillness and mystery (frozen landscape awakening)
- Gradually introduce warmth and humanity (the traveler appears)
- Swell to an emotional embrace (beauty revealed)
- Recede into peaceful resolution (acceptance, continuation)
- Climax: Late-middle section, gentle rather than explosive

**HARMONIC CHARACTER**
- Predominantly major with modal inflections (Lydian brightness, Dorian nostalgia)
- Slow harmonic rhythm—let chords breathe
- Prefer plagal and modal cadences over strong V-I
- Open voicings with perfect 5ths for spaciousness

**DYNAMIC PALETTE**
- Range: pp to mf (no fortissimo—this is intimate, not bombastic)
- Arc: Gradual swell from whisper to warm embrace, then gentle fade
- Texture: Start extremely sparse, layer gradually, never become dense

**ORCHESTRATION GUIDANCE**
- Strings: Ethereal, con sordino feel, shimmering sustained chords, NO aggressive attacks
- French Horn: The "voice"—noble, cantabile, velvety tone in middle register
- Piano: Magical sparkles—sparse high notes like sunlight on snow, NO heavy chords
- Flute: Breathy, fragile doubling of melody, human vulnerability
- Tuba: Nearly subliminal—soft pedal tones for warmth, NOT rhythmic

**PERFORMANCE FEEL**
- Tempo: Flowing adagio, slight rubato allowed
- Articulation: Predominantly legato, seamless phrases
- Human elements: Long breaths between phrases, gentle dynamic swells within sustained notes

=== RULES ===
- Output in English
- Focus on CHARACTER and FEEL, not structure
- Let the composition PLAN handle timing and coordination
- Adapt complexity to available instruments
- If existing context provided, describe how new material should relate to it emotionally"""


def format_instrument_info(instruments: List[Dict[str, Any]]) -> str:
    if not instruments:
        return "No specific instruments provided."

    lines = []
    for inst in instruments:
        name = inst.get("track_name") or inst.get("name") or "Unknown"
        profile = inst.get("profile_name") or inst.get("profile") or ""
        family = inst.get("family") or ""
        role = inst.get("role") or ""

        parts = [name]
        if profile and profile != name:
            parts.append(f"({profile})")
        if family:
            parts.append(f"[{family}]")
        if role:
            parts.append(f"- suggested role: {role}")

        lines.append(" ".join(parts))

    return "\n".join(lines)


def format_music_context(
    key: str,
    bpm: float,
    time_sig: str,
    length_bars: Optional[int],
    length_q: Optional[float],
) -> str:
    parts = []

    if key and key.lower() not in ("unknown", "auto", ""):
        parts.append(f"Key: {key}")
    if bpm:
        parts.append(f"Tempo: {bpm} BPM")
    if time_sig:
        parts.append(f"Time Signature: {time_sig}")
    if length_bars:
        parts.append(f"Length: {length_bars} bars")
    elif length_q:
        parts.append(f"Length: {length_q:.1f} quarter notes")

    return "\n".join(parts) if parts else "No specific musical context provided."


def format_existing_context(context: Optional[Dict[str, Any]]) -> str:
    if not context:
        return ""

    parts = []

    context_notes = context.get("context_notes")
    if context_notes:
        parts.append(f"Existing musical material:\n{context_notes}")

    horizontal = context.get("horizontal")
    if horizontal:
        before = horizontal.get("before", [])
        after = horizontal.get("after", [])
        position = horizontal.get("position", "isolated")
        if before or after:
            parts.append(f"Position in timeline: {position}")
            if before:
                parts.append(f"Material before: {len(before)} notes")
            if after:
                parts.append(f"Material after: {len(after)} notes")

    extended_progression = context.get("extended_progression")
    if extended_progression:
        parts.append(f"Chord progression context: {len(extended_progression)} chords detected")

    return "\n".join(parts) if parts else ""


def build_enhancer_prompt(
    user_prompt: str,
    instruments: List[Dict[str, Any]],
    key: str,
    bpm: float,
    time_sig: str,
    length_bars: Optional[int],
    length_q: Optional[float],
    context: Optional[Dict[str, Any]] = None,
) -> str:
    sections = []

    user_prompt = fix_mojibake(user_prompt)
    sections.append(f"USER REQUEST:\n{user_prompt}")

    inst_info = format_instrument_info(instruments)
    sections.append(f"AVAILABLE INSTRUMENTS:\n{inst_info}")

    music_ctx = format_music_context(key, bpm, time_sig, length_bars, length_q)
    sections.append(f"MUSICAL CONTEXT:\n{music_ctx}")

    existing_ctx = format_existing_context(context)
    if existing_ctx:
        sections.append(f"EXISTING MATERIAL (arrange around this):\n{existing_ctx}")
    else:
        sections.append("MODE: Create composition from scratch (no existing material to arrange).")

    sections.append("Please transform the user's brief request into a detailed, production-ready prompt for music generation. Include specific instructions for each instrument, structural breakdown with bar numbers, and dynamics/expression guidance.")

    return "\n\n".join(sections)


def extract_enhanced_prompt(llm_response: str) -> str:
    content = llm_response.strip()

    if content.startswith("```"):
        lines = content.split("\n")
        start_idx = 1
        end_idx = len(lines) - 1
        for i, line in enumerate(lines):
            if i > 0 and line.strip() == "```":
                end_idx = i
                break
        content = "\n".join(lines[start_idx:end_idx]).strip()

    for prefix in ["Enhanced Prompt:", "ENHANCED PROMPT:", "Output:", "OUTPUT:", "Result:", "RESULT:"]:
        if content.lower().startswith(prefix.lower()):
            content = content[len(prefix):].strip()
            break

    return content
