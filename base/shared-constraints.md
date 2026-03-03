# Shared Constraints

Universal rules for all phases. Injected into every pipeline invocation.

---

## Hard Constraints

Values depend on the source framerate. Determine framerate before starting.

<!-- BEGIN GENERATED CONSTRAINTS -->
| Constraint | 23.976 / 24 fps | 25 fps |
|---|---|---|
| CPS Optimal | 11 | 12 |
| CPS Hard Limit | 15 | 17 |
| CPS Emergency Maximum | 20 | 20 |
| Characters per line | 42 | 42 |
| Maximum cue duration | 7007ms | 7000ms |
| Minimum cue duration | 1400ms | 830ms |
| Minimum cue gap | 125ms (3 frames) | 120ms (3 frames) |
| Max words/min | 180 | 180 |
| Max lines per cue | 2 | 2 |
| CPS calculation | All characters (incl. spaces); `...` counts as 1 char | All characters (incl. spaces); `...` counts as 1 char |
| Merge lines shorter than | 40 chars | 40 chars |
<!-- END GENERATED CONSTRAINTS -->

---

## Content Accuracy

- Include as much original content as possible.
- Do not simplify or water down the original dialogue.
- Truncating limited to reading speed / audio sync issues.
- When editing for reading speed, favor text reduction, deletion and condensing.

## Acronyms & Abbreviations

ALL CAPS, no periods: UNICEF, CIA, FBI, NASA. Washington DC (no periods).

## Character Names

- Nicknames: only translate if they convey specific meaning.
- Historical/mythical characters: use Dutch equivalent (Santa Claus → De Kerstman).

## Titles & Honorifics

- Mr, Mrs, Miss: no period, not translated
- "sir", "lord", "lady", "don": lowercase
- "Dame": capitalize (to avoid confusion with Dutch "dame")
- "mr." (lawyer), "dr." (academic): lowercase with period
- "dokter" (physician): spell out
- Military/job titles: translate to Dutch equivalent

## Numbers

- Spell out 1-12 in dialogue
- Also spell out round tens: twintig, dertig, veertig, vijftig, etc. — UNLESS combined with units (20 km, 30 kg)
- "één" (with accent) to distinguish from "een" (a/an)
- Higher numbers: digits

## Times

24-hour format: 15:40 (not 3:40 PM)

## Measurements

Convert imperial → metric. Round for readability.

## Spelling

Always "oké" — never "okay", "O.K.", "ok"

## What NOT to Translate

Omit entirely:
- Standalone exclamations: "ah", "uhm", "oh", "wow" (unless part of longer sentence)
- Standalone greetings: "hello", "hi", "bye" (unless part of longer sentence)
- Filler words: "you know", "I mean", "like", "well", "so", "listen", "look"
- Tag questions as filler: "right?", "yeah?", "okay?", "you see?", "isn't it?"
- Hedge phrases as filler: "if you like", "if you will", "as it were", "shall we say"
- Stuttering, hesitations, false starts
- Background TV/radio/news (unless plot-relevant)
- Songs (unless functional to plot — musicals, character singing for a reason)

When songs ARE translated: lowercase start, no end period, commas and question marks allowed.

## Repetition

- Identical lines said twice → subtitle once
- Greetings exchanged between characters → subtitle once

## Continuity

- `...` (three dots) for ellipses at **end** of continuation cues (trailing dots)
- **Continuation cue starts lowercase** — the next cue continues mid-sentence, so it must not start with a capital letter (unless proper noun). The merge script strips `...` and joins with a space.
- Leading `...` ("inpunten") allowed when speaker genuinely enters mid-sentence (e.g., `...halverwege een zin`)
- **Never end a continuation cue with a comma** — use `...` instead
- Two hyphens `--` for abrupt interruption; ellipses for trail-off

## Dual Speakers

