local const = require("ai_part_generator.constants")
local profiles = require("ai_part_generator.profiles")
local utils = require("ai_part_generator.utils")
local theme = require("ai_part_generator.ui_theme")
local comp = require("ai_part_generator.ui_components")

local M = {}

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

local function is_near_zero(v)
  return math.abs(v or 0) < 1e-4
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

  local bars_int = nil
  if is_near_zero(start_beats) and is_near_zero(end_beats) and start_meas and end_meas then
    bars_int = math.max(0, end_meas - start_meas)
  end

  return {
    start_sec = start_sec,
    end_sec = end_sec,
    start_bar = (start_meas or 0) + 1,
    bars_int = bars_int,
    num = num,
    denom = denom,
  }
end

local function draw_time_info(ctx)
  local info = get_time_selection_info()
  if not info then
    comp.status_text(ctx, "No time selection set.", "dim")
    return
  end

  local text = string.format("Time Selection: %d/%d", info.num, info.denom)
  if info.bars_int then
    text = text .. string.format(" • %d Bars (%d-%d)", info.bars_int, info.start_bar, info.start_bar + info.bars_int)
  else
    text = text .. " • (Unsnapped)"
  end
  
  comp.label(ctx, text)
end

--------------------------------------------------------------------------------
-- Shared Sections
--------------------------------------------------------------------------------

local function draw_key_selector(ctx, state)
  comp.header(ctx, "🎵 Musical Key")
  
  local key_modes = {
    { display = "Auto (Detect from Context)", value = "Auto" },
    { display = "Manual", value = "Manual" },
    { display = "Unknown (Model decides)", value = "Unknown" },
  }
  
  comp.combo(ctx, "##keymode", state.key_mode, key_modes, function(val)
    state.key_mode = val
    if val == "Unknown" then state.key = const.DEFAULT_KEY end
    if val == "Manual" and utils.is_empty_or_unknown_key(state.key) then
      state.key = const.DEFAULT_MANUAL_KEY
    end
  end, 200)

  if state.key_mode == "Manual" then
    reaper.ImGui_SameLine(ctx)
    local options = utils.get_key_options()
    comp.combo(ctx, "##key_manual", state.key, options, function(val)
      state.key = val
    end, 150)
  end
end

local function draw_prompt_area(ctx, state, callbacks, tracks_info)
  comp.header(ctx, "📝 Instructions")
  
  local w = reaper.ImGui_GetContentRegionAvail(ctx)
  local changed, new_prompt = reaper.ImGui_InputTextMultiline(ctx, "##prompt", state.prompt or "", w, 80)
  if changed then state.prompt = new_prompt end
  
  reaper.ImGui_Spacing(ctx)
  
  if callbacks.on_enhance then
    local has_prompt = state.prompt and state.prompt:match("%S")
    local btn_label = state.enhance_in_progress and "⏳ Enhancing..." or "✨ Enhance Prompt with AI"
    
    comp.action_button(ctx, btn_label, function()
      callbacks.on_enhance(state, tracks_info)
    end, { disabled = not has_prompt or state.enhance_in_progress })
  end
end

--------------------------------------------------------------------------------
-- Tab: Single Generator
--------------------------------------------------------------------------------

