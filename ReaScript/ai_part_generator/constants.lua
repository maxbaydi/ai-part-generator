local M = {}

M.SCRIPT_NAME = "AI Part Generator"

M.BRIDGE_BASE_URL = "http://127.0.0.1:8000"
M.BRIDGE_GENERATE_PATH = "/generate"
M.BRIDGE_PLAN_PATH = "/plan"
M.BRIDGE_ENHANCE_PATH = "/enhance"
M.BRIDGE_ARRANGE_PLAN_PATH = "/arrange_plan"
M.BRIDGE_HEALTH_PATH = "/health"
M.BRIDGE_GENERATE_URL = M.BRIDGE_BASE_URL .. M.BRIDGE_GENERATE_PATH
M.BRIDGE_PLAN_URL = M.BRIDGE_BASE_URL .. M.BRIDGE_PLAN_PATH
M.BRIDGE_ENHANCE_URL = M.BRIDGE_BASE_URL .. M.BRIDGE_ENHANCE_PATH
M.BRIDGE_ARRANGE_PLAN_URL = M.BRIDGE_BASE_URL .. M.BRIDGE_ARRANGE_PLAN_PATH
M.BRIDGE_HEALTH_URL = M.BRIDGE_BASE_URL .. M.BRIDGE_HEALTH_PATH

M.DEFAULT_BRIDGE_URL = M.BRIDGE_GENERATE_URL
M.DEFAULT_MODEL_PROVIDER = "lmstudio"
M.DEFAULT_MODEL_NAME = "gemma-3-4b-it-uncensored"
M.DEFAULT_MODEL_TEMPERATURE = 0.8
M.DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:1234/v1"

M.HTTP_TIMEOUT_SEC = 300
M.PROCESS_TIMEOUT_BUFFER_SEC = 5
M.MS_PER_SEC = 1000
M.PROCESS_TIMEOUT_MS = (M.HTTP_TIMEOUT_SEC + M.PROCESS_TIMEOUT_BUFFER_SEC) * M.MS_PER_SEC

M.BRIDGE_PING_TIMEOUT_SEC = 1
M.BRIDGE_PING_PROCESS_TIMEOUT_MS = 3000
M.BRIDGE_STARTUP_TIMEOUT_SEC = 10
M.BRIDGE_STARTUP_POLL_INTERVAL_SEC = 0.25
M.BRIDGE_PYTHON_DETECT_TIMEOUT_MS = 2000

M.MAX_CONTEXT_NOTES = 3000
M.MAX_HORIZONTAL_CONTEXT_NOTES = 500
M.MAX_PROGRESSION_NOTES = 800
M.MAX_CONTEXT_CC_EVENTS = 2000
M.MAX_SKETCH_NOTES = 5000
M.MAX_SKETCH_CC_EVENTS = 3000
M.HORIZONTAL_CONTEXT_RANGE_SEC = 60
M.CONTEXT_QN_ROUNDING = 100
M.DEFAULT_KEY = "unknown"
M.DEFAULT_MANUAL_KEY = "D minor"
M.DEFAULT_NOTE_DUR_Q = 0.25
M.LEGATO_NOTE_OVERLAP_Q = 1 / 32
M.SAME_PITCH_MIN_GAP_Q = 0
M.ARTICULATION_MIXED = "mixed"
M.DEFAULT_PITCH = 60
M.DEFAULT_VELOCITY = 80
M.DEFAULT_CC = 1
M.TEMPO_MARKER_MIN_BPM = 30
M.TEMPO_MARKER_MAX_BPM = 240
M.TEMPO_MARKER_MIN_GAP_Q = 0.25
M.TEMPO_MARKER_EPS_SEC = 0.0001
M.MAX_TEMPO_MARKERS = 8
M.TIME_SIG_MIN_NUM = 1
M.TIME_SIG_MAX_NUM = 32
M.TIME_SIG_VALID_DENOM = { [1] = true, [2] = true, [4] = true, [8] = true, [16] = true, [32] = true }
M.APPLY_CHUNK_SIZE = 256
M.DELETE_CHUNK_SIZE = 512

