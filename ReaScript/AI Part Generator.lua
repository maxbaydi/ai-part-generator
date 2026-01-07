-- AI Part Generator - entry point

local function get_script_dir()
  local info = debug.getinfo(1, "S")
  local source = info.source
  if source:sub(1, 1) == "@" then
    source = source:sub(2)
  end
  return source:match("^(.*)[/\\]") or "."
end

local script_dir = get_script_dir()
_G.AI_PART_GENERATOR_SCRIPT_DIR = script_dir
package.path = package.path
  .. ";"
  .. script_dir
  .. "/?.lua;"
  .. script_dir
  .. "/ai_part_generator/?.lua"

for name, _ in pairs(package.loaded) do
  if name == "ai_part_generator" or name:match("^ai_part_generator%.") then
    package.loaded[name] = nil
  end
end

local ok, main = pcall(require, "ai_part_generator.main")
if ok and main and main.main then
  main.main()
else
  reaper.ShowMessageBox("Failed to load AI Part Generator modules.", "AI Part Generator", 0)
end