- **CRITICAL: First line NEVER starts with a dash.** Dashes only for second speaker.
- Second speaker: `-` (dash, NO space after dash): `Waar kom je vandaan?\n-Uit Amsterdam.`
- Merge control markers: `[SC]` (speaker change), `[NM]` (no merge), or nothing (same speaker).
- `[SC]` — different speaker from previous cue. **Place liberally.** Missing an `[SC]` causes the merge script to mash two speakers together — this is far worse than an unnecessary `[SC]` (which merely prevents a merge). Note: a speaker redirecting their attention to a different person is NOT a speaker change — e.g., the Major talking to Manuel then turning to greet Basil is still the Major speaking.
- `[NM]` — ONLY for genuinely ambiguous cases (e.g., unclear if narration shifted to interview)
- No marker = same speaker, eligible for merge.

### How to detect speaker changes

**The source SRT is your primary signal.** Most source files already contain dual-speaker dash markers (`- Line A / - Line B`). These tell you exactly where speakers change:

1. **Source cue has dashes** → the cue contains two speakers. When you split this into separate NL cues, mark the second speaker's cue with `[SC]`.
2. **Source cue follows a dashed cue** → check whether the new cue continues speaker A, speaker B, or introduces speaker C. Mark `[SC]` if the speaker differs from the previous NL cue.
3. **Source has no dashes but speaker clearly changes** (e.g., a question followed by an answer from a different character) → mark `[SC]`.

Do NOT guess. Read the source dashes and sentence context.

### Speaker continuity after dual-speaker cues

When a dual-speaker cue is followed by a single-speaker cue, you must determine WHO is speaking in the next cue. The terminal punctuation of the **last speaker** (speaker B) in the dual-speaker cue tells you:

1. **Speaker B ends with `.` `!` `?`** (complete sentence) → next cue's speaker is **ambiguous**. It could be A, B, or even a new speaker C. Mark `[SC]` unless context makes the speaker obvious.
   ```
   Cue 1: Speaker A.        ← complete
          -Speaker B.        ← complete
   Cue 2: ???                ← could be A, B, or C — cannot merge
   ```

2. **Speaker B ends with `...`** (ellipsis = explicit continuation) → next cue is **definitely speaker B**. Safe to merge (no `[SC]`).
   ```
   Cue 1: Speaker A?         ← complete
          -Speaker B...       ← continues
   Cue 2: Speaker B continued ← same speaker — can merge
   ```

3. **Speaker B has no terminal punctuation** (no period, no ellipsis) → next cue is **likely speaker B** (implicit continuation). Safe to merge (no `[SC]`).
   ```
   Cue 1: Speaker A?         ← complete
          -Speaker B          ← no period = continues
   Cue 2: Speaker B continued ← same speaker — can merge
   ```

The same logic applies to speaker A: if speaker A's line is incomplete and the next cue has no dashes, it may be A continuing. But since A appears on line 1 and B on line 2, B's continuation into the next cue is far more common.

### Genre defaults for [SC]

- **Comedy / fast-unscripted:** Assume speaker change unless clearly the same speaker. In rapid-fire dialogue, MOST cues change speaker. When in doubt, mark `[SC]`.
- **Documentary:** Consecutive cues from the same narrator have NO marker. Do not mark `[SC]` or `[NM]` just because there's a pause or topic shift within the same speaker.
- **Drama:** Mark `[SC]` at every speaker change. When uncertain (e.g., off-screen voice), prefer `[SC]` over omitting it.

## Line Treatment

- Maximum two lines, ≤42 chars per line
- If total ≤42 chars → single line, do not break

### Line Break Priority (apply in order)

**NEVER break by dividing character count equally.** Break at a natural point — after a comma, or where you'd insert a breathing pause. Only deviate if the max character count forces it.

Example: `Je weet heel goed dat je die rotte appels nog kunt eten.`
- Wrong: `Je weet heel goed dat je die` / `rotte appels nog kunt eten.`
- Right: `Je weet heel goed` / `dat je die rotte appels nog kunt eten.`

1. **Sentence boundaries** — ALWAYS break at `. ` `? ` `! ` between two sentences sharing a cue. Never let a period fall mid-line with the next sentence continuing on the same line.
2. **Comma + conjunction** — break AFTER the comma, before the conjunction (maar, want, omdat, dus, en, of, noch). The conjunction starts line 2.
3. **Bottom-heavy pyramid** — prefer longer line 2 over longer line 1.
4. **Semantic units on line 2** — line 2 should read as a coherent phrase (noun phrase, verb phrase, prepositional phrase). Never orphan a single article, preposition, or pronoun on line 1.
5. **Never separate:** article+noun, verb+subject pronoun, verb+auxiliary/negation, demonstrative+noun, prepositional verb+preposition, first name+last name

