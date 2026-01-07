local const = require("ai_part_generator.constants")
local utils = require("ai_part_generator.utils")

local M = {}

local function collect_notes_from_item(item, start_sec, end_sec, selection_start_qn)
  local notes = {}
  local take = reaper.GetActiveTake(item)
  if not take or not reaper.TakeIsMIDI(take) then
    return notes
  end

  local _, note_count = reaper.MIDI_CountEvts(take)
  local start_ppq = reaper.MIDI_GetPPQPosFromProjTime(take, start_sec)
  local end_ppq = reaper.MIDI_GetPPQPosFromProjTime(take, end_sec)

  for n = 0, note_count - 1 do
    local ok, _, _, note_start_ppq, note_end_ppq, chan, pitch, vel = reaper.MIDI_GetNote(take, n)
    if ok and note_end_ppq > start_ppq and note_start_ppq < end_ppq then
      local note_start_sec = reaper.MIDI_GetProjTimeFromPPQPos(take, note_start_ppq)
      local note_end_sec = reaper.MIDI_GetProjTimeFromPPQPos(take, note_end_ppq)
      local note_start_qn = reaper.TimeMap2_timeToQN(0, note_start_sec)
      local note_end_qn = reaper.TimeMap2_timeToQN(0, note_end_sec)

      local start_q = note_start_qn - selection_start_qn
      local dur_q = note_end_qn - note_start_qn

      table.insert(notes, {
        start_q = math.max(0, start_q),
        dur_q = dur_q,
        pitch = pitch,
        vel = vel,
        chan = chan + 1,
      })
    end

    if #notes >= const.MAX_CONTEXT_NOTES then
      break
    end
  end

  return notes
end

local function collect_notes_with_abs_position(item, start_sec, end_sec)
  local notes = {}
  local take = reaper.GetActiveTake(item)
  if not take or not reaper.TakeIsMIDI(take) then
    return notes
  end

  local _, note_count = reaper.MIDI_CountEvts(take)
  local start_ppq = reaper.MIDI_GetPPQPosFromProjTime(take, start_sec)
  local end_ppq = reaper.MIDI_GetPPQPosFromProjTime(take, end_sec)

  for n = 0, note_count - 1 do
    local ok, _, _, note_start_ppq, note_end_ppq, chan, pitch, vel = reaper.MIDI_GetNote(take, n)
    if ok and note_end_ppq > start_ppq and note_start_ppq < end_ppq then
      local note_start_sec = reaper.MIDI_GetProjTimeFromPPQPos(take, note_start_ppq)
      local note_end_sec = reaper.MIDI_GetProjTimeFromPPQPos(take, note_end_ppq)
      local note_start_qn = reaper.TimeMap2_timeToQN(0, note_start_sec)
      local note_end_qn = reaper.TimeMap2_timeToQN(0, note_end_sec)

      table.insert(notes, {
        start_qn = note_start_qn,
        end_qn = note_end_qn,
        dur_q = note_end_qn - note_start_qn,
        pitch = pitch,
        vel = vel,
        chan = chan + 1,
      })
    end

    if #notes >= const.MAX_CONTEXT_NOTES then
      break
    end
  end

  return notes
end

local function get_track_name_for_item(item)
  local track = reaper.GetMediaItem_Track(item)
  if track then
    return utils.get_track_name(track)
  end
  return "Unknown"
end

