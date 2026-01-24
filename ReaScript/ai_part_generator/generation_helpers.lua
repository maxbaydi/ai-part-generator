local const = require("ai_part_generator.constants")
local bridge = require("ai_part_generator.bridge")
local key_detect = require("ai_part_generator.key_detect")
local midi = require("ai_part_generator.midi")
local utils = require("ai_part_generator.utils")

local M = {}

M.KEY_MODE_AUTO = "Auto"
M.KEY_MODE_MANUAL = "Manual"
M.KEY_MODE_UNKNOWN = "Unknown"

M.ERROR_NO_TIME_SELECTION = "No time selection set."
M.ERROR_GENERATION_IN_PROGRESS = "Generation already in progress."

M.UNKNOWN_ROLE = "unknown"
M.TIME_SIG_FORMAT = "%d/%d"

local DEFAULT_TIME_SIG_NUM = 4
local DEFAULT_TIME_SIG_DENOM = 4
local ROUND_HALF = 0.5
local REAPER_KEEP_VALUE = -1
local NEW_MARKER_INDEX = -1
local STYLE_SEPARATOR = ", "

function M.ensure_bridge_ready(on_ready, on_error)
  bridge.ensure_running_async(function(ok, err)
    if ok then
      if on_ready then
        on_ready()
      end
      return
    end
    if on_error then
      on_error(err)
      return
    end
    if err then
      utils.show_error(err)
    end
  end)
end

function M.get_time_selection_or_error()
  local start_sec, end_sec = utils.get_time_selection()
  if start_sec == end_sec then
    utils.show_error(M.ERROR_NO_TIME_SELECTION)
    return nil, nil
  end
  return start_sec, end_sec
end

function M.build_api_settings(state)
  return {
    api_provider = state.api_provider,
    api_key = state.api_key,
    api_base_url = state.api_base_url,
    model_name = state.model_name,
  }
end

function M.save_api_settings_extstate(state)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_PROVIDER, state.api_provider or const.API_PROVIDER_LOCAL, true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_KEY, state.api_key or "", true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_API_BASE_URL, state.api_base_url or "", true)
  reaper.SetExtState(const.SCRIPT_NAME, const.EXTSTATE_MODEL_NAME, state.model_name or "", true)
end

function M.get_key_tracks()
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

function M.resolve_key_from_state(state, start_sec, end_sec, opts)
  local key = state.key or const.DEFAULT_KEY
  local mode = state.key_mode
  if mode == M.KEY_MODE_AUTO and not (opts and opts.no_auto) then
    local tracks = M.get_key_tracks()
    key = key_detect.detect_key(tracks, start_sec, end_sec) or const.DEFAULT_KEY
  elseif mode == M.KEY_MODE_UNKNOWN then
    key = const.DEFAULT_KEY
  end
  if opts and opts.treat_empty_as_unknown and key == "" then
    key = const.DEFAULT_KEY
  end
  return key
end

function M.combine_style(musical_style, generation_mood)
  return (musical_style or "") .. STYLE_SEPARATOR .. (generation_mood or "")
end

function M.get_enriched_style_prompt(musical_style, generation_mood, use_style_mood)
  if use_style_mood == false then
    return ""
  end

  local prompt_parts = {}

  if musical_style and musical_style ~= "" then
    local desc = const.STYLE_DESCRIPTIONS[musical_style] or ""
    if desc ~= "" then
      table.insert(prompt_parts, "Musical Style (" .. musical_style .. "): " .. desc)
    else
      table.insert(prompt_parts, "Musical Style: " .. musical_style)
    end
  end

  if generation_mood and generation_mood ~= "" then
    local desc = const.MOOD_DESCRIPTIONS[generation_mood] or ""
    if desc ~= "" then
      table.insert(prompt_parts, "Mood (" .. generation_mood .. "): " .. desc)
    else
      table.insert(prompt_parts, "Mood: " .. generation_mood)
    end
  end

  if #prompt_parts > 0 then
    return table.concat(prompt_parts, "\n") .. "\n"
  end
  return ""
end

function M.build_style_prompt(state, base_prompt)
  local combined_style = nil
  local final_prompt = base_prompt or ""
  if not state.free_mode then
    combined_style = M.combine_style(state.musical_style, state.generation_mood)
    local style_text = M.get_enriched_style_prompt(state.musical_style, state.generation_mood, state.use_style_mood)
    if style_text ~= "" then
      final_prompt = style_text .. final_prompt
    end
  end
  return combined_style, final_prompt
