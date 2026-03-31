# Plan: Reduce Token Usage Without Sacrificing Translation Quality

## Problem

A 1500-cue documentary film costs ~$49 per run (Opus 4.6 pricing). The dominant cost driver is cumulative context growth in multi-turn tool calling: each tool call re-sends the entire conversation history, and the total billed input grows as O(n²) in the number of turns.

See `TOKEN_USAGE_ANALYSIS.md` for the full breakdown.

## Design Principle: Don't Touch Translation Quality

Every change in this plan is either invisible to the model (structural/orchestrator changes) or reduces noise without removing information. No exemplars are trimmed, no reference files are removed, no instructions are weakened.

**What this plan changes:**
- `scripts/orchestrate.sh` — batch size, post-processing split, prompt assembly
- `base/workflow-translate.md` — batch extraction instructions (eliminate duplicate reads)
- `scripts/extract_cues.py` — add `--stdout` flag for direct output

**What this plan does NOT change:**
- `shared-constraints.md` — untouched
- All translator profiles — untouched
- All exemplar files — untouched
- All reference files — untouched
- `workflow-post.md` — untouched (changes are in the orchestrator only)
- Translation output format — untouched
- Post-processing phases — untouched (same work, just split across invocations)

---

## Step 0: Establish Baseline (investigation only)

Before implementing anything, measure what we're actually spending.

### 0a. Check prompt caching status

Anthropic's prefix caching caches the longest common prefix of the full message array at 90% discount. In a multi-turn conversation, this means all prior turns are cached — not just the system prompt. If active, the cumulative context problem is already largely mitigated.

**Action:** Run a translation on a short file (~200 cues, 2 batches) and capture the API response headers or billing data. Look for:
- `cache_creation_input_tokens` and `cache_read_input_tokens` in API responses
- Whether Claude Code's `claude -p` mode structures API calls with a cacheable prefix

**If caching is active:** The cost model changes fundamentally. Re-evaluate whether further optimizations are worth the implementation effort.

**If caching is not active:** Proceed with Steps 1-3.

### 0b. Measure actual token usage

Run a single translation invocation with `--max-batches 6` and `--keep-work`. Capture the stderr log:

```bash
CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 \
  scripts/orchestrate.sh /path/to/video.mkv --max-batches 6 --keep-work 2>&1 | tee run.log
```

Check `${LOG_DIR}/claude_stderr_*.log` for actual token counts per turn. Compare against the theoretical model in `TOKEN_USAGE_ANALYSIS.md`.

---

## Step 1: Increase Batch Size to 200 Cues

**Estimated savings:** ~40% of Phase 2 input tokens (~$13/film).
**Risk:** Must be verified — see testing protocol below.

### Change

In `orchestrate.sh`, change:

```bash
BATCH_SIZE=100
```

to:

```bash
BATCH_SIZE=200
```

This is a one-line change. Everything downstream (extract_cues, batch context, glossary, handoff) works identically — they're parameterized by `BATCH_SIZE` already.

**Effect:**
- 1500-cue film: 8 batches in 2 invocations (was 15 batches in 3 invocations)
- ~18 turns per invocation instead of ~36
- One fewer system prompt payment (~19K tokens × ~18 turns = ~342K saved)
- Lower cumulative context peak per invocation

### Quality verification protocol

The risk is attention degradation on longer batches — particularly `[SC]` marker accuracy in dialogue-heavy content. Test with the hardest case first:

1. **Pick a comedy or fast-unscripted file** with known-good output at batch-100 (the existing baseline).
2. Re-run Phase 2 only with `--phase 2 --max-batches 2` at batch-200.
3. Compare `[SC]` marker placement:
   ```bash
   # Count [SC] markers in both outputs
   grep -c '\[SC\]' draft_100.nl.srt
   grep -c '\[SC\]' draft_200.nl.srt
   ```
4. Diff the two drafts. Focus on:
   - Missing `[SC]` markers (the dangerous failure mode — causes false merges)
   - Translation quality in cues 150-200 (the "attention tail" of a 200-cue batch)
5. Run both through Phase 4 (merge) and compare dual-speaker cue counts.

**Accept criteria:** `[SC]` count within 5% of baseline. No false merges visible in spot-check of 20 merged cues.

**Fallback:** If batch-200 degrades quality, try batch-150 as a middle ground. Even 150 saves ~25% by reducing from 3 invocations to 2 for a 1500-cue file.

---

## Step 2: Eliminate Duplicate Reads in Phase 2

**Estimated savings:** ~$1/film (small direct savings, but reduces context noise).
**Risk:** None.

### Problem

Each batch currently has two duplicate data reads:

