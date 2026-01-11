local theme = require("ai_part_generator.ui_theme")
local utils = require("ai_part_generator.utils")

local M = {}

function M.push_style_color(idx, col)
  reaper.ImGui_PushStyleColor(ctx, idx, col)
end

function M.pop_style_color(count)
  reaper.ImGui_PopStyleColor(ctx, count or 1)
end

function M.header(ctx, text)
  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_TextColored(ctx, theme.colors.header_text, string.upper(text))
  reaper.ImGui_Separator(ctx)
  reaper.ImGui_Spacing(ctx)
end

function M.sub_header(ctx, text)
  reaper.ImGui_Spacing(ctx)
  reaper.ImGui_TextColored(ctx, theme.colors.accent, text)
  reaper.ImGui_Separator(ctx)
end

function M.label(ctx, text, tooltip)
  reaper.ImGui_TextColored(ctx, theme.colors.text_dim, text)
  if tooltip and reaper.ImGui_IsItemHovered(ctx) then
    reaper.ImGui_SetTooltip(ctx, tooltip)
  end
end

function M.button(ctx, label, onClick, opts)
  opts = opts or {}
  local w = opts.width or reaper.ImGui_GetContentRegionAvail(ctx)
  local h = opts.height or theme.layout.button_height
  
  local col_normal = opts.color or theme.colors.btn_secondary
  local col_hover = opts.color_hover or theme.colors.btn_secondary_hover
  local col_active = opts.color_active or theme.colors.btn_secondary_active

  if opts.disabled then
    col_normal = theme.colors.btn_secondary
    col_hover = theme.colors.btn_secondary
    col_active = theme.colors.btn_secondary
    reaper.ImGui_BeginDisabled(ctx)
  end

  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Button(), col_normal)
  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonHovered(), col_hover)
  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_ButtonActive(), col_active)

  if reaper.ImGui_Button(ctx, label, w, h) then
    if onClick and not opts.disabled then onClick() end
  end

  reaper.ImGui_PopStyleColor(ctx, 3)

  if opts.disabled then
    reaper.ImGui_EndDisabled(ctx)
  end
end

function M.primary_button(ctx, label, onClick, opts)
  opts = opts or {}
  opts.color = theme.colors.btn_primary
  opts.color_hover = theme.colors.btn_primary_hover
  opts.color_active = theme.colors.btn_primary_active
  M.button(ctx, label, onClick, opts)
end

function M.action_button(ctx, label, onClick, opts)
  opts = opts or {}
  opts.color = theme.colors.btn_action
  opts.color_hover = theme.colors.btn_action_hover
  opts.color_active = theme.colors.btn_action_active
  M.button(ctx, label, onClick, opts)
end

function M.combo(ctx, label_id, current_val, items, onSelect, width)
  width = width or -1
  reaper.ImGui_PushItemWidth(ctx, width)
  
  local display_val = current_val
  -- Try to find display name if items are objects
  for _, item in ipairs(items) do
    if type(item) == "table" and item.value == current_val then
      display_val = item.display
      break
    end
  end

  if reaper.ImGui_BeginCombo(ctx, label_id, display_val) then
    for _, item in ipairs(items) do
      local val = type(item) == "table" and item.value or item
      local disp = type(item) == "table" and item.display or item
      local selected = (val == current_val)
      
      if reaper.ImGui_Selectable(ctx, disp, selected) then
        onSelect(val)
      end
      if selected then
        reaper.ImGui_SetItemDefaultFocus(ctx)
      end
    end
    reaper.ImGui_EndCombo(ctx)
  end
  reaper.ImGui_PopItemWidth(ctx)
end

function M.input_text(ctx, label_id, value, onChange, opts)
  opts = opts or {}
  local flags = opts.flags or 0
  local w = opts.width or -1
  
  reaper.ImGui_PushItemWidth(ctx, w)
  local changed, new_val = reaper.ImGui_InputText(ctx, label_id, value or "", flags)
  reaper.ImGui_PopItemWidth(ctx)
  
  if changed and onChange then
    onChange(new_val)
  end
  return changed, new_val
end

function M.checkbox(ctx, label, value, onChange)
  local changed, new_val = reaper.ImGui_Checkbox(ctx, label, value)
  if changed and onChange then
    onChange(new_val)
  end
  return changed, new_val
end

function M.status_text(ctx, text, type)
  local col = theme.colors.text
  if type == "warning" then col = theme.colors.text_warning end
  if type == "error" then col = theme.colors.text_error end
  if type == "success" then col = theme.colors.text_success end
  if type == "dim" then col = theme.colors.text_dim end
  
  reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), col)
  reaper.ImGui_TextWrapped(ctx, text)
  reaper.ImGui_PopStyleColor(ctx)
end

return M
