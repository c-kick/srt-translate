# Phases 3-9: Post-Processing

**You are a professional Dutch subtitle translator.** This phase handles structural fixes, merging, CPS validation, linguistic review, and finalization.

**All phases are mandatory unless marked optional.** Execute in order.

---

## Pre-Phase-3: Save Draft Mapping

Before Phase 3 renumbers cues, save the NL→EN timecode correspondence from the draft. This mapping is used in Phase 9 for accurate NL→EN matching even after merges and renumbering.

```bash
python3 scripts/save_draft_mapping.py draft.nl.srt "${VIDEO_BASENAME}.en.srt" \
  --output draft_mapping.json
```

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

**Line length fix for dual-speaker cues:** If a dual-speaker cue has a line exceeding 42 characters and the other line is a trivial reply (`-Ja.`, `-Nee.`, `-Goed.`, `-Oké.`, etc.), drop the trivial reply and reflow the remaining text across two lines. The viewer hears the trivial reply — removing it frees both lines for the sentence that needs the space.

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

### Post-merge verification: dual-speaker count

Count dual-speaker cues (those with `\n-` pattern) in the merged output:

```bash
python3 -c "
with open('merged.nl.srt') as f: content = f.read()
import re
blocks = re.split(r'\n\n+', content.strip())
dual = sum(1 for b in blocks if '\n-' in b)
total = len([b for b in blocks if re.search(r'\d+:\d+', b)])
print(f'Dual-speaker cues: {dual} / {total} ({dual*100//max(total,1)}%)')
"
```

**Expected ranges by genre:**
- Comedy / fast-unscripted: 15-40% of merged cues should be dual-speaker
- Drama: 10-25%
- Documentary: 0-10%

If dual-speaker count is **below the expected range**, the translator likely missed `[SC]` markers. Flag this in the log as a quality warning — the issue originates in Phase 2 and cannot be fully corrected in post-processing.

---

## Phase 4b: Trim to Speech

Pulls back cue end times that linger past speech boundaries. Uses VAD (same approach as Phase 9) to detect where speech actually ends and trims accordingly, guarded by CPS constraints.

```bash
scripts/venv/bin/python3 scripts/trim_to_speech.py \
    "$VIDEO_FILE" \
    merged.nl.srt \
    --output trimmed.nl.srt \
    --fps ${FRAMERATE} \
    --report trim_report.json \
    -v
```

**If the script fails:** Copy merged.nl.srt to trimmed.nl.srt and continue. Phase 9 will catch any lingering issues.

```bash
cp merged.nl.srt trimmed.nl.srt
```

---

## Phase 5: CPS Optimization (Post-Merge)

Validate CPS on the trimmed file:

```bash
python3 scripts/validate_srt.py trimmed.nl.srt --summary --report cps_validation.json
```

### Step 0: Close Small Gaps (Auteursbond)

Gaps shorter than 1 second should be closed by extending end times (Auteursbond: "aansluiten"):

```bash
python3 scripts/extend_end_times.py trimmed.nl.srt \
  --close-gaps 1000 --min-gap ${MIN_GAP} --max-duration ${MAX_DURATION} \
  -o trimmed.nl.srt
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
1. **Drop trivial replies** — if a dual-speaker cue's second line is a trivial acknowledgment (`Ja.`, `Nee.`, `Oké.`, `Goed.`, `Precies.`, `Klopt.`, etc.), drop the second line and convert to single-speaker. The viewer hears these — subtitling them adds characters without information. This is the cheapest CPS reduction.
2. **Targeted re-merge** — if adjacent (gap ≤1000ms) and combined fits constraints, merge
3. **Delete filler** → compress phrases → rephrase
4. Only accept CPS 17-20 when proper nouns/terminology genuinely cannot be cut further

**Condensation quality rule:** Never replace common words with uncommon synonyms to save characters. Always use natural, everyday Dutch.

**Dual-speaker preservation:** When condensing a cue that has dual-speaker dash formatting (`\n-`), the condensed text MUST keep the dash format. Never collapse two speakers onto one line.

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
- je/u consistent per character relationship? (See `dutch-patterns.md` for rules — spouses/family/friends are ALWAYS je, never u)
- Register appropriate for speaker and context?

**Merged cues** (from `merge_report.json`) — these are the highest-priority items. The merge script joins text mechanically (strips `...`, joins with space). Claude must verify every merge boundary reads as correct Dutch:

1. **Capitalization at join point:** If the merged text has an uppercase letter mid-sentence (from cue-initial capitalization), lowercase it. Example: `het blauwe In de la` → `het blauwe in de la`.
2. **Missing punctuation at join point:** If two clauses were joined without proper punctuation, add it. Example: `Ik ben alleen Duitsers komen morgen` → `Ik ben alleen, de Duitsers komen morgen` (comma + article).
3. **Orphaned fragments:** If a merged cue ends with a fragment that doesn't flow (`De soldaten marcheerden. Naar het front.`), rewrite as one sentence (`De soldaten marcheerden naar het front.`).
4. **Parallel constructions:** If merged rhetorical questions or lists lost their separators, add commas. Example: `Groeit die nog steeds woekert die zich naar het bot` → `Groeit die nog steeds, woekert die zich naar het bot`.

Read `merge_report.json`, find every `output_index` with `source_count > 1`, and verify the merged text at that cue number.

### Fix Rules

- **Edit text only.** Do NOT touch timecodes.
- Do NOT change merge decisions or cue count.
- **Preserve dual-speaker formatting:** If a cue has dash formatting (`\n-`), any rewrite MUST keep the two-speaker structure with the dash. Never merge two speakers' text into flowing prose.
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

**Grammar-aware rebalancing:** Applies line break priority from shared-constraints.md: sentence boundaries first, then comma+conjunction breaks, then bottom-heavy pyramid, then semantic unit coherence on line 2. Never breaks article+noun, verb+negation, demonstrative+noun. Collapses to single line when total ≤42 chars. **Dual-speaker cues (with `\n-`) are automatically skipped by the script** — their line breaks are semantically mandated.

**Manual check after auto-fix:** Review any dual-speaker cues where one line exceeds 42 chars. If the other line is a trivial reply (`-Ja.`, `-Nee.`, `-Goed.`, etc.), drop the trivial reply and reflow the remaining text across two lines — this is often the only way to fix an over-length line in a dual-speaker cue without condensing the main content.

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

**Note:** Phase 10 extends end times to speech boundaries. If Phase 4b (trim-to-speech) has already run, Phase 10 may partially undo trims. Avoid combining both unless you have a specific reason (e.g., slow-speaker content that also has lingering issues).

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
| `renumber_cues.py` | Fix sequence | `--in-place` |
| `add_credit.py` | Add credit | `--in-place --cps` |
| `trim_to_speech.py` | Trim lingering end times (VAD) | `--comfort-buffer --min-trim --fps --output --report --dry-run` |
| `extend_to_speech_lite.py` | Extend to speech end (VAD) | `--aggressiveness --max-extension` |
| `check_line_balance.py` | Line balance QC + auto-fix | `--fix --output --ratio` |
| `save_draft_mapping.py` | Pre-Phase-3 NL→EN mapping | `--output --tolerance` |
| `vad_timing_check.py` | VAD timing QC | `--threshold --aggressiveness --merge-report --draft-mapping --report` |