local function draw_tab_generator(ctx, state, profile_list, profiles_by_id, callbacks)
  reaper.ImGui_BeginChild(ctx, "gen_scroll", 0, -40) -- Leave space for footer
  
  -- 1. Instrument
  comp.header(ctx, "🎻 Instrument")
  
  local profile_items = {}
  for _, p in ipairs(profile_list) do
    table.insert(profile_items, { display = p.name, value = p.id })
  end
  
  comp.label(ctx, "Profile")
  comp.combo(ctx, "##profile", state.profile_id, profile_items, function(val)
    state.profile_id = val
    local p = profiles_by_id[val]
    if p then
      state.profile_name = p.name
      state.articulation_list = profiles.build_articulation_list(p)
      state.articulation_name = profiles.get_default_articulation(p)
      state.articulation_info = (p.articulations or {}).map or {}
    end
  end)

  if state.profile_id and not state.free_mode and #(state.articulation_list or {}) > 0 then
    comp.label(ctx, "Articulation")
    local art_items = {}
    for _, art in ipairs(state.articulation_list) do
      local info = state.articulation_info and state.articulation_info[art]
      local disp = (info and info.description) and info.description or art
      table.insert(art_items, { display = disp, value = art })
    end
    comp.combo(ctx, "##art", state.articulation_name, art_items, function(val)
      state.articulation_name = val
    end)
  end

  -- 2. Generation Settings
  comp.header(ctx, "⚡ Generation Settings")
  
  comp.checkbox(ctx, "Free Mode (AI chooses details)", state.free_mode, function(v) state.free_mode = v end)
  
  if not state.free_mode then
    comp.label(ctx, "Type")
    comp.combo(ctx, "##type", state.generation_type, const.GENERATION_TYPES, function(v) state.generation_type = v end)
    
    comp.label(ctx, "Musical Style")
    comp.combo(ctx, "##mus_style", state.musical_style, const.MUSICAL_STYLES, function(v) state.musical_style = v end)

    comp.label(ctx, "Mood")
    comp.combo(ctx, "##gen_mood", state.generation_mood, const.GENERATION_MOODS, function(v) state.generation_mood = v end)
  else
    comp.status_text(ctx, "In Free Mode, the AI decides articulation and style based on your prompt.", "dim")
  end

  reaper.ImGui_Spacing(ctx)
  comp.checkbox(ctx, "Allow Tempo Changes", state.allow_tempo_changes, function(v) state.allow_tempo_changes = v end)
  
  draw_key_selector(ctx, state)

  -- 3. Context & Target
  comp.header(ctx, "🎯 Context")
  comp.checkbox(ctx, "Use Selected Items as Context", state.use_selected_tracks, function(v) state.use_selected_tracks = v end)
  
  reaper.ImGui_SameLine(ctx)
  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_SameLine(ctx)
  
  comp.label(ctx, "Insert To: ")
  reaper.ImGui_SameLine(ctx)
  local targets = {
    { display = "Active Track", value = const.INSERT_TARGET_ACTIVE },
    { display = "New Track", value = const.INSERT_TARGET_NEW }
  }
  comp.combo(ctx, "##target", state.insert_target, targets, function(v) state.insert_target = v end, 150)

  -- 4. Prompt
  draw_prompt_area(ctx, state, callbacks, nil)

  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_Separator(ctx)
  reaper.ImGui_Spacing(ctx)
  comp.primary_button(ctx, "GENERATE PART", function()
    callbacks.on_generate(state)
  end)

  reaper.ImGui_EndChild(ctx)
end

--------------------------------------------------------------------------------
-- Tab: Multi-Track / Arranger
--------------------------------------------------------------------------------

