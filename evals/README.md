# Evaluation Tests

Test suite for the srt-translate skill. Tests use real subtitle cues to verify the full pipeline produces correct output.

## Test Files

### `test_comprehensive.en.srt` — 81 cues (Comedy + Documentary SDH)

| Scenario | Cues | Count |
|---|---|---|
| SDH — sound effects | 1, 66 | 2 |
| SDH — speaker labels | 65 | 1 |
| SDH — music identifier | 61 | 1 |
| Italic — song lyrics | 62-64 | 3 |
| Dual-speaker (dashes) | 3, 21, 26, 45 | 4 |
| Speaker change without dashes | 4→5, 10→11, 17→18, 39→40, 42→43, 48→49 | 6 |
| Continuation — no terminal punctuation | 13→14, 22→23, 25→26, 30→31, 67→68, 72→73 | 6 |
| Continuation — trailing comma | 6→7, 28→29, 33→34, 57→58, 78→79→80 | 5 |
| Continuation — ellipsis | 29 | 1 |
| Fast cues (<1.5s) | 5, 17, 24, 39, 40, 43, 50, 52, 70, 79, 80 | 11 |
| Large / CPS pressure | 36-37, 56, 60, 78 | 4 |
| Multi-cue continuation (3+) | 30-32, 33-35, 67-71, 78-81 | 4 spans |
| Foreign language | 50, 52 | 2 |
| Speaker continuity after dual-speaker | after 21, 26, 45 | 3 |

**Sources:** Cues 1-60 and 67-81 from Fawlty Towers S01E06 "The Germans" (comedy). Cues 61-66 from The Pigeon Tunnel (2023, documentary SDH track) to cover italics and SDH.

### `test_documentary.en.srt` — 31 cues (Documentary)

| Scenario | Cues | Count |
|---|---|---|
| SDH — sound effects | 1, 31 | 2 |
| SDH — speaker labels | 26 | 1 |
| Narration — formal register | 2-18 | 17 |
| Interview — informal register | 19-25 | 7 |
| Nature documentary narration | 27-30 | 4 |
| Statistics / Dutch number formatting | 9 | 1 |
| Military / historical terminology | 2-18 | 17 |
| Multi-cue continuation (3+) | 2→3→4, 5→6, 7→8, 10→11, 13→14→15, 16→17→18, 19→20→21, 22→23→24, 27→28→29→30 | 9 spans |
| CPS-pressure cues | 11, 15 | 2 |

**Sources:** Cues 2-18 from The World At War (1973) S01E18 — WWII documentary narration + occupation description. Cues 19-25 from witness interview segments. Cues 27-30 from Planet Earth (2006) — nature documentary narration. SDH cues (1, 26, 31) from The Pigeon Tunnel (2023).

### `test_drama.en.srt` — 31 cues (Drama)

| Scenario | Cues | Count |
|---|---|---|
| Character voice — Stevens (formal) | 1-3, 17-19, 30 | 7 |
| Character voice — Miss Kenton (direct) | 20-22 | 3 |
| Character voice — Mr. Benn (working class) | 28-29 | 2 |
| T-V register shifts (je/u) | 28-29 | 2 |
| Dual-speaker (dashes) | 4, 28 | 2 |
| Rapid multi-speaker exchange | 4-16 | 13 |
| Emotional scenes without `!` | 23-27 | 5 |
| Period-appropriate vocabulary | 8, 30, 31 | 3 |
| Idiom adaptation | 31 | 1 |
| Multi-cue continuation | 1→2→3, 5→6→7→8, 21→22, 24→25, 26→27 | 5 spans |

**Sources:** From The Remains of the Day (1993) — character-driven period drama with distinct voices, register tracking, and emotional restraint.

## Tests (evals.json)

### Comedy Pipeline (tests 1-3)

#### 1. comprehensive-translation
Translates all 81 cues into Dutch. Verifies:
- `[SC]` markers at every speaker change
- je/jij between Basil/Sybil (married), u for Major/strangers/service
- SDH-only cues removed (1, 61, 66)
- Speaker labels stripped (65)
- Italic song cues translated with tags preserved
- Continuation cues start lowercase
- No exclamation marks

