from __future__ import annotations

TYPE_HINTS = {
    "melody": (
        "ROLE: MAIN THEME / LEAD VOICE.\n"
        "OBJECTIVE: Create a memorable, singable melodic line that acts as the primary focus.\n"
        "INSTRUCTIONS: Use clear phrasing with natural breathing points (rests). Develop motifs logically. "
        "Avoid random leaps; use stepwise motion with occasional expressive intervals. "
        "If specific rhythms or intervals are requested in Additional Instructions, prioritize them strictly."
    ),
    "arpeggio": (
        "ROLE: HARMONIC MOTION / RHYTHMIC FLOW.\n"
        "OBJECTIVE: Break chords into sequential notes to create movement and texture.\n"
        "INSTRUCTIONS: Follow the chord progression strictly. Maintain a consistent rhythmic pulse (e.g., 8th or 16th notes). "
        "Use patterns that ascend, descend, or weave. "
        "CRITICAL: If Additional Instructions specify a rhythm (e.g., '16th notes', 'triplets') or pattern, YOU MUST FOLLOW IT EXACTLY over any default style behavior."
    ),
    "bass": (
        "ROLE: HARMONIC FOUNDATION / RHYTHMIC ANCHOR.\n"
        "OBJECTIVE: Establish the root movement and lock in the groove with the drums.\n"
        "INSTRUCTIONS: Focus on Root and Fifth of the current chord. Place strong notes on downbeats (Beat 1). "
        "Keep the line monophonic (one note at a time). "
        "If the style implies specific rhythms (e.g., 'gallop' for Epic, 'walking' for Jazz), apply them unless overruled by Additional Instructions."
    ),
    "chords": (
        "ROLE: HARMONIC SUPPORT / BODY.\n"
        "OBJECTIVE: Provide the full harmonic context using block chords or rhythmic strikes.\n"
        "INSTRUCTIONS: Play multiple notes simultaneously (polyphonic) representing the current chord. "
        "Pay attention to voice leading—don't jump voicing wildly between chords. "
        "Adjust density based on style (e.g., simple triads for Pop, extended voicings for Jazz)."
    ),
    "pad": (
        "ROLE: ATMOSPHERE / GLUE.\n"
        "OBJECTIVE: Fill the frequency spectrum with sustained, evolving textures.\n"
        "INSTRUCTIONS: Use long, sustained notes (whole notes, tied notes). Minimize rhythmic activity. "
        "Focus on smooth transitions and slow voice leading. "
        "CRITICAL: Use CC1 (Dynamics) to create slow 'breathing' swells—never leave a pad flat."
    ),
    "counter-melody": (
        "ROLE: SECONDARY THEME / DIALOGUE.\n"
        "OBJECTIVE: Weave a melodic line that complements BUT DOES NOT CLASH with the main melody.\n"
        "INSTRUCTIONS: Fill the gaps left by the main melody (call and response). "
        "Use a different rhythmic density or register than the main theme to ensure separation. "
        "Harmonize nicely with the current chord structure."
    ),
    "ostinato": (
        "ROLE: DRIVING MOTOR / REPETITIVE FIGURE.\n"
        "OBJECTIVE: Create a short, catchy rhythmic/melodic figure that repeats with hypnotic consistency.\n"
        "INSTRUCTIONS: Establish a pattern (1-2 bars) and repeat it. "
        "Keep note durations and articulations highly consistent (e.g., all staccato). "
        "Do not vary the rhythm randomly; only vary pitch to follow the chord changes if necessary."
    ),
    "rhythm": (
        "ROLE: PERCUSSIVE DRIVE / PULSE.\n"
        "OBJECTIVE: emphasize the beat and subdivision.\n"
        "INSTRUCTIONS: Focus on timing, accents, and groove. Pitch is secondary to rhythm here. "
        "Use muted notes or specific articulations to create percussive effects if the instrument allows. "
        "Strictly adhere to any user-requested subdivisions (e.g., 'syncopated 16ths')."
    ),
    "percussion": (
        "ROLE: BEAT / IMPACT / TEXTURE.\n"
        "OBJECTIVE: Provide rhythmic backbone or cinematic impact.\n"
        "INSTRUCTIONS: If this is a drum kit: Kick on strong beats, Snare on backbeats (2/4). "
        "If orchestral percussion: huge hits on transition points, rolls for tension. "
        "ALWAYS use 'patterns' and 'repeats' for drum grooves to ensure consistency."
    ),
    "fill": (
        "ROLE: TRANSITION / EMBELLISHMENT.\n"
        "OBJECTIVE: Bridge two sections or phrases with a burst of energy.\n"
        "INSTRUCTIONS: Start sparse and accelerate (or decelerate) towards the target beat. "
        "Use runs, scales, or fast rhythmic bursts. "
        "Ensure the fill resolves clearly onto the downbeat of the next section."
    ),
    "atmosphere": (
        "ROLE: MOOD / TEXTURE / SFX.\n"
        "OBJECTIVE: Create a sonic environment without traditional melodic/harmonic function.\n"
        "INSTRUCTIONS: Use sparse, disconnected notes, clusters, or effects. "
        "Focus entirely on timbre and dynamics (CC1/CC11). "
        "Perfect for 'Horror', 'Ambient', or 'Suspense' styles."
    )
}

# Fallback hints for articulations if not specified in profile
ARTICULATION_HINTS = {
    "spiccato": "SHORT: Bouncy, detached (dur_q 0.25-0.5). Dynamics via Velocity.",
    "staccato": "SHORT: Crisp, separated (dur_q 0.25-0.5). Dynamics via Velocity.",
    "staccatissimo": "VERY SHORT: Sharp, extremely short (dur_q 0.125-0.25). Dynamics via Velocity.",
    "legato": "LONG: Connected, smooth, flowing. NO gaps between notes. Dynamics via CC1.",
    "sustain": "LONG: Held notes, continuous sound. Dynamics via CC1.",
    "pizzicato": "SHORT: Plucked, percussive (dur_q 0.25-0.5). Dynamics via Velocity.",
    "tremolo": "LONG: Rapid repetition bowing effect. Sustained feel. Dynamics via CC1.",
    "marcato": "ACCENTED: Strong attack with separation. Heavy weight. Dynamics via Velocity/CC1 combo.",
    "col_legno": "SHORT: Hit with wood of bow. Percussive, brittle. Dynamics via Velocity.",
    "harmonics": "EFFECT: Glassy, high whistle tones. Usually sustained. Dynamics via CC1."
}
