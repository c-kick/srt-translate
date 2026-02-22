# Comedy Translator

For: comedies, sitcoms, parodies, stand-up specials, films with comedic timing.

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
| `--gap-threshold` | 800ms |
| `--max-duration` | 6000ms |
| Target ratio | 55-70% |

You do not merge during translation. Translate 1:1, then review after script merge.

```bash
python3 scripts/auto_merge_cues.py draft.nl.srt \
  --gap-threshold 800 \
  --max-duration 6000 \
  --output merged.nl.srt \
  --report merge_report.json
```

**Note:** Comedy benefits from aggressive merging to maintain timing.

---

## Style Rules

### The Timing Rule

**Shorter = funnier.** Comedy timing depends on brevity.

```
EN: "Is this what you do with your spare time?"
Bad: "Is dit wat je doet in je vrije tijd?"
Good: "Is dit je hobby?"
```

### Rapid-Fire Collapse

Multiple quick interjections → single essential message:

```
EN: "No, no, Spengie! Hold it, Ray! Hit it!"
Bad: "Nee, Spengie. Vasthouden, Ray. Activeren."
Good: "Zet 'm open."
```

### Insults — Single-Word Punches

| English | Dutch |
|---------|-------|
| fatso | dikzak / vetklep |
| moron | sukkel / eikel |
| idiot | idioot / klojo |
| jerk | lul / eikel |
| slimeball | slijmbal |
| weirdo | engerd |

### Colorful Vocabulary

| English | Dutch (colloquial) |
|---------|---------------------|
| gross | smerig / goor |
| disgusting | walgelijk |
| awesome | gaaf / vet |
| cool | cool / tof |
| crazy | gestoord / gek |
| drunk | lam / bezopen |

### Puns and Wordplay

When English uses wordplay, seek Dutch equivalent:

```
EN: "He was borderline... then he crossed the border"
NL: "Hij was van slag... toen is hij doorgeslagen"

EN: "The cows? They found it very moo-ving"
NL: "De koeien? Die vonden het erg boee-iend"
```

If no Dutch pun exists, prioritize the joke's spirit over literal meaning.

---

## Common Patterns

### Exclamations → Brevity

| English | Dutch |
|---------|-------|
| "Oh my God!" | "Jezus." |
| "What the hell?" | "Wat krijgen we nou?" |
| "Are you kidding me?" | "Meen je dat?" |
| "No way!" | "Niet waar." |

### Sarcasm
Preserve through word choice, not punctuation:

```
EN: "Oh, that's just great."
NL: "Nou, geweldig." (not "Geweldig!")
```

### Running Gags
Track recurring jokes and use consistent Dutch equivalents throughout.

### Sound Effects / Reactions
Keep short:

| English | Dutch |
|---------|-------|
| "Ugh" | "Bah" |
| "Eww" | "Ieuw" / "Getver" |
| "Ouch" | "Au" |
| "Whoa" | "Wow" |

---

## Dialogue Rules

- Second speaker dash only (same as drama)
- Contractions: m'n and z'n only (see dutch-patterns.md)
- Informal register unless character is formal

---

## Gold-Standard Exemplars

Before translating, study these reference files from professional NL broadcast subtitles:

| File | Focus |
|------|-------|
| `references/exemplars/drama.md` | Character voice, register, emotional scenes (applicable to comedy character work) |
| `references/exemplars/condensation.md` | Merge patterns, strong condensation, what to cut |
| `references/exemplars/dual-speaker.md` | Multi-speaker cue construction |
| `references/exemplars/idiom-adaptation.md` | English expression → Dutch equivalent |
| `references/exemplars/v2-word-order.md` | V2 inversion after fronted elements |

---

## Quality Checklist

- [ ] Punchlines short and snappy?
- [ ] Rapid-fire collapsed to essentials?
- [ ] Insults punchy (single words)?
- [ ] Puns adapted (not literally translated)?
- [ ] Running gags consistent?
- [ ] No exclamation marks?
- [ ] d/t/dt verb endings correct?
- [ ] de/het articles correct?
- [ ] V2 word order after fronted elements?
- [ ] Subordinate clause word order (verb-final)?
- [ ] No English syntax calques?
