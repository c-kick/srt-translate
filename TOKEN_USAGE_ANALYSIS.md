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

Every `claude -p` invocation with `--allowedTools` is a **multi-turn conversation**. Each turn, the API re-sends the entire conversation history (system prompt + all prior assistant messages + all tool results). Per-turn context grows linearly (~2K/turn), but the **total billed input** grows as the sum of an arithmetic series — O(n²) in the number of turns.

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

Base system prompt for post-processing: ~7K tokens (shared-constraints + workflow-post + common-errors + translation-defaults). With ~70 turns at ~1.5K growth/turn: sum ≈ 70 × 7K + 1.5K × (69×70/2) = 490K + 3,623K ≈ **~4.1M input tokens** on Sonnet.

---

## 2. The System Prompt Tax

### Always loaded (every Phase 2 invocation)

| File | Words | ~Tokens |
|---|---|---|
| `shared-constraints.md` | 2,451 | 3,270 |
| `workflow-translate.md` | 1,517 | 2,025 |
| `dutch-patterns.md` | 1,250 | 1,670 |
| `common-errors.md` | 632 | 845 |
| `exemplars/condensation.md` | 1,620 | 2,160 |
| `exemplars/idiom-adaptation.md` | 1,368 | 1,825 |
| `exemplars/v2-word-order.md` | 653 | 870 |
| **Subtotal (always)** | **~9,491** | **~12,665** |

Word counts via `wc -w`. Token estimates at ~1.33 tokens/word (reasonable for mixed English/Dutch markdown but unverified against the actual tokenizer; treat as approximate).

### Genre-conditional loading

The orchestrator loads genre-specific exemplars via a case statement (`orchestrate.sh:301-311`):

| Genre | Extra Files | Extra Tokens | Total Prompt |
|---|---|---|---|
| Documentary | translator + `exemplars/documentary.md` (3,766 words) | +6,230 | **~19K** |
| Drama | translator + `exemplars/drama.md` + `exemplars/dual-speaker.md` | +4,080 | **~17K** |
| Comedy | translator + `exemplars/drama.md` + `exemplars/dual-speaker.md` | +4,080 | **~17K** |
| Fast-unscripted | translator + `exemplars/dual-speaker.md` | +2,270 | **~15K** |

Plus inline prompt content (handoff, glossary, batch context, checkpoint): ~500-2,000 tokens depending on batch.

**This system prompt is billed on every single turn.** With ~36 turns per invocation and 3 invocations for a 1500-cue documentary:
- 108 turns × 19K = **~2M tokens** just for re-reading the system prompt

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

## 4. Cost Estimates

**Pricing (Opus 4.6 / Sonnet 4.6, as of March 2026):**
- Opus: **$5/MTok input, $25/MTok output**
- Sonnet: **$3/MTok input, $15/MTok output**

### Scenario A: 1500-cue documentary (feature film, ~100 min)

| Component | Input Tokens | Rate | Cost |
|---|---|---|---|
| **Phase 2 input (Opus, 3 invocations)** | **~6.3M** | **$5/MTok** | **$31.50** |
| **Phase 2 output (Opus)** | **~150K** | **$25/MTok** | **$3.75** |
| Post-processing input (Sonnet) | ~4.1M | $3/MTok | $12.30 |
| Post-processing output (Sonnet) | ~80K | $15/MTok | $1.20 |
| Setup (Sonnet) | ~20K | $3/MTok | $0.06 |
| **Total** | | | **~$49** |

Phase 2 Opus input dominates at ~64% of total cost.

### Scenario B: 600-cue drama (TV episode, ~45 min)

| Component | Input Tokens | Rate | Cost |
|---|---|---|---|
| Phase 2 input (Opus, 1 invocation) | ~2.1M | $5/MTok | $10.50 |
| Phase 2 output (Opus) | ~50K | $25/MTok | $1.25 |
| Post-processing input (Sonnet) | ~1.8M | $3/MTok | $5.40 |
| Post-processing output (Sonnet) | ~35K | $15/MTok | $0.53 |
| Setup (Sonnet) | ~20K | $3/MTok | $0.06 |
| **Total** | | | **~$18** |

### Scenario C: 2400-cue comedy (long film with rapid dialogue)

| Component | Input Tokens | Rate | Cost |
|---|---|---|---|
| Phase 2 input (Opus, 4 invocations) | ~8.4M | $5/MTok | $42.00 |
| Phase 2 output (Opus) | ~200K | $25/MTok | $5.00 |
| Post-processing input (Sonnet) | ~5.5M | $3/MTok | $16.50 |
| Post-processing output (Sonnet) | ~100K | $15/MTok | $1.50 |
| Setup (Sonnet) | ~20K | $3/MTok | $0.06 |
| **Total** | | | **~$65** |

