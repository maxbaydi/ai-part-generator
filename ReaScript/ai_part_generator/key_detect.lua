local utils = require("ai_part_generator.utils")

local M = {}

local NOTE_NAMES = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" }
local MAJOR_PROFILE = { 6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88 }
local MINOR_PROFILE = { 6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17 }

local function init_hist()
  local hist = {}
  for i = 1, 12 do
    hist[i] = 0
  end
  return hist
end

local function score_profile(hist, profile, shift)
  local sum = 0
  for i = 1, 12 do
    local idx = ((i - shift - 1) % 12) + 1
    sum = sum + (hist[i] * profile[idx])
  end
  return sum
end

local function collect_hist(tracks, start_sec, end_sec)
  local hist = init_hist()
  local total = 0
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
            local _, _, _, note_start, note_end, _, pitch = reaper.MIDI_GetNote(take, n)
            if note_end > start_ppq and note_start < end_ppq then
              local dur = math.max(1, note_end - note_start)
              local pc = (pitch % 12) + 1
              hist[pc] = hist[pc] + dur
              total = total + dur
            end
          end
        end
      end
    end
  end
  if total == 0 then
    return nil
  end
  return hist
end

function M.detect_key(tracks, start_sec, end_sec)
  if not tracks or #tracks == 0 then
    return nil
  end
  local hist = collect_hist(tracks, start_sec, end_sec)
  if not hist then
    return nil
  end

  local best_score = -1
  local best_key = nil

  for shift = 0, 11 do
    local major_score = score_profile(hist, MAJOR_PROFILE, shift)
    if major_score > best_score then
      best_score = major_score
      best_key = NOTE_NAMES[shift + 1] .. " major"
    end
    local minor_score = score_profile(hist, MINOR_PROFILE, shift)
    if minor_score > best_score then
      best_score = minor_score
      best_key = NOTE_NAMES[shift + 1] .. " minor"
    end
  end

  return best_key
end

return M
