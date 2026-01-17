local const = require("ai_part_generator.constants")
local helpers = require("ai_part_generator.generation_helpers")
local http = require("ai_part_generator.http")
local utils = require("ai_part_generator.utils")

local M = {}

local enhance_state = nil

local QUARTERS_PER_WHOLE = 4
local ROUND_HALF = 0.5

local function poll_enhance()
  if not enhance_state then
    return
  end

  local done, data, err = http.poll_response(enhance_state.handle)
  if not done then
    reaper.defer(poll_enhance)
    return
  end

  http.cleanup(enhance_state.handle)
  local ui_state = enhance_state.ui_state
  enhance_state = nil

  if ui_state then
    ui_state.enhance_in_progress = false
  end

  if err then
    utils.log("Enhance ERROR: " .. tostring(err))
    utils.show_error("Enhance failed: " .. tostring(err))
    return
  end

  if data and data.enhanced_prompt then
    utils.log("Enhance: received enhanced prompt (" .. #data.enhanced_prompt .. " chars)")
    if ui_state then
      ui_state.prompt = data.enhanced_prompt
    end
  else
    utils.log("Enhance: no enhanced prompt in response")
  end
end

local function build_enhance_request(state, tracks_info, api_settings)
  local instruments = {}

  if tracks_info and #tracks_info > 0 then
    for _, track_data in ipairs(tracks_info) do
      if track_data.profile then
        table.insert(instruments, {
          track_name = track_data.name or "",
          profile_name = track_data.profile.name or "",
          family = track_data.profile.family or "",
          role = track_data.role or "",
        })
      end
    end
  end

  local start_sec, end_sec = utils.get_time_selection()
  local bpm = reaper.Master_GetTempo()
  local num, denom = QUARTERS_PER_WHOLE, QUARTERS_PER_WHOLE
  if start_sec and end_sec and start_sec ~= end_sec then
    num, denom = helpers.get_time_signature_at_time(start_sec)
  end

  local length_bars = nil
  local length_q = nil
  if start_sec and end_sec and start_sec ~= end_sec then
    local start_qn = reaper.TimeMap2_timeToQN(0, start_sec)
    local end_qn = reaper.TimeMap2_timeToQN(0, end_sec)
    length_q = end_qn - start_qn
    local quarters_per_bar = num * (QUARTERS_PER_WHOLE / denom)
    if quarters_per_bar > 0 then
      length_bars = math.floor(length_q / quarters_per_bar + ROUND_HALF)
    end
  end

  local key = helpers.resolve_key_from_state(state, start_sec, end_sec, { no_auto = true, treat_empty_as_unknown = true })
  local provider, model_name, base_url, api_key = helpers.resolve_model_config(api_settings, {})

  return {
    user_prompt = state.prompt or "",
    instruments = instruments,
    key = key,
    bpm = bpm,
    time_sig = string.format(helpers.TIME_SIG_FORMAT, num, denom),
    length_bars = length_bars,
    length_q = length_q,
    context_notes = nil,
    model = {
      provider = provider,
      model_name = model_name,
      temperature = const.DEFAULT_MODEL_TEMPERATURE,
      base_url = base_url,
      api_key = api_key,
    },
  }
end

function M.run_enhance(state, tracks_info)
  if not state.prompt or state.prompt == "" then
    return
  end

  if enhance_state then
    utils.log("Enhance: already in progress")
    return
  end

  utils.log("Enhance: starting prompt enhancement")
  state.enhance_in_progress = true

  local api_settings = helpers.build_api_settings(state)
  local request = build_enhance_request(state, tracks_info, api_settings)

  helpers.ensure_bridge_ready(function()
    if not state.enhance_in_progress then
      return
    end
    local handle, err = http.begin_request(const.BRIDGE_ENHANCE_URL, request)
    if not handle then
      state.enhance_in_progress = false
      utils.log("Enhance: request failed: " .. tostring(err))
      utils.show_error("Enhance request failed: " .. tostring(err))
      return
    end

    enhance_state = {
      handle = handle,
      ui_state = state,
    }

    reaper.defer(poll_enhance)
  end, function(err)
    state.enhance_in_progress = false
    if err then
      utils.show_error(err)
    end
  end)
end

function M.is_in_progress()
  return enhance_state ~= nil
end

return M
