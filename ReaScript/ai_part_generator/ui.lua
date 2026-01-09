local const = require("ai_part_generator.constants")
local profiles = require("ai_part_generator.profiles")
local utils = require("ai_part_generator.utils")

local M = {}

local FALLBACK_SEPARATOR = "|"

local UI = {
  WINDOW_WIDTH = 500,
  WINDOW_HEIGHT = 700,
  SECTION_SPACING = 12,
  ITEM_SPACING = 6,
  BUTTON_HEIGHT = 32,
  COMBO_WIDTH = -1,
  INPUT_WIDTH = -1,
  LABEL_COLOR = 0xB0B0B0FF,
  SECTION_COLOR = 0xFFFFFFFF,
  ACCENT_COLOR = 0x4A9FFFFF,
  GENERATE_BTN_COLOR = 0x2D7D46FF,
  GENERATE_BTN_HOVER = 0x3A9D5AFF,
  GENERATE_BTN_ACTIVE = 0x248F3EFF,
  COMPOSE_BTN_COLOR = 0x7D4D2DFF,
  COMPOSE_BTN_HOVER = 0x9D6D3AFF,
  COMPOSE_BTN_ACTIVE = 0x6D3D24FF,
  ENHANCE_BTN_COLOR = 0x5D4D8DFF,
  ENHANCE_BTN_HOVER = 0x7D6DADFF,
  ENHANCE_BTN_ACTIVE = 0x4D3D7DFF,
  BAR_ALIGN_EPS = 1e-4,
  BAR_RULER_MAX_BARS = 64,
  BAR_RULER_CHAR = "▮",
  PROMPT_MIN_HEIGHT = 60,
  PROMPT_MAX_HEIGHT = 400,
  PROMPT_LINE_HEIGHT = 18,
}

local KEY_ROOTS = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" }
local scale_names_cache = nil
local key_options_cache = nil

local function is_empty_or_unknown_key(key)
  local val = tostring(key or ""):lower()
  return val == "" or val == "unknown" or val == "auto"
end

local function extract_scale_names()
  if scale_names_cache then
    return scale_names_cache
  end

  local script_dir = utils.get_script_dir()
  local path = utils.path_join(script_dir, "..", "..", "bridge", "music_theory.py")
  local content = utils.read_file(path)
  if not content then
    scale_names_cache = {}
    return scale_names_cache
  end

  local start_pos = content:find("SCALE_INTERVALS%s*=%s*{")
  if not start_pos then
    scale_names_cache = {}
    return scale_names_cache
  end

  local brace_start = content:find("{", start_pos)
  if not brace_start then
    scale_names_cache = {}
    return scale_names_cache
  end

  local depth = 0
  local block_end = nil
  local i = brace_start
  while i <= #content do
    local ch = content:sub(i, i)
    if ch == "{" then
      depth = depth + 1
    elseif ch == "}" then
      depth = depth - 1
      if depth == 0 then
        block_end = i
        break
      end
    end
    i = i + 1
  end

  if not block_end then
    scale_names_cache = {}
    return scale_names_cache
  end

  local block = content:sub(brace_start + 1, block_end - 1)
  local names = {}
  for name in block:gmatch("[\"']([^\"']+)[\"']%s*:") do
    if name ~= "" then
      table.insert(names, name)
    end
  end

  scale_names_cache = names
  return scale_names_cache
end

local function get_key_options()
  if key_options_cache then
    return key_options_cache
  end

  local scales = extract_scale_names()
  if #scales == 0 then
    scales = { "major", "minor" }
  end

  local options = {}
  for _, root in ipairs(KEY_ROOTS) do
    for _, scale in ipairs(scales) do
      table.insert(options, root .. " " .. scale)
    end
  end

  key_options_cache = options
  return key_options_cache
end

local function escape_separator(s)
  return (s or ""):gsub(FALLBACK_SEPARATOR, "\\|")
end

local function unescape_separator(s)
  return (s or ""):gsub("\\|", FALLBACK_SEPARATOR)
end

local function split_by_separator(s, sep, count)
  local parts = {}
  local pattern = "([^" .. sep .. "]*)"
  for part in s:gmatch(pattern) do
    table.insert(parts, unescape_separator(part))
    if #parts >= count then
      break
    end
  end
  while #parts < count do
    table.insert(parts, "")
  end
  return parts
