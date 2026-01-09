from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

try:
    from music_theory import NOTE_NAMES, pitch_to_note
except ImportError:
    from .music_theory import NOTE_NAMES, pitch_to_note


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

        pitch_classes = sorted(set(p % 12 for p in pitches))
        if pitch_classes:
            root_pc = pitch_classes[0]
            root_name = NOTE_NAMES[root_pc]

            intervals = frozenset((pc - root_pc) % 12 for pc in pitch_classes)

            chord_type = _identify_chord_quality(intervals)

            chord_changes.append({
                "bar": bar_num,
                "time_q": time_q,
                "chord": f"{root_name}{chord_type}",
                "root": root_name,
                "pitch_classes": pitch_classes,
            })

    harmonic_rhythm = "slow" if len(chord_changes) <= length_q / 4 else "fast"

    return {
        "chord_changes": chord_changes,
        "harmonic_rhythm": harmonic_rhythm,
        "chords_per_bar": len(chord_changes) / max(1, length_q / quarters_per_bar),
    }


def _identify_chord_quality(intervals: frozenset) -> str:
    chord_types = {
        frozenset([0, 4, 7]): "",
        frozenset([0, 3, 7]): "m",
        frozenset([0, 4, 7, 11]): "maj7",
        frozenset([0, 3, 7, 10]): "m7",
        frozenset([0, 4, 7, 10]): "7",
        frozenset([0, 3, 6]): "dim",
        frozenset([0, 3, 6, 9]): "dim7",
        frozenset([0, 4, 8]): "aug",
        frozenset([0, 5, 7]): "sus4",
        frozenset([0, 2, 7]): "sus2",
        frozenset([0, 7]): "5",
    }

    if intervals in chord_types:
        return chord_types[intervals]

    has_major_third = 4 in intervals
    has_minor_third = 3 in intervals
    has_perfect_fifth = 7 in intervals

    if has_major_third and has_perfect_fifth:
        return ""
    if has_minor_third and has_perfect_fifth:
        return "m"
    if has_perfect_fifth:
        return "5"

    return ""


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
