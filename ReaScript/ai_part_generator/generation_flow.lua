local const = require("ai_part_generator.constants")
local context = require("ai_part_generator.context")
local helpers = require("ai_part_generator.generation_helpers")
local http = require("ai_part_generator.http")
local midi = require("ai_part_generator.midi")
local profiles = require("ai_part_generator.profiles")
local utils = require("ai_part_generator.utils")
local apply_flow = require("ai_part_generator.apply_flow")

local M = {}

local pending = nil
local generation_starting = false

local function poll_generation()
  if not pending then
    return
  end
  local done, data, err = http.poll_response(pending.handle)
  if not done then
    reaper.defer(poll_generation)
    return
  end

  http.cleanup(pending.handle)
  local profile_id = pending.profile_id
  local profile = pending.profile
  local articulation_name = pending.articulation_name
  local target_track = pending.target_track
  local start_sec = pending.start_sec
  local end_sec = pending.end_sec
  local allow_tempo_changes = pending.allow_tempo_changes
  pending = nil

  if err then
    utils.log("AI Part Generator ERROR: " .. tostring(err))
    utils.show_error(err)
    return
  end

  if not data then
    utils.log("AI Part Generator ERROR: No data received from bridge")
    utils.show_error("No data received from bridge")
    return
  end

  utils.log("AI Part Generator: bridge response received.")
  utils.log("  notes: " .. tostring(data.notes and #data.notes or 0))
  utils.log("  cc_events: " .. tostring(data.cc_events and #data.cc_events or 0))
  utils.log("  keyswitches: " .. tostring(data.keyswitches and #data.keyswitches or 0))
  utils.log("  program_changes: " .. tostring(data.program_changes and #data.program_changes or 0))

  local tempo_markers = nil
  if allow_tempo_changes then
    tempo_markers = data.tempo_markers
  end

  apply_flow.begin_apply(data, profile_id, profile, articulation_name, target_track, start_sec, end_sec, tempo_markers, nil)
end

local function run_generation_after_bridge(state, profiles_by_id, start_sec, end_sec)
  if pending or apply_flow.is_in_progress() then
    utils.show_error(helpers.ERROR_GENERATION_IN_PROGRESS)
    return
  end

  local bpm, num, denom = helpers.get_bpm_and_timesig(start_sec)
  local target_track = nil
  if state.insert_target == const.INSERT_TARGET_NEW then
    target_track = midi.create_new_track()
  else
    target_track = context.get_last_selected_track()
    if not target_track then
      target_track = midi.get_active_track()
    end
    if not target_track then
      target_track = midi.create_new_track()
    end
  end
  if not target_track then
    utils.show_error("Failed to get target track.")
    return
  end
  utils.log("Target track: " .. utils.get_track_name(target_track))

  local profile = profiles_by_id[state.profile_id]
  if not profile then
    utils.show_error("Profile not found.")
    return
  end

  local ctx = context.build_context(state.use_selected_tracks, target_track, start_sec, end_sec)
  local key = helpers.resolve_key_from_state(state, start_sec, end_sec)
  local api_settings = helpers.build_api_settings(state)

  helpers.save_api_settings_extstate(state)
  profiles.save_track_settings(target_track, state)

  local request = helpers.build_request(
    start_sec,
    end_sec,
    bpm,
    num,
    denom,
    key,
    profile.id,
    state.articulation_name or "",
    state.generation_type or const.DEFAULT_GENERATION_TYPE,
    state.generation_style or const.DEFAULT_GENERATION_STYLE,
    state.prompt or "",
    ctx,
    api_settings,
    state.free_mode or false,
    state.allow_tempo_changes or false,
    nil,
    false,
    nil
  )

  utils.log("AI Part Generator: sending request to bridge.")
  local handle, err = http.begin_request(const.DEFAULT_BRIDGE_URL, request)
  if not handle then
    utils.show_error(err or "Bridge request failed.")
    return
  end
  utils.log("AI Part Generator: bridge request started (async).")
  pending = {
    handle = handle,
    profile_id = profile.id,
    profile = profile,
    target_track = target_track,
    start_sec = start_sec,
    end_sec = end_sec,
    articulation_name = state.articulation_name or "",
    allow_tempo_changes = state.allow_tempo_changes or false,
  }
  reaper.defer(poll_generation)
end

function M.run_generation(state, profiles_by_id)
  local start_sec, end_sec = helpers.get_time_selection_or_error()
  if not start_sec then
    return
  end
  if pending or apply_flow.is_in_progress() or generation_starting then
    utils.show_error(helpers.ERROR_GENERATION_IN_PROGRESS)
    return
  end

  local state_snapshot = {
    profile_id = state.profile_id,
    articulation_name = state.articulation_name,
    generation_type = state.generation_type,
    generation_style = helpers.combine_style(state.musical_style, state.generation_mood),
    musical_style = state.musical_style,
    generation_mood = state.generation_mood,
    free_mode = state.free_mode,
    prompt = state.prompt,
    use_selected_tracks = state.use_selected_tracks,
    insert_target = state.insert_target,
    key_mode = state.key_mode,
    key = state.key,
    allow_tempo_changes = state.allow_tempo_changes,
    api_provider = state.api_provider,
    api_key = state.api_key,
    api_base_url = state.api_base_url,
    model_name = state.model_name,
  }

  generation_starting = true
  helpers.ensure_bridge_ready(function()
    generation_starting = false
    run_generation_after_bridge(state_snapshot, profiles_by_id, start_sec, end_sec)
  end, function(err)
    generation_starting = false
    if err then
      utils.show_error(err)
    end
  end)
end

function M.is_in_progress()
  return pending ~= nil or generation_starting
end

return M