end

local function draw_section_header(ctx, text)
  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_Separator(ctx)
  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), UI.SECTION_COLOR)
  reaper.ImGui_Text(ctx, text)
  reaper.ImGui_PopStyleColor(ctx)
  reaper.ImGui_Spacing(ctx)
end

local function draw_label(ctx, text)
  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), UI.LABEL_COLOR)
  reaper.ImGui_Text(ctx, text)
  reaper.ImGui_PopStyleColor(ctx)
end

local function draw_combo(ctx, id, current_value, items, on_select)
  reaper.ImGui_PushItemWidth(ctx, UI.COMBO_WIDTH)
  if reaper.ImGui_BeginCombo(ctx, id, current_value) then
    for _, item in ipairs(items) do
      local display, value
      if type(item) == "table" then
        display = item.display
        value = item.value
      else
        display = item
        value = item
      end
      local selected = value == current_value
      if reaper.ImGui_Selectable(ctx, display, selected) then
        on_select(value, display)
      end
    end
    reaper.ImGui_EndCombo(ctx)
  end
  reaper.ImGui_PopItemWidth(ctx)
end

local function draw_input(ctx, id, value, flags)
  reaper.ImGui_PushItemWidth(ctx, UI.INPUT_WIDTH)
  local changed, new_val = reaper.ImGui_InputText(ctx, id, value or "", flags or 0)
  reaper.ImGui_PopItemWidth(ctx)
  return changed, new_val
end

local function count_lines(text)
  if not text or text == "" then
    return 1
  end
  local count = 1
  for _ in text:gmatch("\n") do
    count = count + 1
  end
  return count
end

local function calc_prompt_height(text)
  local lines = count_lines(text)
  local height = math.max(UI.PROMPT_MIN_HEIGHT, lines * UI.PROMPT_LINE_HEIGHT + 16)
  return math.min(height, UI.PROMPT_MAX_HEIGHT)
end

local function is_near_zero(v)
  return math.abs(v or 0) < UI.BAR_ALIGN_EPS
end

local function get_time_selection_info()
  local start_sec, end_sec = utils.get_time_selection()
  if not start_sec or not end_sec or start_sec == end_sec then
    return nil
  end

  local start_beats, start_meas, start_cml, _, start_cdenom = reaper.TimeMap2_timeToBeats(0, start_sec)
  local end_beats, end_meas = reaper.TimeMap2_timeToBeats(0, end_sec)

  local num = math.floor((start_cml or 4) + 0.5)
  local denom = math.floor((start_cdenom or 4) + 0.5)
  if num <= 0 then num = 4 end
  if denom <= 0 then denom = 4 end

  local aligned_start = is_near_zero(start_beats)
  local aligned_end = is_near_zero(end_beats)

  local bars_int = nil
  if aligned_start and aligned_end and start_meas and end_meas then
    bars_int = end_meas - start_meas
    if bars_int < 0 then
      bars_int = 0
    end
  end

  local start_qn = reaper.TimeMap2_timeToQN(0, start_sec)
  local end_qn = reaper.TimeMap2_timeToQN(0, end_sec)
  local length_qn = end_qn - start_qn
  local quarters_per_bar = num * (4.0 / denom)
  local bars_float = quarters_per_bar > 0 and (length_qn / quarters_per_bar) or nil

  local start_bar = (start_meas or 0) + 1

  return {
    start_sec = start_sec,
    end_sec = end_sec,
    start_bar = start_bar,
    bars_int = bars_int,
    bars_float = bars_float,
    num = num,
    denom = denom,
    aligned_start = aligned_start,
    aligned_end = aligned_end,
  }
end

local function build_bar_ruler(start_bar, bars, group_size)
  local max_bars = UI.BAR_RULER_MAX_BARS
  local shown = math.min(bars, max_bars)
  local out = {}
  local g = math.max(1, group_size or 4)

  for i = 0, shown - 1 do
    local bar_num = start_bar + i
    if i % g == 0 then
      table.insert(out, string.format("[%d]", bar_num))
    end
    table.insert(out, UI.BAR_RULER_CHAR)
  end

  if bars > shown then
    table.insert(out, string.format("… (+%d)", bars - shown))
  end

  return table.concat(out, "")
