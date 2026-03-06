# Plan: Trim-to-Speech — Fix Subtitle Lingering

## Problem

Subtitles linger on screen well after the speaker stops talking. Confirmed on Helvetica (2007): **152 of 855 NL cues (17.8%) linger after speech**, of which 143 are NL-specific (not inherited from EN source timing).

This is uncomfortable to watch — the subtitle stays visible during silence, creating a disconnection between audio and text.

## Root Cause Analysis (verified 2025-03-05)

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

## Design Principle: Don't Touch What Works

The translator pipeline works very well. This plan adds **one new script** (`trim_to_speech.py`) that slots into the existing pipeline as Phase 4b. It does NOT refactor, restructure, or modify any existing scripts.

**What this plan changes:**
- Creates `scripts/trim_to_speech.py` (new file)
- Creates `scripts/test_trim_to_speech.py` (new file)
- Adds Phase 4b instructions to `base/workflow-post.md`
- Adds Phase 4b invocation to `scripts/orchestrate.sh`

**What this plan does NOT change:**
- `vad_timing_check.py` — untouched
- `extend_to_speech_lite.py` — untouched
- `srt_constants.py` — untouched (we import `get_constraints()`, no new constants)
- `auto_merge_cues.py` — untouched
- `extend_end_times.py` — untouched
- Translation phases (0-2) — untouched
- Phase 6 linguistic review — untouched

### VAD code reuse strategy

`trim_to_speech.py` imports directly from `vad_timing_check.py`:

```python
from vad_timing_check import (
    load_audio, build_speech_map, smooth_speech_map,
    find_transitions, find_nearest,
)
```

These functions are already clean, stateless, and well-tested. No extraction into a shared module needed — that's a refactor for another day, if ever.

### Phase 10 awareness

Phase 10 (`extend_to_speech_lite.py`, `--speech-sync`) extends end times; Phase 4b trims them. They could conflict. But Phase 10 is already opt-in and rarely used. Resolution: add a note in `workflow-post.md` that Phase 10 is not recommended when Phase 4b is active. No orchestrator logic changes needed.

---

## Solution: `trim_to_speech.py`

A new script that uses VAD to detect where speech actually ends and pulls back cue end times accordingly. Guarded by CPS constraints and gap constraints to ensure readability and spec compliance.

### Algorithm

```
1. Load audio, build global speech map (via vad_timing_check imports)
2. Smooth speech map, extract transitions (speech_starts, speech_ends)

For each cue:
  3. Find the last speech-to-silence transition at or before cue end
     - Use find_nearest(speech_ends, cue.end_ms, search_range)
     - If no transition found within search range: SKIP (ambiguous)
     - If speech_end > cue.end_ms: SKIP (cue is too SHORT, not too long)

  4. Compute linger = cue.end_ms - speech_end
     - If linger < min_trim: SKIP (not worth chasing VAD noise)

  5. Compute new_end = speech_end + comfort_buffer

  6. Enforce min_duration:
     - If new_end - cue.start_ms < min_duration_ms: SKIP

  7. Enforce min_gap (from get_constraints(), NOT just "no overlap"):
     - If next_cue exists and new_end > next_cue.start_ms - min_gap_ms:
       new_end = next_cue.start_ms - min_gap_ms
     - If that pushes duration below min_duration_ms: SKIP

  8. CPS guard:
     a. Calculate CPS with new_end
     b. If CPS <= cps_soft_ceiling: apply full trim
     c. If CPS > cps_soft_ceiling but <= cps_hard_limit:
        apply partial trim (find new_end where CPS = cps_soft_ceiling)
     d. If CPS would exceed cps_hard_limit: SKIP (flag for text condensation)

  9. Apply trim. Record: cue_num, old_end, new_end, trim_ms, new_cps, method
```

### Edge cases

