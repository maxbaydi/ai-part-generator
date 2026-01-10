local const = require("ai_part_generator.constants")

local M = {}

local function get_note_start_q(note)
  return tonumber(note.start_q) or tonumber(note.time_q) or 0
end

local function get_note_dur_q(note)
  return tonumber(note.dur_q) or const.DEFAULT_NOTE_DUR_Q
end

local function get_note_pitch(note)
  return tonumber(note.pitch) or const.DEFAULT_PITCH
end

local function get_note_chan(note)
  return tonumber(note.chan) or const.MIDI_CHAN_MIN
end

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
  local note_start = get_note_start_q(note)
  local note_dur = get_note_dur_q(note)
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

local function build_note_groups(notes)
  local entries = {}
  for i, note in ipairs(notes) do
    if type(note) == "table" then
      table.insert(entries, { idx = i, start_q = get_note_start_q(note) })
    end
  end
  if #entries == 0 then
    return {}
  end

  table.sort(entries, function(a, b)
    if a.start_q == b.start_q then
      return a.idx < b.idx
    end
    return a.start_q < b.start_q
  end)

  local groups = {}
  local current_start = entries[1].start_q
  local current = { start_q = current_start, indices = {} }
  table.insert(groups, current)

  for _, entry in ipairs(entries) do
    if entry.start_q ~= current_start then
      current_start = entry.start_q
      current = { start_q = current_start, indices = {} }
      table.insert(groups, current)
    end
    table.insert(current.indices, entry.idx)
  end

  return groups
end

local function ensure_group_min_end(notes, indices, target_end)
  for _, idx in ipairs(indices) do
    local note = notes[idx]
    local note_start = get_note_start_q(note)
    local note_dur = get_note_dur_q(note)
    local note_end = note_start + note_dur
    if note_end < target_end then
      note.dur_q = target_end - note_start
    end
  end
end

function M.apply_legato_overlap(notes, overlap_q)
  if type(notes) ~= "table" then
    return
  end

  local overlap = tonumber(overlap_q) or 0
  if overlap <= 0 then
    return
  end

  local groups = build_note_groups(notes)
  if #groups < 2 then
    return
  end

  for i = 1, #groups - 1 do
    ensure_group_min_end(notes, groups[i].indices, groups[i + 1].start_q + overlap)
  end
end

function M.apply_legato_overlap_by_articulation_changes(notes, overlap_q, changes, is_legato)
  if type(notes) ~= "table" then
    return
  end

  local overlap = tonumber(overlap_q) or 0
  if overlap <= 0 then
    return
  end

  if type(changes) ~= "table" or type(is_legato) ~= "function" then
    return
  end

  local groups = build_note_groups(notes)
  if #groups < 2 then
    return
  end

  table.sort(changes, function(a, b)
    return (tonumber(a.time_q) or 0) < (tonumber(b.time_q) or 0)
  end)

  local group_legato = {}
  local current_articulation = nil
  local j = 1

  for i, group in ipairs(groups) do
    while changes[j] and (tonumber(changes[j].time_q) or 0) <= group.start_q do
      current_articulation = changes[j].articulation
      j = j + 1
    end
    group_legato[i] = current_articulation and is_legato(current_articulation) or false
  end

  for i = 1, #groups - 1 do
    if group_legato[i] and group_legato[i + 1] then
      ensure_group_min_end(notes, groups[i].indices, groups[i + 1].start_q + overlap)
    end
  end
end

function M.read_item_notes(item, max_notes)
  if not item then
    return {}, {}
  end

  local take = reaper.GetActiveTake(item)
  if not take or not reaper.TakeIsMIDI(take) then
    return {}, {}
  end

  local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
  local item_start_qn = reaper.TimeMap_timeToQN(item_start)

  local _, note_count, cc_count = reaper.MIDI_CountEvts(take)
  local limit = max_notes or const.MAX_SKETCH_NOTES
  local cc_limit = const.MAX_SKETCH_CC_EVENTS or 1000

  local notes = {}
  for i = 0, math.min(note_count - 1, limit - 1) do
    local retval, selected, muted, startppq, endppq, chan, pitch, vel = reaper.MIDI_GetNote(take, i)
    if retval and not muted then
      local start_qn = reaper.MIDI_GetProjQNFromPPQPos(take, startppq)
      local end_qn = reaper.MIDI_GetProjQNFromPPQPos(take, endppq)
      local relative_start = start_qn - item_start_qn
      local dur_q = end_qn - start_qn
      table.insert(notes, {
        start_q = math.max(0, relative_start),
        dur_q = math.max(0.01, dur_q),
        pitch = pitch,
        vel = vel,
        chan = chan + 1,
      })
    end
  end

  local cc_events = {}
  for i = 0, math.min(cc_count - 1, cc_limit - 1) do
    local retval, selected, muted, ppqpos, chanmsg, chan, msg2, msg3 = reaper.MIDI_GetCC(take, i)
    if retval and not muted and chanmsg == const.MIDI_CC_STATUS then
      local time_qn = reaper.MIDI_GetProjQNFromPPQPos(take, ppqpos)
      local relative_time = time_qn - item_start_qn
      table.insert(cc_events, {
        time_q = math.max(0, relative_time),
        cc = msg2,
        value = msg3,
        chan = chan + 1,
      })
    end
  end

  return notes, cc_events
end

function M.resolve_same_pitch_overlaps(notes, min_gap_q)
  if type(notes) ~= "table" then
    return notes
  end

  local gap = tonumber(min_gap_q) or 0
  if gap < 0 then
    gap = 0
  end

  local groups = {}
  for i, note in ipairs(notes) do
    if type(note) == "table" then
      local key = tostring(get_note_chan(note)) .. ":" .. tostring(get_note_pitch(note))
      if not groups[key] then
        groups[key] = {}
      end
      table.insert(groups[key], { idx = i, start_q = get_note_start_q(note) })
    end
  end

  local remove = {}
  for _, entries in pairs(groups) do
    table.sort(entries, function(a, b)
      if a.start_q == b.start_q then
        return a.idx < b.idx
      end
      return a.start_q < b.start_q
    end)

    for i = 1, #entries - 1 do
      local curr_idx = entries[i].idx
      local next_idx = entries[i + 1].idx
      local curr = notes[curr_idx]
      local nxt = notes[next_idx]
      local curr_start = get_note_start_q(curr)
      local curr_end = curr_start + get_note_dur_q(curr)
      local next_start = get_note_start_q(nxt)
      local max_end = next_start - gap
      if curr_end > max_end then
        local new_dur = max_end - curr_start
        if new_dur <= 0 then
          remove[curr_idx] = true
        else
          curr.dur_q = new_dur
        end
      end
    end
  end

  if not next(remove) then
    return notes
  end

  local cleaned = {}
  for i, note in ipairs(notes) do
    if not remove[i] then
      table.insert(cleaned, note)
    end
  end
  return cleaned
end

return M
