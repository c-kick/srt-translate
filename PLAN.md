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

## Prerequisite: Extract Shared VAD Module (`vad_utils.py`)

### Why this comes first

Three scripts currently consume WebRTC VAD independently:

| Script | VAD approach | Aggressiveness | Smoothing | Audio caching |
|--------|-------------|----------------|-----------|---------------|
| `vad_timing_check.py` | Global speech map | 2 | Hangover (210ms) | MD5-keyed `/tmp` cache |
| `extend_to_speech_lite.py` | Per-cue sliding window | 1 | None | Temp file (deleted) |
| `trim_to_speech.py` (planned) | Global speech map | 2 | Hangover (210ms) | ? |

Creating a third copy of VAD infrastructure is unacceptable. Before writing `trim_to_speech.py`, extract the shared primitives.

### What moves to `vad_utils.py`

Extract from `vad_timing_check.py`:

```python
# vad_utils.py — Shared VAD primitives for all speech-boundary scripts

# Audio extraction & caching
get_cache_path(video_path) -> str
extract_audio(video_path, wav_path) -> None
load_audio(video_path, no_cache=False) -> tuple[bytes, int]

# Global speech map
build_speech_map(audio, sr, vad, frame_ms=30) -> list[bool]
smooth_speech_map(speech_map, hangover_frames=7) -> list[bool]
find_transitions(speech_map, frame_ms=30) -> tuple[list[int], list[int]]

# Transition search
find_nearest(transitions, target_ms, search_range=2000) -> int | None
```

### Refactoring plan

1. Create `scripts/vad_utils.py` with functions above (extracted verbatim)
2. Update `vad_timing_check.py`: replace inline definitions with `from vad_utils import ...`
3. Update `extend_to_speech_lite.py`: replace its own `extract_audio`, `read_wave`, `frame_generator`, `find_speech_end_vad` with the shared module. **Preserve its per-cue behavior** — only change the imports, not the algorithm. (Full migration to global speech map is out of scope.)
4. New `trim_to_speech.py`: imports from `vad_utils.py` from the start
5. Run existing tests (`test_timing_qc.py`) to verify no regressions

### VAD settings standardization

Add default VAD settings to `srt_constants.py`:

```python
# VAD defaults (consistent across all speech-boundary scripts)
VAD_AGGRESSIVENESS = 2          # 0=lenient, 3=strict
VAD_HANGOVER_MS = 210           # Bridge silence gaps shorter than this
VAD_FRAME_MS = 30               # WebRTC frame duration
VAD_SEARCH_RANGE_MS = 2000      # Max distance to search for transitions
```

All three scripts use these as defaults (overridable via CLI flags). This eliminates the current divergence where `extend_to_speech_lite.py` defaults to aggressiveness=1 while everything else uses 2.

**Note:** `extend_to_speech_lite.py` currently uses aggressiveness=1. Changing its default to 2 is a behavioral change. Document this in the commit message. Users who relied on `--aggressiveness 1` can still pass it explicitly.

---

## Solution: `trim_to_speech.py`

A new script that uses VAD to detect where speech actually ends and pulls back cue end times accordingly. Guarded by CPS constraints and gap constraints to ensure readability and spec compliance.

### Algorithm

```
1. Load audio, build global speech map (via vad_utils)
2. Smooth speech map, extract transitions (speech_starts, speech_ends)

For each cue:
  3. Find the last speech-to-silence transition at or before cue end + tolerance
     - Use find_nearest(speech_ends, cue.end_ms, search_range)
     - If no transition found within search range: SKIP (ambiguous — could be
       music, cross-talk, or VAD noise)
     - If speech_end > cue.end_ms: SKIP (speech extends past cue — the
       opposite problem; this cue is too SHORT, not too long)

  4. Compute linger = cue.end_ms - speech_end
     - If linger < min_trim: SKIP (not worth chasing VAD noise for small gains)

  5. Compute new_end = speech_end + comfort_buffer

  6. Enforce min_duration:
     - If new_end - cue.start_ms < min_duration_ms: SKIP

  7. Enforce min_gap (from srt_constants, NOT just "no overlap"):
     - If next_cue exists and new_end > next_cue.start_ms - min_gap_ms:
       new_end = next_cue.start_ms - min_gap_ms
     - If that pushes new_end <= cue.start_ms + min_duration_ms: SKIP

  8. CPS guard:
     a. Calculate CPS with new_end
     b. If CPS <= cps_soft_ceiling: apply full trim
     c. If CPS > cps_soft_ceiling but <= cps_hard_limit:
        apply partial trim (find new_end where CPS = cps_soft_ceiling)
     d. If CPS would exceed cps_hard_limit: SKIP (flag for text condensation)

  9. Apply trim. Record: cue_num, old_end, new_end, trim_ms, new_cps, method
```

