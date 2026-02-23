# Drama Translator

For: narrative films, TV dramas, thrillers, character-driven stories.

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
| `--gap-threshold` | 1000ms |
| `--max-duration` | 7000ms (25fps) / 7007ms (24fps) |
| Target ratio | 60-75% |

You do not merge during translation. Translate 1:1, then review after script merge.

```bash
python3 scripts/auto_merge_cues.py draft.nl.srt \
  --gap-threshold 1000 \
  --max-duration 7000 \
  --output merged.nl.srt \
  --report merge_report.json
```

---

## Style Rules

### Register
- Match character's voice
- Maintain consistency per character
- Track T-V (je/u) per relationship

| Relationship | Register |
|--------------|----------|
| Friends | je/jij |
| Strangers (initial) | often u |
| Boss-employee | varies by scene |
| Parent-child | usually je |
| Formal settings | u |

### Contractions
Only two contractions are standard in subtitles (Auteursbond). See `references/dutch-patterns.md` for full rules.

| Full | Contraction | Use |
|------|-------------|-----|
| mijn | m'n | informal speech (unstressed) |
| zijn (possessive) | z'n | informal speech (unstressed) |

**Avoid** `'t`, `'s`, `d'r`, `'m`, `'n` — use full forms instead. Exception: set phrases like "'s ochtends", "'s avonds".

### Emotion
- Preserve intensity without exclamation marks
- Viewers hear emphasis, don't write it
- Use word choice and structure for emotion

```
EN: "Get out!"
NL: "Eruit." (not "Eruit!")
```

### Dialogue Rules
- Second speaker dash only (no space after dash):
  ```
  Waar ga je heen?
  -Naar huis.
  ```
- Never both lines with dashes
- Single quotes for quotations: `'Zo gaat dat hier.'`

---

## Common Patterns

### Direct Dutch
Convert rhetoric to direct statements:

| English | Dutch |
|---------|-------|
| "Don't you think we should...?" | "We moeten..." |
| "What do you think I am?" | "Ben ik soms...?" |
| "Isn't that cutting it close?" | "Dat is kort dag." |

### Idioms

| English | Dutch |
|---------|-------|
| couldn't believe it | geloofde z'n oren niet |
| go to hell | bekijk het maar |
| crossed the line | doorgeslagen |
| give me a hand | help 's even |

### Filler Removal
Drop unless emotionally significant:
- "Well, ..." → usually omit
- "You know, ..." → usually omit
- "I mean, ..." → usually omit

---

## Gold-Standard Exemplars

Before translating, study these reference files from professional NL broadcast subtitles:

| File | Focus | Source |
|------|-------|--------|
| `references/exemplars/drama.md` | Character voice, register, emotional scenes, idiom adaptation | The Remains of the Day (1993) |
| `references/exemplars/condensation.md` | Merge patterns, strong condensation, what to cut | Cross-genre |
| `references/exemplars/dual-speaker.md` | Multi-speaker cue construction | The Remains of the Day (1993) |
| `references/exemplars/idiom-adaptation.md` | English expression → Dutch equivalent | Cross-genre |
| `references/exemplars/v2-word-order.md` | V2 inversion after fronted elements | Cross-genre |

Each exemplar shows: EN source → NL translation → WHY (the reasoning).
The WHY annotations teach the translation philosophy, not just the output.

---

## Quality Checklist

- [ ] Character voices consistent?
- [ ] T-V register tracked per relationship?
- [ ] Contractions natural in dialogue?
- [ ] No exclamation marks?
- [ ] Speaker dashes correct (second only)?
- [ ] Idioms adapted, not translated?
- [ ] d/t/dt verb endings correct?
- [ ] de/het articles correct?
- [ ] V2 word order after fronted elements?
- [ ] Subordinate clause word order (verb-final)?
- [ ] No English syntax calques?
