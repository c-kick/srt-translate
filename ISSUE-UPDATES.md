# Issue Update Prompt

Use this prompt with Claude Code to update the GitHub issues that need revision.

---

## Prompt

Update the following GitHub issues for the `c-kick/srt-translate` repository. Use `gh issue edit` to update issue bodies. Preserve existing content where it's accurate — only add, correct, or restructure as specified below.

### Issue #7 — No changes to issue text needed
The issue is well-written and the fix is clearly documented. No update required.

### Issue #9 — Add evidence requirement and sharpen acceptance criteria

Append the following section to the issue body:

```
### Evidence needed

No concrete phase-skipping events have been documented yet. Before implementing, reproduce and log at least one instance where a phase is skipped or conflated during a 300+ cue post-processing run. Without evidence this remains speculative.

### Updated acceptance criteria

- Phase-transition log lines (`Phase N complete. Proceeding to Phase N+1.`) appear in orchestrate.sh log output for every phase (3–9)
- A 300+ cue file completes post-processing with all phases confirmed in logs
- If splitting into two phase groups is pursued: measure skip rates before and after to validate the change
```

### Issue #11 — Add missing specifics

Append the following section to the issue body:

```
### Open questions to resolve before implementation

1. **Timing estimate:** The "< 2 minutes" target needs benchmarking. A single Claude invocation for 20 cues has network and token overhead — measure actual wall-clock time on a test run first.
2. **VAD phases:** The current proposal skips Phase 4b/9 (no audio in test mode), but these are the phases most prone to failure (see #7). Consider including a synthetic VAD test or at minimum flagging their absence in test output.
3. **Baseline format:** Define what `evals/baseline.json` contains — proposed fields: `{cps_mean, cps_max, cps_violations, merge_ratio, constraint_violations, phase_count}`. Include tolerance thresholds for pass/fail (e.g., CPS mean within ±1.0 of baseline).
4. **Baseline regeneration:** Add a `--update-baseline` flag that overwrites `evals/baseline.json` with current run metrics. Document when this should be used (after intentional pipeline changes).

### Related issues

- Blocked by #7 for VAD phase coverage in tests
```

### Issue #12 — Fix inaccurate description and add cross-references

Replace the description of current `--phase N` behavior. Where the issue says `--phase N` accepts values 0–9, correct it to:

```
**Current behavior:** `--phase N` accepts three entry points: `0` (setup), `2` (translation), `3` (post-processing). It does NOT support resuming from individual phases within post-processing (e.g., Phase 6). A Phase 6 failure restarts from Phase 3.
```

Append the following section to the issue body:

```
### Design consideration: silent-skip interaction with #7

Phase 4b and Phase 9 can silently skip due to venv permission issues (#7). The checkpointing design must distinguish between:
- **Phase completed successfully** — mark complete, proceed
- **Phase skipped (silently failed)** — do NOT mark complete; log a warning

Without this distinction, checkpointing would mask #7's bug by recording skipped phases as complete.

### Related issues

- #7 — venv permission mismatch (Phase 4b/9 silent skip)
- #11 — regression testing (needs phase-level granularity)
```

### Issue #13 — Fix broken reference and add evidence requirement

Replace the `PLAN.md` reference. Where the issue says "See `PLAN.md` Level 3 section for detailed design", correct it to:

```
**Note:** No Level 3 section exists in `PLAN.md` yet. The PLAN.md file covers Levels 1–2 only. A Level 3 design section should be written before implementation begins.
```

Also fix the same broken reference in `TODO.md` line 29 — change "See `PLAN.md` Level 3 for details" to "No `PLAN.md` Level 3 section exists yet — write one before implementation."

Append the following section to the issue body:

```
### Evidence needed before implementation

The "When to Consider" triggers are hypothetical. Before investing in Vosk integration:
1. Verify that the Fawlty Towers cues 102–108 case (~00:10:18) actually fails with Levels 1+2
2. Document at least 2–3 real cases where timecode-based mapping produces incorrect or ambiguous results
3. If no such cases exist after several production runs, close this issue as unnecessary

### Acceptance criteria

- Vosk model downloads and runs on i3-13100T in < 30 min per episode
- Level 3 results are additive (supplement, never override Levels 1+2)
- Phase 9 output includes which level produced each finding
- `--no-vosk` flag available to skip when not needed
```

### Additional cleanup tasks

1. **TODO.md line 31–36:** The "Skill Triggering Description" section still describes Issue #8 as open, but #8 is closed. Remove this section from TODO.md or mark it as completed.
2. **Cross-references:** After updating issues, add "Related issues" links between #7, #11, and #12 where not already present.
3. **Labels:** Add labels to closed issues #1–6 retroactively:
   - `gh issue edit 1 --add-label "bug"`
   - `gh issue edit 2 --add-label "enhancement"`
   - `gh issue edit 3 --add-label "enhancement"`
   - `gh issue edit 4 --add-label "enhancement"`
   - `gh issue edit 5 --add-label "enhancement"`
   - `gh issue edit 6 --add-label "enhancement"`
