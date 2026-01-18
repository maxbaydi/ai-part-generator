local const = require("ai_part_generator.constants")
local profiles = require("ai_part_generator.profiles")
local utils = require("ai_part_generator.utils")

local M = {}

local cached_profiles = nil
local cached_profiles_by_id = nil
local get_track_name_for_item
local collect_cc_from_item
local ZERO_TIME_Q = 0

local function get_profiles_cache()
  if cached_profiles ~= nil then
    return cached_profiles, cached_profiles_by_id
  end
  cached_profiles, cached_profiles_by_id = profiles.load_profiles()
  return cached_profiles, cached_profiles_by_id
end

local function resolve_track_profile(track)
  if not track then
    return nil, nil
  end
  local profile_id = profiles.get_track_profile_id(track)
  local profile = nil
  if profile_id then
    local _, by_id = get_profiles_cache()
    profile = by_id and by_id[profile_id] or nil
    return profile_id, profile
  end
  local list, by_id = get_profiles_cache()
  if not list or not by_id then
    return nil, nil
  end
  return profiles.find_profile_for_track(track, list, by_id)
end

local function round_q(value)
  return math.floor((tonumber(value) or 0) * const.CONTEXT_QN_ROUNDING) / const.CONTEXT_QN_ROUNDING
end

local function append_items(target, items)
  if not target or not items then
    return
  end
  for _, item in ipairs(items) do
    table.insert(target, item)
  end
end

local function get_selected_items()
  local items = {}
  local count = reaper.CountSelectedMediaItems(0)
  for i = 0, count - 1 do
    local item = reaper.GetSelectedMediaItem(0, i)
    if item then
      table.insert(items, item)
    end
  end
  return items
end

local function filter_items_by_track(items, track)
  local result = {}
  for _, item in ipairs(items or {}) do
    if reaper.GetMediaItem_Track(item) == track then
      table.insert(result, item)
    end
  end
  return result
end

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

local function collect_selected_continuation_notes(selected_items, target_track, selection_start_qn)
  local notes = {}
  if not selected_items or #selected_items == 0 or not target_track then
    return notes
  end

  for _, item in ipairs(selected_items) do
    if reaper.GetMediaItem_Track(item) == target_track then
      local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
      local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
      local item_end = item_start + item_len
      local item_notes = collect_notes_with_abs_position(item, item_start, item_end)
      for _, note in ipairs(item_notes) do
        table.insert(notes, {
          start_q = note.start_qn - selection_start_qn,
          dur_q = note.dur_q,
          pitch = note.pitch,
          vel = note.vel,
          chan = note.chan,
        })
      end
    end
  end

  return notes
end

local function collect_selected_continuation_cc_events(selected_items, target_track, start_sec, end_sec, selection_start_qn)
  local events = {}
  if not selected_items or #selected_items == 0 or not target_track then
    return events
  end

  local track_name = utils.get_track_name(target_track)
  for _, item in ipairs(selected_items) do
    if reaper.GetMediaItem_Track(item) == target_track then
      local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
      local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
      local item_end = item_start + item_len
      local range_start = item_start
      local range_end = item_end
      if range_end > start_sec and range_start < end_sec then
        local cc_events = collect_cc_from_item(item, range_start, range_end, selection_start_qn, track_name, nil, false)
        append_items(events, cc_events)
      end
    end
  end

  return events
end

local function collect_full_selected_tracks_context(selected_items, target_track, selection_start_qn)
  local tracks_map = {}
  if not selected_items or #selected_items == 0 then
    return {}
  end

  for _, item in ipairs(selected_items) do
    local item_track = reaper.GetMediaItem_Track(item)
    if item_track and item_track ~= target_track then
      local track_name = get_track_name_for_item(item)
      local track_key = tostring(item_track)
      local track_data = tracks_map[track_key]
      if not track_data then
        local profile_id, profile = resolve_track_profile(item_track)
        track_data = {
          name = track_name,
          profile_id = profile_id,
          profile_name = profile and profile.name or nil,
          notes = {},
          cc_events = {},
        }
        tracks_map[track_key] = track_data
      end

      local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
      local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
      local item_end = item_start + item_len
      local notes = collect_notes_with_abs_position(item, item_start, item_end)
      for _, note in ipairs(notes) do
        table.insert(track_data.notes, {
          start_q = note.start_qn - selection_start_qn,
          dur_q = note.dur_q,
          pitch = note.pitch,
          vel = note.vel,
          chan = note.chan,
        })
      end

      local cc_events = collect_cc_from_item(item, item_start, item_end, selection_start_qn, track_name, nil, false)
      append_items(track_data.cc_events, cc_events)
    end
  end

  local result = {}
  for _, data in pairs(tracks_map) do
    if #data.notes > 1 then
      table.sort(data.notes, function(a, b)
        return (a.start_q or 0) < (b.start_q or 0)
      end)
    end
    if #data.cc_events > 1 then
      table.sort(data.cc_events, function(a, b)
        return (a.time_q or 0) < (b.time_q or 0)
      end)
    end
    table.insert(result, data)
  end

  return result
