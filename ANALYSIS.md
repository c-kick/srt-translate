# Analysis: PocketSphinx Timing QC (TODO.md)

## Summary of the Issue

When Claude translates English subtitles to Dutch, it often redistributes content across cue boundaries — merging cues, splitting sentences, or rebalancing text for CPS/readability. The source timecodes are preserved, but the **semantic content** they now carry may not match the speech happening in that time window. Result: text appears 2-4 seconds ahead of or behind the spoken word.

## Current Pipeline State

### What Already Exists

| Component | What it does | Limitation |
|-----------|-------------|------------|
| `vad_timing_check.py` (Phase 9) | WebRTC VAD compares subtitle boundaries against speech/silence transitions | Only knows **when** speech happens, not **which words** are spoken when |
| `extend_to_speech_lite.py` (Phase 10) | Extends end times to match speech end via VAD | Same limitation — no word-level awareness |
| `sync_subtitles.py` (Phase 0) | ffsubsync aligns source SRT to audio | Operates on source only, before translation |
| `match_source_cues()` in vad_timing_check.py | Maps NL→EN cues by start-time proximity (500ms tolerance) | Breaks when translation redistributes content across different time windows |

### The Gap

The current system can detect "subtitle ends but speech continues" or "subtitle starts before speech." It **cannot** detect "this subtitle's content corresponds to speech happening 3 seconds away" because it has no word-level timestamp data.

## TODO.md Proposal Analysis

### Step 1: Forced-align English source (PocketSphinx)

**Assessment:** Feasible but with caveats.

- PocketSphinx is **not currently in the repo or requirements**. Would need to be added.
- PocketSphinx forced alignment is CPU-friendly (important: system is "CPU-only").
- Accuracy is mediocre compared to modern alternatives (Whisper, whisperX, vosk). PocketSphinx's acoustic models are older and struggle with background music, multiple speakers, accented speech, and noise.
- The TODO mentions "existing `forced_align.py`" but **no such file exists** in the repo.

**Alternatives considered:**
- **Whisper** (word-level timestamps via `--word_timestamps`): Most accurate, but extremely slow on CPU. A 100-minute video would take hours.
- **whisperX**: Even heavier (requires GPU).
- **Vosk**: CPU-friendly, supports word-level alignment, better models than PocketSphinx. Reasonable alternative.
- **Gentle**: Good forced aligner but heavy dependency.

**Recommendation:** PocketSphinx is the pragmatic choice given CPU-only constraint, but **vosk** should be considered as it has better accuracy with similar CPU requirements.

### Step 2: Build source word→timestamp index

**Assessment:** Straightforward once Step 1 works. Tokenize source SRT text, map each word to its aligned timestamp from the forced alignment output. Store as `{cue_id: [(word, start_ms, end_ms), ...]}`.

### Step 3: Semantic cue mapping (the hard part)

**Option A — Claude emits alignment hints during translation:**
```
# source: 171-172
106
00:10:32,860 --> 00:10:38,490
in het Rijnland bijvoorbeeld...
```

- **Pros:** Most accurate mapping possible. Claude knows exactly which source cues it drew content from.
- **Cons:** Requires modifying Phase 2 (workflow-translate.md), the translation output format, and adding a parser to strip hints. Increases token usage. Adds cognitive load to translation task. Risk of hallucinated/wrong source mappings.
- **Impact:** Changes to `workflow-translate.md`, `orchestrate.sh` (to pass format requirements), and a new parser/stripper script.

**Option B — Heuristic back-mapping:**
- **Pros:** No changes to translation workflow. Post-hoc, non-invasive.
- **Cons:** Unreliable when content is heavily redistributed. Dutch and English have very different word order. Content words may not translate transparently (idioms, condensation). Named entities and numbers are the only reliable anchors.
- **Accuracy estimate:** Likely 60-70% correct mapping for documentary content, worse for drama/comedy with idioms.

**Assessment:** Option A is architecturally cleaner but more invasive. Option B is simpler but fundamentally limited. A **hybrid approach** may work: use Option B as primary, with Option A as an enhancement for documentary/lecture content where redistribution is most aggressive.

### Step 4: Flag misaligned cues

**Assessment:** Straightforward given Steps 1-3. Compare each translated cue's time window against the word-level timestamps of the source content it's translating. Flag when no source words fall within the window.

The output format proposed (cue number, declared window, detected speech window, delta) is sensible and consistent with the existing `vad_timing_check.py` output format.

### Step 5: Optional auto-correct timecodes

**Assessment:** Risky. Auto-correcting timecodes could create cascading problems (overlaps, gap violations, CPS regressions). The constraints (80ms gaps, no overlap) help, but this should be conservative and opt-in. Better to flag and let Claude fix in a review pass.

## Open Questions Assessment

1. **"Does translation produce enough source→target overlap for Option B?"**
   - For documentary content: moderate overlap (same proper nouns, numbers). But documentary is exactly where redistribution is worst.
   - For drama: better overlap (shorter sentences, fewer merges), but idioms reduce it.
   - **Verdict:** Option B alone is insufficient for high-redistribution content.

2. **"Should alignment hints (Option A) be mandatory for documentary/lecture?"**
   - Yes, if implementing Option A at all. Documentary content has the most redistribution and would benefit most.

3. **"Is 500ms a reasonable threshold?"**
   - For word-level alignment, 500ms is too coarse. PocketSphinx accuracy itself is ~100-200ms. A threshold of 300-400ms would better distinguish real misalignment from alignment noise.
   - However, for the "cue content vs. time window" check, the window is the full cue duration (typically 1-7 seconds), so 500ms is fine as an edge tolerance.

## Feasibility Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| Technical feasibility | Medium | PocketSphinx forced alignment works but accuracy varies |
| Effort | High | New dependency, new scripts, workflow changes (Option A) |
| Value | Medium-High | Solves a real problem that existing Phase 9 can't catch |
| Risk | Medium | PocketSphinx accuracy on varied content; Option A increases translation complexity |
| Priority | Medium | Current Phase 9 VAD catches most gross timing issues; this addresses subtler semantic misalignment |

## Architecture Concerns

1. **Dependency weight:** PocketSphinx adds ~200MB of acoustic models. Vosk models are ~50MB for English.
2. **Processing time:** Forced alignment on CPU for a 100-minute video: PocketSphinx ~1-3 min, Vosk ~2-5 min. Acceptable.
3. **Pipeline integration:** Should be a new phase (Phase 9b or embedded in Phase 9) rather than replacing Phase 9. The existing VAD timing check remains valuable for different kinds of issues.
4. **Fallback:** The TODO mentions "character-proportional timing if alignment fails." This is a reasonable fallback but very approximate. Better to report "alignment failed" and skip QC.

## Files That Would Change

| File | Change |
|------|--------|
| `scripts/requirements.txt` | Add pocketsphinx (or vosk) |
| `scripts/setup.sh` | Install new dependency + download models |
| `scripts/forced_align.py` | **New:** Word-level forced alignment |
| `scripts/qc_timing.py` | **New:** Semantic timing QC (Steps 2-4) |
| `scripts/correct_timecodes.py` | **New, optional:** Auto-correction (Step 5) |
| `base/workflow-post.md` | Add new phase documentation |
| `base/workflow-translate.md` | Add alignment hints format (if Option A) |
| `scripts/orchestrate.sh` | Add new phase invocation |
| `SKILL.md` | Document new phase |
