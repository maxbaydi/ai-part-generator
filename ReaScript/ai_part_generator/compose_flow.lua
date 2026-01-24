local const = require("ai_part_generator.constants")
local context = require("ai_part_generator.context")
local helpers = require("ai_part_generator.generation_helpers")
local http = require("ai_part_generator.http")
local profiles = require("ai_part_generator.profiles")
local utils = require("ai_part_generator.utils")
local apply_flow = require("ai_part_generator.apply_flow")
local generation_flow = require("ai_part_generator.generation_flow")

local M = {}

local compose_state = nil

local LABEL = "Compose"
local ROLE_UNKNOWN = helpers.UNKNOWN_ROLE

local function apply_compose_result_and_continue()
  if not compose_state then
    return
  end

  if apply_flow.is_in_progress() then
    reaper.defer(apply_compose_result_and_continue)
    return
  end

  local current = compose_state.pending_apply
  if current then
    utils.log(string.format("Compose: applying results for '%s' (%d/%d)",
      current.track_name, compose_state.current_index, compose_state.total_tracks))

    local on_tempo_applied = function(new_bpm)
      if compose_state and new_bpm then
        compose_state.bpm = new_bpm
        utils.log("Compose: BPM updated to " .. tostring(new_bpm))
      end
    end

    apply_flow.begin_apply(current.response, current.profile_id, current.profile, current.articulation_name, current.target_track,
      compose_state.start_sec, compose_state.end_sec, current.tempo_markers, on_tempo_applied, true)

    helpers.append_generated_part(compose_state.generated_parts, current)

    compose_state.pending_apply = nil
    reaper.defer(apply_compose_result_and_continue)
    return
  end

  compose_state.current_index = compose_state.current_index + 1
  if compose_state.current_index > compose_state.total_tracks then
    utils.log("Compose: ALL COMPLETE!")
    helpers.apply_deferred_tempo_markers_if_allowed(compose_state, LABEL)

    compose_state = nil
    return
  end

  reaper.defer(start_next_compose_generation)
end

local function poll_compose_plan()
  if not compose_state or not compose_state.plan_handle then
    return
  end

  local done, data, err = http.poll_response(compose_state.plan_handle)
  if not done then
    reaper.defer(poll_compose_plan)
    return
  end

  http.cleanup(compose_state.plan_handle)
  compose_state.plan_handle = nil

  if err then
    utils.log("Compose plan ERROR: " .. tostring(err))
    reaper.defer(start_next_compose_generation)
    return
  end

  if data then
    compose_state.plan_summary = data.plan_summary or ""
    compose_state.plan = data.plan
    utils.log("Compose: plan received.")
    if compose_state.plan_summary ~= "" then
      utils.log("Compose plan summary: " .. compose_state.plan_summary)
    end

    helpers.apply_plan_tempo_if_allowed(compose_state, LABEL)

    local ordered, applied = helpers.apply_plan_order(compose_state.plan, compose_state.tracks)
    if applied then
      compose_state.tracks = ordered
      compose_state.total_tracks = #ordered
      compose_state.ensemble_instruments = helpers.build_ensemble_instruments_from_tracks(ordered)
      compose_state.current_index = 1
      utils.log("Compose: generation order set from plan.")
    end
  end

  reaper.defer(start_next_compose_generation)
end

local function start_compose_plan()
  if not compose_state then
    return
  end

  if compose_state.plan_handle then
    return
  end

  local first_track = compose_state.tracks[1]
  if not first_track then
    reaper.defer(start_next_compose_generation)
    return
  end

  utils.log("Compose: planning step (free mode).")

  local plan_ctx = context.build_context(
    compose_state.use_selected_tracks,
    nil,
    compose_state.start_sec,
    compose_state.end_sec
  )

  local ensemble_info = {
    total_instruments = compose_state.total_tracks,
    instruments = compose_state.ensemble_instruments,
    shared_prompt = compose_state.prompt,
    current_instrument_index = 0,
    current_instrument = nil,
    generation_order = 0,
    is_sequential = true,
    previously_generated = {},
  }

  local combined_style, final_prompt = helpers.build_style_prompt(compose_state, compose_state.prompt)

  local request = helpers.build_request(
    compose_state.start_sec,
    compose_state.end_sec,
    compose_state.bpm,
    compose_state.num,
    compose_state.denom,
    compose_state.key,
    first_track.profile.id,
    "",
    nil,
    combined_style,
    final_prompt,
    plan_ctx,
    compose_state.api_settings,
    compose_state.free_mode,
    false,
    ensemble_info,
    true,
    nil,
    compose_state.length_bars
  )

  utils.log(string.format("Compose: using plan model '%s'", request.model.model_name))

  helpers.ensure_bridge_ready(function()
    if not compose_state then
      return
    end
    local handle, err = http.begin_request(const.BRIDGE_PLAN_URL, request)
    if not handle then
      utils.log("Compose: plan request failed: " .. tostring(err))
      reaper.defer(start_next_compose_generation)
      return
    end

    compose_state.plan_handle = handle
    reaper.defer(poll_compose_plan)
  end, function(err)
    if not compose_state then
      return
    end
    utils.log("Compose: plan request failed: " .. tostring(err))
    reaper.defer(start_next_compose_generation)
  end)
