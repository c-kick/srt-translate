# Translation Defaults Reference

Detailed rules for continuity, dual speakers, line treatment, and condensation.
Loaded by the translator when needed. Summary in SKILL.md, full details here.

---

## Continuity

- When including ellipses in subtitles, please use three dots/periods in a row.
- When an ongoing sentence is split between two or more continuous subtitles, use an ellipsis at the **end** of the first subtitle. Do **not** use an ellipsis at the start of the continuation subtitle (Auteursbond: "uitlooppuntjes" only, no "inpunten").
- **Never end a continuation cue with a comma.** If a cue ends mid-sentence (the sentence continues in the next cue), replace the comma with `...`. The ellipsis signals continuation to the viewer AND enables clean merging by `auto_merge_cues.py` (which strips `...` at merge boundaries).
	```
	❌  In de jaren dertig,            (comma = ambiguous)
	    werd alles anders.

	✓   In de jaren dertig...          (ellipsis = clear continuation)
	    werd alles anders.

	✓   Ik heb altijd geweten...
	    dat je uiteindelijk zou instemmen.
	```
- Use an ellipsis to indicate a pause (2 seconds or more) or if dialogue trails off. If the sentence continues in the next subtitle, do not use an ellipsis at the beginning of the second subtitle. Example:
	```
	Subtitle 1   Had ik het geweten...
	[pause]
	Subtitle 2   Dan had ik je niet gebeld.
	```
- Use two hyphens to indicate an abrupt interruption by an action, sound or other speaker. In the case of a change of thought or trail-off by the same speaker, use ellipses. Example:
	```
	What are you--
	- Be quiet!
	```
- Use ellipses followed by a space when there is a significant pause or hesitation within a subtitle. Example:
	```
	Ze aarzelde... over die baan.
	```
- Only use an ellipsis without a space at the start of a subtitle to indicate that a subtitle is starting mid-sentence (e.g. joining a broadcast already in progress). Example:
	```
	...een akkoord hebben getekend.
	```

---

## Dual Speakers

- **CRITICAL: The first line of a cue should NEVER start with a dash.** Dashes are only used for the second speaker.
- **Merge control markers:** When translating, assess if each cue's speaker differs from the previous cue and prefix accordingly:
  - **Confident same speaker** → no marker (cues may be merged)
  - **Confident different speaker** → prefix with `[SC]` (merged with dash formatting)
  - **Uncertain** → prefix with `[NM]` (cues will not be merged)

  Err on the side of `[NM]` when unsure. An unmerged cue is fine; an incorrectly merged dual-speaker cue is a visible error. Markers are stripped from the final output.

  Example:
  ```
  5
  00:00:10,000 --> 00:00:11,500
  Nee, nog niet.

  6
  00:00:11,600 --> 00:00:13,000
  [SC] Ze hebben haast.
  ```
  After merging becomes:
  ```
  5
  00:00:10,000 --> 00:00:13,000
  Nee, nog niet.
  - Ze hebben haast.
  ```
- Use a hyphen with a space to indicate the second speaker in a dual-speaker subtitle. Example:
	```
	Kom je mee?
	- Over een minuut.
	```
- Single-speaker cues never have dashes, even when indicating a new speaker from the previous cue.
- Text in each line in a dual speaker subtitle must be a contained sentence and should not carry into the preceding or subsequent subtitle. Creating shorter sentences and timing appropriately helps to accommodate this.

### ABBA Avoidance

Never interleave speakers across consecutive cues (A-B-B-A pattern). This confuses the viewer about who is speaking. Restructure dialogue to keep each speaker's content together.

Bad (ABBA):
```
A  Ga je mee een eindje wandelen?
B  -Ik denk het niet...

B  met zulk druilerig weer.
A  -Dat beetje regen...

A  daar ga je niet dood van.
B  -Ik ben pas ziek geweest.
```

Good (restructured):
```
A  Ga je mee een eindje wandelen?
B  -Niet met dit druilerige weer.

A  Van een beetje regen ga je niet dood.

B  Ik ben pas ziek geweest.
A  -Dan zal de buitenlucht je goed doen.
```

When restructuring to avoid ABBA: condense, rephrase, or redistribute text so each cue has at most one speaker change (line 1 → line 2), never across cues.

---

## Synchronicity

Match recognizable words to approximately the same position in the subtitle where they appear in speech. Even viewers who don't understand the source language will hear names, "yes", "no", cities, organizations, and emotionally stressed words. If such a word appears early in the spoken line, place it early in the subtitle too.

- Preserve the order of enumerations
- If splitting a sentence across two cues, ensure the translation in each cue corresponds to what is being said at that moment — not a loose paraphrase that front-loads or delays content

Good synchronicity prevents the jarring effect of hearing a name while reading something unrelated.

---

## Line Treatment