> **Critical caveat:** These are theoretical estimates built on a model of context accumulation. They assume no prompt caching (see Section 5A). **One real API usage dashboard or invoice would validate or invalidate every number here.** Checking actual billing should be step 0 before implementing any optimization.

---

## 5. Mitigation Options

### Tier 1 — Highest Impact

#### A. Verify prompt caching behavior

Anthropic's prompt caching doesn't just cache the system prompt — it caches the **longest common prefix of the full message array**. In a multi-turn conversation, all prior turns are re-sent and would also benefit from caching. This means the cache benefit is potentially much larger than just the system prompt: the entire accumulated conversation history from prior turns would be cached, with only the latest turn's content billed at full rate.

If prefix caching is active in `claude -p` headless mode, the cumulative growth problem described in Section 1 is largely self-solving — the re-billed history is cached at 90% discount, and only the new turn's delta pays full price.

**Action:** Check whether `claude -p` headless mode gets automatic prompt caching. Examine actual API usage data (billing dashboard, `claude_stderr_*.log` files) for cache hit rates. If caching is active, the problem may already be 60-70% smaller than this analysis assumes.

**Estimated savings:** If full prefix caching is active, up to 80-90% of input cost. If only system prompt caching, ~20% of input cost (system prompt is ~19K of the ~60K average context per turn).
**Effort:** Investigation only.
**Risk:** None.

#### B. Increase batch size from 100 to 200 cues

Change `BATCH_SIZE=100` to `BATCH_SIZE=200` in `orchestrate.sh`.

This halves the number of tool call rounds per invocation (~18 turns instead of ~36), halves the invocations needed for a typical film (2 instead of 3 for 1500 cues), and reduces cumulative context growth.

**Derivation (Scenario A, without caching):**
- Current (100-cue batches, 3 invocations): ~6.3M input = $31.50
- With 200-cue batches, 2 invocations of 4 batches each:
  - ~18 turns per invocation, context growth similar but fewer turns
  - Estimated ~3.6M input = $18.00
- Savings: ~$13.50 (43%)

**Estimated savings:** ~40% of Phase 2 input tokens.
**Effort:** One line change + quality testing.
**Risk:** Needs testing. Larger batches risk attention degradation, especially for `[SC]` marker placement in dialogue-heavy content. The claim that "Opus handles 200 cues comfortably" is plausible but unverified. Test with a comedy or fast-unscripted file where `[SC]` accuracy is most critical.

#### C. Eliminate duplicate reads per batch

The workflow currently has the model:
1. Extract source cues via `Bash(extract_cues.py)` — script output goes into context
2. Then `Read()` the same extracted file — file contents go into context again

