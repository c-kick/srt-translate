# Improvement Plan: Skill Hardening & Test Coverage

## Context

This plan captures the next round of improvements identified during a skill-creator assessment (2026-03-02). The previous plan (merge-aware timing QC, Levels 1+2) has been fully implemented. The skill scores 8.2/10 overall — architecture, progressive disclosure, and the exemplar system are strong. The gaps are in test coverage, minor structural improvements, and orchestrator complexity.

## Priority 1: Genre-Diverse Evaluation Test Cases

### Problem

The eval suite has a single 81-cue test file covering comedy (Fawlty Towers) with some documentary cues mixed in. Four genre translators exist (comedy, documentary, drama, fast-unscripted) but only comedy is tested end-to-end. Genre-specific regressions (e.g. register handling in drama, terminology in documentary) would go undetected.

### Plan

1. **Create `evals/test_documentary.en.srt`** (~30 cues)
   - Source: extract representative cues from a documentary with narration + interview segments
   - Cover: formal register, statistics/dates, military/historical terminology, narrator voice, interview speech patterns
   - Include at least 2 CPS-pressure cues and 1 multi-cue continuation

2. **Create `evals/test_drama.en.srt`** (~30 cues)
   - Source: extract representative cues from a character-driven drama
   - Cover: T-V register shifts (je/u), emotional dialogue without `!`, period-appropriate vocabulary, rapid multi-speaker exchanges, idiom adaptation opportunities

3. **Add test entries to `evals/evals.json`**
   - Documentary: translation (25fps, documentary genre) → merge (1000ms/7000ms) → validation
   - Drama: translation (24fps, drama genre) → merge (1000ms/7000ms) → validation
   - Each with genre-appropriate expected outputs and assertions

4. **Update `evals/README.md`** with the new test files and what they cover

### Success Criteria

- Three genre-specific test files (comedy, documentary, drama) in evals/
- Each tests the full pipeline: translate → merge → validate
- Genre-specific assertions (e.g. drama checks T-V consistency, documentary checks terminology)

---

## Priority 2: Unit Tests for Core Scripts

### Problem

`auto_merge_cues.py` (423 lines) and `validate_srt.py` (593 lines) are the two most-changed scripts in the pipeline. They have no unit tests. `test_timing_qc.py` covers the timing QC module well, proving the pattern works. A script change that breaks merge logic or validation would only surface during a full pipeline run.

### Plan

1. **Create `scripts/test_auto_merge.py`** — pytest unit tests for the merge script:
   - `test_detect_merge_marker()` — [SC], [NM], no marker
   - `test_can_merge_text_same_speaker()` — text combination, ellipsis stripping, line length limits
   - `test_can_merge_text_dual_speaker()` — dash formatting, first-line-no-dash rule
   - `test_merge_cues_basic()` — simple 2-cue merge within gap/duration limits
   - `test_merge_cues_respects_nm()` — [NM] marker prevents merge
   - `test_merge_cues_sc_creates_dual_speaker()` — [SC] marker creates dash format
   - `test_merge_cues_gap_too_large()` — no merge when gap exceeds threshold
   - `test_trivial_reply_absorption()` — short reply merged into preceding cue
   - `test_dual_speaker_not_collapsed()` — pre-existing dual-speaker cues preserved

2. **Create `scripts/test_validate_srt.py`** — pytest unit tests for the validator:
   - `test_fix_punctuation()` — `!` → `.`, `;` → `.`
   - `test_fix_ellipsis()` — `…` → `...`
   - `test_fix_line_length()` — re-breaks long lines, bottom-heavy preference
   - `test_fix_overlap()` — adjusts end time to enforce minimum gap
   - `test_fix_speaker_dash()` — normalizes to second-speaker-only dash
   - `test_remove_empty_cues()` — blank/whitespace-only cues removed
   - `test_validate_cps_soft_hard()` — correct error classification by CPS threshold
   - `test_validate_line_count()` — 3+ line cues flagged
   - `test_duplicate_text_detection()` — consecutive identical cues detected

3. **Add a `pytest.ini` or `pyproject.toml` section** for test discovery in `scripts/`