- Maximum two lines.
- Text should usually be kept to one line, unless it exceeds the character limitation.
- If two short sentences of roughly equal length don't fit on one line, put each on its own line.
- If two short sentences DO fit on one line, keep them on one line — unless they address different people or are thematically unrelated.
- Prefer a bottom-heavy pyramid shape for subtitles when multiple line break options present themselves, but avoid having just one or two words on the top line.
- **Top-line-first reading:** Research shows viewers read line 1 first, glance at the image, then read line 2. Break at a natural pause on line 1 so the viewer gets a complete thought before looking up.
- Follow these basic principles when the text has to be broken into 2 lines:
- The line should be broken:
	- after punctuation marks
	- before conjunctions
	- before prepositions
- The line break should not separate
	- a noun from an article
	- a noun from an adjective
	- a first name from a last name
	- a verb from a subject pronoun
	- a prepositional verb from its preposition
	- a verb from an auxiliary, reflexive pronoun or negation

---

## Timestamp Preservation

- Preserve original start times (exception: merged cues inherit first cue's start)
- End times may be extended for CPS compliance (aim for CPS ≤17), but must never result in overlapping cues

---

## Condensation Guidelines

### Philosophy: Maximize Time, Minimize Cues

**Goal:** Create a tranquil viewing experience with low-CPS subtitles that use the full available display time and character budget.

Prefer **one 80-character cue at CPS 13** over **two 40-character cues at CPS 16**. Fewer cues with comfortable reading speed beats more cues with rushed reading.

The math:
- CPS 12 with 84 characters = **7 seconds** display time (relaxed)
- CPS 17 with 60 characters = **3.5 seconds** display time (rushed)

### Think in Sentences, Not Cues

Before condensing, understand the complete thought:
- Read ahead to sentence boundaries (`.!?`)
- Understand the full semantic content across multiple cues
- Then decide how to package it efficiently

A sentence split across 3 fast cues can often become 1-2 comfortable cues:
- Source: 3 cues × ~25 chars × 1.5s each = choppy reading
- Better: 1 cue × 75 chars × 6s = relaxed reading at CPS 12.5

This enables restructuring that cue-by-cue translation cannot achieve.

### Time Budget Principle

For each subtitle position, calculate your budget:
- **Available time** = gap until next speech event (minus 125ms minimum gap)
- **Character budget** = available_time × target CPS

| Available time | CPS 12 (comfortable) | CPS 17 (ceiling) |
|----------------|----------------------|------------------|
| 3 seconds | 36 chars | 51 chars |
| 5 seconds | 60 chars | 85 chars |
| 7 seconds | 84 chars | 119 chars* |

*Capped at 84 chars (2 lines × 42) regardless of time available.

**Use the full budget.** If you have 5 seconds and 40 characters, you're at CPS 8 - extend or merge with adjacent content.

---

### Condensation Priority Order

When reducing subtitle length, apply in this order:

**1. Merge adjacent cues** (no content loss, most effective):
   - Gap ≤1000ms between consecutive cues
   - Combined result ≤2 lines, ≤42 chars/line
   - Same speaker (or format as dual-speaker if different)
   - **Always merge** if combined fits in 84 chars - don't leave short orphan cues
   - Extended duration naturally lowers CPS

**2. Extend end time** (script-handled):
   - If gap to next cue allows extension, extend to reach CPS 12
   - Respect minimum gap (125ms)
   - Minimum CPS after extension: 12 (don't display text too long)

**3. Delete filler** (preserves audio sync):
   - Fillers: "eh", "nou", "zeg maar", "weet je", "hè"
   - Discourse markers: "nou ja", "dus", "eigenlijk", "gewoon", "best wel"
   - Redundant intensifiers: "echt", "heel", "zeer", "behoorlijk"
   - Hedges: "een beetje", "zoiets", "min of meer", "ongeveer"
   - Repetitions and false starts
   - Sentence-initial "en" when it adds nothing

**4. Compress phrases** (same meaning, fewer words):
   - "op dit moment" → "nu"
   - "in verband met" → "door" / "wegens"
   - "het feit dat" → "dat"
   - "een groot aantal" → "veel"
   - "in de richting van" → "naar"
   - "met betrekking tot" → "over"
   - "ten behoeve van" → "voor"

**5. Rephrase** (when deletion insufficient):
   - Use pronouns if referent clear from context
   - Combine clauses
   - Restructure for Dutch efficiency

---

### Sentence-Aware Condensation

When condensing a multi-cue sentence:

1. **Combine** source cues mentally to see the complete thought
2. **Translate** the complete sentence naturally
3. **Condense** at the sentence level (not cue-by-cue)
4. **Segment** into ≤84-char chunks only if needed

Example - source spans 3 cues:
```
Cue 1: "I told him that we"
Cue 2: "would be arriving"
Cue 3: "sometime tomorrow morning."
```

❌ Cue-by-cue (preserves fragmentation):
```
Cue 1: "Ik zei hem dat we"
Cue 2: "zouden aankomen"
Cue 3: "ergens morgenochtend."
```

✓ Sentence-aware (optimal packaging):
```
Cue 1: "Ik zei dat we morgenochtend aankomen."
```
One cue, 40 chars, uses full available time at comfortable CPS.

---

**Never delete meaning-critical elements**: negations, quantifiers that change meaning, names on first mention, commitment verbs (deny, confirm, refuse → ontkennen, bevestigen, weigeren).