Same for the grammar check: the model writes the NL cues (they're in context as the Write input), then extracts + reads them again.

**Fix:** Restructure the workflow so that:
- The extract script's stdout IS the read (no separate Read call needed)
- Grammar review works from the Write input already in context (no re-read)

**Derivation:** ~5K fewer tokens accumulated per batch × 6 batches × 3 invocations × $5/MTok. Direct savings: ~$0.45. Indirect savings (less context accumulation reduces all subsequent turn costs): roughly double, so ~$1 total.

**Estimated savings:** ~$1/film (small in dollar terms, but reduces context noise for better model attention).
**Effort:** Workflow edit.
**Risk:** None.

### Tier 2 — Moderate Impact

#### D. Split post-processing into 2-3 sub-invocations

Currently one massive invocation runs Phases 3-11. By the time Phase 11 starts, it's carrying all of Phases 3-9's tool history (~100K+ tokens of irrelevant past context).

Split into:
1. Phases 3-5 (structural: fix, merge, CPS)
2. Phase 6 (linguistic review)
3. Phases 7-9+11 (finalize, QC, grammar scan)

Each starts with a clean context. State passes via files on disk (already the case).

**Derivation:** Current ~4.1M Sonnet input tokens. Three sub-invocations with fresh contexts would have lower cumulative growth: ~25 turns × 7K base + growth ≈ ~1.0M each × 3 = ~3.0M. Savings: ~1.1M tokens = ~$3.30/film.

**Estimated savings:** ~25-30% of post-processing input tokens (~$3/film).
**Effort:** Script changes to `orchestrate.sh` (add 2 more `invoke_claude` calls, partition the file loading).
**Risk:** None — phases already communicate via files.

#### E. Trim `exemplars/documentary.md`

At 3,766 words (~5,000 tokens), this is the largest single file in the documentary system prompt. It contains ~30+ worked examples. Many demonstrate the same principle (e.g., multiple examples of "abstract to concrete" or "compound adjective replaces clause"). Distilling to the 12-15 most impactful examples could save 2,000-3,000 tokens.

**Derivation (documentary only):** ~2,500 fewer tokens × 36 turns × 3 invocations × $5/MTok = ~$1.35/film. Small absolute savings.

**Estimated savings:** ~$1.35/documentary film.
**Effort:** 1 hour of curation.
**Risk:** Slight quality reduction if removed examples covered edge cases. Low ROI for the quality risk.

#### F. Condense `shared-constraints.md`

At 2,451 words (~3,270 tokens), this is the largest always-loaded file and it's included in **every** phase (setup, translation, post-processing).

The dual-speaker section (Phase 1/2 mechanical+contextual analysis with worked example) is ~800 words. This could move to `exemplars/dual-speaker.md` where it's only loaded for genres that need it.

**Derivation:** ~1,000 fewer tokens × all turns across all phases. For Phase 2 alone: ~1K × 108 turns × $5/MTok = ~$0.54/film. Across all phases: ~$1/film.

**Estimated savings:** ~$1/film.
**Effort:** 1-2 hours of careful refactoring.
**Risk:** Must ensure no rules are lost in the move. Low ROI.

### Tier 3 — Lower Impact / Higher Risk

#### G. Move per-batch grammar check to post-processing

Eliminates 2-3 tool calls per batch (extract + read + edit). Phase 6 already does a full linguistic review, making the per-batch check partially redundant.

**Estimated savings:** ~$1-2/film in Phase 2 tool I/O.
**Effort:** Workflow change.
**Risk:** Grammar errors compound if not caught early. Fixing dt-errors in batch 6 is harder than in batch 1. The per-batch check catches issues while context is fresh.

#### H. Pre-process SRT into compact format

Strip timecodes during translation — they're ~30% of SRT text by volume. Send only `cue_number|text` per line. Reconstruct timecodes from the source mapping after translation.

**Estimated savings:** ~750 tokens per batch read/write ≈ ~$0.50/film.
**Effort:** New pre/post-processing scripts + workflow change.
**Risk:** Loss of timecode awareness during translation (model currently uses timecodes to gauge pacing).

#### I. Use Sonnet for translation

~1.7x cheaper on input, ~1.7x cheaper on output.

**Estimated savings:** ~40% of Phase 2 cost.
**Effort:** Config change.
**Risk:** Translation quality is the core value proposition. Sonnet produces notably fewer `[SC]` markers and weaker idiomatic Dutch. Could be viable for simple narration-heavy content (single-speaker documentaries).

---

## 6. Recommended Implementation Order

| Priority | Change | Savings (Scenario A) | Effort |
|---|---|---|---|
| **0** | **Check actual API billing** | Validates entire analysis | Dashboard check |
| 1 | Verify prompt caching status | Up to 80-90% of input if not cached | Investigation |
| 2 | Batch size 100 → 200 | ~$13 (~27%) | 1 line + quality test |
| 3 | Split post-processing | ~$3 (~6%) | Script edit |
| 4 | Eliminate duplicate reads | ~$1 (~2%) | Workflow edit |
| 5 | Trim documentary exemplar | ~$1.35 (documentary only) | 1 hour |
| 6 | Condense shared-constraints | ~$1 (~2%) | 1-2 hours |

**Without caching:** Items 2-4 combined save ~$17 of $49 = **~35%**.
**With full prefix caching already active:** The base cost may already be ~$10-15, and items 2-4 would save ~$3-5 of that.

---

## 7. Key Unknowns

1. **Actual billing data** — This entire analysis is a theoretical model. One real invoice or API usage dashboard would validate or invalidate every estimate instantly. This should be the first thing checked.

2. **Prompt caching behavior in headless mode** — Does `claude -p` get automatic prefix caching? If yes, the cumulative context problem is largely mitigated. If not, it's the dominant cost driver and worth investigating how to enable it.

3. **Quality cost of optimizations** — Several mitigations (larger batches, trimmed exemplars, Sonnet for translation) trade quality for cost. This analysis doesn't establish what a quality regression costs — in rework time, in having to re-run at full price, or in user dissatisfaction. A batch-200 test that degrades `[SC]` accuracy would require re-running as batch-100, doubling the cost.

4. **Actual turn count** — The estimates assume ~6 tool calls per batch. The real number depends on whether the model parallelizes some calls (e.g., write + validate in one turn) or adds extra calls (e.g., multiple Edit passes for grammar fixes). Real-world logging would sharpen these numbers.

5. **Context compression** — Claude Code may compress older conversation turns when approaching context limits. If active in headless mode, this would reduce the cumulative growth problem but at the cost of potential information loss in earlier batches.