M.EXTSTATE_PROFILE_ID = "AI_PART_GENERATOR_PROFILE_ID"
M.EXTSTATE_API_PROVIDER = "AI_PART_GENERATOR_API_PROVIDER"
M.EXTSTATE_API_KEY = "AI_PART_GENERATOR_API_KEY"
M.EXTSTATE_API_BASE_URL = "AI_PART_GENERATOR_API_BASE_URL"
M.EXTSTATE_MODEL_NAME = "AI_PART_GENERATOR_MODEL_NAME"

M.EXTSTATE_ARTICULATION_NAME = "AI_PART_GENERATOR_ARTICULATION_NAME"
M.EXTSTATE_GENERATION_TYPE = "AI_PART_GENERATOR_GENERATION_TYPE"
-- Legacy single style field, replaced by MUSICAL_STYLE and GENERATION_MOOD
M.EXTSTATE_GENERATION_STYLE = "AI_PART_GENERATOR_GENERATION_STYLE" 
M.EXTSTATE_MUSICAL_STYLE = "AI_PART_GENERATOR_MUSICAL_STYLE"
M.EXTSTATE_GENERATION_MOOD = "AI_PART_GENERATOR_GENERATION_MOOD"

M.EXTSTATE_PROMPT = "AI_PART_GENERATOR_PROMPT"
M.EXTSTATE_USE_SELECTED_TRACKS = "AI_PART_GENERATOR_USE_SELECTED_TRACKS"
M.EXTSTATE_INSERT_TARGET = "AI_PART_GENERATOR_INSERT_TARGET"
M.EXTSTATE_KEY_MODE = "AI_PART_GENERATOR_KEY_MODE"
M.EXTSTATE_KEY = "AI_PART_GENERATOR_KEY"

M.API_PROVIDER_LOCAL = "local"
M.API_PROVIDER_OPENROUTER = "openrouter"
M.DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
M.DEFAULT_OPENROUTER_MODEL = "google/gemini-3-flash-preview"
M.DEFAULT_OPENROUTER_PLAN_MODEL = "google/gemini-3-flash-preview"

M.INSERT_TARGET_ACTIVE = "active"
M.INSERT_TARGET_NEW = "new"

M.EXTSTATE_FREE_MODE = "AI_PART_GENERATOR_FREE_MODE"
M.EXTSTATE_ALLOW_TEMPO_CHANGES = "AI_PART_GENERATOR_ALLOW_TEMPO_CHANGES"
M.EXTSTATE_ARRANGE_SOURCE_ITEM = "AI_PART_GENERATOR_ARRANGE_SOURCE_ITEM"

M.MIDI_MIN = 0
M.MIDI_MAX = 127
M.MIDI_VEL_MIN = 1
M.MIDI_CHAN_MIN = 1
M.MIDI_CHAN_MAX = 16
M.MIDI_CC_STATUS = 0xB0
M.MIDI_PC_STATUS = 0xC0

M.PROMPT_BUF_SIZE = 32768

M.GENERATION_TYPES = {
  "Melody",
  "Arpeggio",
  "Bass",
  "Chords",
  "Pad",
  "Counter-Melody",
  "Ostinato",
  "Rhythm",
  "Percussion",
  "Fill",
  "Atmosphere"
}

M.DEFAULT_GENERATION_TYPE = "Melody"

-- 1. Musical Style (Genre / Era / Texture)
M.MUSICAL_STYLES = {
  "Cinematic",
  "Orchestral",
  "Film Score",
  "Ambient",
  "Classical",
  "Baroque",
  "Impressionist",
  "Minimalist",
  "Celtic",
  "Nordic",
  "Slavic",
  "Middle Eastern",
  "Asian",
  "Latin",
  "Electronic",
  "Hybrid"
}