### Edge cases handled explicitly

| Edge case | Behavior | Rationale |
|-----------|----------|-----------|
| Speech extends past cue end | SKIP | Cue is too short, not too long — opposite problem |
| No speech transition found | SKIP | Could be music, SFX, or cross-talk confusing VAD |
| Dual-speaker cue | Trim normally | VAD sees combined speech; comfort buffer covers inter-speaker pauses |
| Trim would violate min_gap_ms | Clamp to min_gap_ms or SKIP | Must respect framerate-dependent gap (120ms/125ms), not just "no overlap" |
| Trim would violate min_duration_ms | SKIP | Cue needs minimum display time |
| Last cue in file | Trim normally | No next-cue gap constraint |
| CPS between soft and hard ceiling | Partial trim | Find the maximum safe trim that keeps CPS at soft ceiling |

### Parameters

| Parameter | Default | Source | Description |
|-----------|---------|--------|-------------|
| `--comfort-buffer` | 250 | *Initial estimate — see Tuning section* | ms to keep after speech end |
| `--min-trim` | 400 | Avoids chasing VAD noise (VAD accuracy ~30-90ms per frame) | Minimum trim amount in ms |
| `--cps-soft-ceiling` | (fps-aware) | `srt_constants.cps_hard_limit` | Don't trim if CPS would exceed this |
| `--fps` | 25 | From checkpoint | Framerate for constraint lookup |
| `--aggressiveness` | 2 | `srt_constants.VAD_AGGRESSIVENESS` | VAD aggressiveness (0-3) |
| `--hangover` | 210 | `srt_constants.VAD_HANGOVER_MS` | Smooth silence gaps shorter than this (ms) |
| `--report` | - | - | Write JSON report of all trims |
| `--dry-run` | - | - | Report what would be trimmed without modifying |

### CPS guard logic (fps-aware)

The script imports `get_constraints()` from `srt_constants.py` to get framerate-specific limits:

- **24fps:** cps_hard_limit=15, cps_optimal=11
- **25fps:** cps_hard_limit=17, cps_optimal=12

The `--cps-soft-ceiling` default is the fps-aware `cps_hard_limit` from `get_constraints()`, NOT a fixed value. For 25fps content this is 17; for 24fps it's 15.

### Comfort buffer: initial estimate, not a tuned value

The 250ms comfort buffer is an **initial estimate** based on:

- WebRTC VAD frame granularity is 30ms, so speech-end detection has ~30-90ms jitter
- 250ms provides ~8 frames of padding at 30ms/frame
- Netflix minimum gap is 2 frames (80ms at 25fps) — we want significantly more than that for readability
- Too small (<150ms): subtitle disappears abruptly, feels "snatched away"
- Too large (>400ms): defeats the purpose of trimming

**This value needs empirical validation.** The tuning protocol is:

1. Run trim on Helvetica at 150ms, 200ms, 250ms, 300ms
2. For each: count trims applied, measure CPS distribution, re-run Phase 9 VAD QC
3. Spot-check 10 representative cues in VLC at each setting
4. Select the smallest buffer where no cues feel abruptly cut

Document the chosen value's justification in the commit that finalizes it.

---

## Genre-Specific Considerations

WebRTC VAD is designed for speech detection. Its accuracy degrades with:

- **Background music** (common in documentaries) — music detected as speech
- **Laugh tracks** (comedy) — audience laughter detected as speech
- **Cross-talk / overlapping dialogue** (fast-unscripted) — VAD can't distinguish speakers
- **Sound effects** (drama) — loud SFX can trigger false speech detection

### Genre parameter overrides

| Genre | Comfort buffer | Min trim | Aggressiveness | Notes |
|-------|---------------|----------|----------------|-------|
| Documentary | 250ms | 400ms | 2 | Most lingering; background score may extend speech boundaries |
| Drama | 250ms | 400ms | 2 | Generally clean audio |
| Comedy | 300ms | 500ms | 3 | Laugh tracks need stricter VAD + larger buffer |
| Fast-unscripted | 300ms | 500ms | 3 | Cross-talk needs stricter filtering |

These are **starting points**. The `--comfort-buffer`, `--min-trim`, and `--aggressiveness` flags allow per-run override.

The script accepts `--genre` (optional) to apply these defaults automatically. When `--genre` is not passed, the global defaults apply.

---

## Phase 10 Interaction: Explicit Analysis

### The conflict

Phase 4b **trims** cue end times to speech boundaries. Phase 10 (`extend_to_speech_lite.py`) **extends** cue end times to speech boundaries. They operate on the same dimension (end time vs. speech end) but in opposite directions.

Worse, they use **different VAD implementations**:

| | Phase 4b (trim) | Phase 10 (extend) |
|---|---|---|
| Speech map | Global (full audio) | Per-cue (sliding window) |
| Aggressiveness | 2 | 1 (more lenient) |
| Smoothing | Hangover 210ms | None |
| Audio caching | MD5-keyed `/tmp` | Temp file (deleted) |

Phase 10 with aggressiveness=1 will detect "speech" where Phase 4b (aggressiveness=2) detected silence. This means Phase 10 can **undo trims** from Phase 4b.

### Resolution

After the `vad_utils.py` refactor, Phase 10 will share the same audio cache and can optionally use the global speech map. But the fundamental conflict remains: if we trim in Phase 4b, extending in Phase 10 is contradictory.

**Decision: Phase 10 (`--speech-sync`) should be skipped when Phase 4b has run.**

Implementation:
- `trim_to_speech.py` writes a marker file `trim_report.json` when it runs
- `orchestrate.sh`: if `trim_report.json` exists AND `--speech-sync` is set, log a warning: `"Skipping Phase 10: trim-to-speech already aligned end times to speech boundaries"` and skip the Phase 10 invocation
- `workflow-post.md`: add a note under Phase 10 explaining the mutual exclusivity

For users who genuinely want both (trim aggressive lingering, then extend for slow speakers), they can run Phase 10 manually after reviewing the trim report. But the automated pipeline should not fight itself.

---

## File I/O: No In-Place Overwrites

The pipeline must never read from and write to the same file in a single script invocation. A crash mid-write corrupts the pipeline.

### File flow through post-processing

```
Phase 3:  draft.nl.srt           → draft-fixed.nl.srt
Phase 4:  draft-fixed.nl.srt     → merged.nl.srt       + merge_report.json
Phase 4b: merged.nl.srt          → trimmed.nl.srt       + trim_report.json    ← NEW
Phase 5:  trimmed.nl.srt         → optimized.nl.srt                            ← RENAMED
Phase 6:  optimized.nl.srt       → (edited in place by Claude — acceptable for text-only edits)
Phase 7:  optimized.nl.srt       → final.nl.srt
Phase 8:  final.nl.srt           → (auto-fixed in place by check_line_balance.py --fix)
Phase 9:  final.nl.srt           → vad_timing.json (QC report only)
```

**Changes from current pipeline:**
- Phase 4b outputs `trimmed.nl.srt` (new intermediate file)
- Phase 5 reads `trimmed.nl.srt` instead of `merged.nl.srt`
- Phase 5 outputs `optimized.nl.srt` instead of overwriting `merged.nl.srt`
- `workflow-post.md` and `orchestrate.sh` updated to use new filenames

**Note:** Phase 5 currently writes `merged.nl.srt -o merged.nl.srt` (in-place). While we're fixing Phase 4b, fix Phase 5 too: output to `optimized.nl.srt`.

