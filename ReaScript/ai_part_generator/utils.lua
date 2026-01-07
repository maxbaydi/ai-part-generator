local const = require("ai_part_generator.constants")

local M = {}

local json = nil
local is_win = nil
local curl_available = nil

function M.log(msg)
end

function M.show_error(msg)
  reaper.ShowMessageBox(tostring(msg), const.SCRIPT_NAME, 0)
end

function M.exec_process(command, timeout_ms)
  local retval, stdout, stderr = reaper.ExecProcess(command, timeout_ms)
  return retval, stdout or "", stderr or ""
end

function M.is_windows()
  if is_win ~= nil then
    return is_win
  end
  local os_name = reaper.GetOS()
  is_win = tostring(os_name):find("Win") ~= nil
  return is_win
end

function M.has_curl()
  if curl_available ~= nil then
    return curl_available
  end
  local ret = M.exec_process("curl --version", 3000)
  curl_available = (ret == 0)
  return curl_available
end

function M.get_script_dir()
  if _G.AI_PART_GENERATOR_SCRIPT_DIR then
    return _G.AI_PART_GENERATOR_SCRIPT_DIR
  end
  local info = debug.getinfo(1, "S")
  local source = info.source
  if source:sub(1, 1) == "@" then
    source = source:sub(2)
  end
  return source:match("^(.*)[/\\]") or "."
end

function M.path_join(...)
  local sep = package.config:sub(1, 1)
  local parts = { ... }
  return table.concat(parts, sep)
end

function M.file_exists(path)
  local f = io.open(path, "rb")
  if not f then
    return false
  end
  f:close()
  return true
end

function M.read_file(path)
  local f = io.open(path, "rb")
  if not f then
    return nil
  end
  local content = f:read("*a")
  f:close()
  return content
end

function M.write_file(path, content)
  local f = io.open(path, "wb")
  if not f then
    return false
  end
  f:write(content)
  f:close()
  return true
end

function M.load_json_lib()
  if json then
    return json
  end
  local script_dir = _G.AI_PART_GENERATOR_SCRIPT_DIR or M.get_script_dir()
  local vendor_path = M.path_join(script_dir, "vendor", "?.lua")
  if not package.path:find(vendor_path, 1, true) then
    package.path = package.path .. ";" .. vendor_path
  end
  local ok, lib = pcall(require, "json")
  if not ok then
    M.log("Failed to load json.lua, trying alternative path...")
    local alt_vendor = M.path_join(script_dir, "..", "vendor", "?.lua")
    package.path = package.path .. ";" .. alt_vendor
    ok, lib = pcall(require, "json")
  end
  if not ok then
    M.show_error("Failed to load json.lua from vendor folder")
    return nil
  end
  json = lib
  return json
end

function M.get_track_name(track)
  if not track then
    return ""
  end
  local _, name = reaper.GetTrackName(track)
  return name or ""
end

return M
