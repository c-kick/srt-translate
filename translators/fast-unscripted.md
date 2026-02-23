# Fast Unscripted Translator

For: panel shows, talk shows, news discussions, live events, reality TV.

---

## Validation

```bash
python3 scripts/validate_srt.py file.nl.srt --verbose
```

---

## Script Merge Parameters

Merging is handled by `scripts/auto_merge_cues.py` in Phase 4.

| Parameter | Value |
|-----------|-------|
| `--gap-threshold` | 500ms |
| `--max-duration` | 6000ms |
| Target ratio | 50-65% |

You do not merge during translation. Translate 1:1, then review after script merge.

```bash
python3 scripts/auto_merge_cues.py draft.nl.srt \
  --gap-threshold 500 \
  --max-duration 6000 \
  --output merged.nl.srt \
  --report merge_report.json
```

**Note:** Fast speech means many short source cues. Aggressive merging required.

---

## Style Rules

### Multi-Speaker Handling

**2 speakers in one cue (standard):**
```
Waar denk je aan?
-Aan vanavond.
```
- Line 1: Speaker 1 (no dash)
- Line 2: `-` + Speaker 2 (dash, no space)

**3 speakers in one cue (fast dialogue exception):**
```
Hallo, hoe gaat het? -Het gaat goed
-Had je het tegen mij?
```
- Line 1: Speaker 1 + ` -` + Speaker 2 (dash without space before Speaker 2's text)
- Line 2: `-` + Speaker 3 (dash, no space)

**When to use 3-speaker format:**
- Panel shows with rapid crosstalk
- Quick back-and-forth acknowledgments
- All three utterances are short (combined line 1 <50 chars)

**When NOT to use 3-speaker:**
- If any speaker has >25 chars of text
- If timing allows separate cues
- If speaker attribution would be confusing

### Filler Removal — Aggressive

Remove without hesitation:
- "Um", "uh", "er"
- "You know"
- "I mean"
- "Like" (filler)
- "So" (sentence starter)
- "Well" (hedging)
- "Basically"
- "Actually" (unless contrastive)

### Incomplete Sentences

Acceptable in fast speech:
```
EN: "I think that— no, wait, what I mean is—"
NL: "Ik denk dat... nee, ik bedoel..."
```

### Overlap Handling

When speakers overlap:
1. Prioritize main speaker
2. Interrupt marker: "—" (em dash)
3. If both essential, split to separate cues

```
EN: [overlapping] "But the economy—" "No, listen—"
NL: "Maar de economie—"
    (next cue)
    "Nee, luister—"
```

---

## Common Patterns

### Panel Show Interjections

| English | Dutch |
|---------|-------|
| "Right" | "Precies" / "Ja" |
| "Exactly" | "Precies" |
| "Absolutely" | "Absoluut" |
| "Of course" | "Natuurlijk" |
| "I agree" | "Eens" |
| "Good point" | "Goed punt" |

Often omittable if visually clear (nodding).

### Questions in Discussion

| English | Dutch |
|---------|-------|
| "Don't you think?" | Often omit |
| "Right?" (tag) | Often omit |
| "You know?" (tag) | Omit |
| "Am I wrong?" | "Of niet?" |

### Quick Responses

| English | Dutch |
|---------|-------|
| "Yeah" | "Ja" |
| "No" | "Nee" |
| "Maybe" | "Misschien" |
| "I don't know" | "Weet ik niet" |
| "Who knows" | "Wie weet" |

---

## Timing Priorities

1. **Clarity over completeness** — viewer must follow who said what
2. **Main point over elaboration** — cut rambling
3. **Current speaker over interruptions** — unless interruption is the point
4. **Short cues** — max 6000ms, target 3-4 seconds

---

## Dialogue Rules

- First speaker: no dash (ever)
- Second speaker: dash, no space (`-`)
- Third speaker (same cue): first line dash without space (` -`), second line dash no space (`-`)
- Contractions: use liberally
- Informal register default
- Sentence fragments: acceptable

---

## Gold-Standard Exemplars

Before translating, study these reference files from professional NL broadcast subtitles:

| File | Focus |
|------|-------|
| `references/exemplars/documentary.md` | Interview cleanup, filler removal (modern doc section especially relevant) |
| `references/exemplars/condensation.md` | Merge patterns, strong condensation, what to cut |
| `references/exemplars/dual-speaker.md` | Multi-speaker cue construction |
| `references/exemplars/idiom-adaptation.md` | English expression → Dutch equivalent |
| `references/exemplars/v2-word-order.md` | V2 inversion after fronted elements |

---

## Quality Checklist

- [ ] Filler aggressively removed?
- [ ] Speaker attribution clear?
- [ ] 3-speaker format used correctly (when applicable)?
- [ ] Overlaps handled cleanly?
- [ ] Rambling condensed?
- [ ] Main points preserved?
- [ ] d/t/dt verb endings correct?
- [ ] de/het articles correct?
- [ ] V2 word order after fronted elements?
- [ ] Subordinate clause word order (verb-final)?
- [ ] No English syntax calques?
