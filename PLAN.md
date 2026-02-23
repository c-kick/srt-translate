# Implementation Plan: Improved Timing QC

## Context

This plan replaces the PocketSphinx approach described in TODO.md with a simpler, more reliable solution based on two independent analyses and an independent review of the codebase.

## Problem Statement

When Claude translates EN→NL subtitles, it merges and redistributes content across cue boundaries. The current Phase 9 VAD timing check (`vad_timing_check.py`) maps NL cues to EN cues using start-time proximity (`match_source_cues()` with 500ms tolerance). This mapping breaks when:
- Phase 2 (translation) merges/drops cues, changing the NL cue count relative to EN
- Phase 4 (auto merge) further reduces cue count
- Timecodes shift due to Phase 5 end-time extensions

Result: Phase 9 misidentifies which EN speech corresponds to which NL cue, producing false positives and missing real misalignments.

## Why NOT PocketSphinx

Both analyses agree:
1. **PocketSphinx is not in the repo** despite TODO.md claiming "already in repo." No `forced_align.py` exists.
2. **PocketSphinx accuracy (100-300ms) overlaps the detection threshold (500ms)**, making it unreliable for documentary content (the primary use case) where background music/ambience degrades alignment further.
3. **The core problem is mapping, not alignment.** Even with perfect word-level timestamps, you still need to know which EN words correspond to which NL cues. Forced alignment doesn't solve this.
4. **Simpler solutions exist** that leverage data already flowing through the pipeline.

## Key Design Constraint: Use Timecodes, Not Indices

**Learned from review:** Cue indices are rewritten by Phase 3 (`validate_srt.py --fix`) and again by Phase 7 (`renumber_cues.py`). Any mapping keyed by cue index will break when indices change. All mapping must use **start-time timecodes** as the primary key, since start times survive all pipeline phases (only end times are extended in Phase 5).

---

## Strategy: Incremental, Three-Level Improvement

### Level 1: Merge-Aware Cue Mapping (Low effort, High impact)

**What:** Improve Phase 9's NL→EN mapping by consuming the Phase 4 merge report, matching by timecodes rather than indices.

**Why it works:** `auto_merge_cues.py` already records `source_indices` for every merge (line 294). Combined with an enhancement to also record source timecodes, this tells Phase 9 exactly which time windows were combined, enabling accurate matching to EN cues.

**Changes:**

1. **`scripts/auto_merge_cues.py`** — Enhance the merge report to include source cue timecodes alongside indices:
   ```python
   report.append({
       "output_index": new_index,
       "output_start_ms": merge_candidates[0].start_ms,
       "output_end_ms": merge_candidates[-1].end_ms,
       "source_indices": [mc.index for mc in merge_candidates],
       "source_timecodes": [
           {"start_ms": mc.start_ms, "end_ms": mc.end_ms}
           for mc in merge_candidates
       ],
       "source_count": len(merge_candidates),
       ...
   })
   ```

2. **`scripts/vad_timing_check.py`** — Add `--merge-report` argument. Build a timecode-keyed merge map. For each NL cue, check if its start_ms matches a merge output's `output_start_ms` (within 50ms tolerance to account for minor Phase 5 adjustments). If matched, use the `source_timecodes` to find the original time windows, then match those to EN cues. Fall back to existing proximity matching for non-merged cues.

3. **`base/workflow-post.md`** — Update Phase 9 invocation to pass `merge_report.json`.

**No orchestrator changes needed:** Phases 3-9 run in a single Claude invocation within `run_postprocessing()`. The work directory is only cleaned after the invocation returns (line 588), so `merge_report.json` is available throughout all phases.

**Estimated scope:** ~20 lines added to auto_merge_cues.py, ~80-100 lines of Python changes to vad_timing_check.py. No new dependencies. No new scripts.

### Level 2: Draft-to-Source Timecode Mapping (Medium effort, Medium impact)

**What:** Before Phase 3 renumbers/reorders cues, save the draft NL cue timecodes and explicitly match them to EN source cues by start-time proximity. This captures the NL→EN correspondence established during Phase 2 translation, before any post-processing.

**Why timecodes, not indices:** Claude's cue numbering during Phase 2 is non-deterministic — when skipping SDH cues, Claude may number sequentially rather than preserving EN source indices. But start times are deterministic: NL cues inherit their source EN cue's start time. Start-time proximity matching between draft NL and source EN is reliable.

**Changes:**

