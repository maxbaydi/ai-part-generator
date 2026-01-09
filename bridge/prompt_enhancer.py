from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from logger_config import logger
except ImportError:
    from .logger_config import logger


ENHANCER_SYSTEM_PROMPT = """You are an expert music composition consultant. Your task is to transform a brief user request into a detailed, production-ready prompt for AI music generation.

=== YOUR ROLE ===
Transform simple requests like "make epic orchestral music" or "create a track in style of Hans Zimmer" into comprehensive musical blueprints with specific instructions for each instrument.

=== INPUT CONTEXT ===
You will receive:
1. User's brief request (1-2 sentences)
2. List of available instruments/tracks with their profiles
3. Selection length in bars
4. Musical context (key, tempo, time signature)
5. Optional: existing musical material for arrangement (melody, harmony, bass line)

=== OUTPUT FORMAT ===
Generate a detailed English prompt that includes:

1. **STYLE & MOOD**: Specific references, mood descriptors, sonic qualities
2. **STRUCTURE**: Bar-by-bar or section-by-section breakdown (Intro, Theme, Development, Climax, Resolution)
3. **INSTRUMENT ROLES**: For each available instrument, specify:
   - Its role (melody, harmony, bass, rhythm, pad, countermelody)
   - Playing style and articulation (legato, staccato, sustained, etc.)
   - Register (high/mid/low)
   - Dynamic behavior (crescendo, diminuendo, steady)
   - When to play and when to rest

4. **HARMONY & TONALITY**: 
   - Chord progression style or specific progressions
   - Modal/tonal characteristics
   - Harmonic rhythm

5. **DYNAMICS & EXPRESSION**:
   - Overall dynamic arc
   - Climax points
   - Textural density changes

=== STYLE GUIDELINES ===
- Write in clear, professional English
- Be specific and actionable
- Include concrete bar numbers for structural sections
- Reference the actual instruments provided
- If existing context (melody/harmony/bass) is provided, arrange around it
- If no context, create from scratch with clear musical direction

=== EXAMPLE TRANSFORMATION ===

INPUT: "Сделай трек в стиле Jeremy Soule's Far Horizons"
INSTRUMENTS: French Horn, Strings (Violins, Cellos), Piano, Flute, Tuba
LENGTH: 32 bars

OUTPUT:
In the style of Jeremy Soule ("Far Horizons"), create a serene, atmospheric fantasy track. Consisting of a 32-bar adagio structure that centers around a gentle, memorable, and lyrical French Horn melody. The French Horn acts as the lead "vocalist" of the track, playing a soft, velvety, and highly melodic motif (cantabile style) in the middle register, avoiding any brassy or aggressive attacks. The Full String Ensemble creates a shimmering, ethereal backdrop using con sordino (muted) sustain patches; High Violins hold static "misty" chords, while Cellos provide a warm, slow-moving legato counterpoint to the Horn. The Piano adds magical texture, playing very sparse, high-pitched "glistening" notes and occasional delicate grace notes that mimic sunlight on snow, strictly avoiding heavy chords. The Flute enters later to double the Horn melody an octave higher with a breathy, airy tone, adding a fragile "human" element. The Tuba provides a nearly subliminal foundation, playing extremely soft, long pedal tones (root notes) to add warmth and depth to the low end without being rhythmic.

Structure:
[Bars 1-8] Intro: The atmosphere is established by High Strings (tremolo) and sparse, high Piano droplets. The mood is expectant and frozen.
[Bars 9-16] Theme Entry: The French Horn enters with the main memorable motif—a slow, noble, and nostalgic melody played piano to mezzo-piano. It stands out clearly above the quiet strings.
[Bars 17-24] Full Swell: The texture thickens. The Tuba enters to ground the harmony. The Flute joins to harmonize the Horn. The Strings swell in volume (crescendo), creating a warm, enveloping "embrace" of sound.
[Bars 25-32] Resolution: The music gently recedes. The Horn plays a final, lower variation of the motif and fades out. The track ends with a lingering String chord and one final, decaying Piano note.

=== RULES ===
- Always output the enhanced prompt in English
- Adapt structure to the actual selection length
- If fewer instruments, adjust complexity accordingly
- Consider instrument capabilities and ranges
- Make the prompt specific enough to guide generation but flexible for AI creativity"""


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