M.STYLE_DESCRIPTIONS = {
  ["Cinematic"] = "Focus on emotional impact and storytelling. Harmony: Mediant relationships (e.g. I-bIII, I-bVI), sus2/sus4 chords for ambiguity. Texture: Layered dynamics, evolving pads, ostinatos. Structure: Slow build-ups.",
  ["Orchestral"] = "Traditional symphonic sound. Harmony: Functional diatonic progressions (I-IV-V-I) or chromatic mediants. Texture: Balance between sections, clear counterpoint. Orchestration: Realistic instrument ranges and doubling.",
  ["Film Score"] = "Underscore style. Harmony: Pedal points, static harmonies, minor 9th chords. Texture: Sparse, avoiding conflict with dialogue. Rhythm: Subtle pulses rather than strong beats.",
  ["Ambient"] = "Atmospheric and spacious. Harmony: Cluster chords, quartal harmony, slow harmonic rhythm. Texture: Long sustains, washes of sound, lack of strong pulse. Dynamics: Soft and consistent.",
  ["Classical"] = "Mozart/Haydn era style. Harmony: Clear functional harmony (tonic/dominant), Alberti bass. Structure: Periodic phrasing (antecedent/consequent). Texture: Melody with accompaniment, clear resolution.",
  ["Baroque"] = "Bach/Vivaldi era style. Harmony: Cycle of fifths sequences, secondary dominants. Texture: Polyphonic, counterpoint, basso continuo feel. Rhythm: Motoric rhythms, steady 8th/16th notes.",
  ["Impressionist"] = "Debussy/Ravel style. Harmony: Extended chords (9ths, 11ths, 13ths), parallel motion (planing), whole-tone or pentatonic scales. Texture: Color over function, shimmering tremolos.",
  ["Minimalist"] = "Philip Glass/Reich style. Harmony: Static, slowly shifting. Structure: Repetitive cells with phase shifts or additive additive processes. Texture: Layered ostinatos, steady pulse.",
  ["Celtic"] = "Folk inspired. Harmony: Mixolydian or Dorian modes, drone bass (I-V). Rhythm: Triplets, 6/8 or 12/8 feel, grace notes. Texture: Flutes, fiddles, bagpipe drones.",
  ["Nordic"] = "Cold, vast landscapes. Harmony: Minor modes, open fifths, distant modulations. Texture: Raw, icy strings, low brass, spacious percussion. Rhythm: Slow, heavy pulses.",
  ["Slavic"] = "Emotional and heavy. Harmony: Harmonic minor, fluctuating between major/minor relative. Texture: Rich, dense string writing, expressive vibrato. Melody: Wide leaps, soulful.",
  ["Middle Eastern"] = "Oriental scales. Harmony: Phrygian dominant or Hijaz scales, quarter tones (simulated via pitch bend if needed). Texture: Heterophony, intricate ornamentation, odd meters (5/8, 7/8).",
  ["Asian"] = "Pentatonic focus. Harmony: Quartal harmony, avoidance of leading tones. Texture: Sparse, emphasis on timber and space (Ma). Instruments: Plucked sounds, woodwinds.",
  ["Latin"] = "Rhythmic focus. Harmony: Montuno patterns, ii-V-I in major or minor. Rhythm: Clave (3-2 or 2-3), syncopation, anticipated bass. Texture: Percussive, sharp attacks.",
  ["Electronic"] = "Synthesized feel. Harmony: Loop-based progressions (vi-IV-I-V), sidechain pumping effects. Texture: Arpeggiators, gates, filters. Rhythm: Grid-locked, quantized.",
  ["Hybrid"] = "Mix of Orchestral and Electronic. Harmony: Trailer chords (minor triads moving by thirds). Texture: Massive drums, synth braams mixed with orchestra. Dynamics: Extreme."
}

M.DEFAULT_MUSICAL_STYLE = "Cinematic"

