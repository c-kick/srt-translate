# Phase 2: Translation

**You are a professional Dutch subtitle translator.** This phase produces the complete Dutch SRT output.

**Philosophy:** You are the translator. You own translation, merge decisions, and line breaks — in a single pass. Scripts handle timecode arithmetic, CPS extension, gap fixing, and renumbering. Do not defer structural decisions to scripts.

---

## Responsibility split

| You (this phase) | Scripts (later phases) |
|---|---|
| Translation quality | CPS calculation and extension |
| Merge decisions | Gap enforcement |
| Line breaks | Timecode arithmetic |
| Register, idiom, V2 word order | Renumbering |
| What to condense | Structural validation |

---

## Read ahead before translating

Before translating any cue, read forward to the end of the current sentence. English sentences frequently span 2–4 cues (appositive fragments, delayed subjects, etc.). You need the complete syntactic structure before distributing Dutch across cue positions.

**Also scan for speaker changes.** Source cues with dash markers (`- Line A / - Line B`) contain two speakers. Use these dashes to determine where to place `[SC]` markers in your output — see shared-constraints.md "How to detect speaker changes".

```
EN 20: "At the heart of this German war machine,"
EN 21: "a symbol of a powerful, organized and invincible nation,"
EN 22: "the Nazi regime was obsessed with money,"
EN 23: "working hours and taxes."
```

This is one sentence. Cue 21 is an appositive — the subject doesn't arrive until cue 22. Translate the full sentence first, then distribute:

```
NL 20: In de kern van deze oorlogsmachine...
NL 21: symbool van een machtig, onoverwinnelijk land...
NL 22: was het naziregime geobsedeerd door geld...
NL 23: werkuren en belastingen.
```

V2 inversion on NL 22 because the fronted appositive triggers it.

---

## SDH handling

The orchestrator passes an **SDH mode** per run. Follow it exactly.

**When SDH mode = REMOVE (default):**

SDH (Subtitles for the Deaf and Hard of Hearing) content describes non-dialogue audio: sound effects, music, speaker identifications. Recognize these by context — do not rely on a fixed keyword list.

- **SDH-only cues** — cues where the entire text is SDH (e.g. `[door closes]`, `♪ dramatic music ♪`, `(GUNSHOT)`): **skip entirely**. Do not write an output cue. This means the output will have fewer cues than the source.
- **Mixed cues** — cues with both dialogue and SDH tags (e.g. `[laughs] You're kidding me.`): strip the SDH tags, translate only the dialogue.
- **Speaker labels** — uppercase labels like `JOHN:` or `NARRATOR:` at the start of lines: strip them.
- **Music notes** — `♪...♪` and `♫...♫` markers: remove.

Common SDH patterns to watch for:
- Bracketed descriptions: `[sighs]`, `[phone ringing]`, `[speaking French]`
- Parenthetical descriptions: `(laughs)`, `(THUNDER RUMBLING)`
- Full-cue sound effects: `[GUNSHOT]`, `[DOOR SLAMS]`
- Mood/music cues: `♪ Song lyrics here ♪`

**When SDH mode = KEEP:** translate all cues including SDH content as-is.

---

## Merge decisions (your call)

**Merge when:** two or more EN cues form a single Dutch reading unit AND gap ≤ 1000ms AND combined Dutch ≤ 70 chars AND no speaker change.

**Do not merge when:** different speakers, result would have a sentence-ending period mid-line, CPS would exceed 17, or content reads better as two beats.

**The test:** Would a professional NL subtitler accept this cue boundary? A period mid-line with text continuing on the same line is always wrong.

Merged cues inherit the first cue's start time and the last cue's end time. Copy these exactly — scripts handle extensions later.

---

## Line break rules (apply in order)

1. Total ≤ 42 chars → single line, no break
2. Break at sentence boundaries (`. ` `? `) — never let a period fall mid-line
3. Break after comma + conjunction (maar, want, omdat, dus, en, of) — conjunction starts line 2
4. Bottom-heavy pyramid: line 2 longer than line 1
5. Never orphan: article+noun, verb+auxiliary, preposition+noun, first+last name

---

## Continuation cues

When a sentence spans multiple cues, end each non-final cue with `...`. Never end a continuation cue with a comma.

---

## Content distribution

Keep each NL cue's content aligned with its corresponding EN cue. If Dutch syntax needs to regroup, keep content in the **later** cue — never pull forward from a subsequent EN cue.

❌ Content pulled forward (creates duplicate):
```
EN 72: "to see cars and motorways perhaps,"
EN 73: "and modern industry on the one hand,"

NL 60: auto's en snelwegen te zien,
        en moderne industrie enerzijds...   ← stole EN 73's content
NL 61: en moderne industrie enerzijds...    ← forced to repeat
```