end

local function draw_time_selection_bar_counter(ctx)
  local info = get_time_selection_info()
  if not info then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0x808080FF)
    reaper.ImGui_TextWrapped(ctx, "No time selection set. Bars count is based on your time selection.")
    reaper.ImGui_PopStyleColor(ctx)
    return
  end

  local bars_text = ""
  if info.bars_int then
    local end_bar = info.start_bar + info.bars_int - 1
    bars_text = string.format("Selected bars: %d (%d–%d)", info.bars_int, info.start_bar, end_bar)
  else
    local approx = info.bars_float and string.format("%.2f", info.bars_float) or "?"
    bars_text = string.format("Selected bars: ~%s", approx)
  end

  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), UI.ACCENT_COLOR)
  reaper.ImGui_Text(ctx, bars_text)
  reaper.ImGui_PopStyleColor(ctx)

  if info.bars_int and info.bars_int > 0 then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), UI.LABEL_COLOR)
    reaper.ImGui_Text(ctx, string.format("Time signature at start: %d/%d", info.num, info.denom))
    reaper.ImGui_PopStyleColor(ctx)

    reaper.ImGui_TextWrapped(ctx, build_bar_ruler(info.start_bar, info.bars_int, info.num))
  end

  if not info.aligned_start or not info.aligned_end then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0xFFAA00FF)
    reaper.ImGui_TextWrapped(ctx, "⚠ Time selection is not aligned to bar boundaries.")
    reaper.ImGui_PopStyleColor(ctx)
  end
end

function M.run_dialog_fallback(state, profile_list, profiles_by_id, on_generate)
  local profile_names = {}
  for _, profile in ipairs(profile_list) do
    table.insert(profile_names, profile.id .. " - " .. profile.name)
  end
  reaper.ShowMessageBox(
    "Available profiles:\n" .. table.concat(profile_names, "\n"),
    const.SCRIPT_NAME,
    0
  )

  local default_key = state.key or const.DEFAULT_KEY
  if state.key_mode == "Manual" and is_empty_or_unknown_key(default_key) then
    default_key = const.DEFAULT_MANUAL_KEY
  end

  local defaults = {
    escape_separator(state.profile_id or ""),
    escape_separator(state.articulation_name or ""),
    escape_separator(state.generation_type or const.DEFAULT_GENERATION_TYPE),
    escape_separator(state.prompt or ""),
    state.use_selected_tracks and "1" or "0",
    state.insert_target or const.INSERT_TARGET_ACTIVE,
    state.key_mode == "Auto" and "auto" or default_key,
    state.allow_tempo_changes and "1" or "0",
  }
  local labels = table.concat({
    "Profile ID",
    "Articulation",
    "Type (Melody/Arpeggio/Bass Line/Chords)",
    "Instructions",
    "Use selected items (0/1)",
    "Insert target (active/new)",
    "Key",
    "Allow tempo changes (0/1)",
  }, ",")
  local ok, values = reaper.GetUserInputs(
    const.SCRIPT_NAME,
    const.FALLBACK_FIELD_COUNT,
    labels,
    table.concat(defaults, FALLBACK_SEPARATOR)
  )
  if not ok then
    return
  end
  local parts = split_by_separator(values, FALLBACK_SEPARATOR, const.FALLBACK_FIELD_COUNT)
  state.profile_id = parts[1] ~= "" and parts[1] or state.profile_id
  state.articulation_name = parts[2] ~= "" and parts[2] or state.articulation_name
  state.generation_type = parts[3] ~= "" and parts[3] or const.DEFAULT_GENERATION_TYPE
  state.prompt = parts[4] or ""
  state.use_selected_tracks = parts[5] == "1"
  state.insert_target = parts[6] == const.INSERT_TARGET_NEW and const.INSERT_TARGET_NEW or const.INSERT_TARGET_ACTIVE
  state.key = parts[7] ~= "" and parts[7] or const.DEFAULT_KEY
  state.allow_tempo_changes = parts[8] == "1"
  if state.key:lower() == "auto" then
    state.key_mode = "Auto"
    state.key = const.DEFAULT_KEY
  end

  if not profiles_by_id[state.profile_id] then
    utils.show_error("Unknown profile ID.")
    return
  end
  on_generate(state)
end

