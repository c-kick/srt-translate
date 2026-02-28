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

## Skill Triggering Description

The SKILL.md description could be more aggressive about edge cases to improve trigger accuracy. Currently it may miss unusual phrasings. Consider adding explicit mentions of:
- Reviewing existing NL subtitles against EN source
- Requests mentioning `.srt` files with Dutch/Nederlands/NL
- Subtitle QC or quality check requests for Dutch

## Workflow Density in Post-Processing

`workflow-post.md` covers Phases 3–9+LOG in a single context load. If Claude occasionally skips or conflates phases, the density could be a factor. Consider:
- Adding explicit phase-transition markers (e.g. "Phase N complete. Proceeding to Phase N+1.")
- A checklist Claude must tick through before moving to the next phase
- Splitting post-processing into two phase groups if context pressure becomes an issue

## Batch Context Continuity

Translation batches write context summaries to `batchN_context.md`, and subsequent batches read them. When a new Claude invocation starts (every 6 batches), nuanced character voice decisions or terminology choices from earlier batches may lose fidelity through summarization. Consider:
- A cumulative running glossary file that grows across all batches (character names, T-V register choices, recurring terminology) rather than per-batch summaries alone
- Having each new invocation read the glossary in addition to the batch context files

## End-to-End Regression Testing

No automated way to smoke-test the full pipeline. A lightweight regression test could catch regressions faster:
- Translate the first 20 cues of a known file and check constraint compliance on the output
- Compare merge ratios and CPS distributions against a reference baseline
- Could be a `--test` flag on `orchestrate.sh` that runs a truncated pipeline on a bundled test file

## Phase-Level Error Recovery

Individual phase failures restart the entire phase group. If Phase 6 (linguistic review) fails mid-way through a large file, there's no mechanism to resume from the last reviewed chunk. Consider:
- Per-phase checkpointing within post-processing (e.g. writing a `phase_N_complete` marker)
- Allowing `--phase N` to resume within the post-processing group rather than restarting from Phase 3

## References

- Existing misalignment case: Fawlty Towers / documentary test — cues 102-108, ~00:10:18
- Netflix spec: minimum 2-frame gap (80ms @ 25fps)