end

function M.build_ensemble_instruments_from_tracks(tracks)
  local ensemble_instruments = {}
  for i, track_data in ipairs(tracks) do
    table.insert(ensemble_instruments, {
      index = i,
      track_name = track_data.name,
      profile_id = track_data.profile.id,
      profile_name = track_data.profile.name,
      family = track_data.profile.family or M.UNKNOWN_ROLE,
      role = track_data.role or M.UNKNOWN_ROLE,
      range = track_data.profile.range or {},
      description = track_data.profile.description or "",
    })
  end
  return ensemble_instruments
end

function M.normalize_plan_name(value)
  local name = tostring(value or ""):lower()
  name = name:gsub("[^%w]+", "")
  return name
end

function M.apply_plan_order(plan, tracks)
  if type(plan) ~= "table" or type(plan.role_guidance) ~= "table" then
    return tracks, false
  end

  local used = {}
  local ordered = {}

  for _, entry in ipairs(plan.role_guidance) do
    if type(entry) == "table" then
      local entry_index = tonumber(entry.instrument_index)
      if entry_index and tracks[entry_index] and not used[entry_index] then
        local track_data = tracks[entry_index]
        if entry.role and entry.role ~= "" then
          track_data.role = entry.role
        end
        table.insert(ordered, track_data)
        used[entry_index] = true
      else
      local instrument_key = M.normalize_plan_name(entry.instrument)
      if instrument_key ~= "" then
        local best_idx = nil
        local best_score = 0
        for i, track_data in ipairs(tracks) do
          if not used[i] then
            local track_key = M.normalize_plan_name(track_data.name)
            local profile_key = M.normalize_plan_name(track_data.profile and track_data.profile.name)
            local score = 0
            if track_key ~= "" and track_key:find(instrument_key, 1, true) then
              score = 3
            elseif track_key ~= "" and instrument_key:find(track_key, 1, true) then
              score = 2
            elseif profile_key ~= "" and profile_key:find(instrument_key, 1, true) then
              score = 1
            end
            if score > best_score then
              best_idx = i
              best_score = score
            end
          end
        end

        if best_idx then
          local track_data = tracks[best_idx]
          if entry.role and entry.role ~= "" then
            track_data.role = entry.role
          end
          table.insert(ordered, track_data)
          used[best_idx] = true
        end
      end
      end
    end
  end

  for i, track_data in ipairs(tracks) do
    if not used[i] then
      table.insert(ordered, track_data)
    end
  end

  return ordered, #ordered > 0
end

local function resolve_model_config(api_settings, opts)
  local provider = const.DEFAULT_MODEL_PROVIDER
  local model_name = const.DEFAULT_MODEL_NAME
  local base_url = const.DEFAULT_MODEL_BASE_URL
  local api_key = nil

  local use_plan_model = opts and opts.use_plan_model
  local use_openrouter_base_url = opts and opts.use_openrouter_base_url

  if api_settings and api_settings.api_provider == const.API_PROVIDER_OPENROUTER then
    provider = const.API_PROVIDER_OPENROUTER
    api_key = api_settings.api_key
    if use_plan_model then
      model_name = const.DEFAULT_OPENROUTER_PLAN_MODEL
    end
    if use_openrouter_base_url then
      base_url = const.DEFAULT_OPENROUTER_BASE_URL
    end
  end

  if api_settings then
    if not use_plan_model and api_settings.model_name and api_settings.model_name ~= "" then
      model_name = api_settings.model_name
    end
    if api_settings.api_base_url and api_settings.api_base_url ~= "" then
      base_url = api_settings.api_base_url
    end
  end

  return provider, model_name, base_url, api_key
end

function M.resolve_model_config(api_settings, opts)
  return resolve_model_config(api_settings, opts)
end

function M.get_bpm_and_timesig(time_sec)
  local bpm = reaper.Master_GetTempo()
  local num = DEFAULT_TIME_SIG_NUM
  local denom = DEFAULT_TIME_SIG_DENOM

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
    local _, _, cml, _, cdenom = reaper.TimeMap2_timeToBeats(0, 0)
    if cml and cml > 0 then
      num = math.floor(cml)
    end
    if cdenom and cdenom > 0 then
      denom = math.floor(cdenom)
    end
  end

  if num <= 0 then num = DEFAULT_TIME_SIG_NUM end
  if denom <= 0 then denom = DEFAULT_TIME_SIG_DENOM end

  utils.log(string.format("Time signature: %d/%d, BPM: %.1f", num, denom, bpm))
  return bpm, num, denom