local function draw_instrument_section(ctx, state, profile_list, profiles_by_id)
  draw_section_header(ctx, "🎵 Instrument")

  draw_label(ctx, "Profile")
  local profile_preview = state.profile_name ~= "" and state.profile_name or "<select profile>"
  local profile_items = {}
  for _, profile in ipairs(profile_list) do
    table.insert(profile_items, { display = profile.name, value = profile.id })
  end
  draw_combo(ctx, "##profile_id", profile_preview, profile_items, function(value)
    state.profile_id = value
    local profile = profiles_by_id[value]
    if profile then
      state.profile_name = profile.name
      state.articulation_list = profiles.build_articulation_list(profile)
      state.articulation_name = profiles.get_default_articulation(profile)
      state.articulation_info = (profile.articulations or {}).map or {}
    end
  end)

  if state.profile_id and state.profile_id ~= "" and #(state.articulation_list or {}) > 0 and not state.free_mode then
    reaper.ImGui_Spacing(ctx)
    draw_label(ctx, "Articulation")
    local current_art_info = state.articulation_info and state.articulation_info[state.articulation_name]
    local art_label = "<none>"
    if state.articulation_name ~= "" then
      if current_art_info and current_art_info.description then
        art_label = current_art_info.description
      else
        art_label = state.articulation_name
      end
    end
    local art_items = {}
    for _, art in ipairs(state.articulation_list or {}) do
      local art_info = state.articulation_info and state.articulation_info[art]
      local display_name = art
      if art_info and art_info.description then
        display_name = art_info.description
      end
      table.insert(art_items, { display = display_name, value = art })
    end
    draw_combo(ctx, "##articulation", art_label, art_items, function(value)
      state.articulation_name = value
    end)
  end
end

local function draw_generation_section(ctx, state, callbacks, tracks_info)
  draw_section_header(ctx, "⚡ Generation")

  local changed_free, free_mode = reaper.ImGui_Checkbox(ctx, "Free Mode (AI chooses articulations, type & style)", state.free_mode or false)
  if changed_free then
    state.free_mode = free_mode
  end

  if state.free_mode then
    reaper.ImGui_Spacing(ctx)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0x80B0FFFF)
    reaper.ImGui_TextWrapped(ctx, "AI will autonomously select articulations, generation type and style based on context and instructions.")
    reaper.ImGui_PopStyleColor(ctx)
  else
    reaper.ImGui_Spacing(ctx)
    draw_label(ctx, "Type")
    draw_combo(ctx, "##gen_type", state.generation_type or const.DEFAULT_GENERATION_TYPE, const.GENERATION_TYPES, function(value)
      state.generation_type = value
    end)

    reaper.ImGui_Spacing(ctx)
    draw_label(ctx, "Style")
    draw_combo(ctx, "##gen_style", state.generation_style or const.DEFAULT_GENERATION_STYLE, const.GENERATION_STYLES, function(value)
      state.generation_style = value
    end)
  end

  reaper.ImGui_Spacing(ctx)
  draw_label(ctx, "Additional Instructions")
  
  local prompt_text = state.prompt or ""
  local prompt_height = calc_prompt_height(prompt_text)
  local avail_width = reaper.ImGui_GetContentRegionAvail(ctx)
  
  local flags = reaper.ImGui_InputTextFlags_AllowTabInput()
  local changed, new_prompt = reaper.ImGui_InputTextMultiline(
    ctx, 
    "##prompt_input", 
    prompt_text, 
    avail_width, 
    prompt_height, 
    flags
  )
  if changed then
    state.prompt = new_prompt
  end
  
  local has_prompt = state.prompt and state.prompt:match("%S")
  local can_enhance = has_prompt and callbacks and callbacks.on_enhance
  
  if state.enhance_in_progress then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Button(), 0x555555FF)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonHovered(), 0x555555FF)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonActive(), 0x555555FF)
    reaper.ImGui_Button(ctx, "⏳ Enhancing...", avail_width, 24)
    reaper.ImGui_PopStyleColor(ctx, 3)
  elseif can_enhance then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Button(), UI.ENHANCE_BTN_COLOR)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonHovered(), UI.ENHANCE_BTN_HOVER)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonActive(), UI.ENHANCE_BTN_ACTIVE)
    if reaper.ImGui_Button(ctx, "✨ Enhance Prompt", avail_width, 24) then
      callbacks.on_enhance(state, tracks_info)
    end
    reaper.ImGui_PopStyleColor(ctx, 3)
  else
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Button(), 0x444444FF)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonHovered(), 0x444444FF)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonActive(), 0x444444FF)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0x888888FF)
    reaper.ImGui_Button(ctx, "✨ Enhance Prompt", avail_width, 24)
    reaper.ImGui_PopStyleColor(ctx, 4)
  end

  reaper.ImGui_Spacing(ctx)
  local changed_tempo, allow_tempo = reaper.ImGui_Checkbox(ctx, "Allow tempo changes (AI)", state.allow_tempo_changes or false)
  if changed_tempo then
    state.allow_tempo_changes = allow_tempo
  end
  if state.allow_tempo_changes then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0x90A0B0FF)
    reaper.ImGui_TextWrapped(ctx, "AI may output tempo markers within the selected range.")
    reaper.ImGui_PopStyleColor(ctx)
  end
