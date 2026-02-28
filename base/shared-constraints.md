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
- Leading `...` ("inpunten") allowed when speaker genuinely enters mid-sentence (e.g., `...halverwege een zin`)
- **Never end a continuation cue with a comma** — use `...` instead
- Two hyphens `--` for abrupt interruption; ellipses for trail-off

## Dual Speakers

- **CRITICAL: First line NEVER starts with a dash.** Dashes only for second speaker.
- Second speaker: `-` (dash, NO space after dash): `Waar kom je vandaan?\n-Uit Amsterdam.`
- Merge control markers: `[SC]` (speaker change), `[NM]` (no merge), or nothing (same speaker).
- **Default is NO marker** (= same speaker, eligible for merge). Only use markers when speaker status is clear:
  - `[SC]` — confident different speaker from previous cue
  - `[NM]` — ONLY for genuinely ambiguous cases (e.g., unclear if narration shifted to interview)
- In documentary narration: consecutive cues from the same narrator should have NO marker. Do not mark `[NM]` just because there's a pause or topic shift within the same speaker.

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
