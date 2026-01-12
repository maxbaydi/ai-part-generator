# AI Part Generator for REAPER

AI Part Generator is a ReaScript that generates and arranges MIDI parts within a selected range using AI. The script operates via a local Python bridge and a set of instrument profiles.

## Features
- Generate a single part based on selected profile, type, style, and mood.
- Arrange: Orchestration from a MIDI sketch (distributing material to multiple instruments).
- Compose: Multi-track generation from scratch (without a source sketch).
- Prompt Enhancer: Expands text prompts considering context and instruments.
- Instrument profiles with articulations (CC/keyswitch/none), channels, and ranges.
- Context from selected MIDI items and horizontal context surrounding the selection.
- Key detection and optional tempo/time signature changes.

## Requirements
- REAPER with ReaScript support.
- ReaImGui for the full interface (a simplified dialog is used without it).
- Python and bridge dependencies: `fastapi`, `uvicorn`.
- Model access:
  - Local (LM Studio) via OpenAI-compatible API.
  - OpenRouter (requires API key).
- HTTP client: `curl` (if available) or PowerShell on Windows.

## Installation
1) Copy the `ReaScript`, `Profiles`, and `bridge` folders next to each other. The script searches for profiles in `../Profiles` relative to `ReaScript`.

Example structure:
```
AI Part Generator/
  Profiles/
    *.json
  ReaScript/
    AI Part Generator.lua
    ai_part_generator/
    vendor/
  bridge/
```

2) In REAPER: `Actions` -> `Show action list` -> `ReaScript: Load...` -> select `ReaScript/AI Part Generator.lua`.

3) ReaImGui (for full UI):
   - Distributed via ReaPack (see ReaImGui repository).
   - If building from source, ReaImGui's README lists steps via Meson:
     ```
     meson setup build
     cd build
     ninja
     meson install --tags runtime
     ```

4) Install Python bridge dependencies:
```
python -m pip install -r bridge/requirements.txt
```

5) Start the bridge (or let the script do it automatically):
```
bridge/start.ps1    # Windows
bridge/start.sh     # macOS/Linux
```

If Python is not in PATH, you can set the `AI_PART_GENERATOR_PYTHON` variable in `start.ps1`/`start.sh`.

## Quick Start (Generate)
1) In REAPER, make a time selection.
2) Select a MIDI track and run the script.
3) In the `Generate` tab: select profile, type, style, and mood (or enable Free Mode).
4) Optionally check `Use Selected Items as Context` after selecting relevant MIDI items.
5) Click `GENERATE PART`.

## Modes
### Generate (Single Part)
Suitable for quickly creating melodies, basslines, pads, or rhythms on the active track (or a new track - toggle `Insert To`).

### Arrange (From Sketch)
1) Select a MIDI item with the sketch and click `Set Selected Item as Source`.
2) Select target tracks (at least one, excluding the source track).
3) Manually select instrument profiles in the table if needed.
4) Click `ARRANGE (From Source)`.

### Compose (From Scratch)
1) Select 2+ tracks to generate an ensemble.
2) Click `COMPOSE (Scratch)`.
3) The script first builds a plan, then generates parts sequentially.

### Prompt Enhancer
How to use: enter a prompt and click `Enhance Prompt with AI`. The prompt will be expanded considering tempo, key, and selected instruments.

## API Settings (Settings Tab)
- Provider: `Local (LM Studio)` or `OpenRouter (Cloud)`.
- Base URL: default `http://127.0.0.1:1234/v1` (local) or `https://openrouter.ai/api/v1`.
- Model Name: set a model available in your provider.
- API Key: required only for OpenRouter.

## Instrument Profiles
Profiles are located in `Profiles/*.json`. They describe the instrument, ranges, MIDI channel, and articulations. The script:
- Automatically matches a profile based on the track name,
- Saves the selected profile to a track attribute,
- Uses articulations and controllers for correct generation.

Check examples:
- `Profiles/Cello - CSS.json`
- `Profiles/Drums - GM.json`
- `Profiles/Bass - EZBass.json`

## Scenarios
- **Need a quick idea:** enable Free Mode, enter a short prompt, click `GENERATE PART`.
- **Have harmony/rhythm on other tracks:** select those MIDI items and keep `Use Selected Items as Context` checked.
- **Have a piano sketch:** use `Arrange` and distribute material across instruments.
- **Want an ensemble from scratch:** select 2+ tracks and use `Compose`.
- **Need stable tempo:** keep `Allow Tempo Changes` disabled.
- **Need expressive tempo/time sig changes:** enable `Allow Tempo/Time Sig Changes` and check results.

## Common Issues
- **"No time selection set."** - Set a Time Selection.
- **"No profiles found in Profiles/ directory."** - Check folder structure.
- **"ReaImGui not found..."** - Install ReaImGui or use the simplified dialog.
- **"Bridge dependencies not found (fastapi/uvicorn)."** - Run `python -m pip install -r bridge/requirements.txt`.
- **"Bridge server did not start..."** - Run `bridge/start.ps1` or `bridge/start.sh` manually.
- **"No arrange source set..."** - Select a MIDI item and click `Set Selected Item as Source`.
