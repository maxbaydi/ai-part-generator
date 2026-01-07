local const = require("ai_part_generator.constants")
local utils = require("ai_part_generator.utils")

local M = {}

local function list_profile_files(profiles_dir)
  local files = {}
  local idx = 0
  while true do
    local filename = reaper.EnumerateFiles(profiles_dir, idx)
    if not filename then
      break
    end
    if filename:lower():match("%.json$") then
      table.insert(files, utils.path_join(profiles_dir, filename))
    end
    idx = idx + 1
  end
  return files
end

function M.load_profiles()
  local lib = utils.load_json_lib()
  if not lib then
    return {}, {}
  end
  local script_dir = utils.get_script_dir()
  local profiles_dir = utils.path_join(script_dir, "..", "Profiles")
  local files = list_profile_files(profiles_dir)
  local profiles = {}
  local by_id = {}
  for _, path in ipairs(files) do
    local content = utils.read_file(path)
    if content then
      local ok, profile = pcall(lib.decode, content)
      if ok and profile and profile.id then
        table.insert(profiles, profile)
        by_id[profile.id] = profile
      end
    end
  end
  table.sort(profiles, function(a, b)
    return tostring(a.name or ""):lower() < tostring(b.name or ""):lower()
  end)
  return profiles, by_id
end

function M.get_track_profile_id(track)
  if not track then
    return nil
  end
  local _, value = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_PROFILE_ID, "", false)
  if value == "" then
    return nil
  end
  return value
end

function M.save_track_profile_id(track, profile_id)
  if not track or not profile_id then
    return
  end
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_PROFILE_ID, profile_id, true)
end

function M.get_track_settings(track)
  if not track then
    return {}
  end
  local settings = {}
  local _, articulation_name = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_ARTICULATION_NAME, "", false)
  local _, generation_type = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_GENERATION_TYPE, "", false)
  local _, generation_style = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_GENERATION_STYLE, "", false)
  local _, free_mode = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_FREE_MODE, "", false)
  local _, prompt = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_PROMPT, "", false)
  local _, use_selected = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_USE_SELECTED_TRACKS, "", false)
  local _, insert_target = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_INSERT_TARGET, "", false)
  local _, key_mode = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_KEY_MODE, "", false)
  local _, key = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_KEY, "", false)

  if articulation_name ~= "" then settings.articulation_name = articulation_name end
  if generation_type ~= "" then settings.generation_type = generation_type end
  if generation_style ~= "" then settings.generation_style = generation_style end
  if free_mode ~= "" then settings.free_mode = free_mode == "1" end
  if prompt ~= "" then settings.prompt = prompt end
  if use_selected ~= "" then settings.use_selected_tracks = use_selected == "1" end
  if insert_target ~= "" then settings.insert_target = insert_target end
  if key_mode ~= "" then settings.key_mode = key_mode end
  if key ~= "" then settings.key = key end

  return settings
end

function M.save_track_settings(track, state)
  if not track or not state then
    return
  end
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_ARTICULATION_NAME, state.articulation_name or "", true)
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_GENERATION_TYPE, state.generation_type or "", true)
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_GENERATION_STYLE, state.generation_style or "", true)
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_FREE_MODE, state.free_mode and "1" or "0", true)
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_PROMPT, state.prompt or "", true)
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_USE_SELECTED_TRACKS, state.use_selected_tracks and "1" or "0", true)
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_INSERT_TARGET, state.insert_target or "", true)
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_KEY_MODE, state.key_mode or "", true)
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_KEY, state.key or "", true)
end

local function find_profile_by_family(profiles, family)
  for _, profile in ipairs(profiles) do
    if tostring(profile.family or ""):lower() == family then
      return profile.id
    end
  end
  return nil
end

local function heuristic_profile_id(track_name, profiles)
  local name = tostring(track_name or ""):lower()
  if name:find("bass") then
    return find_profile_by_family(profiles, "bass")
  end
  if name:find("string") or name:find("violin") or name:find("cello") or name:find("viola") then
    return find_profile_by_family(profiles, "strings")
  end
  if name:find("drum") or name:find("perc") then
    return find_profile_by_family(profiles, "drums")
  end
  return nil
end

function M.resolve_profile_id(track, profiles, by_id)
  local stored = M.get_track_profile_id(track)
  if stored and by_id[stored] then
    return stored
  end
  local heuristic = heuristic_profile_id(utils.get_track_name(track), profiles)
  if heuristic and by_id[heuristic] then
    return heuristic
  end
  if profiles[1] then
    return profiles[1].id
  end
  return nil
end

function M.build_articulation_list(profile)
  local articulations = {}
  local art_config = profile.articulations or {}
  local map = art_config.map or {}
  for name, _ in pairs(map) do
    table.insert(articulations, name)
  end
  table.sort(articulations)
  return articulations
end

function M.get_default_articulation(profile)
  local art_config = profile.articulations or {}
  if art_config.default and art_config.default ~= "" then
    return art_config.default
  end
  local articulations = M.build_articulation_list(profile)
  if #articulations == 0 then
    return ""
  end
  return articulations[1]
end

function M.get_articulation_info(profile, articulation_name)
  local art_config = profile.articulations or {}
  local map = art_config.map or {}
  return map[articulation_name]
end

return M
