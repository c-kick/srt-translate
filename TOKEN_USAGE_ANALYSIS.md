# Token Usage Analysis — srt-translate

## Architecture Overview

The orchestrator (`orchestrate.sh`) runs 3 phase groups, each as a separate `claude -p` headless invocation with multi-turn tool access:

| Phase Group | Model | Purpose |
|---|---|---|
| Setup (0-1) | Sonnet | Sync, classify, write checkpoint |
| Translation (2) | **Opus** | EN-NL translation in 100-cue batches |
| Post-processing (3-9+11) | Sonnet | Structural fix, merge, CPS, review, finalize |

Translation may span **multiple invocations** (up to 6 batches of 100 cues per invocation = 600 cues/invocation).

---

## 1. The Dominant Cost: Cumulative Context in Multi-Turn Tool Calling

Every `claude -p` invocation with `--allowedTools` is a **multi-turn conversation**. Each turn, the API re-sends the entire conversation history (system prompt + all prior assistant messages + all tool results). The cost compounds quadratically.

### Phase 2 (Translation) — per invocation

Each 100-cue batch requires ~6-8 sequential tool-call turns:

1. `Bash(extract_cues.py)` — extract source batch
2. `Read(batch_source.srt)` — read 100 EN cues (~2,500 tokens)
3. `Write(draft.nl.srt)` — write 100 NL cues (~2,500 tokens)
4. `Bash(extract_cues.py)` — extract NL for grammar check
5. `Read(batch_review.srt)` — re-read the NL translation (~2,500 tokens)
6. `Bash(validate_srt.py)` — validation (~200 tokens)
7. `Write(batch_context.md)` + `Read/Write(glossary)` — bookkeeping

Each turn adds ~1-3K tokens to the conversation. The system prompt (see Section 2) is re-sent on **every** turn.

**Conservative model for 6 batches (~36 turns):**

| Turn | Context Size | Cumulative Billed |
|---|---|---|
| 1 | 19K | 19K |
| 6 (end batch 1) | 32K | 153K |
| 12 (end batch 2) | 45K | 384K |
| 18 (end batch 3) | 58K | 693K |
| 24 (end batch 4) | 72K | 1.08M |
| 30 (end batch 5) | 85K | 1.55M |
| 36 (end batch 6) | 99K | 2.1M |

**~2.1M input tokens billed per invocation on Opus.** For a 1500-cue film (3 invocations): **~6.3M input tokens**.

### Post-processing (Phases 3-9+11) — single invocation on Sonnet

Even heavier on tool calls (~60-80 turns across all sub-phases):

- Phase 6 (linguistic review): ~13 chunks of 80 cues x 3-4 tool calls = ~45 turns
- Phase 11 (grammar scan): ~10 chunks of 100 cues x 3-4 tool calls = ~35 turns
- Phases 3-5, 7-9 (scripts + fixes): ~30 tool calls

Estimated **~3-4M input tokens** on Sonnet. Much cheaper per token but still substantial.

---

## 2. The System Prompt Tax

### Always loaded (every Phase 2 invocation)

| File | Words | ~Tokens |
|---|---|---|
| `shared-constraints.md` | 2,397 | 3,200 |
| `workflow-translate.md` | 1,489 | 2,000 |
| `dutch-patterns.md` | 1,235 | 1,650 |
| `common-errors.md` | 626 | 835 |
| `exemplars/condensation.md` | 1,567 | 2,100 |
| `exemplars/idiom-adaptation.md` | 1,310 | 1,750 |
| `exemplars/v2-word-order.md` | 623 | 830 |
| **Subtotal (always)** | **~9,250** | **~12,365** |

### Genre-conditional loading

| Genre | Extra Files | Extra Tokens | Total Prompt |
|---|---|---|---|
| Documentary | translator + `exemplars/documentary.md` | +5,600 | **~18K** |
| Drama | translator + `exemplars/drama.md` + `exemplars/dual-speaker.md` | +3,950 | **~16K** |
| Comedy | translator + `exemplars/drama.md` + `exemplars/dual-speaker.md` | +3,950 | **~16K** |
| Fast-unscripted | translator + `exemplars/dual-speaker.md` | +2,200 | **~15K** |

Plus inline prompt content (handoff, glossary, batch context, checkpoint): ~500-2,000 tokens depending on batch.

