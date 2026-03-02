# Improvement Plan: Skill Hardening & Test Coverage

## Context

This plan captures the next round of improvements identified during a skill-creator assessment (2026-03-02). The previous plan (merge-aware timing QC, Levels 1+2) has been fully implemented. The skill scores 8.2/10 overall — architecture, progressive disclosure, and the exemplar system are strong. The gaps are in test coverage, minor structural improvements, and orchestrator complexity.

## Priority 1: Genre-Diverse Evaluation Test Cases — DONE

Added two genre-specific test files alongside the existing comedy test:
- `evals/test_documentary.en.srt` (31 cues) — World At War narration, witness interviews, Planet Earth nature narration, SDH
- `evals/test_drama.en.srt` (31 cues) — Remains of the Day: T-V register shifts, rapid multi-speaker, emotional scenes, idiom adaptation
- `evals/evals.json` expanded from 3 to 9 tests (3 pipelines x translate → merge → validate)
- `evals/README.md` updated with full scenario tables for all three test files

---

## Priority 2: Unit Tests for Core Scripts — DONE

Added pytest unit tests for the two most-changed pipeline scripts:
- `scripts/test_auto_merge.py` (391 lines, 11 test classes) — marker detection, merge logic, dual-speaker, trivial replies, edge cases
- `scripts/test_validate_srt.py` (446 lines, 15 test classes) — all fix functions, all validation checks, full round-trip tests
- `pyproject.toml` added with pytest configuration
- 113 total tests (including existing `test_timing_qc.py`), all passing in 0.35s

---

## Priority 3: SKILL.md — Mention Exemplars in Routing Table — DONE

Added `references/exemplars/*` to the Translation row in SKILL.md's phase group table.

---

## Priority 4: Remove One-Off Scripts — DONE

Deleted four hard-coded debugging artifacts that had no reuse value:
- `_condense_cps.py` — episode-specific CPS edits for Blood Money S01E01
- `_check_merge.py` — hard-coded merge diagnostic for Blood Money
- `_run_vad.sh` — hard-coded VAD wrapper for Blood Money
- `run_vad_fawlty.sh` — hard-coded VAD wrapper for Fawlty Towers S01E06

All techniques are already captured in pipeline scripts and workflow docs.

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
| `scripts/_condense_cps.py` | **Deleted:** hard-coded one-off | 4 |
| `scripts/_check_merge.py` | **Deleted:** hard-coded one-off | 4 |
| `scripts/_run_vad.sh` | **Deleted:** hard-coded one-off | 4 |
| `scripts/run_vad_fawlty.sh` | **Deleted:** hard-coded one-off | 4 |
| `SKILL.md` (description) | Optimized triggering description | 5 |
