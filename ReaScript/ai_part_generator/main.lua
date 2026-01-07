local const = require("ai_part_generator.constants")
local context = require("ai_part_generator.context")
local http = require("ai_part_generator.http")
local key_detect = require("ai_part_generator.key_detect")
local midi = require("ai_part_generator.midi")
local profiles = require("ai_part_generator.profiles")
local ui = require("ai_part_generator.ui")
local utils = require("ai_part_generator.utils")

local M = {}

local pending = nil
local apply_state = nil
local compose_state = nil

local ROLE_PRIORITY = {
  melody = 1,
  lead = 1,
  bass = 2,
  rhythm = 3,
  harmony = 4,
  accompaniment = 5,
  pad = 6,
  fill = 7,
}

local FAMILY_DEFAULT_ROLE = {
  brass = "melody",
  woodwinds = "melody",
  strings = "harmony",
  bass = "bass",
  drums = "rhythm",
}

local function detect_instrument_role(track_name, profile, prompt)
  local name_lower = (track_name or ""):lower()
  local prompt_lower = (prompt or ""):lower()
  local family = (profile.family or ""):lower()
  
  if prompt_lower:find("мелод") or prompt_lower:find("melody") or prompt_lower:find("тем") or prompt_lower:find("theme") then
    if name_lower:find(family) or prompt_lower:find(family) then
      if prompt_lower:find(family) and prompt_lower:find("мелод") then
        return "melody"
      end
    end
  end
  
  if prompt_lower:find("аккомпан") or prompt_lower:find("accomp") or prompt_lower:find("гармон") or prompt_lower:find("harmony") then
    if name_lower:find(family) or prompt_lower:find(family) then
      if prompt_lower:find(family) and (prompt_lower:find("аккомпан") or prompt_lower:find("гармон")) then
        return "harmony"
      end
    end
  end
  
  if name_lower:find("lead") or name_lower:find("melody") or name_lower:find("solo") then
    return "melody"
  end
  if name_lower:find("bass") or name_lower:find("бас") or family == "bass" then
    return "bass"
  end
  if name_lower:find("pad") or name_lower:find("chord") then
    return "harmony"
  end
  if name_lower:find("rhythm") or name_lower:find("perc") or name_lower:find("drum") then
    return "rhythm"
  end
  
  return FAMILY_DEFAULT_ROLE[family] or "harmony"
end

local function sort_tracks_by_generation_order(tracks, prompt)
  local with_roles = {}
  for _, track_data in ipairs(tracks) do
    local role = detect_instrument_role(track_data.name, track_data.profile, prompt)
    table.insert(with_roles, {
      track_data = track_data,
      role = role,
      priority = ROLE_PRIORITY[role] or 99,
    })
  end
  
  table.sort(with_roles, function(a, b)
    return a.priority < b.priority
  end)
  
  local sorted = {}
  for _, item in ipairs(with_roles) do
    item.track_data.role = item.role
    table.insert(sorted, item.track_data)
  end
  
  return sorted
end

local function get_time_selection()
  local start_sec, end_sec = reaper.GetSet_LoopTimeRange2(0, false, false, 0, 0, false)
  return start_sec, end_sec
end

local function get_bpm_and_timesig(time_sec)
  local bpm = reaper.Master_GetTempo()
  local num = 4
  local denom = 4

  local marker_count = reaper.CountTempoTimeSigMarkers(0)
  if marker_count > 0 then
    for i = marker_count - 1, 0, -1 do
      local retval, timepos, _, _, _, ts_num, ts_denom = reaper.GetTempoTimeSigMarker(0, i)
      if retval and timepos <= time_sec then
        if ts_num and ts_num > 0 then
          num = ts_num
        end
        if ts_denom and ts_denom > 0 then
          denom = ts_denom
        end
        break
      end
    end
  else
    local retval, measures, cml, fullbeats, cdenom = reaper.TimeMap2_timeToBeats(0, 0)
    if cml and cml > 0 then
      num = math.floor(cml)
    end
    if cdenom and cdenom > 0 then
      denom = math.floor(cdenom)
    end
  end

  if num <= 0 then num = 4 end
  if denom <= 0 then denom = 4 end

  utils.log(string.format("Time signature: %d/%d, BPM: %.1f", num, denom, bpm))
  return bpm, num, denom
end