---

## Pipeline Sanity Checks

### Trim report validation (in orchestrate.sh)

After Phase 4b runs, the orchestrator should validate the trim report before proceeding:

```bash
# In run_postprocessing(), after trim_to_speech.py:
if [[ -f "trim_report.json" ]]; then
    # Check: did trimming cause excessive CPS pressure?
    cps_warnings=$(python3 -c "
import json
with open('trim_report.json') as f: r = json.load(f)
partial = sum(1 for t in r.get('trims', []) if t.get('method') == 'partial')
skipped_cps = sum(1 for t in r.get('skipped', []) if t.get('reason') == 'cps_hard_limit')
total = r.get('summary', {}).get('total_cues', 1)
if (partial + skipped_cps) / total > 0.10:
    print(f'WARNING: {partial + skipped_cps}/{total} cues hit CPS ceiling during trim')
")
    if [[ -n "$cps_warnings" ]]; then
        log "$cps_warnings"
    fi
fi
```

This catches the scenario where the trim is too aggressive for the content — more than 10% of cues hitting the CPS ceiling means the comfort buffer or min-trim may need tuning.

### Phase 9 before/after comparison

Phase 9 (VAD timing QC) is the natural validation point. After Phase 4b exists in the pipeline, the Phase 9 linger count should drop dramatically. Add to the log template:

```markdown
| Linger (Phase 9) | N | <30 | OK/WARN |
```

If linger count doesn't drop below 30 (the ~36 untrimable high-CPS cues), something is wrong with the trim configuration.

---

## Pipeline Integration

### Phase position: 4b (between merge and CPS optimization)

```
Phase 3:  Structural fix
Phase 4:  Merge (auto_merge_cues.py)
Phase 4b: Trim to speech (trim_to_speech.py)       ← NEW
Phase 5:  CPS optimization (extend_end_times.py)    ← reads trimmed.nl.srt
Phase 6:  Linguistic review
...
Phase 9:  VAD timing QC — validates trim effectiveness
Phase 10: Speech sync — SKIPPED when Phase 4b ran
```

**Why between merge and CPS:** Trimming before CPS optimization means Phase 5 can re-extend cues that were trimmed too aggressively (high CPS). This creates a natural push-pull: trim pulls back overlong cues, CPS extension pushes out underlong ones.

### `workflow-post.md` changes

Add between Phase 4 and Phase 5:

```markdown
## Phase 4b: Trim to Speech

Pulls back cue end times that linger past speech boundaries. Uses the same global VAD
approach as Phase 9 for consistency.

\```bash
scripts/venv/bin/python3 scripts/trim_to_speech.py \
    "$VIDEO_FILE" \
    merged.nl.srt \
    --output trimmed.nl.srt \
    --fps ${FRAMERATE} \
    --genre ${CLASSIFICATION} \
    --report trim_report.json \
    -v
\```

**After running:** Check report summary. If >10% of cues were skipped due to CPS hard limit,
note in the log — these cues need text condensation in Phase 5.

**Phase 5 input changes:** Phase 5 now reads `trimmed.nl.srt` instead of `merged.nl.srt`.
```

Update Phase 5 commands to read `trimmed.nl.srt`:

```bash
python3 scripts/extend_end_times.py trimmed.nl.srt \
  --close-gaps 1000 --min-gap ${MIN_GAP} --max-duration ${MAX_DURATION} \
  -o optimized.nl.srt
```

Update Phase 10 section:

```markdown
**Mutual exclusivity with Phase 4b:** When Phase 4b (trim-to-speech) has run, Phase 10 is
skipped in the automated pipeline. Phase 4b aligns end times to speech boundaries (pulling back);
Phase 10 extends end times to speech boundaries (pushing forward). Running both creates
oscillating corrections. If you need Phase 10 after Phase 4b, run it manually after reviewing
the trim report.
```

### `orchestrate.sh` changes

In `run_postprocessing()`, update the inline prompt to include Phase 4b:

