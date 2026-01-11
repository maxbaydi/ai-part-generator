local M = {}

M.colors = {
  text = 0xE0E0E0FF,
  text_dim = 0x909090FF,
  text_warning = 0xFFAA00FF,
  text_error = 0xFF5555FF,
  text_success = 0x80FF80FF,
  
  bg_window = 0x202020FF,
  bg_input = 0x303030FF,
  
  header_bg = 0x353535FF,
  header_text = 0xFFFFFFFF,
  
  accent = 0x4A9FFFFF,
  
  btn_primary = 0x2D7D46FF,
  btn_primary_hover = 0x3A9D5AFF,
  btn_primary_active = 0x248F3EFF,
  
  btn_secondary = 0x444444FF,
  btn_secondary_hover = 0x555555FF,
  btn_secondary_active = 0x666666FF,
  
  btn_action = 0x4D3D7DFF, -- Enhance/Compose
  btn_action_hover = 0x5D4D8DFF,
  btn_action_active = 0x3D2D6DFF,
  
  btn_danger = 0x6D4D4DFF,
  btn_danger_hover = 0x8D5D5DFF,
  
  separator = 0x404040FF,
}

M.layout = {
  width = 500,
  height = 700,
  item_spacing = { 8, 8 },
  padding = { 12, 12 },
  button_height = 32,
  input_height = 24,
  section_spacing = 16,
}

return M