1. **New: `scripts/save_draft_mapping.py`** (~80 lines) — Read draft.nl.srt and source EN SRT. Match each draft NL cue to EN cue(s) by start-time proximity. Output JSON mapping with timecodes as keys:
   ```python
   mapping = []
   for nl_cue in draft_cues:
       matched_en = [en for en in en_cues
                     if abs(en.start_ms - nl_cue.start_ms) <= 500]
       if not matched_en:
           best = min(en_cues, key=lambda e: abs(e.start_ms - nl_cue.start_ms))
           matched_en = [best] if abs(best.start_ms - nl_cue.start_ms) <= 1000 else []
       mapping.append({
           "nl_start_ms": nl_cue.start_ms,
           "nl_end_ms": nl_cue.end_ms,
           "en_indices": [e.index for e in matched_en],
           "en_start_ms": matched_en[0].start_ms if matched_en else None,
           "en_end_ms": matched_en[-1].end_ms if matched_en else None,
       })
   ```

2. **`scripts/vad_timing_check.py`** — Add `--draft-mapping` argument. When provided alongside `--merge-report`, build the complete timecode-based chain:
   - Final NL cue start_ms → merge report (find merge entry by output_start_ms) → source timecodes
   - Source timecodes → draft mapping (find entry by nl_start_ms) → EN source cue timecodes
   - This gives an accurate EN time window for each NL cue, even after multiple rounds of merging and renumbering.

3. **`scripts/orchestrate.sh`** — In `run_postprocessing()`, the mapping step is part of the Claude prompt (Claude runs it as a bash command before Phase 3). Add to the Phase 3 instructions:
   ```bash
   python3 scripts/save_draft_mapping.py "${WORK_DIR}/draft.nl.srt" \
       "${SOURCE_SRT}" --output "${WORK_DIR}/draft_mapping.json"
   ```

4. **`base/workflow-post.md`** — Document the pre-Phase-3 mapping step and updated Phase 9 invocation.

**Estimated scope:** ~80 lines new script + ~60 lines changes to vad_timing_check.py.

### Level 3: Optional Vosk Word-Level Alignment (High effort, Supplementary)

**What:** If Levels 1+2 prove insufficient, add optional Vosk-based forced alignment as a supplementary signal for deep QC.

**Why Vosk over PocketSphinx:** Better accuracy (50-150ms vs 100-300ms), smaller models (50MB vs 200MB), pre-built wheels (no SWIG), still CPU-friendly.

**Changes:**

1. **`scripts/requirements.txt`** — Add `vosk` as optional dependency.
2. **`scripts/setup.sh`** — Add optional model download.
3. **New: `scripts/forced_align.py`** (~150 lines) — Vosk-based word-level alignment, outputs JSON timestamp map.
4. **`scripts/vad_timing_check.py`** — Add `--deep-qc` flag that uses forced alignment data as supplementary signal to confirm/refute flagged cues.

**This level should ONLY be implemented if Levels 1+2 are insufficient.** It is not recommended as an initial step.

---

## Detailed Implementation: Level 1

### Step 1: Enhance `auto_merge_cues.py` merge report

At the `report.append(...)` call (line 294), add `output_start_ms`, `output_end_ms`, and `source_timecodes` fields:

```python
report.append({
    "output_index": new_index,
    "output_start_ms": merge_candidates[0].start_ms,
    "output_end_ms": merge_candidates[-1].end_ms,
    "source_indices": [mc.index for mc in merge_candidates],
    "source_timecodes": [
        {"start_ms": mc.start_ms, "end_ms": mc.end_ms}
        for mc in merge_candidates
    ],
    "source_count": len(merge_candidates),
    "gap_ms": merge_candidates[1].start_ms - merge_candidates[0].end_ms if len(merge_candidates) > 1 else 0,
    "combined_duration_ms": merged_cue.duration_ms,
    "text": combined_text
})
```

### Step 2: Modify `vad_timing_check.py`

Add new function:

```python
def load_merge_report(path):
    """Load merge report JSON, return list of merge entries."""
    if not path or not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    return data.get('merges', [])


def build_merge_timecode_map(merges):
    """Build lookup: output_start_ms → source_timecodes list.

    Uses start_ms as key since start times are stable through pipeline.
    """
    tc_map = {}
    for entry in merges:
        key = entry.get('output_start_ms')
        if key is not None:
            tc_map[key] = entry.get('source_timecodes', [])
    return tc_map


def match_source_cues_enhanced(nl_cues, en_cues, merge_tc_map=None, tolerance_ms=500):
    """
    Map NL→EN using merge timecodes + proximity fallback.

    For merged cues: expand to source timecodes, match each to EN.
    For non-merged cues: use start-time proximity.
    """
    matches = {}
    tc_match_tolerance = 50  # ms tolerance for timecode matching

    for nl in nl_cues:
        # Check if this NL cue is a merge result (by start_ms matching)
        source_timecodes = None
        if merge_tc_map:
            for merge_start, src_tcs in merge_tc_map.items():
                if abs(nl.start_ms - merge_start) <= tc_match_tolerance:
                    source_timecodes = src_tcs
                    break

        if source_timecodes:
            # Merged cue: find EN cues matching each source time window
            matched = []
            for src_tc in source_timecodes:
                for en in en_cues:
                    if (src_tc['start_ms'] - tolerance_ms <= en.start_ms
                            <= src_tc['end_ms'] + tolerance_ms):
                        if en not in matched:
                            matched.append(en)
            matches[nl.index] = matched if matched else _nearest_en(nl, en_cues, tolerance_ms)
        else:
            # Non-merged: existing proximity matching
            matches[nl.index] = _match_by_proximity(nl, en_cues, tolerance_ms)

    return matches


def _match_by_proximity(nl_cue, en_cues, tolerance_ms):
    """Match single NL cue to EN cues by start-time proximity."""
    matched = []
    for en in en_cues:
        if nl_cue.start_ms - tolerance_ms <= en.start_ms <= nl_cue.end_ms + tolerance_ms:
            matched.append(en)
    if not matched and en_cues:
        best = min(en_cues, key=lambda e: abs(e.start_ms - nl_cue.start_ms))
        if abs(best.start_ms - nl_cue.start_ms) <= tolerance_ms:
            matched = [best]
    return matched


def _nearest_en(nl_cue, en_cues, tolerance_ms):
    """Fallback: find nearest EN cue."""
    if not en_cues:
        return []
    best = min(en_cues, key=lambda e: abs(e.start_ms - nl_cue.start_ms))
    return [best] if abs(best.start_ms - nl_cue.start_ms) <= tolerance_ms else []
```

Update `main()`:
- Add `--merge-report` argument
- Load merge report and build timecode map
- Replace `match_source_cues()` call with `match_source_cues_enhanced()`

### Step 3: Update `workflow-post.md`

Update Phase 9 section to show the new invocation:

```bash
scripts/venv/bin/python3 scripts/vad_timing_check.py \
    "$VIDEO_FILE" \
    "${VIDEO_BASENAME}.nl.srt" \
    "${VIDEO_BASENAME}.en.srt" \
    --merge-report merge_report.json \
    --report vad_timing.json
```

---

## What NOT to Implement

1. **Option A (alignment hints during translation):** Adds cognitive load to the most critical phase. Risk of degrading translation quality outweighs benefit.
2. **Auto-correction of timecodes (TODO Step 5):** Too risky — corrections based on imperfect mapping can create cascading timing errors.
3. **PocketSphinx:** Outdated, insufficient accuracy, unnecessary for this problem.
4. **Index-based mapping:** Indices are rewritten by Phase 3 and Phase 7. All mapping must use start-time timecodes.

---

## Review Findings Incorporated

The following issues from the independent plan review have been addressed:

1. **Phase 7 renumbering breaks index-based lookup** → Redesigned to use timecodes as primary mapping keys throughout.
2. **"Draft numbering = EN source mapping" is unreliable** → Level 2 now explicitly matches by start-time proximity rather than assuming index correspondence.
3. **merge_report source_indices refer to post-Phase-3 indices** → Level 1 now uses `source_timecodes` (added to merge report) instead of indices.
4. **Phase 5 end-time modifications not accounted for** → Start times are stable; plan now explicitly notes this and uses start_ms as the matching key with a 50ms tolerance.
5. **Work dir cleanup timing concern overstated** → Clarified that Phases 3-9 run in a single Claude invocation within `run_postprocessing()`; work dir cleanup happens after.

---

## Files Changed (Level 1 + Level 2)

| File | Change | Level |
|------|--------|-------|
| `scripts/auto_merge_cues.py` | Add timecodes to merge report | 1 |
| `scripts/vad_timing_check.py` | Add merge-report and draft-mapping support | 1+2 |
| `scripts/save_draft_mapping.py` | **New:** Match draft NL → EN by timecode | 2 |
| `base/workflow-post.md` | Update Phase 9 docs, add pre-Phase-3 mapping step | 1+2 |
| `TODO.md` | Update to reflect revised approach | 1 |

---

## Testing Strategy

1. **Unit test for mapping logic:** Create a synthetic EN SRT (20 cues), NL SRT (15 cues, with some merges), and merge report. Verify the mapping correctly traces NL→EN using timecodes.
2. **Integration test with real data:** Run the improved Phase 9 on the reference case mentioned in TODO.md (Fawlty Towers cues 102-108, documentary test). Compare flagged cues with/without merge-report support.
3. **Regression check:** Run the improved Phase 9 on a known-good translation. Verify no false positives introduced.

---

## Success Criteria

1. Phase 9 correctly maps NL cues to EN cues even when cue counts differ by 20%+ (documentary merge ratios)
2. Zero new false positives on clean translations
3. Detection of the reference misalignment case (Fawlty Towers cues 102-108)
4. No changes to translation phase (Phase 2) or its output format
5. No new heavy dependencies
6. All mapping uses timecodes, never indices, as primary keys