end

function M.get_time_signature_at_time(time_sec)
  local _, _, cml, _, cdenom = reaper.TimeMap2_timeToBeats(0, time_sec)
  local num = math.floor((cml or DEFAULT_TIME_SIG_NUM) + ROUND_HALF)
  local denom = math.floor((cdenom or DEFAULT_TIME_SIG_DENOM) + ROUND_HALF)
  if num <= 0 then num = DEFAULT_TIME_SIG_NUM end
  if denom <= 0 then denom = DEFAULT_TIME_SIG_DENOM end
  return num, denom
end

function M.validate_time_signature(num, denom)
  local num_int = tonumber(num)
  local denom_int = tonumber(denom)
  if not num_int or not denom_int then
    return nil, nil
  end
  num_int = math.floor(num_int)
  denom_int = math.floor(denom_int)
  if num_int < const.TIME_SIG_MIN_NUM or num_int > const.TIME_SIG_MAX_NUM then
    return nil, nil
  end
  if not const.TIME_SIG_VALID_DENOM[denom_int] then
    return nil, nil
  end
  return num_int, denom_int
end

function M.parse_time_signature_string(value)
  if not value then
    return nil, nil
  end
  local num_str, denom_str = tostring(value):match("(%d+)%s*/%s*(%d+)")
  return M.validate_time_signature(num_str, denom_str)
end

function M.normalize_tempo_markers(markers, length_q)
  if type(markers) ~= "table" then
    return {}
  end
  local cleaned = {}
  for _, marker in ipairs(markers) do
    if type(marker) == "table" then
      local time_q = tonumber(marker.time_q) or tonumber(marker.start_q) or tonumber(marker.time) or 0
      time_q = math.max(0, math.min(length_q, time_q))

      local bpm = tonumber(marker.bpm) or tonumber(marker.tempo)
      if bpm then
        bpm = math.max(const.TEMPO_MARKER_MIN_BPM, math.min(const.TEMPO_MARKER_MAX_BPM, bpm))
      end

      local num_raw = marker.num or marker.numerator or marker.time_sig_num
      local denom_raw = marker.denom or marker.denominator or marker.time_sig_denom
      local num, denom = M.validate_time_signature(num_raw, denom_raw)

      if bpm or num then
        local linear = marker.linear == true or marker.ramp == true
        local entry = { time_q = time_q, linear = linear }
        if bpm then
          entry.bpm = bpm
        end
        if num and denom then
          entry.num = num
          entry.denom = denom
        end
        table.insert(cleaned, entry)
      end
    end
  end

  table.sort(cleaned, function(a, b)
    return a.time_q < b.time_q
  end)

  local result = {}
  local last_time = nil
  for _, marker in ipairs(cleaned) do
    if not last_time or math.abs(marker.time_q - last_time) >= const.TEMPO_MARKER_MIN_GAP_Q then
      table.insert(result, marker)
      last_time = marker.time_q
    end
    if #result >= const.MAX_TEMPO_MARKERS then
      break
    end
  end

  return result
end

function M.find_tempo_marker_index(time_sec)
  local count = reaper.CountTempoTimeSigMarkers(0)
  for i = 0, count - 1 do
    local retval, marker_time = reaper.GetTempoTimeSigMarker(0, i)
    if retval and math.abs((marker_time or 0) - time_sec) <= const.TEMPO_MARKER_EPS_SEC then
      return i
    end
  end
  return nil
end

