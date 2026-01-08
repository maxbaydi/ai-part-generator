local const = require("ai_part_generator.constants")
local utils = require("ai_part_generator.utils")

local M = {}

local LEGATO_KEYWORD = "legato"

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
  local _, allow_tempo = reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_ALLOW_TEMPO_CHANGES, "", false)

  if articulation_name ~= "" then settings.articulation_name = articulation_name end
  if generation_type ~= "" then settings.generation_type = generation_type end
  if generation_style ~= "" then settings.generation_style = generation_style end
  if free_mode ~= "" then settings.free_mode = free_mode == "1" end
  if prompt ~= "" then settings.prompt = prompt end
  if use_selected ~= "" then settings.use_selected_tracks = use_selected == "1" end
  if insert_target ~= "" then settings.insert_target = insert_target end
  if key_mode ~= "" then settings.key_mode = key_mode end
  if key ~= "" then settings.key = key end
  if allow_tempo ~= "" then settings.allow_tempo_changes = allow_tempo == "1" end

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
  reaper.GetSetMediaTrackInfo_String(track, "P_EXT:" .. const.EXTSTATE_ALLOW_TEMPO_CHANGES, state.allow_tempo_changes and "1" or "0", true)
end

local function normalize_name(s)
  return tostring(s or ""):lower():gsub("[%-%_%s]+", " "):gsub("^%s+", ""):gsub("%s+$", "")
end

local function extract_keywords(s)
  local keywords = {}
  for word in normalize_name(s):gmatch("%S+") do
    if #word > 1 then
      keywords[word] = true
    end
  end
  return keywords
end

local INSTRUMENT_ALIASES = {
  violin = { "vln", "vl1", "vl2", "violin1", "violin2", "violins" },
  viola = { "vla", "violas" },
  cello = { "vlc", "vc", "cellos" },
  bass = { "cb", "contrabass", "double bass", "dbass", "basses" },
  ezbass = { "ez bass", "toontrack bass", "electric bass", "bass guitar" },
  flute = { "fl", "flutes", "flauto" },
  oboe = { "ob", "oboes" },
  clarinet = { "cl", "clarinets", "clar" },
  bassoon = { "bsn", "fg", "fagotto", "bassoons" },
  piccolo = { "picc", "pc" },
  horn = { "hn", "fr hn", "french horn", "horns", "cor" },
  trumpet = { "tp", "trp", "tpt", "trumpets", "trompette" },
  trombone = { "tb", "trb", "tbn", "trombones", "pos" },
  tuba = { "tba", "tubas" },
  drums = { "drum", "perc", "percussion", "kit" },
  ad2 = { "addictive drums", "addictive", "xln drums", "xln audio" },
  agpf = { "ample guitar", "ample pf", "ample sound guitar", "electric guitar" },
}

local function find_instrument_match(track_name)
  local name_lower = normalize_name(track_name)
  for instrument, aliases in pairs(INSTRUMENT_ALIASES) do
    if name_lower:find(instrument, 1, true) then
      return instrument
    end
    for _, alias in ipairs(aliases) do
      if name_lower:find(alias, 1, true) then
        return instrument
      end
    end
  end
  return nil
end

local function find_profile_by_family(profiles, family)
  for _, profile in ipairs(profiles) do
    if tostring(profile.family or ""):lower() == family then
      return profile.id
    end
  end
  return nil
end

local function calculate_match_score(profile, track_name)
  local track_lower = normalize_name(track_name)
  local profile_name_lower = normalize_name(profile.name or "")
  local profile_id_lower = normalize_name(profile.id or "")
  local score = 0

  if profile_name_lower:find(track_lower, 1, true) or track_lower:find(profile_name_lower, 1, true) then
    score = score + 100
  end

  local instrument = find_instrument_match(track_name)
  if instrument then
    if profile_name_lower:find(instrument, 1, true) or profile_id_lower:find(instrument, 1, true) then
      score = score + 80
    end
    if normalize_name(profile.description or ""):find(instrument, 1, true) then
      score = score + 20
    end
  end

  local track_keywords = extract_keywords(track_name)
  local profile_keywords = extract_keywords(profile.name or "")
  for word in pairs(track_keywords) do
    if profile_keywords[word] then
      score = score + 30
    end
  end

  return score