end

collect_cc_from_item = function(item, start_sec, end_sec, selection_start_qn, track_name, max_events, clamp_to_zero)
  local events = {}
  if max_events ~= nil and max_events <= 0 then
    return events
  end
  local take = reaper.GetActiveTake(item)
  if not take or not reaper.TakeIsMIDI(take) then
    return events
  end

  local _, _, cc_count = reaper.MIDI_CountEvts(take)
  local start_ppq = reaper.MIDI_GetPPQPosFromProjTime(take, start_sec)
  local end_ppq = reaper.MIDI_GetPPQPosFromProjTime(take, end_sec)

  for c = 0, cc_count - 1 do
    local ok, _, _, ppqpos, chanmsg, chan, msg2, msg3 = reaper.MIDI_GetCC(take, c)
    if ok and chanmsg == const.MIDI_CC_STATUS and ppqpos >= start_ppq and ppqpos <= end_ppq then
      local time_sec = reaper.MIDI_GetProjTimeFromPPQPos(take, ppqpos)
      local time_qn = reaper.TimeMap2_timeToQN(0, time_sec)
      local time_q = time_qn - selection_start_qn
      if clamp_to_zero ~= false then
        time_q = math.max(ZERO_TIME_Q, time_q)
      end
      local event = {
        time_q = time_q,
        cc = msg2,
        value = msg3,
        chan = chan + 1,
      }
      if track_name and track_name ~= "" then
        event.track = track_name
      end
      table.insert(events, event)
    end

    if max_events ~= nil and #events >= max_events then
      break
    end
  end

  return events
end

get_track_name_for_item = function(item)
  local track = reaper.GetMediaItem_Track(item)
  if track then
    return utils.get_track_name(track)
  end
  return "Unknown"
end

local function collect_horizontal_context_from_items(items, start_sec, end_sec, track_name)
  local selection_start_qn = reaper.TimeMap2_timeToQN(0, start_sec)
  local selection_end_qn = reaper.TimeMap2_timeToQN(0, end_sec)

  local before_notes = {}
  local after_notes = {}
  local cc_events = {}

  local before_start_sec = math.max(0, start_sec - const.HORIZONTAL_CONTEXT_RANGE_SEC)
  local after_end_sec = end_sec + const.HORIZONTAL_CONTEXT_RANGE_SEC

  for _, item in ipairs(items or {}) do
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
      local before_cc = collect_cc_from_item(
        item,
        before_start_sec,
        start_sec,
        selection_start_qn,
        track_name,
        const.MAX_CONTEXT_CC_EVENTS - #cc_events
      )
      append_items(cc_events, before_cc)
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
      local after_cc = collect_cc_from_item(
        item,
        end_sec,
        after_end_sec,
        selection_start_qn,
        track_name,
        const.MAX_CONTEXT_CC_EVENTS - #cc_events
      )
      append_items(cc_events, after_cc)
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
    cc_events = cc_events,
  }
end

local function collect_horizontal_context(target_track, start_sec, end_sec, selected_items, require_selected)
  if not target_track then
    return nil
  end

  if selected_items and #selected_items > 0 then
    local items_on_track = filter_items_by_track(selected_items, target_track)
    if #items_on_track > 0 then
      local track_name = utils.get_track_name(target_track)
      return collect_horizontal_context_from_items(items_on_track, start_sec, end_sec, track_name)
    end
    if require_selected then
      return nil
    end
  end

  local items = {}
  local item_count = reaper.CountTrackMediaItems(target_track)
  for i = 0, item_count - 1 do
    local item = reaper.GetTrackMediaItem(target_track, i)
    if item then
      table.insert(items, item)
    end
  end
  local track_name = utils.get_track_name(target_track)
  return collect_horizontal_context_from_items(items, start_sec, end_sec, track_name)
end

local function collect_extended_vertical_context(start_sec, end_sec, target_track, selected_items)
  local items_data = {}
  local all_notes = {}
  local selection_start_qn = reaper.TimeMap2_timeToQN(0, start_sec)
  local all_cc_events = {}

  local extended_start = math.max(0, start_sec - const.HORIZONTAL_CONTEXT_RANGE_SEC)
  local extended_end = end_sec + const.HORIZONTAL_CONTEXT_RANGE_SEC

  local items = selected_items or get_selected_items()
  if #items == 0 then
    return items_data, all_notes, {}, all_cc_events
  end

  local progression_notes = {}
  local selection_end_qn = reaper.TimeMap2_timeToQN(0, end_sec)
  local selection_duration_qn = selection_end_qn - selection_start_qn

  for _, item in ipairs(items) do
    local item_track = reaper.GetMediaItem_Track(item)
    if item_track ~= target_track then
      local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
      local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
      local item_end = item_start + item_len

      if item_start < extended_end and item_end > extended_start then
        local notes = collect_notes_with_abs_position(item, extended_start, extended_end)
        local track_name = get_track_name_for_item(item)
        local profile_id, profile = resolve_track_profile(item_track)
        
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
            if relative_q >= 0 and relative_q < selection_duration_qn then
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
            local track_cc_events = collect_cc_from_item(
              item,
              start_sec,
              end_sec,
              selection_start_qn,
              track_name,
              const.MAX_CONTEXT_CC_EVENTS - #all_cc_events
            )
            append_items(all_cc_events, track_cc_events)
            table.insert(items_data, {
              name = track_name,
              profile_id = profile_id,
              profile_name = profile and profile.name or nil,
              notes = notes_in_selection,
              cc_events = track_cc_events,
            })
          end
        end
      end
    end
  end

  return items_data, all_notes, progression_notes, all_cc_events
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
    local entry = {
      start_q = round_q(n.start_q),
      dur_q = round_q(n.dur_q),
      pitch = n.pitch,
      vel = n.vel,
      chan = n.chan,
    }
    if n.track then
      entry.track = n.track
    end
    table.insert(result, entry)
  end
  return result
