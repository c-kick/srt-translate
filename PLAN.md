# Plan: Trim-to-Speech — Fix Subtitle Lingering

## Problem

Subtitles linger on screen well after the speaker stops talking. Confirmed on Helvetica (2007): **152 of 855 NL cues (17.8%) linger after speech**, of which 143 are NL-specific (not inherited from EN source timing).

This is uncomfortable to watch — the subtitle stays visible during silence, creating a disconnection between audio and text.

## Root Cause Analysis (verified 2026-03-05)

The pipeline has **three mechanisms to extend end times** but **zero automated mechanisms to trim them**.

### How lingering gets created

1. **Inherited EN timing (primary cause — 84% of cases):** EN source subtitles have generous end times that extend past actual speech boundaries. NL cues inherit EN timecodes. Even though NL end times are typically shorter than EN (Dutch is more concise), they still overshoot speech end.

2. **Gap-closing (secondary cause):** Phase 5 Step 0 (`extend_end_times.py --close-gaps 1000`) closes gaps < 1s by extending end times, pushing cues further into silence. This is the cause for the 12 cues where NL end exceeds EN end.

3. **CPS extension (minor cause):** Phase 5 Step 1 extends for CPS > 13. Only affects cues with high CPS — but 99 of 152 lingering cues have CPS < 13, so CPS extension is not the primary driver.

### What exists but doesn't fix it

- **Phase 9 (`vad_timing_check.py`):** Detects lingering but is QC-only — no `--fix` mode.
- **Phase 10 (`extend_to_speech_lite.py`):** Only extends, never shortens (line 154: `return max(speech_end_ms, cue_end_ms)`).
- **Workflow Phase 9 instructions:** Tell Claude to manually fix flagged cues — impractical for 150+ cues.
- **`validate_srt.py`:** Has `fix_overlap()` which shortens for overlap resolution only, not speech alignment.
- **`auto_merge_cues.py`:** Inherits last constituent's end_ms — does not create new lingering.
- **Phase 6 (Linguistic Review):** Explicitly forbidden from touching timecodes.

### Evidence summary

| Metric | Value |
|--------|-------|
| Total NL cues | 855 |
| Lingering cues | 152 (17.8%) |
| NL-specific (not inherited from EN) | 143 |
| Lingering + CPS < 13 (safe to trim) | 99 (65%) |
| Lingering + CPS 13-17 (trim with care) | 17 (11%) |
| Lingering + CPS > 17 (need text condensation) | 36 (24%) |
| NL end shorter than EN end | 127 (84%) |
| NL end longer than EN end | 12 (8%) |

---

## Solution: `trim_to_speech.py`

A new script that uses VAD to detect where speech actually ends and pulls back cue end times accordingly. Guarded by CPS constraints to ensure readability isn't sacrificed.

### Algorithm

```
For each cue:
  1. Run VAD around the cue's time window
  2. Find the last speech-to-silence transition before or near cue end
  3. If cue end > speech_end + comfort_buffer:
     a. Compute new_end = speech_end + comfort_buffer
     b. Calculate resulting CPS with new_end
     c. If CPS <= cps_soft_ceiling: apply trim
     d. If CPS > cps_soft_ceiling but <= cps_hard_limit:
        apply partial trim (extend to reach cps_soft_ceiling)
     e. If CPS would exceed cps_hard_limit: skip (flag for text condensation)
  4. Ensure new duration >= min_duration_ms
  5. Ensure gap to next cue >= 0 (never create overlap)
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--comfort-buffer` | 250 | ms to keep after speech end (prevents abrupt disappearance) |
| `--min-trim` | 400 | Minimum trim amount in ms (skip smaller trims to avoid chasing VAD noise) |
| `--cps-soft-ceiling` | 15 | Don't trim if CPS would exceed this (fps-aware via `--fps`) |
| `--fps` | 25 | Framerate for constraint lookup |
| `--aggressiveness` | 2 | VAD aggressiveness (0-3) |
| `--hangover` | 210 | Smooth silence gaps shorter than this (ms) |
| `--report` | - | Write JSON report of all trims |
| `--dry-run` | - | Report what would be trimmed without modifying |

### CPS guard logic (fps-aware)

The script imports `get_constraints()` from `srt_constants.py` to get framerate-specific limits:

- **24fps:** cps_hard_limit=15, cps_optimal=11
- **25fps:** cps_hard_limit=17, cps_optimal=12

The `--cps-soft-ceiling` default is 15, which is safe for both framerates. For 25fps content, this is well under the hard limit (17), giving comfortable margin.

### Integration with existing VAD infrastructure

Reuse the global VAD approach from `vad_timing_check.py`:
- `build_speech_map()` + `smooth_speech_map()` + `find_transitions()` for speech boundary detection
- Import shared utilities from `srt_utils.py`
- Reuse audio extraction and caching from `vad_timing_check.py`

This avoids the per-cue VAD approach in `extend_to_speech_lite.py` which is less accurate (no global context for smoothing).

---

## Pipeline Integration

### New phase position: Phase 4b (between merge and CPS optimization)

```
Phase 3:  Structural fix
Phase 4:  Merge (auto_merge_cues.py)
Phase 4b: Trim to speech (trim_to_speech.py)  <-- NEW
Phase 5:  CPS optimization (extend_end_times.py)
Phase 6:  Linguistic review
...
Phase 9:  VAD timing QC (vad_timing_check.py) — now mostly clean
```

**Why between merge and CPS:** Trimming before CPS optimization means Phase 5 can re-extend cues that genuinely need more display time (high CPS). This creates a natural push-pull: trim pulls back overlong cues, CPS extension pushes out underlong ones.

### Workflow changes

**`workflow-post.md`:** Add Phase 4b step between Phase 4 and Phase 5:

```bash
scripts/venv/bin/python3 scripts/trim_to_speech.py \
    "$VIDEO_FILE" \
    merged.nl.srt \
    -o merged.nl.srt \
    --fps ${FRAMERATE} \
    --report trim_report.json \
    -v
```

**`orchestrate.sh`:** Add trim invocation in `run_postprocessing()` prompt, between merge and CPS instructions.

### Phase 9 impact

With trim-to-speech in place, Phase 9 VAD QC should report far fewer linger issues. The manual fix instructions in workflow-post.md for lingering become a safety net rather than the primary mechanism.

---

## Files to Create/Modify

| File | Change |
|------|--------|
| `scripts/trim_to_speech.py` | **New:** Core trim-to-speech script |
| `scripts/test_trim_to_speech.py` | **New:** Unit tests (pytest) |
| `base/workflow-post.md` | Add Phase 4b between Phase 4 and Phase 5 |
| `scripts/orchestrate.sh` | Add trim step to post-processing prompt |

---

## Validation

1. **Unit tests:** Test CPS guard, min-trim threshold, comfort buffer, overlap prevention, min-duration guard
2. **Helvetica re-run:** Run `trim_to_speech.py` on current Helvetica NL output, then re-run `vad_timing_check.py` to measure improvement
3. **Target:** Reduce linger count from 152 to < 30 (the ~36 high-CPS cues that can't be trimmed without text condensation, plus VAD edge cases)

---

## Out of Scope

- **Text condensation for high-CPS lingering cues** — these 36 cues need shorter Dutch text, not shorter display time. Phase 5 Step 2 already handles this.
- **`extend_to_speech_lite.py` changes** — Phase 10 (speech sync) is opt-in for slow speakers and orthogonal to this fix.
- **EN source timing correction** — we don't modify the EN source; we work with what we get.