end

local function poll_compose_generation()
  if not compose_state or not compose_state.current_handle then
    return
  end

  local done, data, err = http.poll_response(compose_state.current_handle)
  if not done then
    reaper.defer(poll_compose_generation)
    return
  end

  http.cleanup(compose_state.current_handle)
  compose_state.current_handle = nil

  local current_track = compose_state.tracks[compose_state.current_index]

  if err then
    utils.log(string.format("Compose ERROR for '%s': %s", current_track.name, tostring(err)))
    compose_state.current_index = compose_state.current_index + 1
    if compose_state.current_index <= compose_state.total_tracks then
      reaper.defer(start_next_compose_generation)
    else
      compose_state = nil
    end
    return
  end

  if data then
    utils.log(string.format("Compose: response for '%s' - notes=%d, cc=%d",
      current_track.name,
      data.notes and #data.notes or 0,
      data.cc_events and #data.cc_events or 0))

    local tempo_markers = nil
    if compose_state.allow_tempo_changes and not compose_state.tempo_applied then
      if type(data.tempo_markers) == "table" and #data.tempo_markers > 0 then
        compose_state.deferred_tempo_markers = data.tempo_markers
        compose_state.tempo_applied = true
        utils.log("Compose: received tempo markers (deferred until end)")
      end
    end

    if data.extracted_motif and not compose_state.generated_motif then
      compose_state.generated_motif = data.extracted_motif
      utils.log(string.format("Compose: motif extracted from '%s' with %d notes",
        current_track.name,
        data.extracted_motif.notes and #data.extracted_motif.notes or 0))
    end

    compose_state.pending_apply = {
      response = data,
      profile_id = current_track.profile.id,
      profile_name = current_track.profile.name,
      profile = current_track.profile,
      target_track = current_track.track,
      track_name = current_track.name,
      role = current_track.role,
      articulation_name = compose_state.current_articulation_name or "",
      tempo_markers = tempo_markers,
    }

    reaper.defer(apply_compose_result_and_continue)
  end
end

function start_next_compose_generation()
  if not compose_state then
    return
  end

  if compose_state.current_index > compose_state.total_tracks then
    utils.log("Compose: generation complete!")
    compose_state = nil
    return
  end

  local current_track = compose_state.tracks[compose_state.current_index]
  local profile = current_track.profile

  utils.log(string.format("Compose: generating %d/%d '%s' (role: %s)",
    compose_state.current_index, compose_state.total_tracks,
    current_track.name, current_track.role or ROLE_UNKNOWN))

  local articulation_name = profiles.get_default_articulation(profile)
  compose_state.current_articulation_name = articulation_name
  local ctx = context.build_context(compose_state.use_selected_tracks, current_track.track,
    compose_state.start_sec, compose_state.end_sec)

  local ensemble_info = {
    total_instruments = compose_state.total_tracks,
    instruments = compose_state.ensemble_instruments,
    shared_prompt = compose_state.prompt,
    plan_summary = compose_state.plan_summary or "",
    plan = compose_state.plan,
    current_instrument_index = compose_state.current_index,
    current_instrument = {
      track_name = current_track.name,
      profile_name = profile.name,
      family = profile.family or helpers.UNKNOWN_ROLE,
      role = current_track.role,
    },
    generation_order = compose_state.current_index,
    is_sequential = true,
    previously_generated = compose_state.generated_parts,
    generated_motif = compose_state.generated_motif,
  }

  local combined_style, final_prompt = helpers.build_style_prompt(compose_state, compose_state.prompt)

  local request = helpers.build_request(
    compose_state.start_sec,
    compose_state.end_sec,
    compose_state.bpm,
    compose_state.num,
    compose_state.denom,
    compose_state.key,
    profile.id,
    articulation_name,
    nil,
    combined_style,
    final_prompt,
    ctx,
    compose_state.api_settings,
    compose_state.free_mode,
    compose_state.allow_tempo_changes or false,
    ensemble_info,
    false,
    compose_state.original_bpm,
    compose_state.length_bars
  )

  helpers.ensure_bridge_ready(function()
    if not compose_state then
      return
    end
    local handle, err = http.begin_request(const.DEFAULT_BRIDGE_URL, request)
    if not handle then
      utils.log(string.format("Compose: failed to start request for '%s': %s", current_track.name, tostring(err)))
      compose_state.current_index = compose_state.current_index + 1
      reaper.defer(start_next_compose_generation)
      return
    end

    compose_state.current_handle = handle
    reaper.defer(poll_compose_generation)
  end, function(err)
    if not compose_state then
      return
    end
    utils.log(string.format("Compose: failed to start request for '%s': %s", current_track.name, tostring(err)))
    compose_state.current_index = compose_state.current_index + 1
    reaper.defer(start_next_compose_generation)
  end)
end

function M.run_compose(state, profile_list, profiles_by_id)
  local start_sec, end_sec = helpers.get_time_selection_or_error()
  if not start_sec then
    return
  end

  if generation_flow.is_in_progress() or apply_flow.is_in_progress() or compose_state then
    utils.show_error(helpers.ERROR_GENERATION_IN_PROGRESS)
    return
  end

  local tracks_with_profiles = profiles.get_selected_tracks_with_profiles(profile_list, profiles_by_id)

  if #tracks_with_profiles == 0 then
    utils.show_error("No tracks selected.")
    return
  end

  local valid_tracks, skipped = helpers.filter_tracks_with_profiles(tracks_with_profiles)
  if #valid_tracks == 0 then
    local msg = "Could not determine profiles for selected tracks."
    if #skipped > 0 then
      msg = msg .. "\nUnmatched: " .. table.concat(skipped, ", ")
    end
    utils.show_error(msg)
    return
  end

  local sorted_tracks = {}
  for _, track_data in ipairs(valid_tracks) do
    track_data.role = ROLE_UNKNOWN
    table.insert(sorted_tracks, track_data)
  end

  utils.log(string.format("Compose: %d tracks (plan will define order)", #sorted_tracks))
  for i, td in ipairs(sorted_tracks) do
    utils.log(string.format("  %d. '%s' -> '%s' (role: %s)", i, td.name, td.profile.name, td.role or ROLE_UNKNOWN))
  end

  local bpm, num, denom = helpers.get_bpm_and_timesig(start_sec)
  local length_bars = helpers.calculate_length_bars(start_sec, end_sec, num, denom)

  local key = helpers.resolve_key_from_state(state, start_sec, end_sec)
  local api_settings = helpers.build_api_settings(state)
  local ensemble_instruments = helpers.build_ensemble_instruments_from_tracks(sorted_tracks)

  compose_state = {
    tracks = sorted_tracks,
    total_tracks = #sorted_tracks,
    current_index = 1,
    current_handle = nil,
    pending_apply = nil,
    generated_parts = {},
    generated_motif = nil,
    plan_handle = nil,
    plan_summary = "",
    plan = nil,
    start_sec = start_sec,
    end_sec = end_sec,
    length_bars = length_bars,
    bpm = bpm,
    original_bpm = bpm,
    num = num,
    denom = denom,
    key = key,
    api_settings = api_settings,
    ensemble_instruments = ensemble_instruments,
    prompt = state.prompt or "",
    musical_style = state.musical_style,
    generation_mood = state.generation_mood,
    use_style_mood = state.use_style_mood,
    free_mode = state.free_mode,
    use_selected_tracks = state.use_selected_tracks,
    allow_tempo_changes = state.allow_tempo_changes or false,
    tempo_applied = false,
    deferred_tempo_markers = nil,
  }

  helpers.save_api_settings_extstate(state)
  start_compose_plan()
end

function M.is_in_progress()
  return compose_state ~= nil
end

function M.get_progress()
  if not compose_state then
    return nil
  end
  return {
    current = compose_state.current_index,
    total = compose_state.total_tracks,
    current_track = compose_state.tracks[compose_state.current_index] and
                    compose_state.tracks[compose_state.current_index].name or "",
  }
end

return M