local function collect_horizontal_context(target_track, start_sec, end_sec)
  if not target_track then
    return nil
  end

  local selection_start_qn = reaper.TimeMap2_timeToQN(0, start_sec)
  local selection_end_qn = reaper.TimeMap2_timeToQN(0, end_sec)

  local before_notes = {}
  local after_notes = {}
  local item_count = reaper.CountTrackMediaItems(target_track)

  local before_start_sec = math.max(0, start_sec - const.HORIZONTAL_CONTEXT_RANGE_SEC)
  local after_end_sec = end_sec + const.HORIZONTAL_CONTEXT_RANGE_SEC

  for i = 0, item_count - 1 do
    local item = reaper.GetTrackMediaItem(target_track, i)
    if item then
      local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
      local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
      local item_end = item_start + item_len

      if item_end > before_start_sec and item_start < start_sec then
        local notes = collect_notes_with_abs_position(item, before_start_sec, start_sec)
        for _, note in ipairs(notes) do
          local relative_q = note.start_qn - selection_start_qn
          table.insert(before_notes, {
            start_q = relative_q,
            dur_q = note.dur_q,
            pitch = note.pitch,
            vel = note.vel,
            chan = note.chan,
          })
        end
      end

      if item_start < after_end_sec and item_end > end_sec then
        local notes = collect_notes_with_abs_position(item, end_sec, after_end_sec)
        for _, note in ipairs(notes) do
          local relative_q = note.start_qn - selection_start_qn
          table.insert(after_notes, {
            start_q = relative_q,
            dur_q = note.dur_q,
            pitch = note.pitch,
            vel = note.vel,
            chan = note.chan,
          })
        end
      end
    end
  end

  local has_before = #before_notes > 0
  local has_after = #after_notes > 0
  local position = "isolated"
  if has_before and has_after then
    position = "middle"
  elseif has_before then
    position = "end"
  elseif has_after then
    position = "start"
  end

  return {
    before = before_notes,
    after = after_notes,
    position = position,
    selection_start_qn = selection_start_qn,
    selection_duration_qn = selection_end_qn - selection_start_qn,
  }
end

local function collect_vertical_context(start_sec, end_sec, target_track)
  local items_data = {}
  local all_notes = {}
  local selection_start_qn = reaper.TimeMap2_timeToQN(0, start_sec)

  local item_count = reaper.CountSelectedMediaItems(0)
  if item_count == 0 then
    return items_data, all_notes
  end

  for i = 0, item_count - 1 do
    local item = reaper.GetSelectedMediaItem(0, i)
    if item then
      local item_track = reaper.GetMediaItem_Track(item)
      if item_track ~= target_track then
        local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
        local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
        local item_end = item_start + item_len

        if item_start < end_sec and item_end > start_sec then
          local notes = collect_notes_from_item(item, start_sec, end_sec, selection_start_qn)
          if #notes > 0 then
            local track_name = get_track_name_for_item(item)
            table.insert(items_data, {
              track = track_name,
              notes = notes,
            })
            for _, note in ipairs(notes) do
              note.track = track_name
              table.insert(all_notes, note)
            end
          end
        end
      end
    end
  end

  return items_data, all_notes
end

local function collect_extended_vertical_context(start_sec, end_sec, target_track)
  local items_data = {}
  local all_notes = {}
  local selection_start_qn = reaper.TimeMap2_timeToQN(0, start_sec)

  local extended_start = math.max(0, start_sec - const.HORIZONTAL_CONTEXT_RANGE_SEC)
  local extended_end = end_sec + const.HORIZONTAL_CONTEXT_RANGE_SEC

  local item_count = reaper.CountSelectedMediaItems(0)
  if item_count == 0 then
    return items_data, all_notes, {}
  end

  local progression_notes = {}

  for i = 0, item_count - 1 do
    local item = reaper.GetSelectedMediaItem(0, i)
    if item then
      local item_track = reaper.GetMediaItem_Track(item)
      if item_track ~= target_track then
        local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
        local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
        local item_end = item_start + item_len

        if item_start < extended_end and item_end > extended_start then
          local notes = collect_notes_with_abs_position(item, extended_start, extended_end)
          local track_name = get_track_name_for_item(item)
          
          for _, note in ipairs(notes) do
            local relative_q = note.start_qn - selection_start_qn
            local note_data = {
              start_q = relative_q,
              dur_q = note.dur_q,
              pitch = note.pitch,
              vel = note.vel,
              chan = note.chan,
              track = track_name,
            }
            table.insert(progression_notes, note_data)

            if relative_q >= 0 and relative_q < (reaper.TimeMap2_timeToQN(0, end_sec) - selection_start_qn) then
              table.insert(all_notes, note_data)
            end
          end

          if #notes > 0 then
            local notes_in_selection = {}
            for _, note in ipairs(notes) do
              local relative_q = note.start_qn - selection_start_qn
              if relative_q >= 0 and relative_q < (reaper.TimeMap2_timeToQN(0, end_sec) - selection_start_qn) then
                table.insert(notes_in_selection, {
                  start_q = relative_q,
                  dur_q = note.dur_q,
                  pitch = note.pitch,
                  vel = note.vel,
                  chan = note.chan,
                })
              end
            end
            if #notes_in_selection > 0 then
              table.insert(items_data, {
                track = track_name,
                notes = notes_in_selection,
              })
            end
          end
        end
      end
    end
  end

  return items_data, all_notes, progression_notes