local function get_key_tracks()
  local tracks = {}
  local count = reaper.CountSelectedTracks(0)
  if count > 0 then
    for i = 0, count - 1 do
      local track = reaper.GetSelectedTrack(0, i)
      if track then
        table.insert(tracks, track)
      end
    end
    return tracks
  end
  local active = midi.get_active_track()
  if active then
    table.insert(tracks, active)
  end
  return tracks
end

local function build_request(start_sec, end_sec, bpm, num, denom, key, profile_id, articulation_name, generation_type, generation_style, prompt, ctx, api_settings, free_mode, ensemble_info)
  local provider = const.DEFAULT_MODEL_PROVIDER
  local model_name = const.DEFAULT_MODEL_NAME
  local base_url = const.DEFAULT_MODEL_BASE_URL
  local api_key = nil

  if api_settings then
    if api_settings.api_provider == const.API_PROVIDER_OPENROUTER then
      provider = "openrouter"
      api_key = api_settings.api_key
    end
    if api_settings.model_name and api_settings.model_name ~= "" then
      model_name = api_settings.model_name
    end
    if api_settings.api_base_url and api_settings.api_base_url ~= "" then
      base_url = api_settings.api_base_url
    end
  end

  local request = {
    time = { start_sec = start_sec, end_sec = end_sec },
    music = { bpm = bpm, time_sig = string.format("%d/%d", num, denom), key = key },
    target = { profile_id = profile_id, articulation = articulation_name },
    generation_type = generation_type or const.DEFAULT_GENERATION_TYPE,
    generation_style = generation_style or const.DEFAULT_GENERATION_STYLE,
    free_mode = free_mode or false,
    user_prompt = prompt,
    model = {
      provider = provider,
      model_name = model_name,
      temperature = const.DEFAULT_MODEL_TEMPERATURE,
      base_url = base_url,
      api_key = api_key,
    },
  }
  if ctx then
    request.context = ctx
  end
  if ensemble_info then
    request.ensemble = ensemble_info
  end
  return request
end

local function abort_apply(reason)
  if apply_state and apply_state.undo_started then
    reaper.Undo_EndBlock("AI Part Generator (aborted)", -1)
  end
  apply_state = nil
  if reason then
    utils.show_error(reason)
  end
end