end

local function draw_context_section(ctx, state)
  draw_section_header(ctx, "🎯 Context & Target")

  local changed_ctx, use_ctx = reaper.ImGui_Checkbox(ctx, "Use selected items as context", state.use_selected_tracks)
  if changed_ctx then
    state.use_selected_tracks = use_ctx
  end

  reaper.ImGui_Spacing(ctx)
  draw_label(ctx, "Insert generated notes to")
  local target_items = {
    { display = "Active track", value = const.INSERT_TARGET_ACTIVE },
    { display = "New track", value = const.INSERT_TARGET_NEW },
  }
  local target_label = state.insert_target == const.INSERT_TARGET_NEW and "New track" or "Active track"
  draw_combo(ctx, "##target", target_label, target_items, function(value)
    state.insert_target = value
  end)

  reaper.ImGui_Spacing(ctx)
  draw_label(ctx, "Key Detection")
  local key_modes = {
    { display = "Auto (detect from context)", value = "Auto" },
    { display = "Unknown", value = "Unknown" },
    { display = "Manual", value = "Manual" },
  }
  local key_mode_label = state.key_mode or "Unknown"
  if key_mode_label == "Auto" then
    key_mode_label = "Auto (detect from context)"
  end
  draw_combo(ctx, "##keymode", key_mode_label, key_modes, function(value)
    state.key_mode = value
    if value == "Unknown" then
      state.key = const.DEFAULT_KEY
    elseif value == "Manual" and is_empty_or_unknown_key(state.key) then
      state.key = const.DEFAULT_MANUAL_KEY
    end
  end)

  if state.key_mode == "Manual" then
    reaper.ImGui_Spacing(ctx)
    if is_empty_or_unknown_key(state.key) then
      state.key = const.DEFAULT_MANUAL_KEY
    end
    draw_label(ctx, "Key (Manual)")
    local key_options = get_key_options()
    draw_combo(ctx, "##key_combo", state.key or const.DEFAULT_MANUAL_KEY, key_options, function(value)
      state.key = value
    end)
    local changed_key, key = draw_input(ctx, "##key_input", state.key or "")
    if changed_key then
      state.key = key
    end
  end
end

local function draw_api_section(ctx, state)
  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_Spacing(ctx)

  local header_flags = reaper.ImGui_TreeNodeFlags_Framed()
  if reaper.ImGui_CollapsingHeader(ctx, "⚙️ API Settings", header_flags) then
    reaper.ImGui_Spacing(ctx)

    draw_label(ctx, "Provider")
    local api_items = {
      { display = "Local (LM Studio)", value = const.API_PROVIDER_LOCAL },
      { display = "OpenRouter", value = const.API_PROVIDER_OPENROUTER },
    }
    local api_label = state.api_provider == const.API_PROVIDER_OPENROUTER and "OpenRouter" or "Local (LM Studio)"
    draw_combo(ctx, "##api_provider", api_label, api_items, function(value)
      state.api_provider = value
      if value == const.API_PROVIDER_LOCAL then
        state.api_base_url = const.DEFAULT_MODEL_BASE_URL
        state.model_name = const.DEFAULT_MODEL_NAME
      else
        state.api_base_url = const.DEFAULT_OPENROUTER_BASE_URL
        state.model_name = const.DEFAULT_OPENROUTER_MODEL
      end
    end)

    if state.api_provider == const.API_PROVIDER_OPENROUTER then
      reaper.ImGui_Spacing(ctx)
      draw_label(ctx, "API Key")
      local changed_key, new_key = draw_input(ctx, "##api_key", state.api_key or "", reaper.ImGui_InputTextFlags_Password())
      if changed_key then
        state.api_key = new_key
      end
    end

    reaper.ImGui_Spacing(ctx)
    draw_label(ctx, "Base URL")
    local changed_url, new_url = draw_input(ctx, "##api_base_url", state.api_base_url or "")
    if changed_url then
      state.api_base_url = new_url
    end

    reaper.ImGui_Spacing(ctx)
    draw_label(ctx, "Model Name")
    local changed_model, new_model = draw_input(ctx, "##model_name", state.model_name or "")
    if changed_model then
      state.model_name = new_model
    end

    reaper.ImGui_Spacing(ctx)
  end