function M.apply_tempo_markers(markers, start_sec, end_sec)
  if type(markers) ~= "table" or #markers == 0 then
    return false, nil
  end
  local selection_start_qn = reaper.TimeMap2_timeToQN(0, start_sec)
  local selection_end_qn = reaper.TimeMap2_timeToQN(0, end_sec)
  local length_q = selection_end_qn - selection_start_qn
  if length_q <= 0 then
    return false, nil
  end

  local normalized = M.normalize_tempo_markers(markers, length_q)
  if #normalized == 0 then
    return false, nil
  end

  local prepared = {}
  for _, marker in ipairs(normalized) do
    local target_qn = selection_start_qn + marker.time_q
    local timepos = reaper.TimeMap2_QNToTime(0, target_qn)
    local current_num, current_denom = M.get_time_signature_at_time(timepos)
    local use_num = marker.num or current_num
    local use_denom = marker.denom or current_denom
    local use_bpm = marker.bpm or REAPER_KEEP_VALUE
    table.insert(prepared, {
      timepos = timepos,
      bpm = use_bpm,
      num = use_num,
      denom = use_denom,
      linear = marker.linear,
      has_bpm = marker.bpm ~= nil,
      has_time_sig = marker.num ~= nil and marker.denom ~= nil,
    })
  end

  local first_bpm = nil
  for _, p in ipairs(prepared) do
    local idx = M.find_tempo_marker_index(p.timepos)
    reaper.SetTempoTimeSigMarker(0, idx or NEW_MARKER_INDEX, p.timepos, REAPER_KEEP_VALUE, REAPER_KEEP_VALUE, p.bpm, p.num, p.denom, p.linear and true or false)
    if first_bpm == nil and p.has_bpm then
      first_bpm = p.bpm
    end
    if p.has_time_sig then
      utils.log(string.format("apply_tempo_markers: time_sig changed to %d/%d at %.2f", p.num, p.denom, p.timepos))
    end
  end

  reaper.UpdateTimeline()
  reaper.UpdateArrange()
  return true, first_bpm
end

function M.calculate_length_bars(start_sec, end_sec, num, denom)
  local start_qn = reaper.TimeMap2_timeToQN(0, start_sec)
  local end_qn = reaper.TimeMap2_timeToQN(0, end_sec)
  local length_q = end_qn - start_qn
  local quarters_per_bar = num * (DEFAULT_TIME_SIG_NUM / denom)
  return math.floor(length_q / quarters_per_bar + ROUND_HALF)
end

function M.build_request(start_sec, end_sec, bpm, num, denom, key, profile_id, articulation_name, generation_type, generation_style, prompt, ctx, api_settings, free_mode, allow_tempo_changes, ensemble_info, is_plan, original_bpm, length_bars_override, continuation)
  local provider, model_name, base_url, api_key = resolve_model_config(api_settings, {
    use_plan_model = is_plan == true,
  })

  local effective_type = nil
  local effective_style = nil
  if not free_mode then
    effective_type = generation_type or const.DEFAULT_GENERATION_TYPE
    effective_style = generation_style or const.DEFAULT_GENERATION_STYLE
  end

  local length_bars = length_bars_override
  if type(length_bars) ~= "number" or length_bars <= 0 then
    length_bars = M.calculate_length_bars(start_sec, end_sec, num, denom)
  else
    length_bars = math.floor(length_bars + ROUND_HALF)
  end

  local request = {
    time = { start_sec = start_sec, end_sec = end_sec, length_bars = length_bars },
    music = { bpm = bpm, time_sig = string.format(M.TIME_SIG_FORMAT, num, denom), key = key },
    target = { profile_id = profile_id, articulation = articulation_name },
    generation_type = effective_type,
    generation_style = effective_style,
    free_mode = free_mode or false,
    allow_tempo_changes = allow_tempo_changes or false,
    user_prompt = prompt,
    model = {
      provider = provider,
      model_name = model_name,
      temperature = const.DEFAULT_MODEL_TEMPERATURE,
      base_url = base_url,
      api_key = api_key,
    },
  }

  if original_bpm and original_bpm ~= bpm then
    request.music.original_bpm = original_bpm
  end

  if ctx then
    request.context = ctx
  end
  if ensemble_info then
    request.ensemble = ensemble_info
  end
  if continuation then
    request.continuation = continuation
  end
  return request
end

function M.build_tempo_markers_from_map(tempo_map, num, denom)
  local markers = {}
  if type(tempo_map) ~= "table" or #tempo_map == 0 then
    return markers
  end
  local quarters_per_bar = num * (DEFAULT_TIME_SIG_NUM / denom)
  for _, tm in ipairs(tempo_map) do
    if tm.bar and tm.bar >= 1 and tm.bpm then
      local time_q = (tm.bar - 1) * quarters_per_bar
      local marker = {
        time_q = time_q,
        bpm = tm.bpm,
        linear = tm.linear or false,
      }
      local num_raw = tm.num or tm.numerator or tm.time_sig_num
      local denom_raw = tm.denom or tm.denominator or tm.time_sig_denom
      local map_num, map_denom = M.validate_time_signature(num_raw, denom_raw)
      if map_num and map_denom then
        marker.num = map_num
        marker.denom = map_denom
      end
      table.insert(markers, marker)
    end
  end
  return markers