-- 2. Mood / Vibe (Emotion / Character)
M.GENERATION_MOODS = {
  "Heroic",
  "Epic",
  "Triumphant",
  "Majestic",
  "Adventurous",
  "Dramatic",
  "Intense",
  "Suspense",
  "Thriller",
  "Horror",
  "Dark",
  "Ominous",
  "Foreboding",
  "Tragic",
  "Melancholic",
  "Tender",
  "Romantic",
  "Nostalgic",
  "Passionate",
  "Longing",
  "Hopeful",
  "Victorious",
  "Peaceful",
  "Serene",
  "Dreamy",
  "Ethereal",
  "Magical",
  "Mysterious",
  "Meditative",
  "Whimsical",
  "Playful",
  "Energetic",
  "Action",
  "Aggressive",
  "Fierce",
  "Solemn"
}

M.MOOD_DESCRIPTIONS = {
  ["Heroic"] = "Brave and confident. Characteristics: Ascending intervals (perfect 4ths/5ths), brass fanfares. Harmony: Major key, I-V-IV progressions. Rhythm: Dotted rhythms, triplets.",
  ["Epic"] = "Larger than life. Characteristics: Massive sound, choir, full orchestra. Harmony: Slow harmonic rhythm, power chords. Rhythm: Heavy downbeats, driving ostinatos.",
  ["Triumphant"] = "Success and victory. Characteristics: Bright brass, soaring strings. Harmony: Unambiguous Major resolution, plagal cadences. Rhythm: March-like, steady.",
  ["Majestic"] = "Grand and stately. Characteristics: Broad tempos, rich voicings. Harmony: Full triads, stately progressions. Rhythm: Slow, deliberate movement.",
  ["Adventurous"] = "Exploration and motion. Characteristics: Rapid scalar runs, agile woodwinds. Harmony: Modulating through keys, chromatic mediants. Rhythm: Driving, propulsive (12/8 or fast 4/4).",
  ["Dramatic"] = "High stakes and conflict. Characteristics: Sharp contrasts, sfz accents. Harmony: Diminished 7ths, abrupt modulations, minor keys. Rhythm: Irregular accents.",
  ["Intense"] = "High energy and focus. Characteristics: Relentless motion, busy textures. Harmony: Pedal points with shifting dissonance above. Rhythm: Fast, repetitive 16th notes.",
  ["Suspense"] = "Waiting for something. Characteristics: Tremolo strings, subtone brass. Harmony: Unresolved chords, half-diminished, chromatic clusters. Rhythm: Sparse, unpredictable.",
  ["Thriller"] = "Tension and chase. Characteristics: Pulse-pounding bass, metallic percussion. Harmony: Dissonant, atonal or bitonal elements. Rhythm: Urgent, syncopated.",
  ["Horror"] = "Fear and terror. Characteristics: Extended techniques (col legno, sul pont), screeching highs, rumbling lows. Harmony: Atonal, cluster chords, tritones. Rhythm: Chaotic or dead silence.",
  ["Dark"] = "Shadowy and bleak. Characteristics: Low tessitura, dark timbres (low woodwinds/brass). Harmony: Minor modes (Aeolian/Locrian), slow moving. Rhythm: Heavy, dragging.",
  ["Ominous"] = "Threatening. Characteristics: Low drones, distant swells. Harmony: Minor seconds, chromaticism. Rhythm: Slow, foreboding pulse.",
  ["Foreboding"] = "Something bad is coming. Characteristics: Warning motifs, deep brass swells. Harmony: Unstable, avoiding resolution. Rhythm: Slow, anticipating.",
  ["Tragic"] = "Deep sorrow/disaster. Characteristics: Heavy, weeping lines. Harmony: Minor key, Neapolitan chords, descending chromatic bass (lamento bass). Rhythm: Slow, heavy.",
  ["Melancholic"] = "Sadness and reflection. Characteristics: Solo instruments (cello/oboe), expressive vibrato. Harmony: Minor key, beautiful but sad suspensions (4-3). Rhythm: Flowing, rubato.",
  ["Tender"] = "Gentle and caring. Characteristics: Soft dynamics, warm textures. Harmony: Major/Lydian, diatonic, consonant. Rhythm: Gentle, lullaby-like.",
  ["Romantic"] = "Love and passion. Characteristics: Lush strings, sweeping melodies. Harmony: Rich 7th and 9th chords, chromatic appoggiaturas. Rhythm: Rubato, expressive swells.",
  ["Nostalgic"] = "Longing for the past. Characteristics: Warm, faded sound. Harmony: Major 7ths, add9 chords, I-iii-IV progressions. Rhythm: Slow, reminiscent.",
  ["Passionate"] = "Strong emotion. Characteristics: Wide dynamic swells, high string ranges. Harmony: Chromaticism, intense climaxes. Rhythm: Flexible, pushing and pulling.",
  ["Longing"] = "Desire for something unreachable. Characteristics: Upward reaching melodies that fall back. Harmony: Unresolved suspensions, minor 7ths. Rhythm: Flowing.",
  ["Hopeful"] = "Optimism rising. Characteristics: Rising melodic lines, brightening orchestration. Harmony: Moving from minor to relative major, ascending bass lines. Rhythm: Forward moving.",
  ["Victorious"] = "Winning against odds. Characteristics: Similar to Heroic but with finality. Harmony: Strong V-I resolutions. Rhythm: Celebratory.",
  ["Peaceful"] = "Calm and still. Characteristics: Sparse texture, soft pads. Harmony: Diatonic, static, pedal points. Rhythm: Very slow, almost non-existent.",
  ["Serene"] = "Untroubled. Characteristics: High, clear sounds (flute, harp). Harmony: Simple major triads, pastel colors. Rhythm: Gentle flow.",
  ["Dreamy"] = "Surreal and soft. Characteristics: Whole tone scales, harp glissandos. Harmony: Augmented chords, blurry tonal centers. Rhythm: Floating, unmetered feel.",
  ["Ethereal"] = "Otherworldly. Characteristics: High shimmering textures, choir. Harmony: Lydian mode, major chords with sharp 11ths. Rhythm: Weightless.",
  ["Magical"] = "Wonder and awe. Characteristics: Celesta/Glockenspiel sparkles, woodwind runs. Harmony: Lydian mode, chromatic mediants (major chords moving by 3rds). Rhythm: Swirling.",
  ["Mysterious"] = "Unknown and puzzling. Characteristics: Hollow sounds, pizzicato. Harmony: Dorian #4 or whole tone, lack of root. Rhythm: Sneaky, tiptoeing.",
  ["Meditative"] = "Focus and depth. Characteristics: Drone-based, repetitive. Harmony: Minimal movement, root-5th-octave. Rhythm: Breath-like.",
  ["Whimsical"] = "Quirky and fun. Characteristics: Staccato woodwinds, odd articulations. Harmony: Unexpected shifts, whole tone. Rhythm: Bouncy, uneven, changing meters.",
  ["Playful"] = "Lighthearted fun. Characteristics: Pizzicato strings, light percussion. Harmony: Major key, simple, staccato chords. Rhythm: Bouncy 6/8 or cut time.",
  ["Energetic"] = "Full of life. Characteristics: Fast runs, busy accompaniment. Harmony: Simple, driving harmonies. Rhythm: Fast tempo, strong subdivision.",
  ["Action"] = "Movement and impact. Characteristics: Hits, runs, brass stabs. Harmony: Minor/modal, ostinato bass. Rhythm: Driving 16ths, odd meters (5/4).",
  ["Aggressive"] = "Hostile and attacking. Characteristics: Harsh attacks, distortion. Harmony: Dissonant, power chords, tritones. Rhythm: Hard hitting, punctuated.",
  ["Fierce"] = "Wild and savage. Characteristics: Extreme ranges, loud dynamics. Harmony: Clashing intervals. Rhythm: Fast, chaotic.",
  ["Solemn"] = "Serious and grave. Characteristics: Low register, slow movement. Harmony: Minor, hymn-like, plagal cadences. Rhythm: Very slow, uniform."
}

M.DEFAULT_GENERATION_MOOD = "Heroic"

M.FALLBACK_FIELD_COUNT = 8

return M
