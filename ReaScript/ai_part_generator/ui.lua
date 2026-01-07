local const = require("ai_part_generator.constants")
local profiles = require("ai_part_generator.profiles")
local utils = require("ai_part_generator.utils")

local M = {}

local FALLBACK_SEPARATOR = "|"

local UI = {
  WINDOW_WIDTH = 500,
  WINDOW_HEIGHT = 650,
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
}

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

  local defaults = {
    escape_separator(state.profile_id or ""),
    escape_separator(state.articulation_name or ""),
    escape_separator(state.generation_type or const.DEFAULT_GENERATION_TYPE),
    escape_separator(state.prompt or ""),
    state.use_selected_tracks and "1" or "0",
    state.insert_target or const.INSERT_TARGET_ACTIVE,
    state.key_mode == "Auto" and "auto" or (state.key or const.DEFAULT_KEY),
  }
  local labels = table.concat({
    "Profile ID",
    "Articulation",
    "Type (Melody/Arpeggio/Bass Line/Chords)",
    "Instructions",
    "Use selected tracks (0/1)",
    "Insert target (active/new)",
    "Key",
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

local function draw_generation_section(ctx, state)
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
  local changed, new_prompt = draw_input(ctx, "##prompt_input", state.prompt or "")
  if changed then
    state.prompt = new_prompt
  end
end

local function draw_context_section(ctx, state)
  draw_section_header(ctx, "🎯 Context & Target")

  local changed_ctx, use_ctx = reaper.ImGui_Checkbox(ctx, "Use selected tracks as context", state.use_selected_tracks)
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
    end
  end)

  if state.key_mode == "Manual" then
    reaper.ImGui_Spacing(ctx)
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

  if reaper.ImGui_TreeNode(ctx, "Track Details") then
    for _, track_data in ipairs(tracks_info) do
      local status_icon = track_data.profile and "✓" or "⚠"
      local profile_name = track_data.profile and track_data.profile.name or "(no match)"
      local color = track_data.profile and 0xB0FFB0FF or 0xFFAA00FF
      
      reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), color)
      reaper.ImGui_Text(ctx, string.format("%s %s → %s", status_icon, track_data.name, profile_name))
      reaper.ImGui_PopStyleColor(ctx)
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
      draw_generation_section(ctx, state)
      draw_context_section(ctx, state)
      local tracks_info = draw_multi_track_section(ctx, state, profile_list, profiles_by_id)
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