| Edge case | Behavior | Rationale |
|-----------|----------|-----------|
| Speech extends past cue end | SKIP | Opposite problem — cue is too short |
| No speech transition found | SKIP | Could be music, SFX, or cross-talk |
| Dual-speaker cue | Trim normally | VAD sees combined speech; buffer covers pauses |
| Trim would violate min_gap_ms | Clamp to min_gap_ms or SKIP | Must respect framerate gap (120/125ms) |
| Trim would violate min_duration_ms | SKIP | Cue needs minimum display time |
| Last cue in file | Trim normally | No next-cue gap constraint |
| CPS between soft and hard ceiling | Partial trim | Max safe trim keeping CPS at ceiling |

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--comfort-buffer` | 250 | ms to keep after speech end (see Tuning section) |
| `--min-trim` | 400 | Minimum trim amount in ms (skip smaller trims) |
| `--fps` | 25 | Framerate for constraint lookup via `get_constraints()` |
| `--aggressiveness` | 2 | VAD aggressiveness (0-3) |
| `--hangover` | 210 | Smooth silence gaps shorter than this (ms) |
| `--output` / `-o` | required | Output SRT file (must differ from input) |
| `--report` | - | Write JSON report of all trims |
| `--dry-run` | - | Report only, don't write output |
| `-v` / `--verbose` | - | Print per-cue trim decisions |

### CPS guard logic (fps-aware)

Uses `get_constraints(fps)` from `srt_constants.py`:

- **24fps:** cps_hard_limit=15, cps_optimal=11, min_gap=125ms, min_duration=1400ms
- **25fps:** cps_hard_limit=17, cps_optimal=12, min_gap=120ms, min_duration=830ms

The CPS soft ceiling defaults to the fps-aware `cps_hard_limit`. All constraint values come from the existing single source of truth — no new constants.

### Comfort buffer: needs empirical tuning

250ms is an **initial estimate**. Rationale:

- VAD frame granularity is 30ms → speech-end jitter of ~30-90ms
- 250ms = ~8 frames of padding
- Too small (<150ms): subtitle vanishes abruptly
- Too large (>400ms): defeats the purpose

**Tuning protocol (post-implementation):**

1. Run on Helvetica at 150ms, 200ms, 250ms, 300ms
2. Compare: trims applied, CPS distribution, Phase 9 linger count
3. Spot-check 10 cues in VLC at each setting
4. Pick smallest buffer where nothing feels abruptly cut

### VAD accuracy awareness

WebRTC VAD accuracy degrades with background music, laugh tracks, and cross-talk. The `--min-trim 400` threshold and `--aggressiveness 2` defaults provide built-in conservatism. For noisy content (comedy with laugh tracks, panel shows), users can pass `--aggressiveness 3` and `--min-trim 500` via CLI.

No genre-specific defaults are hard-coded. Keep it simple; tune via flags if needed.

---

## Pipeline Integration

### Phase position: 4b (between merge and CPS optimization)

```
Phase 3:  Structural fix (validate_srt.py)
Phase 4:  Merge (auto_merge_cues.py) → merged.nl.srt
Phase 4b: Trim to speech (trim_to_speech.py) → trimmed.nl.srt    ← NEW
Phase 5:  CPS optimization (extend_end_times.py)
Phase 6:  Linguistic review
...
Phase 9:  VAD timing QC — validates trim effectiveness
```

**Why here:** Trimming before CPS optimization means Phase 5 can re-extend cues that were trimmed too aggressively (high CPS). Natural push-pull: trim pulls back overlong cues, CPS extension pushes out underlong ones.

### File flow

`trim_to_speech.py` reads `merged.nl.srt` and writes to a **separate** `trimmed.nl.srt`. Never in-place.

Phase 5 then reads `trimmed.nl.srt` instead of `merged.nl.srt`.

**Error handling:** If `trim_to_speech.py` fails, fall back to `cp merged.nl.srt trimmed.nl.srt` so the pipeline continues. Phase 9 will catch any lingering.

### `workflow-post.md` changes

Add between Phase 4 and Phase 5:

```markdown
### Phase 4b: Trim to Speech