local function apply_step()
  if not apply_state then
    return
  end

  local take = apply_state.take
  if not reaper.ValidatePtr(take, "MediaItem_Take*") then
    utils.log("apply_step ERROR: take no longer valid")
    abort_apply("MIDI take no longer available.")
    return
  end

  local phase = apply_state.phase
  local processed = 0

  if phase == "clear_notes" then
    local deleted = 0
    while apply_state.note_idx >= 0 and processed < const.DELETE_CHUNK_SIZE do
      local ok, _, _, note_start, note_end = reaper.MIDI_GetNote(take, apply_state.note_idx)
      if ok and note_end > apply_state.start_ppq and note_start < apply_state.end_ppq then
        reaper.MIDI_DeleteNote(take, apply_state.note_idx)
        deleted = deleted + 1
      end
      apply_state.note_idx = apply_state.note_idx - 1
      processed = processed + 1
    end
    if apply_state.note_idx < 0 then
      utils.log("apply_step: clear_notes done, deleted=" .. deleted)
      apply_state.phase = "clear_cc"
    end
    reaper.defer(apply_step)
    return
  end

  if phase == "clear_cc" then
    local deleted = 0
    while apply_state.cc_idx >= 0 and processed < const.DELETE_CHUNK_SIZE do
      local ok, _, _, ppqpos = reaper.MIDI_GetCC(take, apply_state.cc_idx)
      if ok and ppqpos >= apply_state.start_ppq and ppqpos <= apply_state.end_ppq then
        reaper.MIDI_DeleteCC(take, apply_state.cc_idx)
        deleted = deleted + 1
      end
      apply_state.cc_idx = apply_state.cc_idx - 1
      processed = processed + 1
    end
    if apply_state.cc_idx < 0 then
      utils.log("apply_step: clear_cc done, deleted=" .. deleted)
      apply_state.phase = "insert_pc"
      apply_state.pc_idx = 1
      apply_state.ks_idx = 1
      apply_state.cc_ins_idx = 1
      apply_state.note_ins_idx = 1
    end
    reaper.defer(apply_step)
    return
  end

  if phase == "insert_pc" then
    local list = apply_state.program_changes
    while apply_state.pc_idx <= #list and processed < const.APPLY_CHUNK_SIZE do
      midi.insert_program_change(take, apply_state.start_qn, list[apply_state.pc_idx])
      apply_state.pc_idx = apply_state.pc_idx + 1
      processed = processed + 1
    end
    if apply_state.pc_idx > #list then
      utils.log("apply_step: insert_pc done, count=" .. #list)
      apply_state.phase = "insert_keyswitches"
    end
    reaper.defer(apply_step)
    return
  end

  if phase == "insert_keyswitches" then
    local list = apply_state.keyswitches
    while apply_state.ks_idx <= #list and processed < const.APPLY_CHUNK_SIZE do
      midi.insert_note(take, apply_state.start_qn, list[apply_state.ks_idx])
      apply_state.ks_idx = apply_state.ks_idx + 1
      processed = processed + 1
    end
    if apply_state.ks_idx > #list then
      utils.log("apply_step: insert_keyswitches done, count=" .. #list)
      apply_state.phase = "insert_cc"
    end
    reaper.defer(apply_step)
    return
  end

  if phase == "insert_cc" then
    local list = apply_state.cc_events
    while apply_state.cc_ins_idx <= #list and processed < const.APPLY_CHUNK_SIZE do
      midi.insert_cc(take, apply_state.start_qn, list[apply_state.cc_ins_idx])
      apply_state.cc_ins_idx = apply_state.cc_ins_idx + 1
      processed = processed + 1
    end
    if apply_state.cc_ins_idx > #list then
      utils.log("apply_step: insert_cc done, count=" .. #list)
      apply_state.phase = "insert_notes"
    end
    reaper.defer(apply_step)
    return
  end

  if phase == "insert_notes" then
    local list = apply_state.notes
    while apply_state.note_ins_idx <= #list and processed < const.APPLY_CHUNK_SIZE do
      midi.insert_note(take, apply_state.start_qn, list[apply_state.note_ins_idx])
      apply_state.note_ins_idx = apply_state.note_ins_idx + 1
      processed = processed + 1
    end
    if apply_state.note_ins_idx > #list then
      utils.log("apply_step: insert_notes done, count=" .. #list)
      apply_state.phase = "finalize"
    end
    reaper.defer(apply_step)
    return
  end

  if phase == "finalize" then
    utils.log("apply_step: finalizing...")
    midi.sort(take)
    profiles.save_track_profile_id(apply_state.target_track, apply_state.profile_id)
    reaper.Undo_EndBlock("AI Part Generator", -1)
    reaper.UpdateArrange()
    utils.log("AI Part Generator: DONE! All MIDI data applied successfully.")
    apply_state = nil
    return
  end

  utils.log("apply_step WARNING: unknown phase=" .. tostring(phase))
end

local function begin_apply(response, profile_id, target_track, start_sec, end_sec)
  utils.log("begin_apply: starting...")

  if not reaper.ValidatePtr(target_track, "MediaTrack*") then
    utils.log("begin_apply ERROR: Target track no longer available")
    utils.show_error("Target track no longer available.")
    return
  end

  local item, take, created_new_take = midi.get_or_create_midi_item(target_track, start_sec, end_sec, true)
  if not take then
    utils.log("begin_apply ERROR: Failed to get MIDI take")
    utils.show_error("Failed to get MIDI take.")
    return
  end
  utils.log("begin_apply: got MIDI item and take (new_take=" .. tostring(created_new_take) .. ")")

  local start_qn = reaper.TimeMap_timeToQN(start_sec)
  local end_qn_val = reaper.TimeMap_timeToQN(end_sec)
  local start_ppq = reaper.MIDI_GetPPQPosFromProjQN(take, start_qn)
  local end_ppq = reaper.MIDI_GetPPQPosFromProjQN(take, end_qn_val)
  local _, note_count, cc_count = reaper.MIDI_CountEvts(take)

  utils.log(string.format("begin_apply: start_qn=%.2f end_qn=%.2f start_ppq=%.0f end_ppq=%.0f",
    start_qn, end_qn_val, start_ppq, end_ppq))
  utils.log(string.format("begin_apply: existing notes=%d cc=%d", note_count, cc_count))

  local notes = response.notes or {}
  local cc_events = response.cc_events or {}
  local keyswitches = response.keyswitches or {}
  local program_changes = response.program_changes or {}

  utils.log(string.format("begin_apply: to insert: notes=%d cc=%d ks=%d pc=%d",
    #notes, #cc_events, #keyswitches, #program_changes))

  local initial_phase = created_new_take and "insert_pc" or "clear_notes"

  reaper.Undo_BeginBlock()
  apply_state = {
    phase = initial_phase,
    take = take,
    item = item,
    start_qn = start_qn,
    start_ppq = start_ppq,
    end_ppq = end_ppq,
    note_idx = note_count - 1,
    cc_idx = cc_count - 1,
    notes = notes,
    cc_events = cc_events,
    keyswitches = keyswitches,
    program_changes = program_changes,
    target_track = target_track,
    profile_id = profile_id,
    undo_started = true,
    pc_idx = 1,
    ks_idx = 1,
    cc_ins_idx = 1,
    note_ins_idx = 1,
  }

  utils.log("begin_apply: starting apply_step with phase=" .. initial_phase)
  reaper.defer(apply_step)
end

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
  local target_track = pending.target_track
  local start_sec = pending.start_sec
  local end_sec = pending.end_sec
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

  begin_apply(data, profile_id, target_track, start_sec, end_sec)
end

local function run_generation_after_bridge(state, profiles_by_id, start_sec, end_sec)
  if pending or apply_state then
    utils.show_error("Generation already in progress.")
    return
  end

  local bpm, num, denom = get_bpm_and_timesig(start_sec)
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
  local key = state.key or const.DEFAULT_KEY
  if state.key_mode == "Auto" then
    local tracks = get_key_tracks()
    key = key_detect.detect_key(tracks, start_sec, end_sec) or const.DEFAULT_KEY
  elseif state.key_mode == "Unknown" then
    key = const.DEFAULT_KEY
  end
  local api_settings = {
    api_provider = state.api_provider,
    api_key = state.api_key,
    api_base_url = state.api_base_url,
    model_name = state.model_name,
  }

  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_PROVIDER, state.api_provider or const.API_PROVIDER_LOCAL, true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_KEY, state.api_key or "", true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_BASE_URL, state.api_base_url or "", true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_MODEL_NAME, state.model_name or "", true)

  profiles.save_track_settings(target_track, state)

  local request = build_request(
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
    target_track = target_track,
    start_sec = start_sec,
    end_sec = end_sec,
  }
  reaper.defer(poll_generation)
end

local function run_generation(state, profiles_by_id)
  local start_sec, end_sec = get_time_selection()
  if start_sec == end_sec then
    utils.show_error("No time selection set.")
    return
  end
  if pending or apply_state then
    utils.show_error("Generation already in progress.")
    return
  end

  local state_snapshot = {
    profile_id = state.profile_id,
    articulation_name = state.articulation_name,
    generation_type = state.generation_type,
    generation_style = state.generation_style,
    free_mode = state.free_mode,
    prompt = state.prompt,
    use_selected_tracks = state.use_selected_tracks,
    insert_target = state.insert_target,
    key_mode = state.key_mode,
    key = state.key,
    api_provider = state.api_provider,
    api_key = state.api_key,
    api_base_url = state.api_base_url,
    model_name = state.model_name,
  }

  run_generation_after_bridge(state_snapshot, profiles_by_id, start_sec, end_sec)
end

local function apply_compose_result_and_continue()
  if not compose_state then
    return
  end
  
  if apply_state then
    reaper.defer(apply_compose_result_and_continue)
    return
  end
  
  local current = compose_state.pending_apply
  if current then
    utils.log(string.format("Compose: applying results for '%s' (%d/%d)",
      current.track_name, compose_state.current_index, compose_state.total_tracks))
    
    begin_apply(current.response, current.profile_id, current.target_track,
      compose_state.start_sec, compose_state.end_sec)
    
    table.insert(compose_state.generated_parts, {
      track_name = current.track_name,
      profile_name = current.profile_name,
      role = current.role,
      notes = current.response.notes or {},
      cc_events = current.response.cc_events or {},
    })
    
    compose_state.pending_apply = nil
    reaper.defer(apply_compose_result_and_continue)
    return
  end
  
  compose_state.current_index = compose_state.current_index + 1
  if compose_state.current_index > compose_state.total_tracks then
    utils.log("Compose: ALL COMPLETE!")
    compose_state = nil
    return
  end
  
  reaper.defer(start_next_compose_generation)
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
    
    compose_state.pending_apply = {
      response = data,
      profile_id = current_track.profile.id,
      profile_name = current_track.profile.name,
      target_track = current_track.track,
      track_name = current_track.name,
      role = current_track.role,
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
    current_track.name, current_track.role or "unknown"))
  
  local articulation_name = profiles.get_default_articulation(profile)
  local ctx = context.build_context(compose_state.use_selected_tracks, current_track.track,
    compose_state.start_sec, compose_state.end_sec)
  
  local ensemble_info = {
    total_instruments = compose_state.total_tracks,
    instruments = compose_state.ensemble_instruments,
    generation_style = compose_state.generation_style,
    shared_prompt = compose_state.prompt,
    current_instrument_index = compose_state.current_index,
    current_instrument = {
      track_name = current_track.name,
      profile_name = profile.name,
      family = profile.family or "unknown",
      role = current_track.role,
    },
    generation_order = compose_state.current_index,
    is_sequential = true,
    previously_generated = compose_state.generated_parts,
  }
  
  local request = build_request(
    compose_state.start_sec,
    compose_state.end_sec,
    compose_state.bpm,
    compose_state.num,
    compose_state.denom,
    compose_state.key,
    profile.id,
    articulation_name,
    compose_state.generation_type,
    compose_state.generation_style,
    compose_state.prompt,
    ctx,
    compose_state.api_settings,
    true,
    ensemble_info
  )
  
  local handle, err = http.begin_request(const.DEFAULT_BRIDGE_URL, request)
  if not handle then
    utils.log(string.format("Compose: failed to start request for '%s': %s", current_track.name, tostring(err)))
    compose_state.current_index = compose_state.current_index + 1
    reaper.defer(start_next_compose_generation)
    return
  end
  
  compose_state.current_handle = handle
  reaper.defer(poll_compose_generation)
end

local function run_compose(state, profile_list, profiles_by_id)
  local start_sec, end_sec = get_time_selection()
  if start_sec == end_sec then
    utils.show_error("No time selection set.")
    return
  end

  if pending or apply_state or compose_state then
    utils.show_error("Generation already in progress.")
    return
  end

  local tracks_with_profiles = profiles.get_selected_tracks_with_profiles(profile_list, profiles_by_id)
  
  if #tracks_with_profiles == 0 then
    utils.show_error("No tracks selected.")
    return
  end

  local valid_tracks = {}
  local skipped = {}
  for _, track_data in ipairs(tracks_with_profiles) do
    if track_data.profile_id and track_data.profile then
      table.insert(valid_tracks, track_data)
    else
      table.insert(skipped, track_data.name)
    end
  end

  if #valid_tracks == 0 then
    local msg = "Could not determine profiles for selected tracks."
    if #skipped > 0 then
      msg = msg .. "\nUnmatched: " .. table.concat(skipped, ", ")
    end
    utils.show_error(msg)
    return
  end

  local sorted_tracks = sort_tracks_by_generation_order(valid_tracks, state.prompt)
  
  utils.log(string.format("Compose: %d tracks (sorted by role)", #sorted_tracks))
  for i, td in ipairs(sorted_tracks) do
    utils.log(string.format("  %d. '%s' -> '%s' (role: %s)", i, td.name, td.profile.name, td.role or "unknown"))
  end

  local bpm, num, denom = get_bpm_and_timesig(start_sec)
  
  local key = state.key or const.DEFAULT_KEY
  if state.key_mode == "Auto" then
    local key_tracks = get_key_tracks()
    key = key_detect.detect_key(key_tracks, start_sec, end_sec) or const.DEFAULT_KEY
  elseif state.key_mode == "Unknown" then
    key = const.DEFAULT_KEY
  end

  local api_settings = {
    api_provider = state.api_provider,
    api_key = state.api_key,
    api_base_url = state.api_base_url,
    model_name = state.model_name,
  }

  local ensemble_instruments = {}
  for i, track_data in ipairs(sorted_tracks) do
    table.insert(ensemble_instruments, {
      index = i,
      track_name = track_data.name,
      profile_id = track_data.profile.id,
      profile_name = track_data.profile.name,
      family = track_data.profile.family or "unknown",
      role = track_data.role or "unknown",
      range = track_data.profile.range or {},
      description = track_data.profile.description or "",
    })
  end

  compose_state = {
    tracks = sorted_tracks,
    total_tracks = #sorted_tracks,
    current_index = 1,
    current_handle = nil,
    pending_apply = nil,
    generated_parts = {},
    start_sec = start_sec,
    end_sec = end_sec,
    bpm = bpm,
    num = num,
    denom = denom,
    key = key,
    api_settings = api_settings,
    ensemble_instruments = ensemble_instruments,
    generation_type = state.generation_type or const.DEFAULT_GENERATION_TYPE,
    generation_style = state.generation_style or const.DEFAULT_GENERATION_STYLE,
    prompt = state.prompt or "",
    use_selected_tracks = state.use_selected_tracks,
  }

  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_PROVIDER, state.api_provider or const.API_PROVIDER_LOCAL, true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_KEY, state.api_key or "", true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_BASE_URL, state.api_base_url or "", true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_MODEL_NAME, state.model_name or "", true)

  start_next_compose_generation()
end

function M.main()
  local profile_list, profiles_by_id = profiles.load_profiles()
  if #profile_list == 0 then
    utils.show_error("No profiles found in Profiles/ directory.")
    return
  end

  local active_track = midi.get_active_track()
  local profile_id = profiles.resolve_profile_id(active_track, profile_list, profiles_by_id)
  local profile = profiles_by_id[profile_id]

  local saved_api_provider = reaper.GetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_PROVIDER)
  local saved_api_key = reaper.GetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_KEY)
  local saved_api_base_url = reaper.GetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_BASE_URL)
  local saved_model_name = reaper.GetExtState(const.SCRIPT_NAME, const.EXTSTATE_MODEL_NAME)

  local api_provider = saved_api_provider ~= "" and saved_api_provider or const.API_PROVIDER_LOCAL
  local api_base_url = saved_api_base_url
  local model_name = saved_model_name

  if api_base_url == "" then
    api_base_url = api_provider == const.API_PROVIDER_OPENROUTER and const.DEFAULT_OPENROUTER_BASE_URL or const.DEFAULT_MODEL_BASE_URL
  end
  if model_name == "" then
    model_name = api_provider == const.API_PROVIDER_OPENROUTER and const.DEFAULT_OPENROUTER_MODEL or const.DEFAULT_MODEL_NAME
  end

  local track_settings = profiles.get_track_settings(active_track)

  local articulation_name = profile and profiles.get_default_articulation(profile) or ""
  local articulation_list = profile and profiles.build_articulation_list(profile) or {}
  local articulation_info = profile and (profile.articulations or {}).map or {}

  local state = {
    profile_id = profile_id,
    profile_name = profile and profile.name or "",
    articulation_name = track_settings.articulation_name or articulation_name,
    articulation_list = articulation_list,
    articulation_info = articulation_info,
    generation_type = track_settings.generation_type or const.DEFAULT_GENERATION_TYPE,
    generation_style = track_settings.generation_style or const.DEFAULT_GENERATION_STYLE,
    free_mode = track_settings.free_mode or false,
    prompt = track_settings.prompt or "",
    use_selected_tracks = track_settings.use_selected_tracks ~= nil and track_settings.use_selected_tracks or true,
    insert_target = track_settings.insert_target or const.INSERT_TARGET_ACTIVE,
    key_mode = track_settings.key_mode or "Auto",
    key = track_settings.key or const.DEFAULT_KEY,
    api_provider = api_provider,
    api_key = saved_api_key,
    api_base_url = api_base_url,
    model_name = model_name,
    active_track = active_track,
  }

  local on_generate = function(current_state)
    run_generation(current_state, profiles_by_id)
  end

  local on_compose = function(current_state)
    run_compose(current_state, profile_list, profiles_by_id)
  end

  local callbacks = {
    on_generate = on_generate,
    on_compose = on_compose,
  }

  if reaper.ImGui_CreateContext ~= nil then
    ui.run_imgui(state, profile_list, profiles_by_id, callbacks)
  else
    utils.show_error("ReaImGui not found. Using fallback dialog; dropdowns require ReaImGui.")
    ui.run_dialog_fallback(state, profile_list, profiles_by_id, on_generate)
  end
end

function M.is_generation_in_progress()
  return pending ~= nil or apply_state ~= nil or compose_state ~= nil
end

function M.get_compose_progress()
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
