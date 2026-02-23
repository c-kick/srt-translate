# Documentary Translator

For: nature documentaries, historical documentaries, educational content, interview-driven films.

Familiarize yourself with the content. 
- If you recognize quotes, or fragments of speeches - try to find the source, in your knowledge or online, so you have the proper connotation/context for translation.
- If you recognize certain events, e.g. in historical documentaries, use this to make sure your choice of words is apt.
- Make sure you know the subject - you are the subject's specialist translator that was hand-picked for this particular translation job.
- Use subject-relevant technical jargon/terminology

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
| Target ratio | 70-85% |

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
- Formal: prefer "wij" over "we", "mij" over "me" in narration
- Interviews: match speaker's register
- Scientific: use proper Dutch terminology

### Vocabulary

| English | Dutch (documentary) |
|---------|---------------------|
| forage | foerageren |
| ice hole | wak |
| breeding | voortplanting |
| migration | trek |
| habitat | leefgebied |
| species | soort |
| climate | klimaat |
| expedition | expeditie |

### Military (WWII, modern conflicts)

| English | Dutch |
|---------|-------|
| troops | troepen |
| airborne | luchtlandingstroepen |
| infantry | infanterie |
| artillery | artillerie |
| headquarters | hoofdkwartier |
| general | generaal |
| lieutenant | luitenant |
| sergeant | sergeant |
| surrender | overgave |
| invasion | invasie |
| casualties | verliezen |
| counteroffensive | tegenoffensief (NOT "counteroffensief") |
| offensive | offensief |
| frontline | frontlinie |
| assault brigade | stormbrigade |
| platoon | peloton |
| battalion | bataljon |
| fortifications | fortificaties / versterkingen |
| shell shock | shellshock / oorlogsneurose |
| drone strike | droneaanval |
| minefield | mijnenveld |
| Allied Expeditionary Force | Geallieerde Strijdkrachten |

### Narration Style
- Complete, measured sentences
- Formal punctuation (no exclamation marks)
- Bottom-heavy pyramid for 2-line cues:
  ```
  Korte eerste regel
  en langere tweede regel hier.
  ```

### Interview Segments
- Preserve speaker rhythm
- Allow slightly informal register
- Contractions: m'n and z'n only (see `references/dutch-patterns.md`)
- Emotional content: preserve intensity

---

## Common Patterns

### Statistics
```
EN: "176,000 troops landed in the first 24 hours"
NL: "176.000 man landden in de eerste 24 uur"
```
Note: Dutch uses period for thousands, not comma.

### Dates
```
EN: "June 6, 1944"
NL: "6 juni 1944"
```

### Measurements
```
EN: "1.5 kilometers"
NL: "anderhalve kilometer"
```

---

## Gold-Standard Exemplars

Before translating, study these reference files from professional NL broadcast subtitles:

| File | Focus | Source |
|------|-------|--------|
| `references/exemplars/documentary.md` | Narration style, interview cleanup, military terminology, modern doc style | The World At War (1973), Milli Vanilli (2023) |
| `references/exemplars/condensation.md` | Merge patterns, strong condensation, what to cut | Cross-genre |
| `references/exemplars/idiom-adaptation.md` | English expression → Dutch equivalent | Cross-genre |
| `references/exemplars/v2-word-order.md` | V2 inversion after fronted elements | Cross-genre |

Each exemplar shows: EN source → NL translation → WHY (the reasoning).
The WHY annotations teach the translation philosophy, not just the output.

---

## Quality Checklist

- [ ] Narration: formal, complete sentences?
- [ ] Interviews: speaker rhythm preserved?
- [ ] Scientific terms: proper Dutch equivalents?
- [ ] Statistics: Dutch number formatting?
- [ ] Dates: Dutch date format?
- [ ] No exclamation marks in narration?
- [ ] d/t/dt verb endings correct?
- [ ] de/het articles correct?
- [ ] V2 word order after fronted elements?
- [ ] Subordinate clause word order (verb-final)?
- [ ] No English syntax calques?
