local const = require("ai_part_generator.constants")
local http = require("ai_part_generator.http")
local utils = require("ai_part_generator.utils")

local M = {}

local python_cmd = nil

local function resolve_python_command()
  if python_cmd then
    return python_cmd
  end

  local candidates
  if utils.is_windows() then
    candidates = { "py -3", "python", "python3" }
  else
    candidates = { "python3", "python" }
  end

  for _, cmd in ipairs(candidates) do
    local retval = utils.exec_process(cmd .. " --version", const.BRIDGE_PYTHON_DETECT_TIMEOUT_MS)
    if retval == 0 then
      python_cmd = cmd
      return cmd
    end
  end

  return nil
end

local function get_bridge_app_path()
  local script_dir = utils.get_script_dir()
  local root_dir = utils.path_join(script_dir, "..")
  return utils.path_join(root_dir, "bridge", "app.py")
end

local function start_bridge_process()
  local py = resolve_python_command()
  if not py then
    return false, "Python not found (commands: py -3 / python)."
  end

  local app_path = get_bridge_app_path()
  if not utils.file_exists(app_path) then
    return false, "Bridge file not found: " .. tostring(app_path)
  end

  local check_cmd = string.format('%s -c "import fastapi, uvicorn"', py)
  local check_retval = utils.exec_process(check_cmd, const.BRIDGE_PYTHON_DETECT_TIMEOUT_MS)
  if check_retval ~= 0 then
    return false, "Bridge dependencies not found (fastapi/uvicorn). Install from bridge/requirements.txt and try again."
  end

  local cmd
  if utils.is_windows() then
    cmd = string.format('cmd /c "set PYTHONIOENCODING=utf-8 && set PYTHONUTF8=1 && start "" /b %s "%s""', py, app_path)
  else
    cmd = string.format('sh -c \'PYTHONIOENCODING=utf-8 PYTHONUTF8=1 %s "%s" >/dev/null 2>&1 &\'', py, app_path)
  end

  utils.exec_process(cmd, 5000)
  return true, nil
end

function M.ensure_running_async(on_ready)
  if http.http_get_ok(const.BRIDGE_HEALTH_URL, const.BRIDGE_PING_TIMEOUT_SEC) then
    on_ready(true, nil)
    return
  end

  local started, start_err = start_bridge_process()
  if not started then
    on_ready(false, start_err or "Failed to start bridge server.")
    return
  end

  local start_time = reaper.time_precise()
  local next_ping = 0.0

  local function poll()
    local now = reaper.time_precise()
    if (now - start_time) > const.BRIDGE_STARTUP_TIMEOUT_SEC then
      on_ready(false, "Bridge server did not start (timeout). Start it manually and try again.")
      return
    end

    if now >= next_ping then
      if http.http_get_ok(const.BRIDGE_HEALTH_URL, const.BRIDGE_PING_TIMEOUT_SEC) then
        on_ready(true, nil)
        return
      end
      next_ping = now + const.BRIDGE_STARTUP_POLL_INTERVAL_SEC
    end

    reaper.defer(poll)
  end

  reaper.defer(poll)
end

return M