end

local function get_pitch_range(all_notes)
  if #all_notes == 0 then
    return nil, nil
  end
  local min_pitch = 127
  local max_pitch = 0
  for _, n in ipairs(all_notes) do
    min_pitch = math.min(min_pitch, n.pitch)
    max_pitch = math.max(max_pitch, n.pitch)
  end
  return min_pitch, max_pitch
end

local function format_notes_for_bridge(notes, max_count)
  local result = {}
  for i, n in ipairs(notes) do
    if i > max_count then
      break
    end
    table.insert(result, {
      start_q = math.floor(n.start_q * 100) / 100,
      dur_q = math.floor(n.dur_q * 100) / 100,
      pitch = n.pitch,
      vel = n.vel,
    })
  end
  return result
end

function M.build_context(use_selected, target_track, start_sec, end_sec)
  local horizontal = collect_horizontal_context(target_track, start_sec, end_sec)
  
  if not use_selected then
    if horizontal and (#horizontal.before > 0 or #horizontal.after > 0) then
      return {
        horizontal = {
          before = format_notes_for_bridge(horizontal.before, const.MAX_HORIZONTAL_CONTEXT_NOTES),
          after = format_notes_for_bridge(horizontal.after, const.MAX_HORIZONTAL_CONTEXT_NOTES),
          position = horizontal.position,
        },
        selected_tracks_midi = {},
        existing_notes = {},
        pitch_range = nil,
      }
    end
    return nil
  end

  local items_data, all_notes, progression_notes = collect_extended_vertical_context(start_sec, end_sec, target_track)

  if #all_notes == 0 and (not horizontal or (#horizontal.before == 0 and #horizontal.after == 0)) then
    return nil
  end

  local min_pitch, max_pitch = get_pitch_range(all_notes)

  local track_names = {}
  for _, item_data in ipairs(items_data) do
    track_names[item_data.track] = true
  end
  local track_list = {}
  for name in pairs(track_names) do
    table.insert(track_list, name)
  end

  local notes_for_bridge = format_notes_for_bridge(all_notes, 200)

  local context_result = {
    selected_tracks_midi = track_list,
    context_notes = "",
    existing_notes = notes_for_bridge,
    pitch_range = min_pitch and { min = min_pitch, max = max_pitch } or nil,
  }

  if horizontal and (#horizontal.before > 0 or #horizontal.after > 0) then
    context_result.horizontal = {
      before = format_notes_for_bridge(horizontal.before, const.MAX_HORIZONTAL_CONTEXT_NOTES),
      after = format_notes_for_bridge(horizontal.after, const.MAX_HORIZONTAL_CONTEXT_NOTES),
      position = horizontal.position,
    }
  end

  if #progression_notes > 0 then
    context_result.extended_progression = format_notes_for_bridge(progression_notes, const.MAX_PROGRESSION_NOTES)
  end

  return context_result
end

function M.get_last_selected_track()
  local count = reaper.CountSelectedTracks(0)
  if count > 0 then
    return reaper.GetSelectedTrack(0, count - 1)
  end
  return nil
end

return M
