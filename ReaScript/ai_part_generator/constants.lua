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
M.EXTSTATE_CONTINUATION_MODE = "AI_PART_GENERATOR_CONTINUATION_MODE"
M.EXTSTATE_SECTION_POSITION = "AI_PART_GENERATOR_SECTION_POSITION"

M.CONTINUATION_MODE_CONTINUE = "continue"
M.CONTINUATION_MODE_FINISH = "finish"
M.DEFAULT_CONTINUATION_MODE = M.CONTINUATION_MODE_CONTINUE

M.SECTION_POSITION_START = "start"
M.SECTION_POSITION_MIDDLE = "middle"
M.SECTION_POSITION_END = "end"
M.DEFAULT_SECTION_POSITION = M.SECTION_POSITION_END

M.CONTINUATION_MODES = {
  { display = "Continue", value = M.CONTINUATION_MODE_CONTINUE },
  { display = "Finish", value = M.CONTINUATION_MODE_FINISH }
}

M.SECTION_POSITION_OPTIONS = {
  { display = "Start", value = M.SECTION_POSITION_START },
  { display = "Middle", value = M.SECTION_POSITION_MIDDLE },
  { display = "End", value = M.SECTION_POSITION_END }
}

M.MIN_SELECTED_ITEMS_FOR_CONTINUATION = 1
M.ERROR_CONTINUATION_NO_SELECTION = "Select MIDI items for continuation context."

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
  ["Cinematic"] = "Focus on evolution and emotion. Harmony: Chromatic mediants (e.g., Cm to Em), sus2/sus4 chords for ambiguity. Texture: Slow harmonic rhythm, pulsing ostinatos, layered dynamics. Bass: Deep drones/pedal points.",
  ["Orchestral"] = "Traditional symphonic balance. Harmony: Functional diatonic progressions (I-IV-V-I) with occasional chromaticism. Texture: Clear separation of sections (Strings, Woodwinds, Brass). Voicing: Spread chords, avoid muddy low-mid frequencies.",
  ["Film Score"] = "Underscore technique. Harmony: Static or slowly shifting (Neo-Riemannian), minor 9ths, avoidance of perfect cadences. Texture: Sparse, leaves room for dialogue (frequency 'pocketing'). Rhythm: Subtle pulse, not overpowering.",
  ["Ambient"] = "Atmosphere over melody. Harmony: Quartal harmony (stacked 4ths), cluster chords, lack of functional resolution. Texture: Long evolving pads, washes of sound, extensive reverb tails. Rhythm: Non-existent or very slow drift.",
  ["Classical"] = "Mozart/Haydn era clarity. Harmony: Strong tonic-dominant relationships, Alberti bass accompaniments. Structure: Periodic phrasing (antecedent/consequent calls). Texture: Melody with clear accompaniment, homophonic.",
  ["Baroque"] = "Bach/Vivaldi counterpoint. Harmony: Cycle of fifths sequences, secondary dominants (V/V). Texture: Polyphonic, independent melodic lines, Basso Continuo feel. Rhythm: Motoric, steady 16th/8th note drive.",
  ["Impressionist"] = "Debussy/Ravel color. Harmony: Extended chords (9th, 11th, 13th), parallel motion (planing chords), Whole-tone or Pentatonic scales. Texture: Shimmering, tremolos, emphasis on timber color rather than functional progression.",
  ["Minimalist"] = "Glass/Reich repetition. Structure: Repetitive melodic cells with phase shifting or additive rhythms. Harmony: Static diatonicism, very slow chord changes. Texture: Layered interlocking patterns, steady unvarying pulse.",
  ["Celtic"] = "Folk authenticity. Harmony: Mixolydian (Major with b7) or Dorian modes. Avoid V-I resolution; use VII-I. Bass: Open fifth drones. Rhythm: Triplets, compound meter (6/8, 12/8), ornamentation (grace notes) in melody.",
  ["Nordic"] = "Scandi-Noir icy sound. Harmony: Minor modes, open fifths, distant modulations. Texture: Raw/scratchy strings (sul ponticello), spacious piano, felt piano. Vibe: Cold, vast, 'less is more', silence as an instrument.",
  ["Slavic"] = "Deep emotional weight. Harmony: Harmonic Minor, fluctuating relative Major/Minor. Melody: Expressive, wide intervals (leaps), soulful. Texture: Rich, thick string writing, heavy vibrato, lower registers.",
  ["Middle Eastern"] = "Maqam suggestions. Harmony: Phrygian Dominant (Hijas) or double harmonic scales. Use pitch bends to simulate quarter tones. Texture: Heterophony (simultaneous variations of same melody), Drone bass, odd meters.",
  ["Asian"] = "Eastern aesthetics. Concept: 'Ma' (negative space/silence). Harmony: Pentatonic, Quartal stacks. Avoid leading tones. Texture: Sparse, distinct instrumental colors (plucked, breathy winds), pitch bending.",
  ["Latin"] = "Afro-Cuban rhythmic drive. Harmony: Montuno piano patterns, ii-V-I progressions. Rhythm: Clave compliance (3-2 or 2-3), anticipated bass (tumbao) acts as the heartbeat. Texture: Sharp attacks, syncopated layers.",
  ["Electronic"] = "Synth-based production. Harmony: Loop-friendly progressions (vi-IV-I-V). Texture: Arpeggiated lines, sidechain pumping (dynamic volume ducking), filter sweeps. Timbre: Sawtooth/Square waves, noise elements.",
  ["Hybrid"] = "Trailer Music style. Structure: 3-Act (Build-up -> Climax -> Outro). Harmony: Minor key, power chords, ostinatos. Sound Design: Braams (brass+synth blasts), Risers, heavy percussion mixed with orchestra."
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
  ["Heroic"] = "Confident and rising. Harmony: Major key, strong I-V-IV progressions. Melody: Ascending intervals (Perfect 4th/5th), triplets. Orchestration: Brass fanfares, horns in unison. Rhythm: March-like, dotted rhythms.",
  ["Epic"] = "Larger than life. Harmony: Slow harmonic rhythm, Power Chords (root+5th), chromatic mediants for drama. Rhythm: Driving ostinatos, heavy downbeats (Taiko/Timpani). Texture: Massive wall of sound, choir backing.",
  ["Triumphant"] = "Victory achieved. Harmony: Unambiguous Major resolution, Plagal Cadences (IV-I). Melody: Soaring high strings/brass. Rhythm: Steady, celebratory, strong finality.",
  ["Majestic"] = "Grand and stately. Tempo: Slow/Broad. Harmony: Rich voicings, full triads, avoiding dissonance. Rhythm: Deliberate, heavy, regal feel. Texture: Full orchestra playing tutti.",
  ["Adventurous"] = "Journey and motion. Harmony: Frequent modulations, Lydian mode (raised 4th) for wonder. Melody: Rapid scalar runs, agile woodwinds/strings. Rhythm: Propulsive, forward momentum (fast 12/8 or 6/8).",
  ["Dramatic"] = "Conflict and contrast. Harmony: Diminished 7ths, Neapolitan chords (bII), abrupt key changes. Dynamics: Sudden sfz accents, extreme swells. Texture: Heavy interaction between sections.",
  ["Intense"] = "High stakes focus. Rhythm: Relentless 16th notes (moto perpetuo). Harmony: Pedal points with shifting dissonance above. Texture: Busy, frantic, no rest.",
  ["Suspense"] = "Waiting for the unknown. Harmony: Unresolved chords, Half-Diminished, Tritones. Texture: Tremolo strings, subtone brass, high clusters. Rhythm: Unpredictable, sparse, heartbeat-like pulses.",
  ["Thriller"] = "Tension and chase. Bass: Pulse-pounding, steady. Harmony: Dissonant, bitonal (two keys at once), chromatic slips. Rhythm: Urgent, syncopated, metallic percussion.",
  ["Horror"] = "Pure fear. Techniques: Aleatoric (random) clusters, extended techniques (col legno, screeching). Harmony: Atonal, minor seconds, Tritone dominance. Dynamics: Extreme quiet to sudden loud.",
  ["Dark"] = "Shadowy atmosphere. Tessitura: Low register focus (Cellos, Bassoons, Trombones). Harmony: Minor modes (Aeolian/Locrian), minor chords moving by minor 3rds. Rhythm: Slow, dragging.",
  ["Ominous"] = "Threatening presence. Texture: Deep drones, distant rumbles. Harmony: Chromaticism, minor 2nd intervals. Rhythm: Slow, plodding, foreboding.",
  ["Foreboding"] = "Impending doom. Motif: Warning calls in brass. Harmony: Unstable, avoiding resolution, suspended chords that never resolve. Rhythm: Anticipatory.",
  ["Tragic"] = "Deep loss. Harmony: Minor key, descending chromatic bass lines (Lamento bass), Neapolitan 6th. Melody: Weeping, falling intervals. Tempo: Slow, heavy.",
  ["Melancholic"] = "Sad reflection. Melody: Expressive solo (Cello/Oboe), focus on minor 6th intervals. Harmony: Minor key, suspensions (4-3) creating 'sweet' sadness. Rhythm: Flowing, rubato.",
  ["Tender"] = "Gentle intimacy. Dynamics: Soft (p/pp). Harmony: Major key, consonant, simple triads. Texture: Warm pads, soft piano/harp. Rhythm: Lullaby-like, smooth.",
  ["Romantic"] = "Passion and love. Harmony: Lush extended chords (Maj7, add9, m7b5), chromatic appoggiaturas. Melody: Sweeping, large interval leaps, expressive swells. Rhythm: Flexible, push-and-pull (rubato).",
  ["Nostalgic"] = "Sepia-toned memories. Harmony: Major 7ths, I-iii-IV progressions, 'secondary' chords. Tone: Warm, slightly detuned or lo-fi aesthetic. Rhythm: Slow, reminiscent.",
  ["Passionate"] = "Overwhelming emotion. Dynamics: Wide swells (crescendo/decrescendo). Harmony: Intense chromaticism, climactic high points. Melody: Singing quality, high string ranges.",
  ["Longing"] = "Desire for the unreachable. Melody: Upward reaching lines that fall back. Harmony: Unresolved suspensions, Minor 7ths, Major 7ths. Vibe: Bittersweet.",
  ["Hopeful"] = "Optimism rising. Harmony: Progression from Minor to Relative Major. Melody: Rising lines, brightening orchestration. Rhythm: Steady forward motion, building energy.",
  ["Victorious"] = "Winning the battle. Similar to Heroic but with finality. Harmony: Strong V-I resolutions, fanfare motifs. Rhythm: Celebratory, syncopated accents.",
  ["Peaceful"] = "Calm stillness. Harmony: Diatonic, static, Pedal points. Texture: Sparse, avoiding clutter. Rhythm: Very slow harmonic changes, breath-like.",
  ["Serene"] = "Untroubled clarity. Instrumentation: High, clear sounds (Flute, Harp, Glockenspiel). Harmony: Pastel colors, simple Major triads. Rhythm: Gentle flow.",
  ["Dreamy"] = "Surreal softness. Harmony: Whole-tone scales, Augmented chords, blurring tonal centers. Texture: Harp glissandos, soft attacks. Rhythm: Floating, unmetered feel.",
  ["Ethereal"] = "Otherworldly. Harmony: Lydian mode (Major with #4), Major chords with sharp 11ths. Texture: High shimmering strings/choir, excessive reverb. Rhythm: Weightless.",
  ["Magical"] = "Wonder and awe. Harmony: Chromatic mediants (Major chords moving by 3rds), Lydian mode. Instrumentation: Celesta, Glockenspiel sparkles, woodwind runs. Texture: Swirling.",
  ["Mysterious"] = "The puzzle. Scale: Dorian #4 or Whole-tone. Texture: Hollow sounds, pizzicato, lack of root notes. Rhythm: Sneaky, tiptoeing, staccato.",
  ["Meditative"] = "Deep focus. Structure: Drone-based, minimal movement. Harmony: Root-5th-Octave purity. Rhythm: Extremely slow, cyclical, mantra-like.",
  ["Whimsical"] = "Quirky fun. Articulation: Staccato, Spiccato. Instrumentation: Woodwinds (Bassoon/Oboe), Pizzicato strings. Harmony: Unexpected shifts, Whole-tone snippets. Rhythm: Bouncy, odd meters, stop-and-go.",
  ["Playful"] = "Lighthearted. Rhythm: Bouncy 6/8 or Cut time. Harmony: Major key, simple functional progressions. Texture: Light percussion, pizzicato strings.",
  ["Energetic"] = "Full of life. Tempo: Fast. Rhythm: Strong subdivision, driving accents. Harmony: Simple, static but rhythmic. Texture: Busy accompaniment, fast runs.",
  ["Action"] = "Adrenaline. Rhythm: Driving 16ths, Ostinatos, Odd meters (5/4, 7/8). Harmony: Minor/Modal, dissonance for impact. Orchestration: Brass stabs, percussion hits.",
  ["Aggressive"] = "Hostility. Articulation: Marcato, accents. Harmony: Tritones, cluster chords, distortion. Rhythm: Hard hitting, syncopated, punctuated.",
  ["Fierce"] = "Wild savagery. Dynamics: fff. Range: Extreme highs and lows. Harmony: Clashing intervals, chromatic runs. Rhythm: Chaotic, fast, relentless.",
  ["Solemn"] = "Serious gravity. Tempo: Very slow (Largo). Harmony: Minor, Hymn-like, Plagal cadences. Texture: Low register, uniform movement (homophonic)."
}

M.DEFAULT_GENERATION_MOOD = "Heroic"

M.FALLBACK_FIELD_COUNT = 8

return M
