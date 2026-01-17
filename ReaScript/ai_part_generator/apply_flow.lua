local const = require("ai_part_generator.constants")
local helpers = require("ai_part_generator.generation_helpers")
local midi = require("ai_part_generator.midi")
local profiles = require("ai_part_generator.profiles")
local utils = require("ai_part_generator.utils")

local M = {}

local PHASE_CLEAR_NOTES = "clear_notes"
local PHASE_CLEAR_CC = "clear_cc"
local PHASE_INSERT_PC = "insert_pc"
local PHASE_INSERT_KS = "insert_keyswitches"
local PHASE_INSERT_CC = "insert_cc"
local PHASE_INSERT_NOTES = "insert_notes"
local PHASE_FINALIZE = "finalize"

local apply_state = nil

local function abort_apply(reason)
  if apply_state then
    reaper.Undo_EndBlock("AI Part Generator (aborted)", -1)
  end
  apply_state = nil
  if reason then
    utils.show_error(reason)
  end
end

local function apply_step()
  if not apply_state then
    return
  end

  local take = apply_state.take
  if not reaper.ValidatePtr(take, "MediaItem_Take*") then
    utils.log("apply_step ERROR: take no longer valid")
    abort_apply("MIDI take no longer available.")
    return
  end

  local phase = apply_state.phase
  local processed = 0

  if phase == PHASE_CLEAR_NOTES then
    local deleted = 0
    while apply_state.note_idx >= 0 and processed < const.DELETE_CHUNK_SIZE do
      local ok, _, _, note_start, note_end = reaper.MIDI_GetNote(take, apply_state.note_idx)
      if ok and note_end > apply_state.start_ppq and note_start < apply_state.end_ppq then
        reaper.MIDI_DeleteNote(take, apply_state.note_idx)
        deleted = deleted + 1
      end
      apply_state.note_idx = apply_state.note_idx - 1
      processed = processed + 1
    end
    if apply_state.note_idx < 0 then
      utils.log("apply_step: clear_notes done, deleted=" .. deleted)
      apply_state.phase = PHASE_CLEAR_CC
    end
    reaper.defer(apply_step)
    return
  end

  if phase == PHASE_CLEAR_CC then
    local deleted = 0
    while apply_state.cc_idx >= 0 and processed < const.DELETE_CHUNK_SIZE do
      local ok, _, _, ppqpos = reaper.MIDI_GetCC(take, apply_state.cc_idx)
      if ok and ppqpos >= apply_state.start_ppq and ppqpos <= apply_state.end_ppq then
        reaper.MIDI_DeleteCC(take, apply_state.cc_idx)
        deleted = deleted + 1
      end
      apply_state.cc_idx = apply_state.cc_idx - 1
      processed = processed + 1
    end
    if apply_state.cc_idx < 0 then
      utils.log("apply_step: clear_cc done, deleted=" .. deleted)
      apply_state.phase = PHASE_INSERT_PC
      apply_state.pc_idx = 1
      apply_state.ks_idx = 1
      apply_state.cc_ins_idx = 1
      apply_state.note_ins_idx = 1
    end
    reaper.defer(apply_step)
    return
  end

  if phase == PHASE_INSERT_PC then
    local list = apply_state.program_changes
    while apply_state.pc_idx <= #list and processed < const.APPLY_CHUNK_SIZE do
      midi.insert_program_change(take, apply_state.start_qn, list[apply_state.pc_idx])
      apply_state.pc_idx = apply_state.pc_idx + 1
      processed = processed + 1
    end
    if apply_state.pc_idx > #list then
      utils.log("apply_step: insert_pc done, count=" .. #list)
      apply_state.phase = PHASE_INSERT_KS
    end
    reaper.defer(apply_step)
    return
  end

  if phase == PHASE_INSERT_KS then
    local list = apply_state.keyswitches
    while apply_state.ks_idx <= #list and processed < const.APPLY_CHUNK_SIZE do
      midi.insert_note(take, apply_state.start_qn, list[apply_state.ks_idx])
      apply_state.ks_idx = apply_state.ks_idx + 1
      processed = processed + 1
    end
    if apply_state.ks_idx > #list then
      utils.log("apply_step: insert_keyswitches done, count=" .. #list)
      apply_state.phase = PHASE_INSERT_CC
    end
    reaper.defer(apply_step)
    return
  end

  if phase == PHASE_INSERT_CC then
    local list = apply_state.cc_events
    while apply_state.cc_ins_idx <= #list and processed < const.APPLY_CHUNK_SIZE do
      midi.insert_cc(take, apply_state.start_qn, list[apply_state.cc_ins_idx])
      apply_state.cc_ins_idx = apply_state.cc_ins_idx + 1
      processed = processed + 1
    end
    if apply_state.cc_ins_idx > #list then
      utils.log("apply_step: insert_cc done, count=" .. #list)
      apply_state.phase = PHASE_INSERT_NOTES
    end
    reaper.defer(apply_step)
    return
  end

  if phase == PHASE_INSERT_NOTES then
    local list = apply_state.notes
    while apply_state.note_ins_idx <= #list and processed < const.APPLY_CHUNK_SIZE do
      midi.insert_note(take, apply_state.start_qn, list[apply_state.note_ins_idx])
      apply_state.note_ins_idx = apply_state.note_ins_idx + 1
      processed = processed + 1
    end
    if apply_state.note_ins_idx > #list then
      utils.log("apply_step: insert_notes done, count=" .. #list)
      apply_state.phase = PHASE_FINALIZE
    end
    reaper.defer(apply_step)
    return
  end

  if phase == PHASE_FINALIZE then
    utils.log("apply_step: finalizing...")
    midi.sort(take)
    profiles.save_track_profile_id(apply_state.target_track, apply_state.profile_id)
    reaper.Undo_EndBlock("AI Part Generator", -1)
    reaper.UpdateArrange()
    utils.log("AI Part Generator: DONE! All MIDI data applied successfully.")
    apply_state = nil
    return
  end

  utils.log("apply_step WARNING: unknown phase=" .. tostring(phase))
end

function M.begin_apply(response, profile_id, profile, articulation_name, target_track, start_sec, end_sec, tempo_markers, on_tempo_applied, skip_tempo_markers)
  utils.log("begin_apply: starting...")

  if not reaper.ValidatePtr(target_track, "MediaTrack*") then
    utils.log("begin_apply ERROR: Target track no longer available")
    utils.show_error("Target track no longer available.")
    return
  end

  reaper.Undo_BeginBlock()

  local applied_bpm = nil
  if not skip_tempo_markers and tempo_markers and type(tempo_markers) == "table" and #tempo_markers > 0 then
    local success, first_bpm = helpers.apply_tempo_markers(tempo_markers, start_sec, end_sec)
    if success and first_bpm then
      applied_bpm = first_bpm
      utils.log("begin_apply: tempo markers applied, first BPM=" .. tostring(first_bpm))
    end
  elseif skip_tempo_markers and tempo_markers and #tempo_markers > 0 then
    utils.log("begin_apply: skipping tempo markers (compose mode - will apply after all parts)")
  end

  if on_tempo_applied and applied_bpm then
    on_tempo_applied(applied_bpm)
  end

  local item, take, created_new_take = midi.get_or_create_midi_item(target_track, start_sec, end_sec, true)
  if not take then
    utils.log("begin_apply ERROR: Failed to get MIDI take")
    reaper.Undo_EndBlock("AI Part Generator (aborted)", -1)
    utils.show_error("Failed to get MIDI take.")
    return
  end
  utils.log("begin_apply: got MIDI item and take (new_take=" .. tostring(created_new_take) .. ")")

  local start_qn = reaper.TimeMap_timeToQN(start_sec)
  local end_qn_val = reaper.TimeMap_timeToQN(end_sec)
  local start_ppq = reaper.MIDI_GetPPQPosFromProjQN(take, start_qn)
  local end_ppq = reaper.MIDI_GetPPQPosFromProjQN(take, end_qn_val)
  local _, note_count, cc_count = reaper.MIDI_CountEvts(take)

  utils.log(string.format("begin_apply: start_qn=%.2f end_qn=%.2f start_ppq=%.0f end_ppq=%.0f",
    start_qn, end_qn_val, start_ppq, end_ppq))
  utils.log(string.format("begin_apply: existing notes=%d cc=%d", note_count, cc_count))

  local notes = response.notes or {}
  local cc_events = response.cc_events or {}
  local keyswitches = response.keyswitches or {}
  local program_changes = response.program_changes or {}

  local response_articulation = tostring(response.articulation or "")
  local effective_articulation = tostring(articulation_name or "")
  if response_articulation ~= "" and response_articulation ~= const.ARTICULATION_MIXED then
    effective_articulation = response_articulation
  end

  if response_articulation ~= const.ARTICULATION_MIXED and profiles.is_legato_articulation(profile, effective_articulation) then
    midi.apply_legato_overlap(notes, const.LEGATO_NOTE_OVERLAP_Q)
  elseif response_articulation == const.ARTICULATION_MIXED then
    local changes = profiles.get_articulation_changes(profile, response)
    if #changes > 0 then
      midi.apply_legato_overlap_by_articulation_changes(
        notes,
        const.LEGATO_NOTE_OVERLAP_Q,
        changes,
        function(name)
          return profiles.is_legato_articulation(profile, name)
        end
      )
    end
  end
  notes = midi.resolve_same_pitch_overlaps(notes, const.SAME_PITCH_MIN_GAP_Q)

  utils.log(string.format("begin_apply: to insert: notes=%d cc=%d ks=%d pc=%d",
    #notes, #cc_events, #keyswitches, #program_changes))

  local initial_phase = created_new_take and PHASE_INSERT_PC or PHASE_CLEAR_NOTES

  apply_state = {
    phase = initial_phase,
    take = take,
    item = item,
    start_qn = start_qn,
    start_ppq = start_ppq,
    end_ppq = end_ppq,
    note_idx = note_count - 1,
    cc_idx = cc_count - 1,
    notes = notes,
    cc_events = cc_events,
    keyswitches = keyswitches,
    program_changes = program_changes,
    target_track = target_track,
    profile_id = profile_id,
    pc_idx = 1,
    ks_idx = 1,
    cc_ins_idx = 1,
    note_ins_idx = 1,
  }

  utils.log("begin_apply: starting apply_step with phase=" .. initial_phase)
  reaper.defer(apply_step)
end

function M.is_in_progress()
  return apply_state ~= nil
end

function M.abort(reason)
  abort_apply(reason)
end

return M