end

local function draw_multi_track_section(ctx, state, profile_list, profiles_by_id)
  draw_section_header(ctx, "🎼 Multi-Track Generation")

  draw_time_selection_bar_counter(ctx)
  reaper.ImGui_Spacing(ctx)
  
  local tracks_info = profiles.get_selected_tracks_with_profiles(profile_list, profiles_by_id)
  local selected_count = #tracks_info
  
  if selected_count == 0 then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0x808080FF)
    reaper.ImGui_TextWrapped(ctx, "No tracks selected. Select 2+ tracks to generate parts for multiple instruments.")
    reaper.ImGui_PopStyleColor(ctx)
    return tracks_info
  end

  local matched_count = 0
  local unmatched = {}
  
  for _, track_data in ipairs(tracks_info) do
    if track_data.profile then
      matched_count = matched_count + 1
    else
      table.insert(unmatched, track_data.name)
    end
  end

  reaper.ImGui_Text(ctx, string.format("Selected tracks: %d", selected_count))
  
  if matched_count > 0 then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0x80FF80FF)
    reaper.ImGui_Text(ctx, string.format("✓ Profiles matched: %d", matched_count))
    reaper.ImGui_PopStyleColor(ctx)
  end
  
  if #unmatched > 0 then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0xFFAA00FF)
    reaper.ImGui_Text(ctx, string.format("⚠ No profile: %d", #unmatched))
    reaper.ImGui_PopStyleColor(ctx)
  end

  local tree_flags = reaper.ImGui_TreeNodeFlags_DefaultOpen()
  if reaper.ImGui_TreeNode(ctx, "Track → Profile Mapping", tree_flags) then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0x90A0B0FF)
    reaper.ImGui_TextWrapped(ctx, "Click on profile to change mapping manually")
    reaper.ImGui_PopStyleColor(ctx)
    reaper.ImGui_Spacing(ctx)
    
    local profile_items = {{ display = "(no profile)", value = "" }}
    for _, profile in ipairs(profile_list) do
      table.insert(profile_items, { display = profile.name, value = profile.id })
    end
    
    for i, track_data in ipairs(tracks_info) do
      local status_icon = track_data.profile and "✓" or "⚠"
      local profile_name = track_data.profile and track_data.profile.name or "(no match)"
      local color = track_data.profile and 0xB0FFB0FF or 0xFFAA00FF
      local is_manual = track_data.is_manual_profile
      
      reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), color)
      local label_text = string.format("%s %s", status_icon, track_data.name)
      if is_manual then
        label_text = label_text .. " [manual]"
      end
      reaper.ImGui_Text(ctx, label_text)
      reaper.ImGui_PopStyleColor(ctx)
      
      reaper.ImGui_SameLine(ctx)
      reaper.ImGui_Text(ctx, "→")
      reaper.ImGui_SameLine(ctx)
      
      reaper.ImGui_PushItemWidth(ctx, 180)
      local combo_id = "##track_profile_" .. tostring(i)
      if reaper.ImGui_BeginCombo(ctx, combo_id, profile_name) then
        for _, item in ipairs(profile_items) do
          local selected = item.value == (track_data.profile_id or "")
          if reaper.ImGui_Selectable(ctx, item.display, selected) then
            if item.value == "" then
              profiles.clear_track_profile_id(track_data.track)
            else
              profiles.save_track_profile_id(track_data.track, item.value)
            end
            track_data.profile_id = item.value ~= "" and item.value or nil
            track_data.profile = item.value ~= "" and profiles_by_id[item.value] or nil
            track_data.is_manual_profile = item.value ~= ""
          end
        end
        reaper.ImGui_EndCombo(ctx)
      end
      reaper.ImGui_PopItemWidth(ctx)
    end
    reaper.ImGui_TreePop(ctx)
  end

  return tracks_info
