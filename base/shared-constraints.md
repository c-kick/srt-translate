# Shared Constraints

Universal rules for all phases. Injected into every pipeline invocation.

---

## Hard Constraints

| Constraint | Value |
|---|---|
| CPS Target | 12 |
| CPS Soft Ceiling | 17 (normal working limit) |
| CPS Hard Limit | 20 (emergency only) |
| Characters per line | 42 |
| Maximum cue duration | 7000ms |
| Minimum cue duration | 830ms |
| Minimum cue gap | 120ms (3 frames @ 25fps) |
| Max words/min | 180 |
| Max lines per cue | 2 |

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

- Mr/Mrs/Ms: no period, not translated
- "sir": military = "sir"; civilian = "meneer"
- "mr." (lawyer), "dr." (academic): lowercase with period
- "dokter" (physician): spell out
- Military/job titles: translate to Dutch equivalent

## Numbers

- Spell out 1-12 in dialogue
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

- `...` (three dots) for ellipses, only at **end** of continuation cues (no "inpunten")
- **Never end a continuation cue with a comma** — use `...` instead
- Two hyphens `--` for abrupt interruption; ellipses for trail-off

## Dual Speakers

- **CRITICAL: First line NEVER starts with a dash.** Dashes only for second speaker.
- Merge control markers: `[SC]` (speaker change), `[NM]` (no merge), or nothing (same speaker).
- **Default is NO marker** (= same speaker, eligible for merge). Only use markers when speaker status is clear:
  - `[SC]` — confident different speaker from previous cue
  - `[NM]` — ONLY for genuinely ambiguous cases (e.g., unclear if narration shifted to interview)
- In documentary narration: consecutive cues from the same narrator should have NO marker. Do not mark `[NM]` just because there's a pause or topic shift within the same speaker.

## Line Treatment

- Maximum two lines, ≤42 chars per line
- If total ≤42 chars → single line, do not break

### Line Break Priority (apply in order)

1. **Sentence boundaries** — ALWAYS break at `. ` `? ` `! ` between two sentences sharing a cue. Never let a period fall mid-line with the next sentence continuing on the same line.
2. **Comma + conjunction** — break AFTER the comma, before the conjunction (maar, want, omdat, dus, en, of, noch). The conjunction starts line 2.
3. **Bottom-heavy pyramid** — prefer longer line 2 over longer line 1.
4. **Semantic units on line 2** — line 2 should read as a coherent phrase (noun phrase, verb phrase, prepositional phrase). Never orphan a single article, preposition, or pronoun on line 1.
5. **Never separate:** article+noun, verb+subject pronoun, verb+auxiliary/negation, demonstrative+noun, prepositional verb+preposition, first name+last name

## Timestamp Preservation

- Preserve original start times (exception: merged cues inherit first cue's start)
- End times may be extended for CPS compliance, must never overlap

## Universal Rules

1. **Maximum 2 lines per cue** — verify before writing
2. **Natural Dutch > text compression**
3. **Timecodes: copy exactly from source** — script handles merging
4. **Second speaker dash only** — first line NEVER starts with dash
5. **No fabrication** — translate what's there
6. **Write incrementally** — save after each batch
7. **Omit visually redundant** — don't subtitle what's visible
8. **NEVER output cues to terminal** — always write to file (Write tool for first batch, `cat >>` for subsequent)