#### 2. comprehensive-merge
Runs `auto_merge_cues.py` on the translation output with comedy parameters (`--gap-threshold 800 --max-duration 6000`). Verifies:
- Merge ratio 55-70%
- `[SC]` cues become dual-speaker dash formatting
- Same-speaker continuations merged
- No dual-speaker cues collapsed into single-speaker

#### 3. comprehensive-validation
Runs `validate_srt.py` on the merged output. Verifies:
- Zero hard errors
- No line-length violations (all lines ≤42 chars)
- No empty cues
- CPS warnings acceptable for fast comedy dialogue

### Documentary Pipeline (tests 4-6)

#### 4. documentary-translation
Translates all 31 documentary cues into Dutch. Verifies:
- SDH-only cues (1, 31) removed, speaker label (26) stripped
- Narration uses formal, complete sentences
- Interview segments preserve speaker rhythm with filler removed
- Military terminology correct (para's, tanks)
- Dutch number formatting (176.000)
- Dutch date format (10 mei 1940)
- No exclamation marks

#### 5. documentary-merge
Runs `auto_merge_cues.py` with documentary parameters (`--gap-threshold 1000 --max-duration 7000`). Verifies:
- Merge ratio 70-85%
- Multi-cue continuations merged correctly
- No same-speaker dual-speaker collapse

#### 6. documentary-validation
Runs `validate_srt.py` on the merged output. Verifies:
- Zero hard errors
- No line-length violations
- No empty cues

### Drama Pipeline (tests 7-9)

#### 7. drama-translation
Translates all 31 drama cues into Dutch. Verifies:
- T-V register consistency (Stevens uses u, Benn shifts to je with Sarah)
- Character voice preservation (formal Stevens, direct Miss Kenton)
- No exclamation marks (cue 23 "damn it!" → no ".")
- Period-appropriate vocabulary (sous-butler, provisiekamer)
- Idiom adaptation ("not turning a hair" → Dutch equivalent)
- Rapid exchange sequence tracked correctly

#### 8. drama-merge
Runs `auto_merge_cues.py` with drama parameters (`--gap-threshold 1000 --max-duration 7000`). Verifies:
- Merge ratio 60-75%
- Rapid exchange merged correctly
- Dual-speaker cues preserved

#### 9. drama-validation
Runs `validate_srt.py` on the merged output. Verifies:
- Zero hard errors
- No line-length violations
- No empty cues

## Running Tests

Tests are sequential within each pipeline (each depends on the previous):

```bash
cd /mnt/nas/video/.claude/skills/srt-translate

# Comedy Pipeline
# Test 1: Translation (requires Claude subagent)
# Test 2: Merge
scripts/venv/bin/python3 scripts/auto_merge_cues.py \
  draft.nl.srt \
  --gap-threshold 800 --max-duration 6000 \
  --output merged.nl.srt \
  --report merge_report.json
# Test 3: Validation
scripts/venv/bin/python3 scripts/validate_srt.py merged.nl.srt --fps 25

# Documentary Pipeline
# Test 4: Translation (requires Claude subagent)
# Test 5: Merge
scripts/venv/bin/python3 scripts/auto_merge_cues.py \
  draft.nl.srt \
  --gap-threshold 1000 --max-duration 7000 \
  --output merged.nl.srt \
  --report merge_report.json
# Test 6: Validation
scripts/venv/bin/python3 scripts/validate_srt.py merged.nl.srt --fps 25

# Drama Pipeline
# Test 7: Translation (requires Claude subagent)
# Test 8: Merge
scripts/venv/bin/python3 scripts/auto_merge_cues.py \
  draft.nl.srt \
  --gap-threshold 1000 --max-duration 7000 \
  --output merged.nl.srt \
  --report merge_report.json
# Test 9: Validation
scripts/venv/bin/python3 scripts/validate_srt.py merged.nl.srt --fps 24
```

After merge, Phase 6 (Linguistic Review) should be run to verify merge boundary correctness — see `workflow-post.md`.

## Results

Test outputs are stored in `srt-translate-workspace/iteration-N/` per test run. Each iteration preserves its inputs and outputs for comparison.
