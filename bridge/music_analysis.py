from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

try:
    from music_theory import analyze_chord, NOTE_NAMES, pitch_to_note
except ImportError:
    from .music_theory import analyze_chord, NOTE_NAMES, pitch_to_note


def analyze_melodic_context(notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not notes:
        return {}

    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    pitches = [n.get("pitch", 60) for n in sorted_notes]

    if len(pitches) < 2:
        return {
            "range": {"low": pitches[0], "high": pitches[0]},
            "contour": "static",
            "intervals": [],
            "rhythm_type": "sparse",
            "density": "minimal",
        }

    intervals = [pitches[i + 1] - pitches[i] for i in range(len(pitches) - 1)]

    ascending = sum(1 for i in intervals if i > 0)
    descending = sum(1 for i in intervals if i < 0)
    static = sum(1 for i in intervals if i == 0)

    if ascending > descending * 1.5:
        contour = "ascending"
    elif descending > ascending * 1.5:
        contour = "descending"
    elif static > (ascending + descending):
        contour = "static"
    else:
        contour = "wave"

    start_times = [n.get("start_q", 0) for n in sorted_notes]
    beat_positions = [t % 1 for t in start_times]
    on_beat = sum(1 for b in beat_positions if b < 0.1 or b > 0.9)
    syncopated = len(beat_positions) - on_beat

    if syncopated > on_beat:
        rhythm_type = "syncopated"
    elif on_beat > syncopated * 2:
        rhythm_type = "on-beat"
    else:
        rhythm_type = "mixed"

    durations = [n.get("dur_q", 1.0) for n in sorted_notes]
    avg_duration = sum(durations) / len(durations)

    if avg_duration > 2.0:
        density = "sparse"
    elif avg_duration > 1.0:
        density = "moderate"
    elif avg_duration > 0.5:
        density = "active"
    else:
        density = "dense"

    gaps = []
    for i in range(len(sorted_notes) - 1):
        note_end = sorted_notes[i].get("start_q", 0) + sorted_notes[i].get("dur_q", 0)
        next_start = sorted_notes[i + 1].get("start_q", 0)
        gap = next_start - note_end
        gaps.append(gap)

    phrase_breaks = [i + 1 for i, g in enumerate(gaps) if g > 0.75]

    interval_counts = Counter(abs(i) for i in intervals)
    common_intervals = interval_counts.most_common(3)
    interval_names = []
    interval_map = {
        0: "unison",
        1: "m2",
        2: "M2",
        3: "m3",
        4: "M3",
        5: "P4",
        6: "tritone",
        7: "P5",
        8: "m6",
        9: "M6",
        10: "m7",
        11: "M7",
        12: "octave",
    }
    for interval, count in common_intervals:
        name = interval_map.get(interval % 12, f"{interval}st")
        interval_names.append({"interval": name, "semitones": interval, "count": count})

    stepwise = sum(1 for i in intervals if abs(i) <= 2)
    leaps = sum(1 for i in intervals if abs(i) > 4)

    if stepwise > leaps * 2:
        motion_type = "stepwise"
    elif leaps > stepwise:
        motion_type = "disjunct"
    else:
        motion_type = "mixed"

    return {
        "range": {"low": min(pitches), "high": max(pitches), "span": max(pitches) - min(pitches)},
        "contour": contour,
        "motion_type": motion_type,
        "intervals": interval_names,
        "rhythm_type": rhythm_type,
        "density": density,
        "avg_duration": round(avg_duration, 2),
        "phrase_breaks": phrase_breaks,
        "note_count": len(pitches),
    }


def analyze_rhythmic_pattern(notes: List[Dict[str, Any]], time_sig: str = "4/4") -> Dict[str, Any]:
    if not notes:
        return {}

    try:
        parts = time_sig.split("/")
        beats_per_bar = int(parts[0])
        beat_unit = int(parts[1])
    except (ValueError, IndexError):
        beats_per_bar = 4
        beat_unit = 4

    quarters_per_bar = beats_per_bar * (4.0 / beat_unit)

    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    start_times = [n.get("start_q", 0) for n in sorted_notes]

    beat_histogram: Dict[float, int] = {}
    for t in start_times:
        beat_in_bar = round((t % quarters_per_bar) * 4) / 4
        beat_histogram[beat_in_bar] = beat_histogram.get(beat_in_bar, 0) + 1

    strong_beats = [0, quarters_per_bar / 2] if quarters_per_bar >= 2 else [0]
    strong_beat_hits = sum(beat_histogram.get(b, 0) for b in strong_beats)
    total_hits = sum(beat_histogram.values())

    if total_hits > 0:
        strong_ratio = strong_beat_hits / total_hits
    else:
        strong_ratio = 0

    if strong_ratio > 0.6:
        groove_type = "downbeat-heavy"
    elif strong_ratio < 0.3:
        groove_type = "offbeat-heavy"
    else:
        groove_type = "balanced"

    sorted_beats = sorted(beat_histogram.items(), key=lambda x: x[1], reverse=True)
    anchor_beats = [b for b, _ in sorted_beats[:4]]

    durations = [n.get("dur_q", 1.0) for n in sorted_notes]
    duration_counts = Counter(round(d * 4) / 4 for d in durations)
    common_durations = duration_counts.most_common(3)

    duration_names = []
    dur_map = {
        0.25: "16th",
        0.5: "8th",
        0.75: "dotted 8th",
        1.0: "quarter",
        1.5: "dotted quarter",
        2.0: "half",
        3.0: "dotted half",
        4.0: "whole",
    }
    for dur, count in common_durations:
        name = dur_map.get(dur, f"{dur}q")
        duration_names.append({"duration": name, "quarters": dur, "count": count})

    patterns = []
    if len(sorted_notes) >= 4:
        for bar_start in range(0, int(max(start_times) // quarters_per_bar) + 1):
            bar_notes = [n for n in sorted_notes
                         if bar_start * quarters_per_bar <= n.get("start_q", 0) < (bar_start + 1) * quarters_per_bar]
            if bar_notes:
                bar_pattern = tuple(round((n.get("start_q", 0) % quarters_per_bar) * 4) / 4 for n in bar_notes)
                patterns.append(bar_pattern)

    pattern_counts = Counter(patterns)
    repeating_patterns = [p for p, c in pattern_counts.items() if c > 1]

    return {
        "time_sig": time_sig,
        "groove_type": groove_type,
        "anchor_beats": anchor_beats,
        "common_durations": duration_names,
        "has_repeating_pattern": len(repeating_patterns) > 0,
        "strong_beat_ratio": round(strong_ratio, 2),
    }


def analyze_harmony_from_notes(
    notes: List[Dict[str, Any]],
    time_sig: str = "4/4",
    length_q: float = 16.0,
) -> Dict[str, Any]:
    if not notes:
        return {}

    try:
        parts = time_sig.split("/")
        beats_per_bar = int(parts[0])
        beat_unit = int(parts[1])
    except (ValueError, IndexError):
        beats_per_bar = 4
        beat_unit = 4

    quarters_per_bar = beats_per_bar * (4.0 / beat_unit)
    chord_unit = quarters_per_bar

    segments: Dict[int, List[int]] = {}
    for note in notes:
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

    chord_changes = []
    for seg_idx in sorted(segments.keys()):
        pitches = segments[seg_idx]
        bar_num = seg_idx + 1
        time_q = seg_idx * chord_unit

        chord_name, root_pc = analyze_chord(pitches)
        if root_pc is None:
            continue
        pitch_classes = sorted(set(p % 12 for p in pitches))
        chord_changes.append(
            {
                "bar": bar_num,
                "time_q": time_q,
                "chord": chord_name,
                "root": NOTE_NAMES[root_pc],
                "pitch_classes": pitch_classes,
            }
        )

    harmonic_rhythm = "slow" if len(chord_changes) <= length_q / 4 else "fast"

    return {
        "chord_changes": chord_changes,
        "harmonic_rhythm": harmonic_rhythm,
        "chords_per_bar": len(chord_changes) / max(1, length_q / quarters_per_bar),
    }


def build_melodic_context_prompt(analysis: Dict[str, Any], instrument_name: str = "") -> str:
    if not analysis:
        return ""

    lines = ["### MELODIC ANALYSIS OF PREVIOUS PARTS"]

    range_info = analysis.get("range", {})
    if range_info:
        low = range_info.get("low", 60)
        high = range_info.get("high", 72)
        span = range_info.get("span", 12)
        lines.append(f"- Range: {pitch_to_note(low)} to {pitch_to_note(high)} (MIDI {low}-{high}, span {span} semitones)")

    contour = analysis.get("contour", "")
    motion = analysis.get("motion_type", "")
    if contour or motion:
        lines.append(f"- Melodic character: {contour} contour, {motion} motion")

    intervals = analysis.get("intervals", [])
    if intervals:
        interval_str = ", ".join(f"{i['interval']} ({i['count']}x)" for i in intervals[:3])
        lines.append(f"- Common intervals: {interval_str}")

    rhythm = analysis.get("rhythm_type", "")
    density = analysis.get("density", "")
    if rhythm or density:
        lines.append(f"- Rhythm: {rhythm}, density: {density}")

    phrase_breaks = analysis.get("phrase_breaks", [])
    if phrase_breaks:
        lines.append(f"- Phrase breaks at note indices: {phrase_breaks}")

    lines.append("")
    lines.append("COMPLEMENTING OPTIONS:")
    lines.append("1. SIMILAR: Match the contour and density for unity")
    lines.append("2. CONTRAST: Use opposite contour/density for variety")
    lines.append("3. COUNTERPOINT: Move when existing parts hold, hold when they move")
    lines.append("4. IMITATION: Echo melodic fragments at different pitch/time")

    if range_info:
        suggested_low = range_info.get("high", 72)
        suggested_high = min(suggested_low + 12, 96)
        lines.append(f"5. REGISTER: Consider MIDI {suggested_low}-{suggested_high} to avoid masking")

    return "\n".join(lines)


def build_rhythmic_context_prompt(analysis: Dict[str, Any]) -> str:
    if not analysis:
        return ""

    lines = ["### RHYTHMIC COORDINATION"]

    groove = analysis.get("groove_type", "")
    if groove:
        lines.append(f"- Ensemble groove: {groove}")

    anchor_beats = analysis.get("anchor_beats", [])
    if anchor_beats:
        beats_str = ", ".join(str(b) for b in anchor_beats[:4])
        lines.append(f"- Anchor beats (strong pulse points): {beats_str}")
        lines.append("  ALIGN your accents to these beats for cohesion")

    durations = analysis.get("common_durations", [])
    if durations:
        dur_str = ", ".join(f"{d['duration']}" for d in durations[:3])
        lines.append(f"- Common note values: {dur_str}")

    strong_ratio = analysis.get("strong_beat_ratio", 0.5)
    if strong_ratio > 0.6:
        lines.append("- Style: Strong downbeat emphasis - add syncopation carefully")
    elif strong_ratio < 0.3:
        lines.append("- Style: Offbeat/syncopated - can add downbeat anchors")
    else:
        lines.append("- Style: Balanced rhythm - maintain the pulse")

    has_pattern = analysis.get("has_repeating_pattern", False)
    if has_pattern:
        lines.append("- Repeating pattern detected - consider complementary ostinato")

    return "\n".join(lines)


def build_harmony_context_prompt(analysis: Dict[str, Any]) -> str:
    if not analysis:
        return ""

    lines = ["### HARMONIC CONTEXT TO FOLLOW"]

    chord_changes = analysis.get("chord_changes", [])
    if chord_changes:
        lines.append("Chord progression (play chord tones on these changes):")
        for change in chord_changes[:16]:
            bar = change.get("bar", 1)
            chord = change.get("chord", "?")
            time_q = change.get("time_q", 0)
            lines.append(f"  Bar {bar} (time_q {time_q}): {chord}")

    harmonic_rhythm = analysis.get("harmonic_rhythm", "")
    if harmonic_rhythm:
        lines.append(f"- Harmonic rhythm: {harmonic_rhythm}")

    lines.append("")
    lines.append("HARMONY RULES:")
    lines.append("- On STRONG beats (1, 3): Prioritize root, 3rd, 5th")
    lines.append("- On WEAK beats: Passing tones and extensions allowed")
    lines.append("- Change your harmony TOGETHER with these chord changes")
    lines.append("- Avoid clashing with the root on downbeats")

    return "\n".join(lines)


def analyze_previously_generated(
    previously_generated: List[Dict[str, Any]],
    time_sig: str = "4/4",
    length_q: float = 16.0,
) -> Dict[str, Any]:
    if not previously_generated:
        return {}

    all_notes = []
    parts_analysis = []

    for part in previously_generated:
        notes = part.get("notes", [])
        if not notes:
            continue

        all_notes.extend(notes)

        part_name = part.get("profile_name") or part.get("track_name") or "Unknown"
        role = part.get("role", "unknown")

        melodic = analyze_melodic_context(notes)
        rhythmic = analyze_rhythmic_pattern(notes, time_sig)

        parts_analysis.append({
            "name": part_name,
            "role": role,
            "melodic": melodic,
            "rhythmic": rhythmic,
        })

    combined_melodic = analyze_melodic_context(all_notes)
    combined_rhythmic = analyze_rhythmic_pattern(all_notes, time_sig)
    harmony = analyze_harmony_from_notes(all_notes, time_sig, length_q)

    all_pitches = [n.get("pitch", 60) for n in all_notes]
    occupied_registers = []
    if all_pitches:
        min_p, max_p = min(all_pitches), max(all_pitches)
        if min_p < 48:
            occupied_registers.append("bass")
        if 48 <= min_p < 60 or 48 <= max_p < 60:
            occupied_registers.append("low-mid")
        if 60 <= min_p < 72 or 60 <= max_p < 72:
            occupied_registers.append("mid")
        if 72 <= min_p < 84 or 72 <= max_p < 84:
            occupied_registers.append("high-mid")
        if max_p >= 84:
            occupied_registers.append("high")

    available_registers = []
    if "high" not in occupied_registers:
        available_registers.append("high (MIDI 84+)")
    if "high-mid" not in occupied_registers:
        available_registers.append("high-mid (MIDI 72-84)")
    if "low-mid" not in occupied_registers:
        available_registers.append("low-mid (MIDI 48-60)")
    if "bass" not in occupied_registers:
        available_registers.append("bass (MIDI <48)")

    return {
        "parts_analysis": parts_analysis,
        "combined": {
            "melodic": combined_melodic,
            "rhythmic": combined_rhythmic,
            "harmony": harmony,
        },
        "occupied_registers": occupied_registers,
        "available_registers": available_registers,
        "total_parts": len(parts_analysis),
    }


def build_full_context_prompt(
    previously_generated: List[Dict[str, Any]],
    time_sig: str = "4/4",
    length_q: float = 16.0,
    current_role: str = "",
    skip_auto_harmony: bool = False,
) -> str:
    analysis = analyze_previously_generated(previously_generated, time_sig, length_q)
    if not analysis:
        return ""

    lines = ["### ANALYSIS OF PREVIOUSLY GENERATED PARTS"]
    lines.append(f"Parts already composed: {analysis.get('total_parts', 0)}")
    lines.append("")

    parts = analysis.get("parts_analysis", [])
    for part in parts[:5]:
        name = part.get("name", "Unknown")
        role = part.get("role", "unknown")
        melodic = part.get("melodic", {})
        lines.append(f"**{name}** (role: {role}):")

        range_info = melodic.get("range", {})
        if range_info:
            lines.append(f"  - Range: MIDI {range_info.get('low', 60)}-{range_info.get('high', 72)}")
        lines.append(f"  - Contour: {melodic.get('contour', 'unknown')}, Motion: {melodic.get('motion_type', 'unknown')}")
        lines.append(f"  - Rhythm: {melodic.get('rhythm_type', 'unknown')}, Density: {melodic.get('density', 'unknown')}")

    lines.append("")

    combined = analysis.get("combined", {})
    if not skip_auto_harmony:
        harmony = combined.get("harmony", {})
        harmony_prompt = build_harmony_context_prompt(harmony)
        if harmony_prompt:
            lines.append(harmony_prompt)
            lines.append("")

    rhythmic = combined.get("rhythmic", {})
    rhythmic_prompt = build_rhythmic_context_prompt(rhythmic)
    if rhythmic_prompt:
        lines.append(rhythmic_prompt)
        lines.append("")

    available = analysis.get("available_registers", [])
    occupied = analysis.get("occupied_registers", [])
    if available or occupied:
        lines.append("### REGISTER ALLOCATION")
        if occupied:
            lines.append(f"- OCCUPIED: {', '.join(occupied)}")
        if available:
            lines.append(f"- AVAILABLE (prefer these): {', '.join(available)}")
        lines.append("")

    lines.append("### YOUR TASK")
    if current_role:
        lines.append(f"Your role: {current_role.upper()}")

    lines.append("1. DO NOT duplicate existing melodies/rhythms")
    lines.append("2. USE a different register from existing parts")
    lines.append("3. FOLLOW the harmonic changes above")
    lines.append("4. ALIGN with the rhythmic pulse")
    lines.append("5. CREATE complementary material that ENHANCES the whole")

    return "\n".join(lines)


def extract_motif_from_notes(
    notes: List[Dict[str, Any]],
    max_notes: int = 8,
    source_instrument: str = "",
) -> Optional[Dict[str, Any]]:
    if not notes or len(notes) < 3:
        return None

    sorted_notes = sorted(notes, key=lambda n: n.get("start_q", 0))
    motif_notes = sorted_notes[:max_notes]

    pitches = [n.get("pitch", 60) for n in motif_notes]
    intervals = [pitches[i + 1] - pitches[i] for i in range(len(pitches) - 1)]

    rhythm_pattern = [n.get("dur_q", 1.0) for n in motif_notes]

    start_pitch = pitches[0] if pitches else 60

    ascending = sum(1 for i in intervals if i > 0)
    descending = sum(1 for i in intervals if i < 0)

    if ascending > descending * 1.5:
        character = "ascending"
    elif descending > ascending * 1.5:
        character = "descending"
    elif max(intervals, default=0) - min(intervals, default=0) > 7:
        character = "dramatic"
    else:
        character = "lyrical"

    formatted_notes = []
    for note in motif_notes:
        formatted_notes.append({
            "start_q": round(note.get("start_q", 0) - motif_notes[0].get("start_q", 0), 3),
            "dur_q": round(note.get("dur_q", 1.0), 3),
            "pitch": note.get("pitch", 60),
        })

    return {
        "source_instrument": source_instrument,
        "notes": formatted_notes,
        "intervals": intervals,
        "rhythm_pattern": rhythm_pattern,
        "start_pitch": start_pitch,
        "character": character,
    }


def analyze_horizontal_continuity(
    before_notes: List[Dict[str, Any]],
    after_notes: List[Dict[str, Any]],
    key_str: str = "C major",
) -> Dict[str, Any]:
    result = {
        "needs_continuation": False,
        "melodic_direction": "neutral",
        "last_pitch": None,
        "last_interval": 0,
        "suggested_start_direction": "any",
        "phrase_incomplete": False,
        "resolution_needed": False,
        "suggested_resolution_pitch": None,
    }

    if not before_notes:
        return result

    sorted_before = sorted(before_notes, key=lambda n: n.get("start_q", 0))
    last_notes = sorted_before[-min(6, len(sorted_before)):]

    if last_notes:
        result["last_pitch"] = last_notes[-1].get("pitch", 60)

    if len(last_notes) >= 2:
        pitches = [n.get("pitch", 60) for n in last_notes]
        intervals = [pitches[i + 1] - pitches[i] for i in range(len(pitches) - 1)]

        ascending = sum(1 for i in intervals if i > 0)
        descending = sum(1 for i in intervals if i < 0)

        if ascending > descending:
            result["melodic_direction"] = "ascending"
            result["suggested_start_direction"] = "continue_up_or_resolve_down"
        elif descending > ascending:
            result["melodic_direction"] = "descending"
            result["suggested_start_direction"] = "continue_down_or_resolve_up"
        else:
            result["melodic_direction"] = "static"

        result["last_interval"] = intervals[-1] if intervals else 0

        if abs(intervals[-1]) > 4:
            result["suggested_start_direction"] = "stepwise_opposite"
            result["needs_continuation"] = True

    if result["last_pitch"]:
        last_pc = result["last_pitch"] % 12

        try:
            from music_theory import parse_key, SCALE_INTERVALS
        except ImportError:
            from .music_theory import parse_key, SCALE_INTERVALS

        root_pc, scale_type = parse_key(key_str)
        scale_intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])
        scale_pcs = set((root_pc + i) % 12 for i in scale_intervals)

        relative_pc = (last_pc - root_pc) % 12

        unstable_degrees = {1, 3, 6, 10, 11}
        if relative_pc in unstable_degrees:
            result["phrase_incomplete"] = True
            result["resolution_needed"] = True
            result["needs_continuation"] = True

            if relative_pc == 11:
                result["suggested_resolution_pitch"] = result["last_pitch"] + 1
            elif relative_pc == 10:
                result["suggested_resolution_pitch"] = result["last_pitch"] - 3
            elif relative_pc in {1, 6}:
                result["suggested_resolution_pitch"] = result["last_pitch"] - 1
            elif relative_pc == 3:
                result["suggested_resolution_pitch"] = result["last_pitch"] + 1

    last_note = last_notes[-1] if last_notes else None
    if last_note:
        last_dur = last_note.get("dur_q", 1.0)
        if last_dur < 0.5:
            result["phrase_incomplete"] = True
            result["needs_continuation"] = True

    return result


def build_horizontal_continuity_prompt(analysis: Dict[str, Any]) -> str:
    if not analysis:
        return ""

    lines = ["### HORIZONTAL CONTINUITY (connect with surrounding material)"]

    direction = analysis.get("melodic_direction", "neutral")
    if direction != "neutral":
        lines.append(f"- Previous phrase direction: {direction}")

    suggestion = analysis.get("suggested_start_direction", "any")
    if suggestion != "any":
        lines.append(f"- Suggested start: {suggestion.replace('_', ' ')}")

    last_pitch = analysis.get("last_pitch")
    if last_pitch:
        try:
            from music_theory import pitch_to_note
        except ImportError:
            from .music_theory import pitch_to_note
        lines.append(f"- Last note before selection: {pitch_to_note(last_pitch)} (MIDI {last_pitch})")

    if analysis.get("resolution_needed"):
        resolution = analysis.get("suggested_resolution_pitch")
        if resolution:
            try:
                from music_theory import pitch_to_note
            except ImportError:
                from .music_theory import pitch_to_note
            lines.append(f"- RESOLUTION NEEDED: Consider starting with {pitch_to_note(resolution)} (MIDI {resolution})")

    if analysis.get("phrase_incomplete"):
        lines.append("- Previous phrase feels INCOMPLETE - consider continuing or resolving it")
    else:
        lines.append("- Previous phrase ended naturally - OK to start fresh")

    last_interval = analysis.get("last_interval", 0)
    if abs(last_interval) > 4:
        opposite = "down" if last_interval > 0 else "up"
        lines.append(f"- Large leap ({last_interval:+d}) detected - move stepwise {opposite} to balance")

    return "\n".join(lines)