1. **Source cues:** `Bash(extract_cues.py --output file)` writes to disk, then `Read(file)` reads it back. Both outputs land in the conversation context.
2. **Grammar review:** Model writes NL cues via `Write(draft.nl.srt)`, then `Bash(extract_cues.py)` + `Read()` re-reads them for review. The cues are already in context from the Write call.

### Solution

#### 2a. Add `--stdout` flag to `extract_cues.py`

When `--stdout` is passed (instead of `--output`), print the SRT content directly to stdout. The model reads the cues from the Bash tool output — no separate Read call needed.

```python
# In extract_cues.py, add to argparse:
parser.add_argument('--stdout', action='store_true',
                    help='Print extracted SRT to stdout instead of writing to file')
```

```python
# In extract_cues(), after building extracted list:
if stdout:
    from io import StringIO
    buf = StringIO()
    write_srt(extracted, buf)
    print(buf.getvalue())
    return {'success': True, 'extracted': len(extracted)}
```

This replaces a 2-step flow (Bash → Read) with a 1-step flow (Bash), eliminating ~2,500 tokens of duplicate context per batch.

#### 2b. Remove grammar re-read from workflow

In `workflow-translate.md`, change the per-batch grammar check from:

```markdown
### Per-batch grammar check

After writing each batch:

\`\`\`bash
python3 scripts/extract_cues.py draft.nl.srt --start {batch_start} --end {batch_end} --output batch_review.srt
\`\`\`

Check (see `references/common-errors.md`):
```

to:

```markdown
### Per-batch grammar check

After writing each batch, review the cues you just wrote (already in your context from the Write/append step) against this checklist (see `references/common-errors.md`):
```

The model already has the NL cues in context — it just wrote them. Telling it to re-read them via extract+Read is pure waste.

#### 2c. Update inline prompt in orchestrate.sh

In the Phase 2 inline prompt, change the batch extraction instruction from:

```
**Batch plan:** Process ${BATCH_SIZE} cues per batch. Extract each batch with:
\`\`\`bash
python3 ${SKILL_DIR}/scripts/extract_cues.py ${SOURCE_SRT} --start N --end M --output ${WORK_DIR}/batch_source.srt
\`\`\`
```

to:

```
**Batch plan:** Process ${BATCH_SIZE} cues per batch. Extract each batch directly:
\`\`\`bash
python3 ${SKILL_DIR}/scripts/extract_cues.py ${SOURCE_SRT} --start N --end M --stdout
\`\`\`
This prints the source cues directly — read them from the command output. No separate Read call needed.
```

### Files changed

| File | Change |
|------|--------|
| `scripts/extract_cues.py` | Add `--stdout` flag |
| `base/workflow-translate.md` | Remove extract+read for grammar check; update batch extraction to use `--stdout` |
| `scripts/orchestrate.sh` | Update inline batch plan instructions |

---

## Step 3: Split Post-Processing into Sub-Invocations

**Estimated savings:** ~$3/film (~25% of post-processing Sonnet cost).
**Risk:** None — phases already communicate via files on disk.

### Problem

Post-processing runs as a single monolithic `invoke_claude` call covering Phases 3-9+11. By the time Phase 11 (grammar scan) runs, the context contains the full tool history of Phases 3-9 — tens of thousands of tokens of irrelevant script output, validation results, and intermediate file reads.

### Solution

Split `run_postprocessing()` into three separate invocations:

| Invocation | Phases | Input Files | Purpose |
|---|---|---|---|
| `run_postprocessing_structural` | 3, 4, 4b, 5 | draft.nl.srt → trimmed.nl.srt | Structural fixes, merge, trim, CPS |
| `run_postprocessing_review` | 6 | merged.nl.srt + merge_report.json | Linguistic review (the heaviest phase) |
| `run_postprocessing_finalize` | 7, 8, 9, 11 + log | final SRT | Finalize, QC, grammar scan, log |

Each invocation starts with a clean context. The `$WORKFLOW_POST` file already documents each phase independently — the instructions don't depend on prior phases' tool output.

### Implementation

Replace `run_postprocessing()` with three functions. Each loads only the workflow sections it needs.

**Option A (simple):** Keep loading the full `$WORKFLOW_POST` in each invocation, but the inline prompt specifies which phases to run. The unused phase instructions add ~2K tokens of noise but are otherwise harmless.

**Option B (optimal):** Split `workflow-post.md` into `workflow-post-structural.md`, `workflow-post-review.md`, `workflow-post-finalize.md`. Each invocation loads only its section.

**Recommendation:** Start with Option A. It's a pure orchestrator change — no workflow file changes. If token savings from Option B are needed, do it as a follow-up.

### Invocation 1: Structural (Phases 3-5)