```bash
## Instructions

Execute all phases in order:

1. **Phase 3:** Structural fix on draft.nl.srt → draft-fixed.nl.srt
2. **Phase 4:** Script merge → merged.nl.srt + merge_report.json
3. **Phase 4b:** Trim to speech → trimmed.nl.srt + trim_report.json
4. **Phase 5:** CPS optimization on trimmed.nl.srt → optimized.nl.srt
5. **Phase 6:** Linguistic review on optimized.nl.srt (text only)
6. **Phase 7:** Finalize → final.nl.srt
7. **Phase 8:** Line balance QC (auto-fix)
8. **Phase 9:** VAD timing QC
${speech_sync_instruction}
9. **Write log**
```

Update `speech_sync_instruction` logic:

```bash
local speech_sync_instruction=""
if $SPEECH_SYNC; then
    speech_sync_instruction="After Phase 9, run Phase 10 (Speech Sync) ONLY IF trim_report.json does NOT exist. If trim_report.json exists, log: 'Phase 10 skipped: trim-to-speech already applied.' and skip."
fi
```

Add Phase 4b script invocation to the allowed tools:

```bash
--allowedTools "...,Bash(scripts/venv/bin/python3:scripts/trim_to_speech.py*)"
```

### Full Phase 4b command as invoked by Claude

```bash
scripts/venv/bin/python3 scripts/trim_to_speech.py \
    "${VIDEO_FILE}" \
    merged.nl.srt \
    --output trimmed.nl.srt \
    --fps ${FRAMERATE} \
    --genre ${CLASSIFICATION} \
    --report trim_report.json \
    -v
```

**Error handling:** If `trim_to_speech.py` fails (exit code != 0), fall back:
```bash
cp merged.nl.srt trimmed.nl.srt
log "WARNING: trim_to_speech.py failed — using untrimmed merged output"
```

This ensures the pipeline continues even if trim fails. The Phase 9 QC will catch any lingering issues.

---

## Files to Create/Modify

| File | Change | Priority |
|------|--------|----------|
| `scripts/vad_utils.py` | **New:** Shared VAD primitives (extracted from `vad_timing_check.py`) | P0 — prerequisite |
| `scripts/vad_timing_check.py` | Refactor: import from `vad_utils.py` instead of inline definitions | P0 — prerequisite |
| `scripts/extend_to_speech_lite.py` | Refactor: import audio extraction from `vad_utils.py`; update default aggressiveness to 2 | P0 — prerequisite |
| `scripts/srt_constants.py` | Add `VAD_AGGRESSIVENESS`, `VAD_HANGOVER_MS`, `VAD_FRAME_MS`, `VAD_SEARCH_RANGE_MS` | P0 — prerequisite |
| `scripts/trim_to_speech.py` | **New:** Core trim-to-speech script | P1 — main feature |
| `scripts/test_trim_to_speech.py` | **New:** Unit tests | P1 — main feature |
| `base/workflow-post.md` | Add Phase 4b; update Phase 5 input filename; update Phase 10 docs | P2 — integration |
| `scripts/orchestrate.sh` | Add Phase 4b invocation; update Phase 10 skip logic; update file flow | P2 — integration |

---

## Testing Strategy

### Test approach: synthetic speech maps

Unit tests for `trim_to_speech.py` do NOT require real audio or video files. The algorithm operates on:

1. A list of `Subtitle` objects (from `srt_utils.py`)
2. Two lists of ints: `speech_starts` and `speech_ends` (from `find_transitions()`)

Tests inject synthetic speech maps directly, bypassing VAD entirely. This is the same pattern used by `test_timing_qc.py` (which tests `analyze_cue` and `classify_issues` with hand-crafted data).

### Test file: `scripts/test_trim_to_speech.py`