end

local function draw_generate_button(ctx, callbacks, state, tracks_info)
  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_Separator(ctx)
  reaper.ImGui_Spacing(ctx)

  local avail_width = reaper.ImGui_GetContentRegionAvail(ctx)

  local matched_count = 0
  if tracks_info then
    for _, t in ipairs(tracks_info) do
      if t.profile then
        matched_count = matched_count + 1
      end
    end
  end

  if callbacks.on_compose and matched_count >= 2 then
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Button(), UI.COMPOSE_BTN_COLOR)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonHovered(), UI.COMPOSE_BTN_HOVER)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonActive(), UI.COMPOSE_BTN_ACTIVE)

    local btn_label = string.format("🎼  Compose (%d Tracks)", matched_count)
    if reaper.ImGui_Button(ctx, btn_label, avail_width, UI.BUTTON_HEIGHT) then
      callbacks.on_compose(state)
    end

    reaper.ImGui_PopStyleColor(ctx, 3)
    
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), 0x90A0B0FF)
    reaper.ImGui_TextWrapped(ctx, "Generates tracks sequentially, each part aware of previous ones for cohesive orchestration.")
    reaper.ImGui_PopStyleColor(ctx)
    
    reaper.ImGui_Spacing(ctx)
  end

  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Button(), UI.GENERATE_BTN_COLOR)
  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonHovered(), UI.GENERATE_BTN_HOVER)
  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonActive(), UI.GENERATE_BTN_ACTIVE)

  if reaper.ImGui_Button(ctx, "🎹  Generate (Single Track)", avail_width, UI.BUTTON_HEIGHT) then
    callbacks.on_generate(state)
  end

  reaper.ImGui_PopStyleColor(ctx, 3)
end

function M.run_imgui(state, profile_list, profiles_by_id, callbacks)
  local ctx = reaper.ImGui_CreateContext(const.SCRIPT_NAME)

  reaper.ImGui_SetConfigVar(ctx, reaper.ImGui_ConfigVar_WindowsMoveFromTitleBarOnly(), 1)

  local function loop()
    reaper.ImGui_PushStyleVar(ctx, reaper.ImGui_StyleVar_WindowPadding(), 16, 12)
    reaper.ImGui_PushStyleVar(ctx, reaper.ImGui_StyleVar_ItemSpacing(), 8, UI.ITEM_SPACING)
    reaper.ImGui_PushStyleVar(ctx, reaper.ImGui_StyleVar_FrameRounding(), 4)
    reaper.ImGui_PushStyleVar(ctx, reaper.ImGui_StyleVar_FramePadding(), 8, 6)

    local window_flags = reaper.ImGui_WindowFlags_NoCollapse()
    reaper.ImGui_SetNextWindowSize(ctx, UI.WINDOW_WIDTH, UI.WINDOW_HEIGHT, reaper.ImGui_Cond_FirstUseEver())

    local visible, open = reaper.ImGui_Begin(ctx, const.SCRIPT_NAME, true, window_flags)

    if visible then
      draw_instrument_section(ctx, state, profile_list, profiles_by_id)
      local tracks_info = draw_multi_track_section(ctx, state, profile_list, profiles_by_id)
      draw_generation_section(ctx, state, callbacks, tracks_info)
      draw_context_section(ctx, state)
      draw_api_section(ctx, state)
      draw_generate_button(ctx, callbacks, state, tracks_info)
    end

    reaper.ImGui_End(ctx)

    reaper.ImGui_PopStyleVar(ctx, 4)

    if open then
      reaper.defer(loop)
    else
      if reaper.ImGui_DestroyContext then
        reaper.ImGui_DestroyContext(ctx)
      end
    end
  end
  reaper.defer(loop)
end

return M
