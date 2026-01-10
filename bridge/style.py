from __future__ import annotations

# Detailed instructions for each musical style.
# These tell the model how to interpret the style musically (scales, rhythms, dynamics, orchestration).

MOOD_HINTS = {
    # --- CINEMATIC / ORCHESTRAL ---
    "heroic": (
        "STYLE: HEROIC / ADVENTURE.\n"
        "CHARACTER: Bold, confident, triumphant, rising.\n"
        "MUSICAL TRAITS: Major tonality. Strong intervals (perfect 4ths, 5ths, octaves). "
        "Fanfare-like rhythms (triplets, dotted 8th+16th). Emphasize the downbeat.\n"
        "DYNAMICS: Loud and proud (mf to ff). Strong accents. Crescendos into new phrases."
    ),
    "epic": (
        "STYLE: EPIC / TRAILER.\n"
        "CHARACTER: Massive, grand, overwhelming, slow-burn to explosion.\n"
        "MUSICAL TRAITS: Huge unison lines. Slow harmonic rhythm (long chords). "
        "Ostinatos driving the rhythm. Wide orchestration (low lows, high highs).\n"
        "DYNAMICS: Extreme dynamic range (pp to fff). Massive swells. Sforzando accents."
    ),
    "cinematic": (
        "STYLE: MODERN CINEMATIC.\n"
        "CHARACTER: Evolving, emotional, storytelling, visual.\n"
        "MUSICAL TRAITS: Mix of organic and synthetic textures. Minimalist repetitive motifs that build over time. "
        "Focus on texture and timbre over complex melody.\n"
        "DYNAMICS: Constant evolution (CC1). Never static. Ebb and flow like waves."
    ),
    "dramatic": (
        "STYLE: DRAMATIC / EMOTIONAL.\n"
        "CHARACTER: Intense, conflicted, heavy, narrative.\n"
        "MUSICAL TRAITS: Minor keys or modal interchanges. Unexpected chord changes. "
        "Wide melodic leaps (6ths, 7ths). Tension and release.\n"
        "DYNAMICS: Volatile. Sudden drops to whisper, sudden explosions to scream."
    ),
    "triumphant": (
        "STYLE: TRIUMPHANT / VICTORY.\n"
        "CHARACTER: Celebrating, winning, final resolution.\n"
        "MUSICAL TRAITS: Pure Major key. Ascending lines. Bright harmony. "
        "Rhythmic unison. Brass fanfares. Ending on the Tonic with power.\n"
        "DYNAMICS: Sustained high energy (f to ff). Bright and punchy."
    ),
    "majestic": (
        "STYLE: MAJESTIC / ROYAL.\n"
        "CHARACTER: Dignified, slow, noble, spacious.\n"
        "MUSICAL TRAITS: Slow tempos. Dotted rhythms. Rich harmony (suspensions). "
        "Processional feel. Avoid rapid notes.\n"
        "DYNAMICS: Controlled power. stately swells. Heavy weight."
    ),
    "adventurous": (
        "STYLE: ADVENTUROUS / JOURNEY.\n"
        "CHARACTER: Forward-moving, exciting, eager, exploring.\n"
        "MUSICAL TRAITS: Fast 12/8 or triplet feel. Lydian mode (raised 4th) touches. "
        "Running scales. Agile melodic movement.\n"
        "DYNAMICS: Energetic. Accented syncopations."
    ),
    "suspense": (
        "STYLE: SUSPENSE / TENSION.\n"
        "CHARACTER: Waiting, dangerous, uncertain, holding breath.\n"
        "MUSICAL TRAITS: Dissonant clusters (minor 2nds). Chromaticism. Tremolos. "
        "Unresolved questions. High string pedals or low rumbles.\n"
        "DYNAMICS: Mostly quiet (pp) with sudden scary spikes (sfz)."
    ),
    "thriller": (
        "STYLE: THRILLER / CHASE.\n"
        "CHARACTER: Urgent, nervous, panic, running.\n"
        "MUSICAL TRAITS: Fast, irregular rhythms (5/8, 7/8). Staccato ostinatos. "
        "Dissonant stabs. Rising pitch sequences (Shepard tone effect).\n"
        "DYNAMICS: Nervous pulsing. Sudden silences."
    ),
    "horror": (
        "STYLE: HORROR / SCARY.\n"
        "CHARACTER: Terrifying, chaotic, nightmarish, dissonant.\n"
        "MUSICAL TRAITS: Atonal or highly chromatic. Tritones. Extended techniques (screeches, scrapes). "
        "Unpredictable rhythm. Low clusters.\n"
        "DYNAMICS: Extreme shock. Silence vs. Noise."
    ),

    # --- EMOTIONAL / ATMOSPHERIC ---
    "romantic": (
        "STYLE: ROMANTIC / LOVE.\n"
        "CHARACTER: Passionate, sweeping, rubato, warm.\n"
        "MUSICAL TRAITS: Lush harmonies (7ths, 9ths). Long singing melodies. "
        "Expressive leaps. Chromatic passing tones. Slow harmonic pace.\n"
        "DYNAMICS: Deep, breathing expression. Large crescendos and decrescendos."
    ),
    "melancholic": (
        "STYLE: MELANCHOLIC / SAD.\n"
        "CHARACTER: Sorrowful, lonely, reflective, weeping.\n"
        "MUSICAL TRAITS: Minor key. Falling melodic lines (sigh motif). "
        "Slow tempo. Sparse accompaniment. Solo instruments featured.\n"
        "DYNAMICS: Soft (mp to pp). Fading away. Gentle."
    ),
    "tender": (
        "STYLE: TENDER / INTIMATE.\n"
        "CHARACTER: Gentle, fragile, close, caring.\n"
        "MUSICAL TRAITS: Simple melody. Consonant harmony. High register piano or strings. "
        "Avoid harsh intervals. Lullaby quality.\n"
        "DYNAMICS: Very soft (pp to p). Delicate touch. No sudden changes."
    ),
    "nostalgic": (
        "STYLE: NOSTALGIC / MEMORY.\n"
        "CHARACTER: Bittersweet, looking back, warm but sad.\n"
        "MUSICAL TRAITS: Major key with borrowed minor chords (iv). Simple, folk-like melody. "
        "Waltz time (3/4) often works well.\n"
        "DYNAMICS: Warm and flowing. Moderate range."
    ),
    "hopeful": (
        "STYLE: HOPEFUL / INSPIRING.\n"
        "CHARACTER: Rising, brightening, dawn, optimism.\n"
        "MUSICAL TRAITS: Starts sparse/low, builds up/high. Major key. "
        "Ascending chord progressions. Steady, reassuring rhythm.\n"
        "DYNAMICS: Gradual build from p to f over the whole section."
    ),
    "dreamy": (
        "STYLE: DREAMY / FANTASY.\n"
        "CHARACTER: Floating, blurred, magical, unreal.\n"
        "MUSICAL TRAITS: Whole tone or Lydian scales. Arpeggiated harps/pianos. "
        "Blurred harmony (pedal held down). Soft attacks.\n"
        "DYNAMICS: Fluid, water-like. No hard edges."
    ),
    "ethereal": (
        "STYLE: ETHEREAL / CELESTIAL.\n"
        "CHARACTER: Angelic, weightless, holy, space.\n"
        "MUSICAL TRAITS: Very high register. Open chords (no 3rds). Long reverb tails. "
        "Slow motion. Choir-like textures.\n"
        "DYNAMICS: Static, shimmering. Very constant."
    ),
    "mysterious": (
        "STYLE: MYSTERIOUS / ENIGMATIC.\n"
        "CHARACTER: Puzzling, searching, fog, shadows.\n"
        "MUSICAL TRAITS: Dorian or Phrygian mode. Wandering melody without clear home. "
        "Pizzicato bass. unexpected harmonic shifts.\n"
        "DYNAMICS: Quiet, sneaking."
    ),
    "meditative": (
        "STYLE: MEDITATIVE / ZEN.\n"
        "CHARACTER: Still, inner peace, breath, timeless.\n"
        "MUSICAL TRAITS: Drones. Pentatonic scales. Extrememly slow. "
        "Repetitive minimal motifs. Silence is as important as sound.\n"
        "DYNAMICS: Flat, steady, very gentle."
    ),
    "ambient": (
        "STYLE: AMBIENT / DRONE.\n"
        "CHARACTER: Background, texture, pad, vibe.\n"
        "MUSICAL TRAITS: No distinct melody. Focus on timbre evolution. "
        "Deep bass drones. High shimmers. Slow filter sweeps.\n"
        "DYNAMICS: Very slow evolution over many bars."
    ),

    # --- ACTION / ENERGY ---
    "energetic": (
        "STYLE: ENERGETIC / UPBEAT.\n"
        "CHARACTER: Active, busy, running, happy.\n"
        "MUSICAL TRAITS: Fast tempo. Constant 8th or 16th note motion. "
        "Staccato articulations. Syncopated pop/rock rhythms.\n"
        "DYNAMICS: High energy (f). Punchy."
    ),
    "playful": (
        "STYLE: PLAYFUL / COMEDY.\n"
        "CHARACTER: Light, bouncy, mischievous, quirky.\n"
        "MUSICAL TRAITS: Staccato woodwinds/strings. Pizzicato. Grace notes. "
        "Unexpected pauses. Chromatic runs. Polka or march rhythms.\n"
        "DYNAMICS: Light (mp). bouncy accents."
    ),
    "action": (
        "STYLE: ACTION / BATTLE.\n"
        "CHARACTER: Fighting, aggressive, danger, adrenaline.\n"
        "MUSICAL TRAITS: Driving percussion. Brass stabs. Fast string ostinatos. "
        "Minor or diminished scales. Heavy syncopation on weak beats.\n"
        "DYNAMICS: Loud, aggressive, punchy."
    ),
    "aggressive": (
        "STYLE: AGGRESSIVE / HEAVY.\n"
        "CHARACTER: Angry, forceful, destructive, mean.\n"
        "MUSICAL TRAITS: Distortion. Power chords. Low register riffs. "
        "Chromatic palm-muted chugs. Hard-hitting drums.\n"
        "DYNAMICS: Maximum volume (ff). Wall of sound."
    ),

    # --- GENRE SPECIFIC ---
    "celtic": (
        "STYLE: CELTIC / FOLK.\n"
        "CHARACTER: Earthy, green, dance-like, ancient.\n"
        "MUSICAL TRAITS: Dorian or Mixolydian modes. Triplets (jig/reel). "
        "Drone bass. Grace notes/ornaments. Flutes, fiddles, bags.\n"
        "DYNAMICS: Rhythmic pulsing."
    ),
    "middle eastern": (
        "STYLE: MIDDLE EASTERN / DESERT.\n"
        "CHARACTER: Exotic, heat, mystical, ancient.\n"
        "MUSICAL TRAITS: Double Harmonic scale (Hijaz). Quarter tones (pitch bends). "
        "Ornamental melismas (turns/trills). Percussion heavy.\n"
        "DYNAMICS: Expressive melodic swells."
    ),
    "asian": (
        "STYLE: EAST ASIAN / ZEN.\n"
        "CHARACTER: Nature, refined, bamboo, silk.\n"
        "MUSICAL TRAITS: Pentatonic scales. Pitch bending. Sparse texture. "
        "Wood block percussion. Flute ornaments.\n"
        "DYNAMICS: Sudden loud hits followed by decay."
    ),
    "latin": (
        "STYLE: LATIN / TROPICAL.\n"
        "CHARACTER: Hot, dancing, rhythmic, party.\n"
        "MUSICAL TRAITS: Clave rhythms (3-2, 2-3). Montuno piano patterns. "
        "Syncopated bass (tumbao). Brass punches.\n"
        "DYNAMICS: Tight, rhythmic, sharp."
    ),
    "nordic": (
        "STYLE: NORDIC / VIKING.\n"
        "CHARACTER: Cold, ice, vast, ancient war.\n"
        "MUSICAL TRAITS: Low drones. Throat singing style (deep rasp). "
        "Simple minor melodies. heavy constant drums. Raw strings.\n"
        "DYNAMICS: Raw, primal, building."
    ),
    "baroque": (
        "STYLE: BAROQUE / CLASSICAL.\n"
        "CHARACTER: Ornate, mathematical, busy, formal.\n"
        "MUSICAL TRAITS: Counterpoint. Constant 16th note motion (motor rhythm). "
        "Harpsichord/Strings. Trills and ornaments. Circle of 5ths.\n"
        "DYNAMICS: Terraced (sudden changes between p and f)."
    ),
    "minimalist": (
        "STYLE: MINIMALIST / MODERN.\n"
        "CHARACTER: Repetitive, hypnotic, process-based, glass.\n"
        "MUSICAL TRAITS: Short repeated cells. Phase shifting. Gradual changes. "
        "Consonant harmony. Pulse is everything.\n"
        "DYNAMICS: Very gradual, long-form changes."
    ),
}

# Simplified dynamics hints to append to the main prompt if needed, 
# though the MOOD_HINTS above now cover dynamics well.
DYNAMICS_HINTS = {
    "default": "EXPRESSION: Follow the phrase shape. DYNAMICS: Natural breathing."
}