```python
# Test structure (not full implementation — shows the approach)

class TestTrimDecision(unittest.TestCase):
    """Test the per-cue trim decision logic."""

    def test_basic_trim(self):
        """Cue lingers 800ms after speech → trimmed to speech_end + buffer."""
        cue = make_cue(1, 1000, 3000, "Kort zinnetje.")
        speech_ends = [2200]  # speech ends at 2200ms
        # Expected: new_end = 2200 + 250 (buffer) = 2450
        result = compute_trim(cue, speech_ends, ..., comfort_buffer=250)
        assert result.new_end == 2450
        assert result.trim_ms == 550

    def test_skip_when_speech_extends_past_cue(self):
        """Speech ends AFTER cue end → don't trim (opposite problem)."""
        cue = make_cue(1, 1000, 2000, "Tekst.")
        speech_ends = [2500]
        result = compute_trim(cue, speech_ends, ...)
        assert result.action == 'skip'
        assert result.reason == 'speech_extends_past_cue'

    def test_skip_below_min_trim(self):
        """Linger of 300ms < min_trim 400ms → skip."""
        cue = make_cue(1, 1000, 2500, "Tekst.")
        speech_ends = [2200]
        result = compute_trim(cue, speech_ends, ..., min_trim=400)
        assert result.action == 'skip'

    def test_cps_guard_full_trim(self):
        """CPS after trim still under ceiling → full trim applied."""
        cue = make_cue(1, 0, 5000, "Kort.")  # 5 chars / 5s = 1 CPS
        speech_ends = [3000]
        result = compute_trim(cue, speech_ends, ..., cps_soft_ceiling=17)
        assert result.action == 'trim'

    def test_cps_guard_partial_trim(self):
        """Full trim would exceed soft ceiling → partial trim to ceiling."""
        # 40 chars, currently 4000ms duration = 10 CPS
        # Speech ends at 1500ms. Full trim to 1750ms → 40/(1.75) = 22.9 CPS (too high)
        # Partial: find end where CPS = 17 → 40/17*1000 + 0 = 2353ms
        cue = make_cue(1, 0, 4000, "A" * 40)
        speech_ends = [1500]
        result = compute_trim(cue, speech_ends, ..., cps_soft_ceiling=17)
        assert result.action == 'partial_trim'
        assert result.new_cps <= 17

    def test_cps_guard_skip(self):
        """Even partial trim would exceed hard limit → skip."""
        cue = make_cue(1, 0, 2000, "A" * 80)  # 80/2 = 40 CPS already
        speech_ends = [500]
        result = compute_trim(cue, speech_ends, ..., cps_hard_limit=20)
        assert result.action == 'skip'
        assert result.reason == 'cps_hard_limit'

    def test_min_gap_enforcement(self):
        """Trim must leave min_gap_ms before next cue, not just avoid overlap."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        next_cue = make_cue(2, 2800, 4000, "Meer.")
        speech_ends = [2000]
        # new_end = 2000 + 250 = 2250, but 2800 - 2250 = 550 > min_gap → OK
        result = compute_trim(cue, speech_ends, ..., next_cue=next_cue, min_gap_ms=120)
        assert result.new_end == 2250

    def test_min_gap_clamp(self):
        """When trim + buffer would violate min_gap, clamp to min_gap."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        next_cue = make_cue(2, 2300, 4000, "Meer.")
        speech_ends = [2000]
        # new_end = 2000 + 250 = 2250, next starts at 2300
        # 2300 - 2250 = 50 < min_gap 120 → clamp to 2300 - 120 = 2180
        result = compute_trim(cue, speech_ends, ..., next_cue=next_cue, min_gap_ms=120)
        assert result.new_end == 2180

    def test_min_duration_enforcement(self):
        """Trim must not push duration below min_duration_ms."""
        cue = make_cue(1, 1000, 2500, "Lange tekst hier en daar.")
        speech_ends = [1100]
        # new_end = 1100 + 250 = 1350 → duration = 350ms < min_duration 830ms
        result = compute_trim(cue, speech_ends, ..., min_duration_ms=830)
        assert result.action == 'skip'
        assert result.reason == 'min_duration'

    def test_no_transition_found(self):
        """No speech transition near cue → skip (ambiguous)."""
        cue = make_cue(1, 1000, 3000, "Tekst.")
        speech_ends = []  # no transitions
        result = compute_trim(cue, speech_ends, ...)
        assert result.action == 'skip'
        assert result.reason == 'no_transition'


class TestTrimBatch(unittest.TestCase):
    """Test batch trimming with cue interactions."""

    def test_no_cascading_overlaps(self):
        """Trimming multiple sequential cues doesn't create overlaps."""
        cues = [
            make_cue(1, 0, 2000, "Een."),
            make_cue(2, 2200, 4000, "Twee."),
            make_cue(3, 4200, 6000, "Drie."),
        ]
        speech_ends = [1200, 3200, 5200]
        results = trim_all(cues, speech_ends, ...)
        for i in range(len(results) - 1):
            gap = results[i+1].start_ms - results[i].end_ms
            assert gap >= 120  # min_gap for 25fps


class TestDryRun(unittest.TestCase):
    """Dry run must not modify cues."""

    def test_dry_run_no_modification(self):
        cues = [make_cue(1, 0, 3000, "Test.")]
        original_end = cues[0].end_ms
        trim_all(cues, [1500], ..., dry_run=True)
        assert cues[0].end_ms == original_end
```

