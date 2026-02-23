# Phases 3-9: Post-Processing

**You are a professional Dutch subtitle translator.** This phase handles structural fixes, merging, CPS validation, linguistic review, and finalization.

**All phases are mandatory unless marked optional.** Execute in order.

---

## Phase 3: Structural Fix

Fix structural errors only. **Do NOT condense text for CPS — that happens after merge in Phase 5.**

```bash
python3 scripts/validate_srt.py draft.nl.srt --fix --output draft-fixed.nl.srt
```

Fix before merge:
- Overlapping cues (timestamp errors) — fix first
- Line length > 42 characters (reflow or shorten)
- Gap violations (< minimum gap, framerate-dependent)
- 3+ line cues (restructure to 2 lines max)

**Do NOT fix:** CPS violations. Merging extends durations and lowers CPS naturally.

---

## Phase 4: Script-Based Merge

The script handles merge decisions mechanically.

```bash
python3 scripts/auto_merge_cues.py draft-fixed.nl.srt \
  --gap-threshold ${GAP_THRESHOLD} \
  --max-duration ${MAX_DURATION} \
  --output merged.nl.srt \
  --report merge_report.json
```

Genre parameters (from checkpoint):

| Genre | --gap-threshold | --max-duration | Target ratio |
|-------|-----------------|----------------|--------------|
| documentary | 1000 | 7000 | 70-85% |
| drama | 1000 | 7000 | 60-75% |
| comedy | 800 | 6000 | 55-70% |
| fast-unscripted | 500 | 6000 | 50-65% |

After running, check ratio:
```bash
source_count=$(grep -c '^[0-9]' source.en.srt)
merged_count=$(grep -c '^[0-9]' merged.nl.srt)
echo "Ratio: $((merged_count * 100 / source_count))%"
```

---

## Phase 5: CPS Optimization (Post-Merge)

Validate CPS on the merged file:

```bash
python3 scripts/validate_srt.py merged.nl.srt --summary --report cps_validation.json
```

### Step 0: Close Small Gaps (Auteursbond)

Gaps shorter than 1 second should be closed by extending end times (Auteursbond: "aansluiten"):

```bash
python3 scripts/extend_end_times.py merged.nl.srt \
  --close-gaps 1000 --min-gap ${MIN_GAP} --max-duration ${MAX_DURATION} \
  -o merged.nl.srt
```

### Step 1: Extend End Times (ALL cues with CPS > 13)

**This is the primary CPS tool.** For EVERY cue with CPS above 13, extend the end time to fill the available gap before the next cue. Target CPS: **12.5**.

```
For each cue where CPS > 13:
  available_gap = next_cue_start - current_cue_end
  if available_gap > ${MIN_GAP}ms:
    extend end time, leaving ${MIN_GAP}ms minimum gap
    recalculate CPS
```

This is a mechanical operation. Do it for ALL qualifying cues, not just outliers. The user's expectation is CPS 12-12.5 wherever display time permits.

### Step 2: Text Condensation (only for CPS still > CPS hard limit after extension)

After extending all end times, some cues will still exceed the CPS hard limit (fps-dependent: 15 at 24fps, 17 at 25fps) because there's no gap to extend into. Only THEN condense text:

- **CPS hard limit to 20:** condense if possible without losing meaning
- **CPS > 20:** must condense (emergency — meaning loss acceptable)

**Condensation priority order** (try each before the next):
1. **Targeted re-merge** — if adjacent (gap ≤1000ms) and combined fits constraints, merge
2. **Delete filler** → compress phrases → rephrase
3. Only accept CPS 17-20 when proper nouns/terminology genuinely cannot be cut further

**Condensation quality rule:** Never replace common words with uncommon synonyms to save characters. Always use natural, everyday Dutch.

---

## Phase 6: Linguistic Review

Review **all cues** for grammar, naturalness, and linguistic quality. **Fix text only — never touch timecodes.**

### Working Method

Work through the full `.nl.srt` in chunks of ~80 cues:

```bash
python3 scripts/extract_cues.py merged.nl.srt --start 1 --end 80 --output review_chunk.srt
```

Also load `merge_report.json` to know which cues were merged.

### Review Checklist (every chunk)

**Grammar:**
- d/t/dt verb endings correct?
- de/het articles correct?
- V2 word order after fronted elements?
- Subordinate clause word order (verb-final)?
- er/daar/hier compounds correct?

**Naturalness:**
- No English syntax calques?
- No literal translations where Dutch idiom exists?
- Word order feels native, not translated?

**Punctuation:**
- Correct `...` use (end-of-cue continuation only)?
- No semicolons or exclamation marks?

**Register:**
- je/u consistent per character relationship?
- Register appropriate for speaker and context?

**Merged cues** (from `merge_report.json`) — additionally:
- Grammar correct after text combination?
- Sentence flows naturally (no orphaned fragments)?
- No awkward joins — rewrite as natural sentence if needed

### Fix Rules

- **Edit text only.** Do NOT touch timecodes.
- Do NOT change merge decisions or cue count.
- Apply fixes in batch (collect all issues in a chunk, fix together).
- Reference `references/common-errors.md` for known patterns.

### Merge Artifact Example

After script merge:
```
Cue 5: "De soldaten marcheerden. Naar het front."
```
Review: "Naar het front." is orphaned fragment.
Fix: "De soldaten marcheerden naar het front."

---

## Phase 7: Finalization

```bash
python3 scripts/validate_srt.py merged.nl.srt --fix --output final.nl.srt
python3 scripts/renumber_cues.py final.nl.srt --in-place
python3 scripts/add_credit.py final.nl.srt --in-place --cps 12
mv final.nl.srt "${VIDEO_BASENAME}.nl.srt"
```

---

## Phase 8: Line Balance QC

