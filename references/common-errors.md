# Common Errors Reference

## Anglicism Patterns to Avoid

| Anglicism | Correct Dutch |
|-----------|---------------|
| "Ik denk het niet" | "Ik denk van niet" |
| "Het maakt geen zin" | "Het slaat nergens op" / "Het heeft geen zin" |
| "In de eerste plaats" (as filler) | Often omit or restructure |
| "Aan het einde van de dag" | "Uiteindelijk" / "Per slot van rekening" |
| "Ik ben geëxciteerd" | "Ik heb er zin in" / "Ik kijk ernaar uit" |
| "Dat is cool" | "Dat is gaaf" / "Vet" (or keep "cool" if character would say it) |

---

## False Friends

| English | Looks like | Actually means in Dutch |
|---------|-----------|------------------------|
| actual | actueel | current, up-to-date |
| eventually | eventueel | possibly, optionally |
| brave | braaf | well-behaved, obedient |
| sympathetic | sympathiek | likeable, nice |
| sensible | sensibel | sensitive |
| consequent | consequent | consistent |
| fabric | fabriek | factory |

---

## Common Grammar Mistakes

### de/het Confusion
Common errors:
- ~~de meisje~~ → het meisje
- ~~de huis~~ → het huis
- ~~de probleem~~ → het probleem

**When unsure, verify with dictionary.** Common het-words: het meisje, het huis, het probleem, het kind, het boek.

### d/t/dt Endings
| Subject | Verb stem ends in -d | Example |
|---------|---------------------|---------|
| ik | -d | ik word |
| jij/je | -dt (inverted: -d) | jij wordt / word jij |
| hij/zij/het | -dt | hij wordt |
| wij/jullie/zij | -den | wij worden |

Common error: ~~hij word~~ → hij wordt

### Word Order (V2 Rule)
Dutch requires the finite verb in second position:
- ~~Ik vandaag ga~~ → Ik ga vandaag
- ~~Morgen ik kom~~ → Morgen kom ik

---

## 3-Line Violation Prevention

### Why It Happens
- Over-merging cues without checking line count
- Not breaking long sentences properly
- Combining content that should stay separate

### How to Avoid

**Before writing each cue:**
```
Line count = newlines in text + 1
If > 2: STOP and restructure
```

**When merging would exceed 2 lines:**

Option A - Keep separate:
```
1
00:05:12,100 --> 00:05:13,900
De mannetjes schuifelen in groepen.

2
00:05:14,000 --> 00:05:16,800
Hun eieren nog op hun poten.
```

Option B - Condense to fit:
```
1
00:05:12,100 --> 00:05:16,800
De mannetjes schuifelen in groepen,
eieren nog op hun poten.
```

**Never create a 3-line cue. Split or condense instead.**

---

## Speaker Dash Errors

### Wrong (both lines have dashes):
```
- Waar ga je heen?
- Naar huis.
```

### Correct (only second speaker gets dash):
```
Waar ga je heen?
- Naar huis.
```

### Wrong (dash for single speaker):
Documentary interviews sometimes have dashes in source. Remove them for single-speaker segments.

---

## Punctuation Errors

| Error | Correct |
|-------|---------|
| Using `…` (single character) | Use `...` (three dots) |
| Using `"quote"` | Use `'quote'` (single quotes) |
| Exclamation marks | Omit (viewers hear emphasis) |
| Semicolons | Use period or restructure |

---

## Register Inconsistency

**Problem:** Switching between je and u for same character relationship.

**Solution:** Document register choices at start:
- Character A to B: je (informal)
- Character A to C: u (formal)
- Maintain throughout film

---

## Literal Translation Traps

| English | Literal (wrong) | Natural Dutch |
|---------|-----------------|---------------|
| "It's raining cats and dogs" | *Never* | "Het regent pijpenstelen" |
| "Break a leg" | *Never* | "Succes" / "Toi toi toi" |
| "Piece of cake" | *Never* | "Eitje" / "Makkie" |
| "Speak of the devil" | *Never* | "Als je het over de duivel hebt" |