### Integration test

After implementation, run on Helvetica to validate end-to-end:

```bash
# 1. Run trim
scripts/venv/bin/python3 scripts/trim_to_speech.py \
    helvetica.mkv merged.nl.srt \
    --output trimmed.nl.srt --fps 25 --report trim_report.json -v

# 2. Validate structural integrity
scripts/venv/bin/python3 scripts/validate_srt.py trimmed.nl.srt --summary

# 3. Re-run Phase 9 QC on trimmed output
scripts/venv/bin/python3 scripts/vad_timing_check.py \
    helvetica.mkv trimmed.nl.srt helvetica.en.srt \
    --report trimmed_vad.json

# 4. Compare linger counts
python3 -c "
import json
before = json.load(open('vad_timing.json'))
after = json.load(open('trimmed_vad.json'))
b_linger = sum(1 for f in before['flagged']
               if any(i['type']=='lingers_after_speech' for i in f.get('issues',[])))
a_linger = sum(1 for f in after['flagged']
               if any(i['type']=='lingers_after_speech' for i in f.get('issues',[])))
print(f'Linger: {b_linger} → {a_linger} ({b_linger - a_linger} fixed)')
"
```

**Target:** Reduce linger count from 152 to <30 (the ~36 high-CPS cues that can't be trimmed without text condensation, plus VAD edge cases).

---

## Implementation Order

| Step | What | Depends on | Estimate |
|------|------|-----------|----------|
| 1 | Create `vad_utils.py` (extract from `vad_timing_check.py`) | — | Small |
| 2 | Refactor `vad_timing_check.py` to use `vad_utils.py` | Step 1 |Small |
| 3 | Refactor `extend_to_speech_lite.py` to use `vad_utils.py` | Step 1 | Small |
| 4 | Add VAD constants to `srt_constants.py` | — | Trivial |
| 5 | Run existing tests to verify no regressions | Steps 1-4 | Trivial |
| 6 | Implement `trim_to_speech.py` | Steps 1, 4 | Medium |
| 7 | Write `test_trim_to_speech.py` | Step 6 | Medium |
| 8 | Update `workflow-post.md` (Phase 4b, file flow, Phase 10 docs) | Step 6 | Small |
| 9 | Update `orchestrate.sh` (Phase 4b invocation, Phase 10 skip) | Step 8 | Small |
| 10 | Integration test on Helvetica | Steps 6-9 | Manual |

Steps 1-4 can be done as a single "refactor" commit. Steps 6-7 as the "feature" commit. Steps 8-9 as the "integration" commit.

---

## Out of Scope

- **Text condensation for high-CPS lingering cues** — these 36 cues need shorter Dutch text, not shorter display time. Phase 5 Step 2 already handles this.
- **Full migration of `extend_to_speech_lite.py` to global speech map** — the refactor only extracts shared utilities; the per-cue algorithm is preserved.
- **EN source timing correction** — we don't modify the EN source; we work with what we get.
- **Genre-specific comfort buffer tuning** — the initial implementation uses a single default with CLI override. Genre-specific presets are documented but not hard-coded until validated.
