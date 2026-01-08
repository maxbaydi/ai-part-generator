from __future__ import annotations

TYPE_HINTS = {
    "melody": "Generate the MAIN MELODY - the primary musical theme. Must be memorable, singable, and emotionally engaging. Clear phrases with natural breathing points.",
    "arpeggio": "Generate an ARPEGGIO pattern - broken chord notes played sequentially. Flowing, harp-like movement following the harmony.",
    "bass line": "Generate a BASS LINE - the harmonic foundation. Supportive low notes that anchor the rhythm and harmony.",
    "chords": "Generate CHORDS - harmonic accompaniment. Block or broken chords providing harmonic support.",
    "pad": "Generate a PAD - sustained atmospheric background. Long, evolving notes creating harmonic bed.",
    "pad/sustained": "Generate a PAD - sustained atmospheric background. Long, evolving notes creating harmonic bed.",
    "counter-melody": "Generate a COUNTER-MELODY - a secondary melody complementing the main theme. Independent but harmonically related.",
    "accompaniment": "Generate ACCOMPANIMENT - rhythmic/harmonic support. Background pattern that enhances without dominating.",
    "rhythmic": "Generate a RHYTHMIC pattern - percussive, groove-focused. Short notes emphasizing beat and syncopation.",
    "ostinato": "Generate an OSTINATO - a repeating musical figure. Hypnotic, consistent pattern with subtle variations. KEEP NOTE DURATIONS CONSISTENT throughout - if using short articulations, ALL notes must be short.",
    "fill": "Generate a FILL - transitional ornamental passage. Connects sections with flourishes and runs.",
}

ARTICULATION_HINTS = {
    "spiccato": "Use SHORT notes (dur_q: 0.25-0.5). Bouncy, detached.",
    "staccato": "Use VERY SHORT notes (dur_q: 0.125-0.25). Crisp, separated.",
    "legato": "Use CONNECTED notes. Smooth, flowing lines.",
    "pizzicato": "Use SHORT plucked notes (dur_q: 0.25-0.5).",
    "tremolo": "Use SUSTAINED notes with trembling effect.",
}
