local const = require("ai_part_generator.constants")
local utils = require("ai_part_generator.utils")

local M = {}

local function safe_remove(path)
  if path then
    pcall(os.remove, path)
  end
end

local function strip_bom(content)
  if not content then
    return content
  end
  if content:sub(1, 3) == "\239\187\191" then
    return content:sub(4)
  end
  return content
end

local function trim(s)
  if not s then
    return s
  end
  return s:match("^%s*(.-)%s*$")
end

local function build_temp_paths()
  local base = string.format("ai_part_gen_%d_%d", os.time(), math.floor(reaper.time_precise() * 1000))
  local root = reaper.GetResourcePath()
  return {
    request = utils.path_join(root, base .. "_req.json"),
    response = utils.path_join(root, base .. "_resp.json"),
  }
end

local function run_curl_sync(url, request_path, response_path)
  local cmd = string.format(
    'curl -s -X POST -H "Content-Type: application/json" --max-time %d --data-binary "@%s" -o "%s" "%s"',
    const.HTTP_TIMEOUT_SEC,
    request_path,
    response_path,
    url
  )
  utils.log("curl command: " .. cmd)
  local retval, stdout, stderr = utils.exec_process(cmd, const.PROCESS_TIMEOUT_MS)
  utils.log("curl result: retval=" .. tostring(retval))
  if stderr and stderr ~= "" then
    utils.log("curl stderr: " .. stderr)
  end
  return retval
end

local function run_powershell_sync(url, request_path, response_path)
  local ps_code = string.format([[
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
  $body = [System.IO.File]::ReadAllText('%s', [System.Text.Encoding]::UTF8)
  $headers = @{ 'Content-Type' = 'application/json; charset=utf-8' }
  $resp = Invoke-RestMethod -Uri '%s' -Method Post -Headers $headers -Body $body -TimeoutSec %d
  $json = $resp | ConvertTo-Json -Depth 100 -Compress
  [System.IO.File]::WriteAllText('%s', $json, (New-Object System.Text.UTF8Encoding $false))
  exit 0
} catch {
  $err = @{ detail = $_.Exception.Message } | ConvertTo-Json -Compress
  [System.IO.File]::WriteAllText('%s', $err, (New-Object System.Text.UTF8Encoding $false))
  exit 1
}
]], request_path, url, const.HTTP_TIMEOUT_SEC, response_path, response_path)

  local script_path = request_path:gsub("_req%.json$", "_script.ps1")
  if not utils.write_file(script_path, ps_code) then
    return -1, "Failed to write PowerShell script"
  end

  local cmd = string.format(
    'powershell -NoProfile -ExecutionPolicy Bypass -File "%s"',
    script_path
  )
  utils.log("PowerShell command: " .. cmd)
  local retval, stdout, stderr = utils.exec_process(cmd, const.PROCESS_TIMEOUT_MS)
  utils.log("PowerShell result: retval=" .. tostring(retval))
  if stderr and stderr ~= "" then
    utils.log("PowerShell stderr: " .. stderr)
  end
  safe_remove(script_path)
  return retval
end

local function run_curl_get_ok(url, timeout_sec)
  local cmd = string.format('curl -s -f --max-time %d "%s"', timeout_sec, url)
  local retval = utils.exec_process(cmd, const.BRIDGE_PING_PROCESS_TIMEOUT_MS)
  return retval == 0
end

local function run_powershell_get_ok(url, timeout_sec)
  local cmd = string.format(
    'powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference=\'Stop\'; try { Invoke-RestMethod -Uri \'%s\' -Method Get -TimeoutSec %d | Out-Null; exit 0 } catch { exit 1 }"',
    url,
    timeout_sec
  )
  local retval = utils.exec_process(cmd, const.BRIDGE_PING_PROCESS_TIMEOUT_MS)
  return retval == 0
end

function M.http_get_ok(url, timeout_sec)
  local timeout = timeout_sec or const.BRIDGE_PING_TIMEOUT_SEC
  if utils.has_curl() then
    return run_curl_get_ok(url, timeout)
  end
  if utils.is_windows() then
    return run_powershell_get_ok(url, timeout)
  end
  return false
end

