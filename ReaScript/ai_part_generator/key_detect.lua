local utils = require("ai_part_generator.utils")

local M = {}

local NOTE_NAMES = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" }

local MAJOR_PROFILE = { 6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88 }
local MINOR_PROFILE = { 6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17 }

local DOWNBEAT_WEIGHT = 3.0
local FIRST_NOTE_WEIGHT = 4.0
local LAST_NOTE_WEIGHT = 5.0
local BASS_WEIGHT = 2.0
local BASS_THRESHOLD = 48

local function init_hist()
  local hist = {}
  for i = 1, 12 do
    hist[i] = 0
  end
  return hist
end

local function normalize_hist(hist)
  local sum = 0
  for i = 1, 12 do
    sum = sum + hist[i]
  end
  if sum == 0 then return hist end
  local normalized = {}
  for i = 1, 12 do
    normalized[i] = hist[i] / sum
  end
  return normalized
end

local function pearson_correlation(hist, profile)
  local n = 12
  local sum_h, sum_p = 0, 0
  for i = 1, n do
    sum_h = sum_h + hist[i]
    sum_p = sum_p + profile[i]
  end
  local mean_h = sum_h / n
  local mean_p = sum_p / n
  
  local cov, var_h, var_p = 0, 0, 0
  for i = 1, n do
    local dh = hist[i] - mean_h
    local dp = profile[i] - mean_p
    cov = cov + dh * dp
    var_h = var_h + dh * dh
    var_p = var_p + dp * dp
  end
  
  if var_h == 0 or var_p == 0 then return 0 end
  return cov / math.sqrt(var_h * var_p)
end

local function rotate_profile(profile, shift)
  local rotated = {}
  for i = 1, 12 do
    local src_idx = ((i - shift - 1) % 12) + 1
    rotated[i] = profile[src_idx]
  end
  return rotated
end

local function collect_weighted_hist(tracks, start_sec, end_sec, tempo)
  local hist = init_hist()
  local total = 0
  local first_note_pitch = nil
  local first_note_time = math.huge
  local last_note_pitch = nil
  local last_note_time = -math.huge
  local bass_hist = init_hist()
  
  local beat_dur = 60 / tempo
  
  for _, track in ipairs(tracks) do
    local item_count = reaper.CountTrackMediaItems(track)
    for i = 0, item_count - 1 do
      local item = reaper.GetTrackMediaItem(track, i)
      local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
      local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
      local item_end = item_start + item_len
      
      if item_start < end_sec and item_end > start_sec then
        local take = reaper.GetActiveTake(item)
        if take and reaper.TakeIsMIDI(take) then
          local _, note_count = reaper.MIDI_CountEvts(take)
          local start_ppq = reaper.MIDI_GetPPQPosFromProjTime(take, start_sec)
          local end_ppq = reaper.MIDI_GetPPQPosFromProjTime(take, end_sec)
          
          for n = 0, note_count - 1 do
            local _, _, _, note_start_ppq, note_end_ppq, _, pitch, vel = reaper.MIDI_GetNote(take, n)
            
            if note_end_ppq > start_ppq and note_start_ppq < end_ppq then
              local note_time = reaper.MIDI_GetProjTimeFromPPQPos(take, note_start_ppq)
              local dur = math.max(1, note_end_ppq - note_start_ppq)
              local pc = (pitch % 12) + 1
              
              local weight = dur * (vel / 127)
              
              local beat_pos = (note_time - start_sec) / beat_dur
              local is_downbeat = math.abs(beat_pos - math.floor(beat_pos + 0.1)) < 0.15
              if is_downbeat then
                weight = weight * DOWNBEAT_WEIGHT
              end
              
              hist[pc] = hist[pc] + weight
              total = total + weight
              
              if pitch < BASS_THRESHOLD then
                bass_hist[pc] = bass_hist[pc] + weight * BASS_WEIGHT
              end
              
              if note_time < first_note_time then
                first_note_time = note_time
                first_note_pitch = pitch
              end
              if note_time > last_note_time then
                last_note_time = note_time
                last_note_pitch = pitch
              end
            end
          end
        end
      end
    end
  end
  
  if total == 0 then
    return nil, nil, nil
  end
  
  for i = 1, 12 do
    hist[i] = hist[i] + bass_hist[i]
  end
  
  if first_note_pitch then
    local pc = (first_note_pitch % 12) + 1
    hist[pc] = hist[pc] + total * 0.1 * FIRST_NOTE_WEIGHT
  end
  
  if last_note_pitch then
    local pc = (last_note_pitch % 12) + 1
    hist[pc] = hist[pc] + total * 0.15 * LAST_NOTE_WEIGHT
  end
  
  return hist, first_note_pitch, last_note_pitch
end

function M.detect_key(tracks, start_sec, end_sec)
  if not tracks or #tracks == 0 then
    return nil
  end
  
  local tempo = 120
  local _, proj_tempo = reaper.GetProjectTimeSignature2(0)
  if proj_tempo and proj_tempo > 0 then
    tempo = proj_tempo
  end
  
  local hist, first_pitch, last_pitch = collect_weighted_hist(tracks, start_sec, end_sec, tempo)
  if not hist then
    return nil
  end
  
  local norm_hist = normalize_hist(hist)
  
  local best_corr = -2
  local best_key = nil
  local second_best_corr = -2
  
  for shift = 0, 11 do
    local major_rotated = rotate_profile(MAJOR_PROFILE, shift)
    local major_corr = pearson_correlation(norm_hist, major_rotated)
    
    if last_pitch and (last_pitch % 12) == shift then
      major_corr = major_corr + 0.1
    end
    
    if major_corr > best_corr then
      second_best_corr = best_corr
      best_corr = major_corr
      best_key = NOTE_NAMES[shift + 1] .. " major"
    elseif major_corr > second_best_corr then
      second_best_corr = major_corr
    end
    
    local minor_rotated = rotate_profile(MINOR_PROFILE, shift)
    local minor_corr = pearson_correlation(norm_hist, minor_rotated)
    
    if last_pitch and (last_pitch % 12) == shift then
      minor_corr = minor_corr + 0.1
    end
    
    if minor_corr > best_corr then
      second_best_corr = best_corr
      best_corr = minor_corr
      best_key = NOTE_NAMES[shift + 1] .. " minor"
    elseif minor_corr > second_best_corr then
      second_best_corr = minor_corr
    end
  end
  
  local confidence = best_corr - second_best_corr
  if confidence < 0.05 then
    utils.log(string.format("Key detection low confidence: %.3f (best: %.3f, second: %.3f)", 
      confidence, best_corr, second_best_corr))
  end
  
  return best_key
end

return M