**This system prompt is billed on every single turn.** With ~36 turns per invocation and 3 invocations for a 1500-cue documentary:
- 108 turns x 19K = **~2M tokens** just for re-reading the system prompt

---

## 3. Duplicate Data Reads

Within each batch, the same data gets read multiple times:

| Data | First appearance | Duplicate read | Wasted tokens |
|---|---|---|---|
| 100 source EN cues | `Bash(extract_cues.py)` output | `Read(batch_source.srt)` | ~2,500 |
| 100 NL translated cues | `Write(draft.nl.srt)` input | `Read(batch_review.srt)` via extract | ~2,500 |
| Glossary | `Read(glossary)` | Written even if unchanged | ~200-800 |

~5,000 tokens of duplicate data per batch, accumulating in context for all subsequent turns.

---

## 4. Cost Estimate (1500-cue documentary)

| Component | Input Tokens | Rate | Cost |
|---|---|---|---|
| **Phase 2 input (Opus, 3 invocations)** | **~6.3M** | **$15/MTok** | **$94.50** |
| **Phase 2 output (Opus)** | **~150K** | **$75/MTok** | **$11.25** |
| Post-processing input (Sonnet) | ~3.5M | $3/MTok | $10.50 |
| Post-processing output (Sonnet) | ~80K | $15/MTok | $1.20 |
| Setup (Sonnet) | ~20K | $3/MTok | $0.06 |
| **Total** | | | **~$117** |

**Phase 2 Opus input dominates at ~81% of total cost.** Within that, re-reading the system prompt across turns is the single biggest contributor (~$30).

> **Note:** These numbers assume no prompt caching. If Claude Code headless mode activates Anthropic's prompt caching (which caches the static prefix at 90% discount), the actual cost could be drastically lower. Verifying cache hit rates is the single highest-leverage investigation.

---

## 5. Mitigation Options

### Tier 1 — Highest Impact

#### A. Verify/enable prompt caching

The ~19K system prompt is identical across all turns within an invocation. If Anthropic's prompt caching is active, cached tokens cost 90% less. This alone could drop Phase 2 input cost from $94.50 to ~$15.

**Action:** Check whether `claude -p` headless mode gets prompt caching. If not, investigate whether the system prompt can be structured to maximize cache hits (e.g., static prefix before dynamic inline content).

**Estimated savings:** Up to 80% of Phase 2 input cost.
**Effort:** Investigation only.
**Risk:** None.

#### B. Increase batch size from 100 to 200 cues

Change `BATCH_SIZE=100` to `BATCH_SIZE=200` in `orchestrate.sh`.

This halves the number of tool call rounds per invocation (~18 turns instead of ~36), halves the invocations needed for a typical film (2 instead of 3 for 1500 cues), and drastically reduces cumulative context growth.

**Estimated savings:** 40-50% of Phase 2 input tokens.
**Effort:** One line change + test.
**Risk:** Minimal. Opus handles 200 cues comfortably. Batch context summaries may be slightly less granular.

#### C. Eliminate duplicate reads per batch

The workflow currently has the model:
1. Extract source cues via `Bash(extract_cues.py)` — script output goes into context
2. Then `Read()` the same extracted file — file contents go into context again

