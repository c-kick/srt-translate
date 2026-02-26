# TODO: Timing QC Improvements

## Completed: Merge-Aware Cue Mapping (Levels 1+2)

Replaced the PocketSphinx approach with timecode-based mapping. See `PLAN.md` for full analysis.

### What was done

1. **`auto_merge_cues.py`** — Merge report now includes `output_start_ms`, `output_end_ms`, and `source_timecodes` for each merge, enabling Phase 9 to trace merged cues back to their source time windows.

2. **`vad_timing_check.py`** — New `--merge-report` and `--draft-mapping` arguments. Uses a three-strategy matching approach:
   - Merge timecodes → source windows → EN cues (for merged cues)
   - Draft mapping → EN cue timecodes (for non-merged cues with draft data)
   - Start-time proximity fallback (original behavior)

3. **`save_draft_mapping.py`** (new) — Run before Phase 3 to capture NL→EN timecode correspondence from the translation draft, before renumbering destroys the relationship.

4. **`workflow-post.md`** — Updated with pre-Phase-3 mapping step and Phase 9 invocation with new flags.

### Why not PocketSphinx

- Not in the repo (TODO.md previously claimed it was)
- Accuracy (100-300ms) overlaps the detection threshold (500ms)
- The core problem is NL→EN mapping, not speech alignment
- Simpler timecode-based solutions work better

### Future: Level 3 (Vosk, if needed)

If Levels 1+2 prove insufficient, optional Vosk-based forced alignment can be added as a supplementary signal. See `PLAN.md` Level 3 for details.

## References

- Existing misalignment case: Fawlty Towers / documentary test — cues 102-108, ~00:10:18
- Netflix spec: minimum 2-frame gap (80ms @ 25fps)
