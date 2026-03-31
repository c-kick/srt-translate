# Phases 7-11: Finalization & QC

**You are a professional Dutch subtitle translator.** This phase handles finalization, quality checks, final grammar scan, and log writing.

**All phases are mandatory.** Execute in order.

---

## Phase 7: Finalization

```bash
python3 scripts/validate_srt.py merged.nl.srt \
  --source "${VIDEO_BASENAME}.en.srt" \
  --fix --output final.nl.srt
python3 scripts/renumber_cues.py final.nl.srt --in-place
python3 scripts/add_credit.py final.nl.srt --in-place --cps 12
mv final.nl.srt "${VIDEO_BASENAME}.nl.srt"
```

If `drift_errors` is non-empty here, timing drift survived post-processing. Follow the correction procedure from Phase 3 and re-run Phase 7.

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

**Grammar-aware rebalancing:** Applies line break priority from shared-constraints.md: sentence boundaries first, then comma+conjunction breaks, then bottom-heavy pyramid, then semantic unit coherence on line 2. Never breaks article+noun, verb+negation, demonstrative+noun. Collapses to single line when total ≤42 chars. **Dual-speaker cues (with `\n-`) are automatically skipped by the script** — their line breaks are semantically mandated.

**Manual check after auto-fix:** Review any dual-speaker cues where one line exceeds 42 chars. If the other line is a trivial reply (`-Ja.`, `-Nee.`, `-Goed.`, etc.), drop the trivial reply and reflow the remaining text across two lines — this is often the only way to fix an over-length line in a dual-speaker cue without condensing the main content.

**CPS guard:** Skips rebalancing if result would push CPS over 17.

**After auto-fix:** Re-run `validate_srt.py --summary` to confirm no CPS regressions. If found, fix CPS (Phase 5 priority order) and do NOT re-run line balance.

---

## Phase 9: VAD Timing QC

Checks subtitle timing against actual speech via WebRTC VAD.

```bash
scripts/run-venv.sh scripts/vad_timing_check.py \
    "$VIDEO_FILE" \
    "${VIDEO_BASENAME}.nl.srt" \
    "${VIDEO_BASENAME}.en.srt" \
    --merge-report merge_report.json \
    --draft-mapping draft_mapping.json \
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
scripts/run-venv.sh scripts/extend_to_speech_lite.py \
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

**Note:** Phase 10 extends end times to speech boundaries. If Phase 4b (trim-to-speech) has already run, Phase 10 may partially undo trims. Avoid combining both unless you have a specific reason (e.g., slow-speaker content that also has lingering issues).

---

## Phase 11: Final Grammar Scan

**Purpose:** Safety net for grammar and punctuation errors introduced or missed by earlier phases. This is the last quality gate before the log.

Read the entire `${VIDEO_BASENAME}.nl.srt` as continuous text (ignore timecodes). Scan for:

1. **Missing punctuation between sentences** — two sentences joined without a period, comma, or other separator (common merge artifact)
2. **Incomplete or broken sentences** — fragments that don't form a complete thought
3. **Grammar errors** — d/t/dt endings, de/het, wrong word order
4. **Orphaned words from rebalancing** — text artifacts from Phase 8

**Fix rules:**
- Edit text only — do NOT touch timecodes or cue structure
- Do NOT change cue count or merge decisions
- Preserve dual-speaker formatting (`\n-`)
- If a fix would push CPS above the soft ceiling, condense elsewhere in the cue to compensate

**Working method:** Read in ~100-cue chunks. Fix directly — no separate report needed. If zero issues found, note "Phase 11: no issues" in the log.

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
| `validate_srt.py` | Validate + fix | `--fix --output --summary --report --source EN_SRT` |
| `auto_merge_cues.py` | Adjacent cue merge | `--gap-threshold --max-duration --report` |
| `extract_cues.py` | Extract range | `--start N --end M --indices --stdout` |
| `renumber_cues.py` | Fix sequence | `--in-place` |
| `add_credit.py` | Add credit | `--in-place --cps` |
| `trim_to_speech.py` | Trim lingering end times (VAD) | `--comfort-buffer --min-trim --fps --output --report --dry-run` |
| `extend_to_speech_lite.py` | Extend to speech end (VAD) | `--aggressiveness --max-extension` |
| `check_line_balance.py` | Line balance QC + auto-fix | `--fix --output --ratio` |
| `save_draft_mapping.py` | Pre-Phase-3 NL→EN mapping | `--output --tolerance` |
| `vad_timing_check.py` | VAD timing QC | `--threshold --aggressiveness --merge-report --draft-mapping --report` |