local function draw_tab_arranger(ctx, state, profile_list, profiles_by_id, callbacks)
  reaper.ImGui_BeginChild(ctx, "arr_scroll", 0, -40)

  comp.sub_header(ctx, "1. Source Sketch")
  
  local source = state.arrange_source
  if source then
    comp.status_text(ctx, "✓ Source: " .. (source.track_name or "Unknown"), "success")
    comp.status_text(ctx, string.format("%d notes in sketch", source.notes and #source.notes or 0), "dim")
    
    reaper.ImGui_Spacing(ctx)
    if reaper.ImGui_Button(ctx, "Update Source") then callbacks.on_set_arrange_source(state) end
    reaper.ImGui_SameLine(ctx)
    if reaper.ImGui_Button(ctx, "Clear Source") then callbacks.on_clear_arrange_source(state) end
  else
    comp.status_text(ctx, "Select a MIDI item containing your sketch/piano part:", "warning")
    if reaper.ImGui_Button(ctx, "📌 Set Selected Item as Source", -1) then
      callbacks.on_set_arrange_source(state)
    end
  end

  comp.sub_header(ctx, "2. Target Tracks")
  
  local tracks_info = profiles.get_selected_tracks_with_profiles(profile_list, profiles_by_id)
  if #tracks_info == 0 then
    comp.status_text(ctx, "Select 2+ tracks in Reaper to arrange for.", "dim")
  else
    comp.label(ctx, string.format("%d Tracks Selected", #tracks_info))
    
    if reaper.ImGui_BeginTable(ctx, "track_table", 2, reaper.ImGui_TableFlags_BordersInnerH and reaper.ImGui_TableFlags_BordersInnerH() or 0) then
      reaper.ImGui_TableSetupColumn(ctx, "Track")
      reaper.ImGui_TableSetupColumn(ctx, "Profile")
      
      for i, t in ipairs(tracks_info) do
        reaper.ImGui_TableNextRow(ctx)
        reaper.ImGui_TableNextColumn(ctx)
        reaper.ImGui_Text(ctx, t.name)
        
        reaper.ImGui_TableNextColumn(ctx)
        -- Profile Selector
        local preview = t.profile and t.profile.name or "(No Profile)"
        reaper.ImGui_PushID(ctx, i)
        reaper.ImGui_SetNextItemWidth(ctx, -1)
        if reaper.ImGui_BeginCombo(ctx, "##tprof", preview) then
           -- Quick profile selection logic inline or helper? 
           -- keeping it simple for now, relying on auto-detect usually
           for _, p in ipairs(profile_list) do
             if reaper.ImGui_Selectable(ctx, p.name, t.profile_id == p.id) then
                profiles.save_track_profile_id(t.track, p.id)
                t.profile_id = p.id
                t.profile = p
             end
           end
           reaper.ImGui_EndCombo(ctx)
        end
        reaper.ImGui_PopID(ctx)
      end
      reaper.ImGui_EndTable(ctx)
    end
  end
  
  comp.sub_header(ctx, "3. Global Settings")
  
  comp.checkbox(ctx, "Free Mode (AI chooses details)", state.free_mode, function(v) state.free_mode = v end)

  if not state.free_mode then
    draw_key_selector(ctx, state)
    
    local use_style_mood = state.use_style_mood ~= false
    comp.checkbox(ctx, "Use Style & Mood", use_style_mood, function(v) state.use_style_mood = v end)
    
    if use_style_mood then
      comp.label(ctx, "Musical Style")
      comp.combo(ctx, "##mus_style_arr", state.musical_style, const.MUSICAL_STYLES, function(v) state.musical_style = v end)

      comp.label(ctx, "Mood")
      comp.combo(ctx, "##gen_mood_arr", state.generation_mood, const.GENERATION_MOODS, function(v) state.generation_mood = v end)
    else
      comp.status_text(ctx, "Style & Mood disabled. Generation will follow only the prompt.", "dim")
    end
  else
    comp.status_text(ctx, "In Free Mode, the AI decides style, mood and roles based on your prompt and context.", "dim")
    draw_key_selector(ctx, state)
  end
  
  reaper.ImGui_Spacing(ctx)
  comp.checkbox(ctx, "Allow Tempo/Time Sig Changes", state.allow_tempo_changes, function(v) state.allow_tempo_changes = v end)

  draw_prompt_area(ctx, state, callbacks, tracks_info)

  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_Separator(ctx)
  reaper.ImGui_Spacing(ctx)

  local can_arrange = source and #tracks_info > 0
  local can_compose = #tracks_info > 1
  
  if can_arrange then
    comp.action_button(ctx, "ARRANGE (From Source)", function() callbacks.on_arrange(state) end)
  elseif can_compose then
    comp.action_button(ctx, "COMPOSE (Scratch)", function() callbacks.on_compose(state) end)
  else
    comp.button(ctx, "Select Source or Tracks", nil, { disabled = true })
  end

  reaper.ImGui_EndChild(ctx)
end

--------------------------------------------------------------------------------
-- Tab: Settings
--------------------------------------------------------------------------------

local function draw_tab_settings(ctx, state)
  comp.header(ctx, "⚙️ API Configuration")
  
  local providers = {
    { display = "LM Studio (Local)", value = const.API_PROVIDER_LOCAL },
    { display = "OpenRouter (Cloud)", value = const.API_PROVIDER_OPENROUTER },
  }
  
  comp.label(ctx, "Provider")
  comp.combo(ctx, "##prov", state.api_provider, providers, function(val)
    state.api_provider = val
    if val == const.API_PROVIDER_LOCAL then
      state.api_base_url = const.DEFAULT_MODEL_BASE_URL
      state.model_name = const.DEFAULT_MODEL_NAME
    else
      state.api_base_url = const.DEFAULT_OPENROUTER_BASE_URL
      state.model_name = const.DEFAULT_OPENROUTER_MODEL
    end
  end)
  
  if state.api_provider == const.API_PROVIDER_OPENROUTER then
    comp.label(ctx, "API Key")
    comp.input_text(ctx, "##apikey", state.api_key, function(v) state.api_key = v end, { flags = reaper.ImGui_InputTextFlags_Password() })
  end
  
  comp.label(ctx, "Base URL")
  comp.input_text(ctx, "##baseurl", state.api_base_url, function(v) state.api_base_url = v end)
  
  comp.label(ctx, "Model Name")
  comp.input_text(ctx, "##model", state.model_name, function(v) state.model_name = v end)
end

--------------------------------------------------------------------------------
-- Main Entry
--------------------------------------------------------------------------------

function M.run_imgui(state, profile_list, profiles_by_id, callbacks)
  local ctx = reaper.ImGui_CreateContext(const.SCRIPT_NAME)
  reaper.ImGui_SetConfigVar(ctx, reaper.ImGui_ConfigVar_WindowsMoveFromTitleBarOnly(), 1)

  local function loop()
    -- Theme vars
    reaper.ImGui_PushStyleVar(ctx, reaper.ImGui_StyleVar_WindowPadding(), 12, 12)
    reaper.ImGui_PushStyleVar(ctx, reaper.ImGui_StyleVar_ItemSpacing(), 8, 8)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_WindowBg(), theme.colors.bg_window)
    reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), theme.colors.text)

    local visible, open = reaper.ImGui_Begin(ctx, const.SCRIPT_NAME, true, reaper.ImGui_WindowFlags_NoCollapse())
    
    if visible then
      -- Status Bar (Top)
      draw_time_info(ctx)
      reaper.ImGui_Separator(ctx)
      
      if reaper.ImGui_BeginTabBar(ctx, "MainTabs") then
        if reaper.ImGui_BeginTabItem(ctx, "Generate") then
          draw_tab_generator(ctx, state, profile_list, profiles_by_id, callbacks)
          reaper.ImGui_EndTabItem(ctx)
        end
        
        if reaper.ImGui_BeginTabItem(ctx, "Arrange / Compose") then
          draw_tab_arranger(ctx, state, profile_list, profiles_by_id, callbacks)
          reaper.ImGui_EndTabItem(ctx)
        end
        
        if reaper.ImGui_BeginTabItem(ctx, "Settings") then
          draw_tab_settings(ctx, state)
          reaper.ImGui_EndTabItem(ctx)
        end
        reaper.ImGui_EndTabBar(ctx)
      end
      
      reaper.ImGui_End(ctx)
    end

    reaper.ImGui_PopStyleColor(ctx, 2)
    reaper.ImGui_PopStyleVar(ctx, 2)

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

-- Fallback Dialog (Legacy/No-ImGui)
function M.run_dialog_fallback(state, profile_list, profiles_by_id, on_generate)
  -- Minimal implementation to satisfy "no dead code" but provide fallback
  local names = {}
  for _, p in ipairs(profile_list) do table.insert(names, p.id) end
  
  local ret, inputs = reaper.GetUserInputs(const.SCRIPT_NAME, 2, "Profile ID,Prompt", 
    (state.profile_id or "") .. "," .. (state.prompt or ""))
    
  if not ret then return end
  
  local pid, prm = inputs:match("([^,]+),([^,]*)")
  if profiles_by_id[pid] then
    state.profile_id = pid
    state.prompt = prm
    on_generate(state)
  else
    utils.show_error("Invalid Profile ID")
  end
end

return M