```bash
invoke_claude --model "$MODEL_POST" "Post-processing: structural (Phases 3-5)" \
    "$SHARED_CONSTRAINTS" \
    "$WORKFLOW_POST" \
    "$COMMON_ERRORS" \
    "$TRANSLATION_DEFAULTS" \
    <<EOF
## Task
Run post-processing phases 3 through 5 on the translated draft.
...
Execute these phases in order:
1. **Pre-Phase-3:** Save draft mapping
2. **Phase 3:** Structural fix on draft.nl.srt
3. **Phase 4:** Script merge with genre parameters
4. **Phase 4b:** Trim to speech
5. **Phase 5:** CPS optimization on trimmed.nl.srt
Stop after Phase 5. Do not proceed to Phase 6.
EOF
```

### Invocation 2: Linguistic Review (Phase 6)

```bash
invoke_claude --model "$MODEL_POST" "Post-processing: linguistic review (Phase 6)" \
    "$SHARED_CONSTRAINTS" \
    "$WORKFLOW_POST" \
    "$COMMON_ERRORS" \
    <<EOF
## Task
Run Phase 6 (Linguistic Review) on the merged subtitle file.
...
Work through the full file in chunks of ~80 cues.
Stop after Phase 6. Do not proceed to Phase 7.
EOF
```

Note: `$TRANSLATION_DEFAULTS` is not loaded here — Phase 6 doesn't need it.

### Invocation 3: Finalize + QC (Phases 7-9, 11 + log)

```bash
invoke_claude --model "$MODEL_POST" "Post-processing: finalize + QC (Phases 7-9, 11)" \
    "$SHARED_CONSTRAINTS" \
    "$WORKFLOW_POST" \
    "$COMMON_ERRORS" \
    "$TRANSLATION_DEFAULTS" \
    <<EOF
## Task
Run finalization and QC phases on the reviewed subtitle file.
...
Execute these phases in order:
1. **Phase 7:** Finalize
2. **Phase 8:** Line balance QC
3. **Phase 9:** VAD timing QC
4. **Phase 11:** Final grammar scan
5. **Write log**
EOF
```

### Error handling

Same as current: if the output file isn't found after each invocation, log a warning. The safety net at the end of `main()` still catches missing output.

Between invocations, verify the expected intermediate file exists:
- After structural: check `trimmed.nl.srt` (or `merged.nl.srt`) exists
- After review: check the SRT was modified (mtime changed or cue count stable)
- After finalize: check `${OUTPUT_SRT}` exists (existing behavior)

### Files changed

| File | Change |
|------|--------|
| `scripts/orchestrate.sh` | Split `run_postprocessing()` into 3 functions; update `main()` call chain |

---

## Implementation Order

| Step | Change | Files | Effort | Savings |
|---|---|---|---|---|
| 0 | Measure baseline (caching + actual tokens) | None | 1 test run | Informs everything |
| 1 | Batch size 100 → 200 | `orchestrate.sh` | 1 line + quality test | ~$13/film (40%) |
| 2 | Eliminate duplicate reads | `extract_cues.py`, `workflow-translate.md`, `orchestrate.sh` | Small | ~$1/film |
| 3 | Split post-processing | `orchestrate.sh` | Moderate | ~$3/film (25% of post) |

**Total estimated savings (no caching):** ~$17 of $49 = **~35%** per 1500-cue film.
**If prefix caching is already active:** Savings from Steps 1-3 are smaller in absolute terms (~$3-5), but the baseline cost is also much lower (~$10-15 per film), making it potentially acceptable as-is.

---

## What This Plan Explicitly Does NOT Do

- **Trim exemplars or reference files** — These are the quality backbone. Saving ~$1.35/film by cutting documentary examples is not worth the risk.
- **Condense shared-constraints.md** — Moving the dual-speaker section saves ~$1/film but risks dropping rules. Not worth it.
- **Move grammar check to post-processing** — Catching errors while context is fresh is valuable. The duplicate-read elimination (Step 2b) captures the easy savings without removing the check itself.
- **Switch models** — Sonnet for translation loses `[SC]` accuracy and idiomatic quality. The cost difference ($35 vs $18) doesn't justify the quality regression.
- **Pre-process SRT into compact format** — Saves ~$0.50/film for significant implementation effort. The model's timecode awareness during translation is worth more than $0.50.

---

## Validation

After implementing Steps 1-3, run a full translation on a known-good file and compare:

| Metric | Baseline | Target |
|---|---|---|
| `[SC]` marker count | ±5% | Must match |
| Dual-speaker cues after merge | ±5% | Must match |
| CPS distribution | Same | Must match |
| Phase 9 VAD issues (HIGH severity) | Same | Must match |
| Translation quality (spot-check 30 cues) | Baseline | No degradation |
| Total API cost | ~$49 | ~$32 or less |