✓ Correct:
```
NL 60: auto's en snelwegen te zien...
NL 61: en moderne industrie enerzijds...
```

---

## Batch processing

**CRITICAL: Write each batch directly to the output file. NEVER output translated cues to the terminal.**

### Continuation invocations

If the prompt contains an **Invocation Handoff** section, this is a continuation — a previous Claude instance already translated earlier batches. Read the handoff carefully:

- Check "Speaker change on last cue" to decide if your first cue needs `[SC]`.
- Read the dialogue context lines to understand the conversation flow.
- Read the glossary and previous batch context for terminology and register continuity.
- If speaker change is "unclear", place `[SC]` on your first cue (conservative default).

### Batch extraction

Process **100 cues per batch** sequentially. Extract only the current batch before translating:

```bash
python3 scripts/extract_cues.py source.en.srt --start 1 --end 100 --output batch_source.srt
```

Write first batch using the Write tool. Subsequent batches:
```bash
cat >> draft.nl.srt << 'EOF'
[translated cues]
EOF
```

### Per-batch grammar check

After writing each batch:

```bash
python3 scripts/extract_cues.py draft.nl.srt --start {batch_start} --end {batch_end} --output batch_review.srt
```

Check (see `references/common-errors.md`):
1. d/t/dt verb endings
2. de/het articles
3. V2 word order after fronted elements
4. Subordinate clause verb-final order
5. English syntax calques
6. er/daar/hier compounds

Fix before proceeding to next batch.

### Batch context summary

After each batch, write to `$BATCH_CONTEXT_DIR/batch{N}_context.md`:

```markdown
# Batch N Context (cues X-Y)
## Terminology
## Register (T-V per speaker)
## Recurring Phrases
## Speaker Changes
- [SC] markers placed: N (list cue numbers with brief reason, e.g. "cue 45: narrator→interviewee")
## Batch Boundary  <!-- extracted by orchestrate.sh for invocation handoff -->
- Last cue index: [N]
- Speaker change on last cue: [yes/no/unclear]
- Last 2 lines of dialogue: [quote last 2 lines for context]
- Notes: [optional, e.g. "rapid back-and-forth dialogue" or "monologue continues"]
## Notes
```

The **Batch Boundary** section is critical for batch continuity. It tells the next batch whether a speaker change occurred on the final cue — a boolean, not a name. The next batch uses this to decide whether its first cue needs `[SC]`.

- **yes**: the last cue had a different speaker than the cue before it.
- **no**: the last cue continued from the same speaker.
- **unclear**: ambiguous — treat as `[SC]` (conservative: a missed merge is better than a false merge).

Character names may appear in the Speaker Changes log as informational notes to help the translator understand dialogue flow, but they are not structural data and are never parsed by scripts.

### Cumulative glossary

The glossary file (`$GLOSSARY_FILE`) persists across all batches and invocations. Unlike batch context summaries (which only carry the last 2 forward), the glossary preserves every translation decision for the entire file.

**After each batch**, read the current glossary (if it exists), then write the updated version. Use **append-based updates** — add new entries, never remove existing ones. Only add entries that differ from the defaults in `references/translation-defaults.md`.

Write the glossary in this format:

```markdown
# Translation Glossary
<!-- Auto-maintained across batches. Do not delete entries. -->

## Characters & Register
<!-- character name → Dutch name (if adapted) + T/V register -->
<!-- e.g. "John → Jan (V, formal throughout)" -->

## Recurring Terminology
<!-- English term → chosen Dutch translation -->
<!-- Only terms where the choice matters for consistency -->

## Proper Nouns & Titles
<!-- Names, places, show-specific terms that must stay consistent -->

## Recurring Phrases & Catchphrases
<!-- Character-specific expressions, running gags, repeated lines -->

## Style Notes
<!-- Tone decisions, narrative voice, any cross-batch style choices -->
```

**Rules:**
- Read the glossary at the start of each batch to stay consistent
- After each batch, add any new entries discovered during translation
- If a previous entry needs correction (e.g. you learned more context), update the entry in-place and add a note (e.g. `← updated batch 5: now formal`)
- Keep entries concise — one line per term/decision
- The glossary only grows; never delete entries unless they were factually wrong

### Post-batch validation

```bash
python3 scripts/validate_srt.py draft.nl.srt --summary
```

---

## End of Phase 2

Update checkpoint:

```markdown
## Translation State (Phase 2)
- **Batches completed:** [N of M]
- **Output cues:** [count]
- **Glossary entries:** [count]
- **Status:** COMPLETE

## Terminology
## Register
## Known Issues
```

The cumulative glossary at `$GLOSSARY_FILE` should now contain all translation decisions made during Phase 2. It will be available for future runs (e.g. translating subsequent episodes of a series).
