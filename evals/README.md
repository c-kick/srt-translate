# Evaluation Tests

Test suite for the srt-translate skill. Tests use real subtitle cues to verify the full pipeline produces correct output.

## Test File

**`test_comprehensive.en.srt`** — 81 cues covering all scenarios the pipeline must handle:

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

## Tests (evals.json)

### 1. comprehensive-translation

Translates all 81 cues into Dutch. Verifies:
- `[SC]` markers at every speaker change
- je/jij between Basil/Sybil (married), u for Major/strangers/service
- SDH-only cues removed (1, 61, 66)
- Speaker labels stripped (65)
- Italic song cues translated with tags preserved
- Continuation cues start lowercase
- No exclamation marks

### 2. comprehensive-merge

Runs `auto_merge_cues.py` on the translation output with comedy parameters (`--gap-threshold 800 --max-duration 6000`). Verifies:
- Merge ratio 55-70%
- `[SC]` cues become dual-speaker dash formatting
- Same-speaker continuations merged
- No dual-speaker cues collapsed into single-speaker

### 3. comprehensive-validation

Runs `validate_srt.py` on the merged output. Verifies:
- Zero hard errors
- No line-length violations (all lines ≤42 chars)
- No empty cues
- CPS warnings acceptable for fast comedy dialogue

## Running Tests

Tests are sequential (each depends on the previous):

```bash
cd /mnt/nas/video/.claude/skills/srt-translate

# Test 1: Translation (requires Claude subagent)
# Output: evals/srt-translate-workspace/iteration-N/.../draft.nl.srt

# Test 2: Merge
scripts/venv/bin/python3 scripts/auto_merge_cues.py \
  draft.nl.srt \
  --gap-threshold 800 --max-duration 6000 \
  --output merged.nl.srt \
  --report merge_report.json

# Test 3: Validation
scripts/venv/bin/python3 scripts/validate_srt.py merged.nl.srt --fps 25
```

After merge, Phase 6 (Linguistic Review) should be run to verify merge boundary correctness — see `workflow-post.md`.

## Results

Test outputs are stored in `srt-translate-workspace/iteration-N/` per test run. Each iteration preserves its inputs and outputs for comparison.