### Success Criteria

- `pytest scripts/test_auto_merge.py scripts/test_validate_srt.py scripts/test_timing_qc.py` passes
- Tests use synthetic SRT data (no external file dependencies)
- Merge script and validator have >80% function coverage

---

## Priority 3: SKILL.md — Mention Exemplars in Routing Table

### Problem

SKILL.md's phase group table doesn't mention the exemplar system. A first-time reader wouldn't know exemplars exist until they're deep into workflow-translate.md. Since exemplars are the single biggest quality driver, they deserve visibility at the routing level.

### Plan

Update the Translation row in SKILL.md's phase group table:

| Group | Phases | Context loaded |
|-------|--------|----------------|
| Translation | 2 | shared-constraints + workflow-translate + translator + `references/exemplars/*` |

One-line change. The workflow-translate.md Phase 1 already instructs loading them — this just makes them visible from the top level.

### Success Criteria

- SKILL.md Translation row mentions exemplars
- No other SKILL.md changes needed

---

## Priority 4: Archive One-Off Scripts

### Problem

Four one-off scripts sit alongside pipeline scripts: `_condense_cps.py`, `_check_merge.py`, `_run_vad.sh`, `run_vad_fawlty.sh`. The underscore convention signals "not pipeline" but they still clutter `scripts/` and could confuse someone reading the codebase.

### Plan

1. Create `scripts/_archive/`
2. Move all four files there
3. Update `.gitignore` if needed (unlikely — they're tracked)
4. Add a one-line `scripts/_archive/README.md`: "One-off helper scripts kept for reference. Not part of the pipeline."

### Success Criteria

- `scripts/` contains only pipeline scripts and tests
- Archived scripts are still accessible for reference
- No pipeline behavior changes

---

## Priority 5: Description Optimization (Triggering)

### Problem

The SKILL.md description is functional but could be tuned for better triggering accuracy. The skill-creator framework has a `run_loop.py` script that systematically tests and improves descriptions using train/test split evaluation.

### Plan

1. Generate 20 trigger eval queries (10 should-trigger, 10 should-not-trigger)
   - Should-trigger: various phrasings of EN→NL subtitle translation, SRT localization, Dutch subtitle review, subtitle QC
   - Should-not-trigger: near-misses like general translation without SRT, subtitle OCR, audio transcription, other-language subtitles, English-only standardization (srt-standardize-en territory)
2. Review with user via HTML template
3. Run `run_loop.py` with current model
4. Apply best description

### Success Criteria

- Triggering accuracy ≥ 90% on held-out test set
- No false triggers on srt-standardize-en territory
- Description remains concise (under 100 words)

---

## Deferred: Orchestrate.sh Complexity

### Observation

`orchestrate.sh` is 691 lines of Bash and growing. It works, but Bash at this scale is fragile for error handling, string processing, and debugging. Parts of it (file concatenation, prompt construction, checkpoint management) would be cleaner in Python.

### Why Deferred

- It works reliably today
- A rewrite is high-effort with no immediate quality gain
- The risk of introducing regressions during migration is real
- Better to invest in test coverage first (Priorities 1-2), which will make a future rewrite safer

### Trigger for Revisiting

- If a bug in orchestrate.sh takes >1 hour to debug
- If a new feature requires significant Bash additions
- After unit tests (Priority 2) are in place to catch regressions

---

## Files Changed (All Priorities)

| File | Change | Priority |
|------|--------|----------|
| `evals/test_documentary.en.srt` | **New:** Documentary test cues | 1 |
| `evals/test_drama.en.srt` | **New:** Drama test cues | 1 |
| `evals/evals.json` | Add documentary + drama test entries | 1 |
| `evals/README.md` | Document new test files | 1 |
| `scripts/test_auto_merge.py` | **New:** Merge script unit tests | 2 |
| `scripts/test_validate_srt.py` | **New:** Validator unit tests | 2 |
| `SKILL.md` | Add exemplars to Translation row | 3 |
| `scripts/_archive/` | **New:** Move one-off scripts here | 4 |
| `SKILL.md` (description) | Optimized triggering description | 5 |
