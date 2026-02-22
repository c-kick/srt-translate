# TODO: PocketSphinx Timing QC

## Problem

When Claude redistributes content across cue boundaries during translation (for CPS/readability),
the timecodes from the source are preserved but may no longer match the speech content they now
carry. The misalignment is subtle — cue count stays consistent, starts/ends are technically valid,
but the text visible on screen is 2–4 seconds ahead of (or behind) the spoken word.

## Approach

Use forced alignment on the **English source audio** to derive word-level timestamps, then validate
whether each translated cue's timecode window contains the source words it is translating.

---

## Phase: Post-translation QC (new phase, after timecode merge)

### Step 1 — Forced-align English source

- Run PocketSphinx forced alignment on source audio + source SRT text
- Output: word-level timestamp map `{word: (start_ms, end_ms)}`
- Tool: existing `forced_align.py` or equivalent
- Input audio: English original (not translated)
- Fallback: character-proportional timing if alignment fails

### Step 2 — Build source word→timestamp index

- Tokenize each source cue's text into words
- Map each word to its aligned timestamp
- Store as lookup: `{cue_id: [(word, start_ms, end_ms), ...]}`

### Step 3 — Semantic cue mapping

This is the hard part. Two options:

**Option A (preferred): Claude emits alignment hints during translation**
- During translation phase, Claude outputs a comment per cue indicating which source cue(s)
  the Dutch text is derived from, e.g.:
  ```
  # source: 171-172
  106
  00:10:32,860 --> 00:10:38,490
  in het Rijnland bijvoorbeeld...
  ```
- Parser strips hints before final SRT output but uses them for QC

**Option B (fallback): heuristic back-mapping**
- For each translated cue, find its key nouns/content words in the source word index
- Look up their timestamps
- Flag if those timestamps fall outside the translated cue's window by >500ms

### Step 4 — Flag misaligned cues

Misalignment signal: no source words (from the content the cue is translating) fall within
the cue's declared time window.

Output: validation report listing flagged cues with:
- Cue number
- Declared window
- Detected speech window (from word timestamps)
- Delta

### Step 5 — Optional: auto-correct timecodes

If source cue mapping is unambiguous (Option A), reanchor the translated cue's timecodes
to the word-timestamp window of the source content it covers.

Constraints:
- Maintain minimum 80ms gaps between cues (2 frames @ 25fps)
- Do not extend cue beyond adjacent cue boundaries
- Log all corrections made

---

## Open questions

- Does the current translation phase produce enough source→target cue overlap to make
  Option B reliable, or does content shuffling make back-mapping too ambiguous?
- Should alignment hints (Option A) be a mandatory output format for documentary/lecture
  content where cue redistribution is common?
- Is 500ms a reasonable threshold for flagging, or should it be tighter?

---

## Files to create/modify

| File | Action |
|------|--------|
| `forced_align.py` | Extend to output word-level JSON, not just cue-level |
| `qc_timing.py` | New script: runs Steps 2–4, outputs validation report |
| `correct_timecodes.py` | New script (optional): applies Step 5 auto-corrections |
| `SKILL.md` | Add Option A alignment hint format to translation output spec |

---

## References

- Existing misalignment case: Fawlty Towers / documentary test — cues 102–108, ~00:10:18
- Netflix spec: minimum 2-frame gap (80ms @ 25fps)
- PocketSphinx integration: already in repo for fallback timing