Same for the grammar check: the model writes the NL cues (they're in context as the Write input), then extracts + reads them again.

**Fix:** Restructure the workflow so that:
- The extract script's stdout IS the read (no separate Read call needed)
- Grammar review works from the Write input already in context (no re-read)

**Estimated savings:** ~5,000 tokens less context growth per batch = ~30K less accumulation per invocation.
**Effort:** Workflow edit.
**Risk:** None.

### Tier 2 — Moderate Impact

#### D. Trim `exemplars/documentary.md`

At 3,553 words (~4,700 tokens), this is the largest single file in the system prompt. It's loaded on every documentary translation invocation (and documentary is the most common content type).

It contains ~30+ worked examples. Many demonstrate the same principle (e.g., multiple examples of "abstract to concrete" or "compound adjective replaces clause"). Distilling to the 12-15 most impactful examples could save 2,000-3,000 tokens.

**Estimated savings:** ~2,500 tokens x 108 turns = ~270K tokens per film.
**Effort:** 1 hour of curation.
**Risk:** Slight quality reduction if the removed examples covered edge cases. Mitigated by keeping the most diverse set.

#### E. Split post-processing into 2-3 sub-invocations

Currently one massive invocation runs Phases 3-11. By the time Phase 11 starts, it's carrying all of Phases 3-9's tool history (~100K+ tokens of irrelevant past context).

Split into:
1. Phases 3-5 (structural: fix, merge, CPS)
2. Phase 6 (linguistic review)
3. Phases 7-9+11 (finalize, QC, grammar scan)

Each starts with a clean context. State passes via files on disk (already the case).

**Estimated savings:** 30-40% of post-processing input tokens.
**Effort:** Script changes to `orchestrate.sh` (add 2 more `invoke_claude` calls, partition the file loading).
**Risk:** None — phases already communicate via files.

#### F. Condense `shared-constraints.md`

At 2,397 words (~3,200 tokens), this is the largest always-loaded file and it's included in **every** phase (setup, translation, post-processing).

The dual-speaker section alone (Phase 1/2 mechanical+contextual analysis with worked example) is ~800 words. This could move to `exemplars/dual-speaker.md` where it's only loaded for genres that need it (drama, comedy, fast-unscripted).

Several rules in shared-constraints are also restated in translator profiles (e.g., line break rules, contraction rules).

**Estimated savings:** ~1,000 tokens per turn across all phases.
**Effort:** 1-2 hours of careful refactoring.
**Risk:** Must ensure no rules are lost in the move.

### Tier 3 — Lower Impact / Higher Risk

#### G. Move per-batch grammar check to post-processing

Eliminates 2-3 tool calls per batch (extract + read + edit). Phase 6 already does a full linguistic review, making the per-batch check partially redundant.

**Estimated savings:** ~15% of Phase 2 tool I/O.
**Effort:** Workflow change.
**Risk:** Grammar errors compound if not caught early. Fixing dt-errors in batch 6 is harder than in batch 1.

#### H. Pre-process SRT into compact format

Strip timecodes during translation — they're ~30% of SRT text by volume. Send only `cue_number|text` per line. Reconstruct timecodes from the source mapping after translation.

**Estimated savings:** ~750 tokens per batch read/write.
**Effort:** New pre/post-processing scripts + workflow change.
**Risk:** Loss of timecode awareness during translation (model currently uses timecodes to gauge pacing).

#### I. Use Sonnet for translation

5x cheaper on both input and output. Would reduce Phase 2 cost from ~$106 to ~$21.

**Estimated savings:** 80% of Phase 2 cost.
**Effort:** Config change.
**Risk:** Translation quality is the core value proposition. Sonnet produces notably fewer `[SC]` markers and weaker idiomatic Dutch. Could be viable for simple narration-heavy content (single-speaker documentaries).

---

## 6. Recommended Implementation Order

| Priority | Change | Savings | Effort |
|---|---|---|---|
| 1 | Verify prompt caching status | Up to 80% of input | Check only |
| 2 | Batch size 100 -> 200 | 40-50% of Phase 2 input | 1 line |
| 3 | Eliminate duplicate reads | 15-20% of Phase 2 tool I/O | Workflow edit |
| 4 | Trim documentary exemplar | 10-15% of documentary prompt | 1 hour |
| 5 | Split post-processing | 30-40% of Sonnet input | Script edit |
| 6 | Condense shared-constraints | 5-10% across all phases | 1-2 hours |

**Combining items 1-3 could reduce total cost by 85-90%** (if caching is confirmed) or **50-60%** (without caching).

---

## 7. Key Unknowns

1. **Prompt caching behavior in headless mode** — Does `claude -p` get automatic prompt caching? If yes, the system prompt tax is already 90% mitigated and the main target shifts to reducing per-batch tool I/O volume.

2. **Actual turn count** — The estimates assume ~6 tool calls per batch. The real number depends on whether the model parallelizes some calls (e.g., write + validate in one turn) or adds extra calls (e.g., multiple Edit passes for grammar fixes). Real-world logging would sharpen these numbers significantly.

3. **Context compression** — Claude Code may compress older conversation turns when approaching context limits. If active in headless mode, this would reduce the cumulative growth problem but at the cost of potential information loss in earlier batches.