function M.http_post_json(url, payload)
  local lib = utils.load_json_lib()
  if not lib then
    return nil, "JSON library not loaded"
  end

  local paths = build_temp_paths()
  local encoded = lib.encode(payload)
  if not utils.write_file(paths.request, encoded) then
    return nil, "Failed to write request file"
  end
  utils.log("Request written to: " .. paths.request)

  local function cleanup()
    safe_remove(paths.request)
    safe_remove(paths.response)
  end

  local retval
  if utils.has_curl() then
    retval = run_curl_sync(url, paths.request, paths.response)
  elseif utils.is_windows() then
    retval = run_powershell_sync(url, paths.request, paths.response)
  else
    cleanup()
    return nil, "No HTTP client available"
  end

  local content = utils.read_file(paths.response)
  cleanup()

  if not content or content == "" then
    return nil, "Empty response from server (retval=" .. tostring(retval) .. ")"
  end

  content = strip_bom(content)
  content = trim(content)
  utils.log("Response received: " .. #content .. " bytes")
  utils.log("Response preview: " .. content:sub(1, 300))

  local ok, data = pcall(lib.decode, content)
  if not ok then
    utils.log("JSON decode error: " .. tostring(data))
    return nil, "Invalid JSON response"
  end

  if type(data) == "table" and data.detail then
    return nil, tostring(data.detail)
  end

  return data, nil
end

function M.begin_request(url, payload)
  local lib = utils.load_json_lib()
  if not lib then
    return nil, "JSON library not loaded"
  end

  local paths = build_temp_paths()
  local encoded = lib.encode(payload)
  if not utils.write_file(paths.request, encoded) then
    return nil, "Failed to write request file"
  end
  utils.log("Async request written to: " .. paths.request)

  local script_path = nil
  local cmd

  if utils.has_curl() then
    cmd = string.format(
      'cmd /c start /b curl -s -X POST -H "Content-Type: application/json" --max-time %d --data-binary "@%s" -o "%s" "%s"',
      const.HTTP_TIMEOUT_SEC,
      paths.request,
      paths.response,
      url
    )
  elseif utils.is_windows() then
    local ps_code = string.format([[
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
  $body = [System.IO.File]::ReadAllText('%s', [System.Text.Encoding]::UTF8)
  $headers = @{ 'Content-Type' = 'application/json; charset=utf-8' }
  $resp = Invoke-RestMethod -Uri '%s' -Method Post -Headers $headers -Body $body -TimeoutSec %d
  $json = $resp | ConvertTo-Json -Depth 100 -Compress
  [System.IO.File]::WriteAllText('%s', $json, (New-Object System.Text.UTF8Encoding $false))
} catch {
  $err = @{ detail = $_.Exception.Message } | ConvertTo-Json -Compress
  [System.IO.File]::WriteAllText('%s', $err, (New-Object System.Text.UTF8Encoding $false))
}
]], paths.request, url, const.HTTP_TIMEOUT_SEC, paths.response, paths.response)

    script_path = paths.request:gsub("_req%.json$", "_async.ps1")
    if not utils.write_file(script_path, ps_code) then
      safe_remove(paths.request)
      return nil, "Failed to write async script"
    end
    cmd = string.format(
      'cmd /c start /b powershell -NoProfile -ExecutionPolicy Bypass -File "%s"',
      script_path
    )
  else
    safe_remove(paths.request)
    return nil, "No HTTP client available"
  end

  utils.log("Starting async: " .. cmd)
  local retval = utils.exec_process(cmd, 5000)
  utils.log("Async start result: " .. tostring(retval))

  return {
    request_path = paths.request,
    response_path = paths.response,
    script_path = script_path,
    start_time = reaper.time_precise(),
  }, nil
end

function M.poll_response(handle)
  if not handle then
    return true, nil, "Invalid handle"
  end

  local elapsed = reaper.time_precise() - handle.start_time
  if elapsed > (const.HTTP_TIMEOUT_SEC + const.PROCESS_TIMEOUT_BUFFER_SEC) then
    utils.log("Request timed out after " .. string.format("%.1f", elapsed) .. "s")
    return true, nil, "Request timed out"
  end

  local content = utils.read_file(handle.response_path)
  if not content or content == "" then
    return false, nil, nil
  end

  content = strip_bom(content)
  content = trim(content)

  if content == "" then
    return false, nil, nil
  end

  if content:sub(1, 1) ~= "{" and content:sub(1, 1) ~= "[" then
    if elapsed < 3 then
      return false, nil, nil
    end
  end

  utils.log("Async response received: " .. #content .. " bytes after " .. string.format("%.1f", elapsed) .. "s")
  utils.log("Response preview: " .. content:sub(1, 300))

  local lib = utils.load_json_lib()
  if not lib then
    return true, nil, "JSON library not loaded"
  end

  local ok, data = pcall(lib.decode, content)
  if not ok then
    if elapsed < 5 then
      utils.log("JSON parse failed, waiting... (" .. tostring(data) .. ")")
      return false, nil, nil
    end
    utils.log("JSON decode error: " .. tostring(data))
    return true, nil, "Invalid JSON response"
  end

  if type(data) == "table" and data.detail then
    return true, nil, tostring(data.detail)
  end

  utils.log("Response parsed OK: notes=" .. tostring(#(data.notes or {})) ..
    " cc=" .. tostring(#(data.cc_events or {})))

  return true, data, nil
end

function M.cleanup(handle)
  if not handle then
    return
  end
  safe_remove(handle.request_path)
  safe_remove(handle.response_path)
  if handle.script_path then
    safe_remove(handle.script_path)
  end
end

return M