end

function M.find_profile_for_track(track, profiles, by_id)
  if not track then
    return nil, nil
  end

  local stored = M.get_track_profile_id(track)
  if stored and by_id[stored] then
    return stored, by_id[stored]
  end

  local track_name = utils.get_track_name(track)
  if not track_name or track_name == "" then
    return nil, nil
  end

  local best_profile = nil
  local best_score = 0

  for _, profile in ipairs(profiles) do
    local score = calculate_match_score(profile, track_name)
    if score > best_score then
      best_score = score
      best_profile = profile
    end
  end

  if best_profile and best_score >= 30 then
    return best_profile.id, best_profile
  end

  return nil, nil
end

local function heuristic_profile_id(track_name, profiles)
  local name = tostring(track_name or ""):lower()

  for _, profile in ipairs(profiles) do
    local score = calculate_match_score(profile, track_name)
    if score >= 50 then
      return profile.id
    end
  end

  if name:find("bass") and not name:find("trombone") then
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

local function contains_legato(s)
  return tostring(s or ""):lower():find(LEGATO_KEYWORD, 1, true) ~= nil
end

function M.is_legato_articulation(profile, articulation_name)
  if not profile then
    return false
  end

  local name = tostring(articulation_name or "")
  if name == "" then
    return false
  end

  if contains_legato(name) then
    return true
  end

  local info = M.get_articulation_info(profile, name)
  if not info then
    return false
  end

  return contains_legato(info.description)
end

function M.get_articulation_changes(profile, response)
  if not profile or type(response) ~= "table" then
    return {}
  end

  local art_config = profile.articulations or {}
  local mode = tostring(art_config.mode or "none"):lower()
  local map = art_config.map or {}

  if mode == "cc" then
    local cc_num = tonumber(art_config.cc_number)
    if not cc_num then
      return {}
    end

    local value_to_name = {}
    for name, data in pairs(map) do
      if type(data) == "table" then
        local v = tonumber(data.cc_value) or tonumber(data.value) or tonumber(data.cc)
        if v ~= nil then
          value_to_name[v] = name
        end
      end
    end

    local changes = {}
    for _, evt in ipairs(response.cc_events or {}) do
      if type(evt) == "table" then
        local cc = tonumber(evt.cc) or tonumber(evt.controller)
        if cc == cc_num then
          local val = tonumber(evt.value) or tonumber(evt.val)
          local art_name = val and value_to_name[val] or nil
          if art_name then
            local t = tonumber(evt.time_q) or tonumber(evt.start_q) or 0
            table.insert(changes, { time_q = t, articulation = art_name })
          end
        end
      end
    end

    table.sort(changes, function(a, b)
      return (a.time_q or 0) < (b.time_q or 0)
    end)

    return changes
  end

  if mode == "keyswitch" then
    local pitch_to_name = {}
    for name, data in pairs(map) do
      if type(data) == "table" then
        local pitch = tonumber(data.pitch)
        if pitch ~= nil then
          pitch_to_name[pitch] = name
        end
      end
    end

    local changes = {}
    for _, ks in ipairs(response.keyswitches or {}) do
      if type(ks) == "table" then
        local pitch = tonumber(ks.pitch)
        local art_name = pitch and pitch_to_name[pitch] or nil
        if art_name then
          local t = tonumber(ks.time_q) or tonumber(ks.start_q) or 0
          table.insert(changes, { time_q = t, articulation = art_name })
        end
      end
    end

    table.sort(changes, function(a, b)
      return (a.time_q or 0) < (b.time_q or 0)
    end)

    return changes
  end

  return {}
end

function M.get_selected_tracks_with_profiles(profiles, by_id)
  local tracks = {}
  local count = reaper.CountSelectedTracks(0)
  
  if count == 0 then
    return tracks
  end

  for i = 0, count - 1 do
    local track = reaper.GetSelectedTrack(0, i)
    if track then
      local profile_id, profile = M.find_profile_for_track(track, profiles, by_id)
      local track_name = utils.get_track_name(track)
      table.insert(tracks, {
        track = track,
        name = track_name,
        profile_id = profile_id,
        profile = profile,
        index = i + 1,
      })
    end
  end

  return tracks
end

return M