end

function M.build_tempo_markers_from_plan(plan, num, denom)
  local markers = {}
  if type(plan) ~= "table" then
    return markers
  end

  local initial_bpm = tonumber(plan.initial_bpm)
  if initial_bpm and initial_bpm > 0 then
    local entry = { time_q = 0, bpm = initial_bpm }
    if num and denom then
      entry.num = num
      entry.denom = denom
    end
    table.insert(markers, entry)
  elseif num and denom then
    table.insert(markers, { time_q = 0, num = num, denom = denom })
  end

  local tempo_map = plan.tempo_map
  if tempo_map and type(tempo_map) == "table" and #tempo_map > 0 then
    local map_markers = M.build_tempo_markers_from_map(tempo_map, num, denom)
    for _, marker in ipairs(map_markers) do
      table.insert(markers, marker)
    end
  end

  return markers
end

function M.apply_plan_tempo_if_allowed(state, label)
  if not state or not state.plan then
    return
  end
  if not state.allow_tempo_changes then
    local tempo_map = state.plan.tempo_map
    if state.plan.initial_bpm or (type(tempo_map) == "table" and #tempo_map > 0) then
      utils.log(string.format("%s: tempo changes disabled, plan tempo ignored", label))
    end
    return
  end

  local plan_time_sig = state.plan.time_sig or state.plan.time_signature
  local plan_num, plan_denom = M.parse_time_signature_string(plan_time_sig)
  if plan_num and plan_denom then
    state.num = plan_num
    state.denom = plan_denom
    utils.log(string.format("%s: time_sig from plan = %d/%d", label, plan_num, plan_denom))
  end

  local initial_bpm = state.plan.initial_bpm
  if initial_bpm and initial_bpm > 0 then
    state.bpm = initial_bpm
    state.original_bpm = initial_bpm
    utils.log(string.format("%s: initial_bpm from plan = %.1f", label, initial_bpm))
  end

  local markers = M.build_tempo_markers_from_plan(state.plan, state.num, state.denom)
  if #markers > 0 then
    state.deferred_tempo_markers = markers
    utils.log(string.format("%s: saved %d deferred tempo markers for later", label, #markers))
  end
end

function M.apply_deferred_tempo_markers_if_allowed(state, label)
  if not state or not state.allow_tempo_changes then
    return false
  end
  if not state.deferred_tempo_markers or #state.deferred_tempo_markers == 0 then
    return false
  end
  utils.log(string.format("%s: applying %d deferred tempo markers...", label, #state.deferred_tempo_markers))
  local markers_to_apply = nil
  local first_marker = state.deferred_tempo_markers[1]
  if first_marker and type(first_marker) == "table" and first_marker.time_q ~= nil then
    markers_to_apply = state.deferred_tempo_markers
  else
    markers_to_apply = M.build_tempo_markers_from_map(state.deferred_tempo_markers, state.num, state.denom)
  end
  if markers_to_apply and #markers_to_apply > 0 then
    M.apply_tempo_markers(markers_to_apply, state.start_sec, state.end_sec)
    utils.log(string.format("%s: deferred tempo markers applied successfully", label))
    return true
  end
  return false
end

function M.append_generated_part(collection, entry)
  table.insert(collection, {
    track_name = entry.track_name,
    profile_name = entry.profile_name,
    role = entry.role,
    notes = entry.response.notes or {},
    cc_events = entry.response.cc_events or {},
  })
end

function M.filter_tracks_with_profiles(tracks, opts)
  local valid = {}
  local skipped = {}
  local exclude_track = opts and opts.exclude_track

  for _, track_data in ipairs(tracks) do
    if track_data.profile_id and track_data.profile then
      if not exclude_track or track_data.track ~= exclude_track then
        table.insert(valid, track_data)
      end
    else
      table.insert(skipped, track_data.name)
    end
  end

  return valid, skipped
end

return M