end

local function format_cc_events_for_bridge(events, max_count)
  local result = {}
  for i, evt in ipairs(events) do
    if i > max_count then
      break
    end
    local entry = {
      time_q = round_q(evt.time_q),
      cc = evt.cc,
      value = evt.value,
      chan = evt.chan,
    }
    if evt.track then
      entry.track = evt.track
    end
    table.insert(result, entry)
  end
  return result
end

function M.build_context(use_selected, target_track, start_sec, end_sec)
  local selected_items = use_selected and get_selected_items() or nil
  local require_selected = use_selected and selected_items and #selected_items > 0
  local selection_start_qn = reaper.TimeMap2_timeToQN(0, start_sec)
  local horizontal = collect_horizontal_context(target_track, start_sec, end_sec, selected_items, require_selected)
  
  if not use_selected then
    if horizontal and (#horizontal.before > 0 or #horizontal.after > 0) then
      local result = {
        horizontal = {
          before = format_notes_for_bridge(horizontal.before, const.MAX_HORIZONTAL_CONTEXT_NOTES),
          after = format_notes_for_bridge(horizontal.after, const.MAX_HORIZONTAL_CONTEXT_NOTES),
          position = horizontal.position,
        },
        selected_tracks_midi = {},
        existing_notes = {},
        pitch_range = nil,
      }
      local horizontal_cc = horizontal.cc_events or {}
      if #horizontal_cc > 0 then
        result.cc_events = format_cc_events_for_bridge(horizontal_cc, const.MAX_CONTEXT_CC_EVENTS)
      end
      return result
    end
    return nil
  end

  local items_data, all_notes, progression_notes, all_cc_events = collect_extended_vertical_context(
    start_sec,
    end_sec,
    target_track,
    selected_items
  )

  if #all_notes == 0 and (not horizontal or (#horizontal.before == 0 and #horizontal.after == 0)) then
    return nil
  end

  local min_pitch, max_pitch = get_pitch_range(all_notes)

  local track_names = {}
  for _, item_data in ipairs(items_data) do
    if item_data.name and item_data.name ~= "" then
      track_names[item_data.name] = true
    end
  end
  local track_list = {}
  for name in pairs(track_names) do
    table.insert(track_list, name)
  end

  local notes_for_bridge = format_notes_for_bridge(all_notes, 200)
  local continuation_notes = collect_selected_continuation_notes(selected_items, target_track, selection_start_qn)
  if #continuation_notes > 1 then
    table.sort(continuation_notes, function(a, b)
      return (a.start_q or 0) < (b.start_q or 0)
    end)
  end
  local continuation_cc_events = collect_selected_continuation_cc_events(
    selected_items,
    target_track,
    start_sec,
    end_sec,
    selection_start_qn
  )
  local full_selected_tracks = collect_full_selected_tracks_context(selected_items, target_track, selection_start_qn)

  local context_result = {
    selected_tracks_midi = track_list,
    context_tracks = items_data,
    context_notes = "",
    existing_notes = notes_for_bridge,
    pitch_range = min_pitch and { min = min_pitch, max = max_pitch } or nil,
  }

  if #continuation_notes > 0 then
    context_result.continuation_source = format_notes_for_bridge(continuation_notes, #continuation_notes)
  end
  if #continuation_cc_events > 0 then
    context_result.continuation_cc_events = format_cc_events_for_bridge(continuation_cc_events, #continuation_cc_events)
  end
  if #full_selected_tracks > 0 then
    context_result.selected_tracks_full = full_selected_tracks
  end

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

  local combined_cc_events = {}
  local horizontal_cc = horizontal and horizontal.cc_events or {}
  append_items(combined_cc_events, horizontal_cc)
  append_items(combined_cc_events, all_cc_events)
  if #combined_cc_events > 0 then
    context_result.cc_events = format_cc_events_for_bridge(combined_cc_events, const.MAX_CONTEXT_CC_EVENTS)
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