Checks two-line cues for proper line balancing. Detects orphan words, top-heavy pyramids, bad break points.

```bash
# Report only
python3 scripts/check_line_balance.py "${VIDEO_BASENAME}.nl.srt"

# Auto-fix and overwrite
python3 scripts/check_line_balance.py "${VIDEO_BASENAME}.nl.srt" --fix
```

| Issue | Example | Problem |
|-------|---------|---------|
| Orphan word | `"De"\n"Reichswehr moest..."` | Single short word alone |
| Top-heavy | `"Dit was het economische wonder"\n"van de nazi's."` | Top >> bottom |
| Bad break | `"...beperkte de"\n"Duitse landmacht..."` | Splits article + noun |

**Grammar-aware rebalancing:** Applies line break priority from shared-constraints.md: sentence boundaries first, then comma+conjunction breaks, then bottom-heavy pyramid, then semantic unit coherence on line 2. Never breaks article+noun, verb+negation, demonstrative+noun. Collapses to single line when total ≤42 chars.

**CPS guard:** Skips rebalancing if result would push CPS over 17.

**After auto-fix:** Re-run `validate_srt.py --summary` to confirm no CPS regressions. If found, fix CPS (Phase 5 priority order) and do NOT re-run line balance.

---

## Phase 9: VAD Timing QC

Checks subtitle timing against actual speech via WebRTC VAD.

```bash
scripts/venv/bin/python3 scripts/vad_timing_check.py \
    "$VIDEO_FILE" \
    "${VIDEO_BASENAME}.nl.srt" \
    "${VIDEO_BASENAME}.en.srt" \
    --report vad_timing.json
```

| Issue | Meaning | Action |
|-------|---------|--------|
| Lingers after speech | Subtitle stays after narrator stops | Shorten end time or condense |
| Cuts off during speech | Subtitle disappears while talking | Extend end time or split |
| Late start | Speech before subtitle (no prior cue) | Check source sync |
| Early start | Subtitle before speech (low severity) | Usually fine |
| Missing anticipation | Subtitle doesn't lead speech by 2-5 frames | Check source timing |

**Context-aware:** Split cues with next subtitle picking up immediately are NOT flagged. Source-inherited issues labeled `[source timing]` and downgraded.

**Severity:** HIGH = must review. MEDIUM = should review. LOW = informational.

**Typical fixes:**
- **Lingering** (most common): Pull back end time. If shortened cue → CPS > soft ceiling, condense text instead.
- **Cuts off**: Restore closer to EN source end time.

---

## Phase 10: Speech Sync (Optional)

**When:** Content with slow speakers where subtitles disappear before speaker finishes.

```bash
scripts/venv/bin/python3 scripts/extend_to_speech_lite.py \
    "$VIDEO_FILE" \
    "${VIDEO_BASENAME}.nl.srt" \
    -o "${VIDEO_BASENAME}.nl.srt" \
    --report speech_extensions.json \
    -v
```

| Flag | Default | Description |
|------|---------|-------------|
| `--aggressiveness` | 1 | VAD strictness (0=permissive, 3=strict) |
| `--max-extension` | 3000 | Max extension per cue (ms) |
| `--search-buffer` | 3000 | How far past cue end to search (ms) |
| `--min-gap` | 125 | Min gap before next cue (ms) |

**When NOT to use:** Fast dialogue (comedy, action), music-heavy content, already well-timed source.

---

## Write Log File (Final Step)

**Translation is not complete until the log is written.**

Write to `${LOG_DIR}/YYYY-MM-DD_video-name.md`:

```markdown
# SRT-Translate Log

**Date:** YYYY-MM-DD
**File:** [video filename]
**Content Type:** [documentary/drama/comedy/fast-unscripted]

## Results

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Source cues | N | - | - |
| Output cues | N | per translator | OK/WARN |
| Merge ratio | N% | per translator | OK/WARN |
| CPS avg | N | ~12 | OK/WARN |
| CPS max | N | <17 | OK/WARN |
| CPS > 17 | N | 0 | OK/WARN |
| CPS > 20 | N | 0 | PASS/FAIL |
| Hard errors | 0 | 0 | PASS/FAIL |

## Issues Encountered
- [constraint violations and fixes]

## Quality Notes
- [terminology decisions, register choices, difficult passages]

## Output File
- [full path to .nl.srt]
```

---

## Error Correction Strategy

When fixing validation errors:

1. **Use `--fix` flag first** — auto-fixes line breaks and renumbers
2. **Batch remaining fixes** — collect all text changes, apply in single edit
3. **Prioritize by severity:**
   - Overlapping cues (timestamp errors) — fix first
   - Line length > 42 — reflow or shorten
   - CPS > 17 — condense text (only after merge)

**Avoid** running many individual bash commands per fix. Instead: read multiple cues at once, prepare all fixes, apply in one or few Edit operations.

---

## Scripts Reference

All scripts require `srt_utils.py` in same directory.

| Script | Purpose | Key flags |
|--------|---------|-----------|
| `validate_srt.py` | Validate + fix | `--fix --output --summary --report` |
| `auto_merge_cues.py` | Adjacent cue merge | `--gap-threshold --max-duration --report` |
| `extract_cues.py` | Extract range | `--start N --end M --indices` |
| `merge_cues.py` | Merge retranslated back | `--output` |
| `renumber_cues.py` | Fix sequence | `--in-place` |
| `add_credit.py` | Add credit | `--in-place --cps` |
| `extend_to_speech_lite.py` | Extend to speech end (VAD) | `--aggressiveness --max-extension` |
| `check_line_balance.py` | Line balance QC + auto-fix | `--fix --output --ratio` |
| `vad_timing_check.py` | VAD timing QC | `--threshold --aggressiveness --report` |