Pulls back cue end times that linger past speech boundaries.

```bash
scripts/venv/bin/python3 scripts/trim_to_speech.py \
    "$VIDEO_FILE" \
    merged.nl.srt \
    --output trimmed.nl.srt \
    --fps ${FRAMERATE} \
    --report trim_report.json \
    -v
```

If the script fails, copy merged.nl.srt to trimmed.nl.srt and continue.

Phase 5 now reads trimmed.nl.srt instead of merged.nl.srt.
```

Add note to Phase 10 section:

```markdown
**Note:** Phase 10 (speech sync) extends end times to speech boundaries. If Phase 4b
(trim-to-speech) has already run, Phase 10 may partially undo trims. Avoid combining both
unless you have a specific reason (e.g., slow-speaker content that also has lingering issues).
```

### `orchestrate.sh` changes

In `run_postprocessing()`, add Phase 4b to the inline prompt between Phase 4 and Phase 5:

```
3. **Phase 4b:** Trim to speech → trimmed.nl.srt + trim_report.json
4. **Phase 5:** CPS optimization on trimmed.nl.srt (not merged.nl.srt)
```

That's it. No conditional logic, no Phase 10 auto-skip, no report validation in the orchestrator.

---

## Files to Create/Modify

| File | Change |
|------|--------|
| `scripts/trim_to_speech.py` | **New:** Core trim-to-speech script (~200-300 lines) |
| `scripts/test_trim_to_speech.py` | **New:** Unit tests with synthetic speech maps |
| `base/workflow-post.md` | Add Phase 4b section; update Phase 5 input; add Phase 10 note |
| `scripts/orchestrate.sh` | Add Phase 4b to post-processing prompt |

---

## Validation

1. **Unit tests** with synthetic speech maps (no audio needed) — cover the algorithm edge cases
2. **Helvetica integration test:** Run trim, then re-run Phase 9 VAD QC to measure improvement
3. **Target:** Reduce linger count from 152 to <30 (the ~36 high-CPS cues that need text condensation, not shorter display time)

### Integration test commands

```bash
# 1. Trim
scripts/venv/bin/python3 scripts/trim_to_speech.py \
    helvetica.mkv merged.nl.srt \
    --output trimmed.nl.srt --fps 25 --report trim_report.json -v

# 2. Structural integrity check
scripts/venv/bin/python3 scripts/validate_srt.py trimmed.nl.srt --summary

# 3. Re-run Phase 9 QC
scripts/venv/bin/python3 scripts/vad_timing_check.py \
    helvetica.mkv trimmed.nl.srt helvetica.en.srt \
    --report trimmed_vad.json

# 4. Compare linger counts
python3 -c "
import json
before = json.load(open('vad_timing.json'))
after = json.load(open('trimmed_vad.json'))
b = sum(1 for f in before['flagged']
        if any(i['type']=='lingers_after_speech' for i in f.get('issues',[])))
a = sum(1 for f in after['flagged']
        if any(i['type']=='lingers_after_speech' for i in f.get('issues',[])))
print(f'Linger: {b} → {a} ({b - a} fixed)')
"
```

---

## Out of Scope

- **Refactoring existing scripts** — `vad_timing_check.py` and `extend_to_speech_lite.py` work fine; extracting a shared `vad_utils.py` is a future nice-to-have, not a prerequisite.
- **Changing `extend_to_speech_lite.py` defaults** — its aggressiveness=1 is intentional for its use case (extending). Don't change working code.
- **Adding VAD constants to `srt_constants.py`** — the defaults live in the script's argparse; `srt_constants.py` stays focused on subtitle constraints.
- **Orchestrator Phase 10 auto-skip logic** — Phase 10 is already opt-in. A docs note is sufficient.
- **Genre-specific presets** — CLI flags handle this. Don't over-engineer before the first run.
- **Text condensation for high-CPS cues** — these need shorter Dutch text, not shorter display time.
- **EN source timing correction** — we work with what we get.