## Timestamp Preservation

- Preserve original start times (exception: merged cues inherit first cue's start)
- End times may be extended for CPS compliance, must never overlap

## Forbidden Punctuation

- **No exclamation marks** — replace with period. Viewers hear emphasis; don't write it.
- **No semicolons** — replace with period or rephrase as two sentences.

## Contractions

- `z'n` (zijn) and `m'n` (mijn): standard in informal dialogue (unstressed possessives)
- `'t`, `'m`, `'n`: only when space is genuinely tight — prefer full forms (`het`, `hem`, `een`)
- Set phrases: `'s ochtends`, `'s avonds`, etc. — always contracted

## Quotation Marks

- Use **single** quotation marks: `'Kom binnen.'`
- Only use quotation marks when confusion is possible. If context or visuals make it clear someone is reading aloud or quoting, omit them entirely:
  - `Hij zei tegen me: Barst jij maar.`
  - `Ik antwoordde: Val dood.`
- For a quote spanning multiple cues, place quotation marks around each cue. This does NOT apply to cues with continuation ellipsis (`...`).

## Colon & Capitalization

- Colon + direct speech or thoughts → **capital** letter: `Hij zei: Kom binnen.`
- All other colon uses → **lowercase**: `drie landen: nederland, belgië en luxemburg`
- If a cue **ends** with a colon, do not use ellipsis — start the next cue with a capital letter.

## Inserts & Graphic Text

- Short inserts (signs, labels): ALL CAPS, no punctuation: `UITGANG`
- Long inserts (letters, screens): lowercase with original punctuation

## Hyphenation (Line Breaks)

- Only break compound words at morpheme boundary at line end: `stoom-\nwals` (not `stoo-\nmwals`)
- Never break simple (non-compound) words across lines

## Italics

Minimize italic use. When needed:
- **Do** italicize: titles of films, TV/radio programs, books, songs, albums, artworks
- **Do** italicize: foreign words that are genuinely unfamiliar to a Dutch audience
- **Do NOT** italicize: band names, newspapers, magazines
- Mechanical or thought voices: only italicize when absolutely necessary for clarity (e.g., multiple "voices" in one cue)

## Genitief

Prefer `van`-construction over apostrophe-s possessive:
- Prefer: `het huis van oma` — not: `oma's huis`
- Only use apostrophe-s when omitting it creates a pronunciation problem: `papa's pijp`, `mama's paraplu`

## Compound Words (Samenstellingen)

Three-part compounds: hyphen between first and second part, second and third part joined:
- `onroerende-zaakbelasting`, `1-meiviering`, `multiple-choicetest`

Compounds with names or readability issues: space between first and second, hyphen between second and third:
- `Tour de France-winnaar`, `ad hoc-beslissing`, `nummer één-hit`

## Tense Preservation

Do not change tense to save space. Condensation must not alter the temporal meaning:
- Not: `Hoe kwam je binnen?` (onvoltooid verleden)
- But: `Hoe ben je binnengekomen?` (voltooid verleden, as spoken)

## Translation Quality (Auteursbond)

- **Grammar must be correct**, even when the original contains grammatical errors
- **Do NOT reproduce broken grammar** for comic effect — "gaan we daar liever niet in mee"
- **Profanity:** tone down in written form (written impact > spoken). "fuck" and "shit" are naturalized in Dutch — keep as-is or omit; do not translate
- **Readability:** subtitle must read fluently in one glance ("vlot leesbaar, in één oogopslag meekrijgen") — avoid complex sentence constructions and words that don't scan smoothly

## Universal Rules

1. **Maximum 2 lines per cue** — verify before writing
2. **Natural Dutch > text compression**
3. **Timecodes: copy exactly from source** — script handles merging
4. **Second speaker dash only** — first line NEVER starts with dash, no space after dash
5. **No fabrication** — translate what's there
6. **Write incrementally** — save after each batch
7. **Omit visually redundant** — don't subtitle what's visible
8. **NEVER output cues to terminal** — always write to file (Write tool for first batch, `cat >>` for subsequent)
