local const = require("ai_part_generator.constants")
local context = require("ai_part_generator.context")
local helpers = require("ai_part_generator.generation_helpers")
local http = require("ai_part_generator.http")
local midi = require("ai_part_generator.midi")
local profiles = require("ai_part_generator.profiles")
local utils = require("ai_part_generator.utils")
local apply_flow = require("ai_part_generator.apply_flow")
local compose_flow = require("ai_part_generator.compose_flow")
local generation_flow = require("ai_part_generator.generation_flow")

local M = {}

local arrange_state = nil
local arrange_source = nil

local LABEL = "Arrange"
local ROLE_UNKNOWN = helpers.UNKNOWN_ROLE

local function normalize_assignment_name(name)
  return tostring(name or ""):gsub("[%-%_%.%s]+", " "):gsub("^%s+", ""):gsub("%s+$", ""):lower()
end

local function matches_assignment(inst_name, track_norm, profile_norm)
  if inst_name == "" then
    return false
  end
  local inst_norm = normalize_assignment_name(inst_name)
  local inst_first_word = inst_norm:match("^(%w+)")
  local track_first_word = track_norm:match("^(%w+)")
  local profile_first_word = profile_norm:match("^(%w+)")

  if track_norm:find(inst_norm, 1, true) or inst_norm:find(track_norm, 1, true) then
    return true
  end
  if profile_norm:find(inst_norm, 1, true) or inst_norm:find(profile_norm, 1, true) then
    return true
  end
  if inst_first_word and (inst_first_word == track_first_word or inst_first_word == profile_first_word) then
    return true
  end
  return false
end

