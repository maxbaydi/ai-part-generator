local const = require("ai_part_generator.constants")

local M = {}

function M.get_active_track()
  local track = reaper.GetSelectedTrack(0, 0)
  if track then
    return track
  end
  return reaper.GetLastTouchedTrack()
end

function M.create_new_track()
  local count = reaper.CountTracks(0)
  reaper.InsertTrackAtIndex(count, true)
  return reaper.GetTrack(0, count)
end

function M.find_midi_item(track, start_sec, end_sec)
  local count = reaper.CountTrackMediaItems(track)
  for i = 0, count - 1 do
    local item = reaper.GetTrackMediaItem(track, i)
    local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
    local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
    local item_end = item_start + item_len
    if item_start < end_sec and item_end > start_sec then
      local take_count = reaper.CountTakes(item)
      for t = 0, take_count - 1 do
        local take = reaper.GetTake(item, t)
        if take and reaper.TakeIsMIDI(take) then
          return item, take
        end
      end
    end
  end
  return nil, nil
end

function M.create_new_take_in_item(item, start_sec, end_sec)
  local track = reaper.GetMediaItem_Track(item)
  if not track then
    return nil
  end

  local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
  local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
  local item_end = item_start + item_len

  local tmp_start = (item_end > item_start) and item_start or start_sec
  local tmp_end = (item_end > item_start) and item_end or end_sec

  local tmp_item = reaper.CreateNewMIDIItemInProj(track, tmp_start, tmp_end, false)
  if not tmp_item then
    return nil
  end

  local tmp_take = reaper.GetActiveTake(tmp_item)
  local tmp_source = tmp_take and reaper.GetMediaItemTake_Source(tmp_take) or nil
  if not tmp_source then
    reaper.DeleteTrackMediaItem(track, tmp_item)
    return nil
  end

  local new_take = reaper.AddTakeToMediaItem(item)
  if not new_take then
    reaper.DeleteTrackMediaItem(track, tmp_item)
    return nil
  end

  reaper.SetMediaItemTake_Source(new_take, tmp_source)
  reaper.SetActiveTake(new_take)
  reaper.DeleteTrackMediaItem(track, tmp_item)

  local _, note_count, cc_count, text_count = reaper.MIDI_CountEvts(new_take)
  for i = note_count - 1, 0, -1 do
    reaper.MIDI_DeleteNote(new_take, i)
  end
  for i = cc_count - 1, 0, -1 do
    reaper.MIDI_DeleteCC(new_take, i)
  end
  for i = text_count - 1, 0, -1 do
    reaper.MIDI_DeleteTextSysexEvt(new_take, i)
  end
  reaper.MIDI_Sort(new_take)
  reaper.UpdateItemInProject(item)

  return new_take
end

function M.get_or_create_midi_item(track, start_sec, end_sec, create_new_take)
  local item, existing_take = M.find_midi_item(track, start_sec, end_sec)
  
  if item and existing_take then
    if create_new_take then
      local new_take = M.create_new_take_in_item(item, start_sec, end_sec)
      if not new_take then
        return nil, nil, false
      end
      local take_count = reaper.CountTakes(item)
      local take_name = "Gen " .. take_count
      reaper.GetSetMediaItemTakeInfo_String(new_take, "P_NAME", take_name, true)
      return item, new_take, true
    end
    return item, existing_take, false
  end
  
  local new_item = reaper.CreateNewMIDIItemInProj(track, start_sec, end_sec, false)
  local take = reaper.GetActiveTake(new_item)
  return new_item, take, false
end

local function to_reaper_chan(chan)
  local c = tonumber(chan) or const.MIDI_CHAN_MIN
  if c < const.MIDI_CHAN_MIN then
    c = const.MIDI_CHAN_MIN
  end
  if c > const.MIDI_CHAN_MAX then
    c = const.MIDI_CHAN_MAX
  end
  return c - 1
end

local function insert_note(take, start_qn, note)
  if not note or type(note) ~= "table" then
    return false
  end
  local note_start = tonumber(note.start_q) or tonumber(note.time_q) or 0
  local note_dur = tonumber(note.dur_q) or const.DEFAULT_NOTE_DUR_Q
  local start_qn_abs = start_qn + note_start
  local end_qn_abs = start_qn_abs + note_dur
  local start_ppq = reaper.MIDI_GetPPQPosFromProjQN(take, start_qn_abs)
  local end_ppq = reaper.MIDI_GetPPQPosFromProjQN(take, end_qn_abs)
  local chan = to_reaper_chan(note.chan)
  local pitch = tonumber(note.pitch) or const.DEFAULT_PITCH
  local vel = tonumber(note.vel) or const.DEFAULT_VELOCITY
  pitch = math.max(const.MIDI_MIN, math.min(const.MIDI_MAX, pitch))
  vel = math.max(1, math.min(const.MIDI_MAX, vel))
  reaper.MIDI_InsertNote(take, false, false, start_ppq, end_ppq, chan, pitch, vel, true)
  return true
end

local function insert_cc(take, start_qn, cc)
  if not cc or type(cc) ~= "table" then
    return false
  end
  local cc_time = tonumber(cc.time_q) or tonumber(cc.start_q) or 0
  local qn_abs = start_qn + cc_time
  local ppq = reaper.MIDI_GetPPQPosFromProjQN(take, qn_abs)
  local chan = to_reaper_chan(cc.chan)
  local cc_num = tonumber(cc.cc) or tonumber(cc.controller) or const.DEFAULT_CC
  local cc_val = tonumber(cc.value) or tonumber(cc.val) or const.MIDI_MIN
  cc_num = math.max(const.MIDI_MIN, math.min(const.MIDI_MAX, cc_num))
  cc_val = math.max(const.MIDI_MIN, math.min(const.MIDI_MAX, cc_val))
  reaper.MIDI_InsertCC(take, false, false, ppq, const.MIDI_CC_STATUS, chan, cc_num, cc_val)
  return true
end

local function insert_program_change(take, start_qn, pc)
  if not pc or type(pc) ~= "table" then
    return false
  end
  local pc_time = tonumber(pc.time_q) or tonumber(pc.start_q) or 0
  local qn_abs = start_qn + pc_time
  local ppq = reaper.MIDI_GetPPQPosFromProjQN(take, qn_abs)
  local chan = to_reaper_chan(pc.chan)
  local program = tonumber(pc.program) or const.MIDI_MIN
  program = math.max(const.MIDI_MIN, math.min(const.MIDI_MAX, program))
  reaper.MIDI_InsertCC(take, false, false, ppq, const.MIDI_PC_STATUS, chan, program, const.MIDI_MIN)
  return true
end

function M.insert_note(take, start_qn, note)
  insert_note(take, start_qn, note)
end

function M.insert_cc(take, start_qn, cc)
  insert_cc(take, start_qn, cc)
end

function M.insert_program_change(take, start_qn, pc)
  insert_program_change(take, start_qn, pc)
end

function M.sort(take)
  reaper.MIDI_Sort(take)
end

return M