local function set_arrange_source(item)
  if not item or not reaper.ValidatePtr(item, "MediaItem*") then
    arrange_source = nil
    return false
  end

  local take = reaper.GetActiveTake(item)
  if not take or not reaper.TakeIsMIDI(take) then
    utils.show_error("Selected item is not a MIDI item.")
    arrange_source = nil
    return false
  end

  local track = reaper.GetMediaItem_Track(item)
  local track_name = utils.get_track_name(track)
  local notes, cc_events = midi.read_item_notes(item, const.MAX_SKETCH_NOTES)

  if #notes == 0 then
    utils.show_error("No notes found in selected MIDI item.")
    arrange_source = nil
    return false
  end

  arrange_source = {
    item = item,
    track = track,
    track_name = track_name,
    notes = notes,
    cc_events = cc_events,
  }

  utils.log(string.format("Arrange source set: '%s' with %d notes", track_name, #notes))
  return true
end

local function clear_arrange_source()
  arrange_source = nil
  utils.log("Arrange source cleared")
end

local function get_arrange_source()
  if arrange_source and arrange_source.item then
    if not reaper.ValidatePtr(arrange_source.item, "MediaItem*") then
      arrange_source = nil
      return nil
    end
  end
  return arrange_source
end

local function apply_arrange_result_and_continue()
  if not arrange_state then
    return
  end

  if apply_flow.is_in_progress() then
    reaper.defer(apply_arrange_result_and_continue)
    return
  end

  local current = arrange_state.pending_apply
  if current then
    utils.log(string.format("Arrange: applying results for '%s' (%d/%d)",
      current.track_name, arrange_state.current_index, arrange_state.total_tracks))

    local tempo_markers = nil
    if arrange_state.allow_tempo_changes and not arrange_state.tempo_applied then
      if type(current.response.tempo_markers) == "table" and #current.response.tempo_markers > 0 then
        tempo_markers = current.response.tempo_markers
        arrange_state.tempo_applied = true
      end
    end

    local on_tempo_applied = function(new_bpm)
      if new_bpm then
        arrange_state.bpm = new_bpm
      end
    end

    apply_flow.begin_apply(current.response, current.profile_id, current.profile, current.articulation_name, current.target_track,
      arrange_state.start_sec, arrange_state.end_sec, tempo_markers, on_tempo_applied, true)

    helpers.append_generated_part(arrange_state.generated_parts, current)

    arrange_state.pending_apply = nil
    reaper.defer(apply_arrange_result_and_continue)
    return
  end

  arrange_state.current_index = arrange_state.current_index + 1
  if arrange_state.current_index > arrange_state.total_tracks then
    utils.log("Arrange: ALL COMPLETE!")
    helpers.apply_deferred_tempo_markers_if_allowed(arrange_state, LABEL)

    arrange_state = nil
    return
  end

  reaper.defer(start_next_arrange_generation)
end

local function poll_arrange_generation()
  if not arrange_state or not arrange_state.current_handle then
    return
  end

  local done, data, err = http.poll_response(arrange_state.current_handle)
  if not done then
    reaper.defer(poll_arrange_generation)
    return
  end

  http.cleanup(arrange_state.current_handle)
  arrange_state.current_handle = nil

  local current_track = arrange_state.tracks[arrange_state.current_index]

  if err then
    utils.log(string.format("Arrange ERROR for '%s': %s", current_track.name, tostring(err)))
    arrange_state.current_index = arrange_state.current_index + 1
    if arrange_state.current_index <= arrange_state.total_tracks then
      reaper.defer(start_next_arrange_generation)
    else
      arrange_state = nil
    end
    return
  end

  if data then
    utils.log(string.format("Arrange: response for '%s' - notes=%d, cc=%d",
      current_track.name,
      data.notes and #data.notes or 0,
      data.cc_events and #data.cc_events or 0))

    arrange_state.pending_apply = {
      response = data,
      profile_id = current_track.profile.id,
      profile_name = current_track.profile.name,
      profile = current_track.profile,
      target_track = current_track.track,
      track_name = current_track.name,
      role = current_track.role,
      articulation_name = arrange_state.current_articulation_name or "",
    }

    reaper.defer(apply_arrange_result_and_continue)
  end
end

function start_next_arrange_generation()
  if not arrange_state then
    return
  end

  if arrange_state.current_index > arrange_state.total_tracks then
    utils.log("Arrange: generation complete!")
    arrange_state = nil
    return
  end

  local current_track = arrange_state.tracks[arrange_state.current_index]
  local profile = current_track.profile

  utils.log(string.format("Arrange: generating %d/%d '%s' (role: %s)",
    arrange_state.current_index, arrange_state.total_tracks,
    current_track.name, current_track.role or ROLE_UNKNOWN))

  local articulation_name = profiles.get_default_articulation(profile)
  arrange_state.current_articulation_name = articulation_name
  local ctx = context.build_context(arrange_state.use_selected_tracks, current_track.track,
    arrange_state.start_sec, arrange_state.end_sec)

  local assignment = nil
  if arrange_state.arrangement_assignments then
    local track_norm = normalize_assignment_name(current_track.name)
    local profile_norm = normalize_assignment_name(profile.name)
    local family_lower = (profile.family or ""):lower()

    for _, a in ipairs(arrange_state.arrangement_assignments) do
      local inst_name = (a.instrument or ""):lower()
      if matches_assignment(inst_name, track_norm, profile_norm) then
        assignment = a
        utils.log(string.format("Arrange: matched assignment '%s' for track '%s'", a.instrument or "", current_track.name))
        break
      end
    end

    if not assignment then
      utils.log(string.format("Arrange: WARNING - no assignment found for '%s' (profile: '%s', family: '%s')",
        current_track.name, profile.name, family_lower))
    end
  end

  local ensemble_info = {
    total_instruments = arrange_state.total_tracks,
    instruments = arrange_state.ensemble_instruments,
    shared_prompt = arrange_state.prompt,
    plan_summary = arrange_state.plan_summary or "",
    plan = arrange_state.plan,
    current_instrument_index = arrange_state.current_index,
    current_instrument = {
      track_name = current_track.name,
      profile_name = profile.name,
      family = profile.family or helpers.UNKNOWN_ROLE,
      role = current_track.role,
    },
    generation_order = arrange_state.current_index,
    is_sequential = true,
    previously_generated = arrange_state.generated_parts,
    arrangement_mode = true,
    source_sketch = {
      track_name = arrange_state.source_sketch.track_name,
      notes = arrange_state.source_sketch.notes,
    },
    arrangement_assignment = assignment,
  }

  local combined_style, final_prompt = helpers.build_style_prompt(arrange_state, arrange_state.prompt)

  local request = helpers.build_request(
    arrange_state.start_sec,
    arrange_state.end_sec,
    arrange_state.bpm,
    arrange_state.num,
    arrange_state.denom,
    arrange_state.key,
    profile.id,
    articulation_name,
    nil,
    combined_style,
    final_prompt,
    ctx,
    arrange_state.api_settings,
    arrange_state.free_mode,
    arrange_state.allow_tempo_changes or false,
    ensemble_info,
    false,
    arrange_state.original_bpm,
    arrange_state.length_bars
  )

  helpers.ensure_bridge_ready(function()
    if not arrange_state then
      return
    end
    local handle, err = http.begin_request(const.DEFAULT_BRIDGE_URL, request)
    if not handle then
      utils.log(string.format("Arrange: failed to start request for '%s': %s", current_track.name, tostring(err)))
      arrange_state.current_index = arrange_state.current_index + 1
      reaper.defer(start_next_arrange_generation)
      return
    end

    arrange_state.current_handle = handle
    reaper.defer(poll_arrange_generation)
  end, function(err)
    if not arrange_state then
      return
    end
    utils.log(string.format("Arrange: failed to start request for '%s': %s", current_track.name, tostring(err)))
    arrange_state.current_index = arrange_state.current_index + 1
    reaper.defer(start_next_arrange_generation)
  end)
end

local function poll_arrange_plan()
  if not arrange_state or not arrange_state.plan_handle then
    return
  end

  local done, data, err = http.poll_response(arrange_state.plan_handle)
  if not done then
    reaper.defer(poll_arrange_plan)
    return
  end

  http.cleanup(arrange_state.plan_handle)
  arrange_state.plan_handle = nil

  if err then
    utils.log("Arrange plan ERROR: " .. tostring(err))
    arrange_state = nil
    utils.show_error("Arrange planning failed: " .. tostring(err))
    return
  end

  if data then
    arrange_state.plan_summary = data.plan_summary or ""
    arrange_state.plan = data.plan
    arrange_state.arrangement_assignments = data.arrangement_assignments or {}
    utils.log("Arrange: plan received with " .. #arrange_state.arrangement_assignments .. " assignments")

    for i, a in ipairs(arrange_state.arrangement_assignments) do
      utils.log(string.format("  Assignment %d: instrument='%s', role='%s', verbatim='%s'",
        i, a.instrument or "?", a.role or "?", a.verbatim_level or "?"))
    end

    helpers.apply_plan_tempo_if_allowed(arrange_state, LABEL)

    if arrange_state.plan_summary ~= "" then
      utils.log("Arrange plan summary: " .. arrange_state.plan_summary)
    end

    if arrange_state.arrangement_assignments and #arrange_state.arrangement_assignments > 0 then
      for _, track_data in ipairs(arrange_state.tracks) do
        for _, assignment in ipairs(arrange_state.arrangement_assignments) do
          local inst_name = (assignment.instrument or ""):lower()
          local track_name_lower = (track_data.name or ""):lower()
          local profile_name_lower = (track_data.profile and track_data.profile.name or ""):lower()
          if inst_name ~= "" and (track_name_lower:find(inst_name, 1, true) or profile_name_lower:find(inst_name, 1, true) or inst_name:find(track_name_lower, 1, true)) then
            track_data.role = assignment.role or ROLE_UNKNOWN
            break
          end
        end
      end
    end
  end

  reaper.defer(start_next_arrange_generation)
end

local function start_arrange_plan()
  if not arrange_state then
    return
  end

  if arrange_state.plan_handle then
    return
  end

  utils.log("Arrange: starting plan phase")

  local target_instruments = {}
  for i, track_data in ipairs(arrange_state.tracks) do
    table.insert(target_instruments, {
      index = i,
      track_name = track_data.name,
      profile_id = track_data.profile.id,
      profile_name = track_data.profile.name,
      family = track_data.profile.family or helpers.UNKNOWN_ROLE,
      role = ROLE_UNKNOWN,
      range = track_data.profile.range or {},
    })
  end

  local provider, model_name, base_url, api_key = helpers.resolve_model_config(arrange_state.api_settings, {
    use_plan_model = true,
    use_openrouter_base_url = true,
  })

  utils.log(string.format("Arrange: using plan model '%s'", model_name))

  local _, prompt_with_style = helpers.build_style_prompt(arrange_state, arrange_state.prompt)

  local request = {
    time = { start_sec = arrange_state.start_sec, end_sec = arrange_state.end_sec, length_bars = arrange_state.length_bars },
    music = { bpm = arrange_state.bpm, time_sig = string.format(helpers.TIME_SIG_FORMAT, arrange_state.num, arrange_state.denom), key = arrange_state.key },
    source_sketch = {
      track_name = arrange_state.source_sketch.track_name,
      notes = arrange_state.source_sketch.notes,
      cc_events = arrange_state.source_sketch.cc_events or {},
    },
    target_instruments = target_instruments,
    user_prompt = prompt_with_style,
    model = {
      provider = provider,
      model_name = model_name,
      temperature = const.DEFAULT_MODEL_TEMPERATURE,
      base_url = base_url,
      api_key = api_key,
    },
  }

  helpers.ensure_bridge_ready(function()
    if not arrange_state then
      return
    end
    local handle, err = http.begin_request(const.BRIDGE_ARRANGE_PLAN_URL, request)
    if not handle then
      utils.log("Arrange: plan request failed: " .. tostring(err))
      arrange_state = nil
      utils.show_error("Arrange plan request failed: " .. tostring(err))
      return
    end

    arrange_state.plan_handle = handle
    reaper.defer(poll_arrange_plan)
  end, function(err)
    if not arrange_state then
      return
    end
    utils.log("Arrange: plan request failed: " .. tostring(err))
    arrange_state = nil
    utils.show_error("Arrange plan request failed: " .. tostring(err))
  end)
end

function M.run_arrange(state, profile_list, profiles_by_id)
  local start_sec, end_sec = helpers.get_time_selection_or_error()
  if not start_sec then
    return
  end

  if generation_flow.is_in_progress() or apply_flow.is_in_progress() or compose_flow.is_in_progress() or arrange_state then
    utils.show_error(helpers.ERROR_GENERATION_IN_PROGRESS)
    return
  end

  local source = get_arrange_source()
  if not source or not source.notes or #source.notes == 0 then
    utils.show_error("No arrange source set. Select a MIDI item and click 'Set as Source'.")
    return
  end

  local tracks_with_profiles = profiles.get_selected_tracks_with_profiles(profile_list, profiles_by_id)

  if #tracks_with_profiles == 0 then
    utils.show_error("No target tracks selected.")
    return
  end

  local valid_tracks, skipped = helpers.filter_tracks_with_profiles(tracks_with_profiles, { exclude_track = source.track })
  if #valid_tracks == 0 then
    local msg = "No valid target tracks found (excluding source track)."
    if #skipped > 0 then
      msg = msg .. "\nUnmatched: " .. table.concat(skipped, ", ")
    end
    utils.show_error(msg)
    return
  end

  for _, track_data in ipairs(valid_tracks) do
    track_data.role = ROLE_UNKNOWN
  end

  utils.log(string.format("Arrange: source='%s' (%d notes), %d target tracks",
    source.track_name, #source.notes, #valid_tracks))
  for i, td in ipairs(valid_tracks) do
    utils.log(string.format("  %d. '%s' -> '%s'", i, td.name, td.profile.name))
  end

  local bpm, num, denom = helpers.get_bpm_and_timesig(start_sec)
  local length_bars = helpers.calculate_length_bars(start_sec, end_sec, num, denom)

  local key = helpers.resolve_key_from_state(state, start_sec, end_sec)
  local api_settings = helpers.build_api_settings(state)
  local ensemble_instruments = helpers.build_ensemble_instruments_from_tracks(valid_tracks)

  arrange_state = {
    tracks = valid_tracks,
    total_tracks = #valid_tracks,
    current_index = 1,
    current_handle = nil,
    pending_apply = nil,
    generated_parts = {},
    plan_handle = nil,
    plan_summary = "",
    plan = nil,
    arrangement_assignments = {},
    source_sketch = {
      track_name = source.track_name,
      notes = source.notes,
      cc_events = source.cc_events or {},
    },
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
  }

  helpers.save_api_settings_extstate(state)
  start_arrange_plan()
end

function M.is_in_progress()
  return arrange_state ~= nil
end

function M.get_progress()
  if not arrange_state then
    return nil
  end
  return {
    current = arrange_state.current_index,
    total = arrange_state.total_tracks,
    current_track = arrange_state.tracks[arrange_state.current_index] and
                    arrange_state.tracks[arrange_state.current_index].name or "",
    source_track = arrange_state.source_sketch and arrange_state.source_sketch.track_name or "",
  }
end

function M.set_arrange_source(item)
  return set_arrange_source(item)
end

function M.clear_arrange_source()
  clear_arrange_source()
end

function M.get_arrange_source()
  return get_arrange_source()
end

return M
