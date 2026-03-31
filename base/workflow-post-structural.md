# Phases 3-5: Structural Post-Processing

**You are a professional Dutch subtitle translator.** This phase handles structural fixes, merging, trim-to-speech, and CPS optimization.

**All phases are mandatory.** Execute in order.

---

## Pre-Phase-3: Save Draft Mapping

Before Phase 3 renumbers cues, save the NL→EN timecode correspondence from the draft. This mapping is used in Phase 9 for accurate NL→EN matching even after merges and renumbering.

```bash
python3 scripts/save_draft_mapping.py draft.nl.srt "${VIDEO_BASENAME}.en.srt" \
  --output draft_mapping.json
```

---

## Phase 3: Structural Fix

Fix structural errors only. **Do NOT condense text for CPS — that happens after merge in Phase 5.**

```bash
python3 scripts/validate_srt.py draft.nl.srt \
  --source "${VIDEO_BASENAME}.en.srt" \
  --fix --output draft-fixed.nl.srt
```

Fix before merge:
- Overlapping cues (timestamp errors) — fix first
- Line length > 42 characters (reflow or shorten)
- Gap violations (< minimum gap, framerate-dependent)
- 3+ line cues (restructure to 2 lines max)

**Line length fix for dual-speaker cues:** If a dual-speaker cue has a line exceeding 42 characters and the other line is a trivial reply (`-Ja.`, `-Nee.`, `-Goed.`, `-Oké.`, etc.), drop the trivial reply and reflow the remaining text across two lines. The viewer hears the trivial reply — removing it frees both lines for the sentence that needs the space.

**Do NOT fix:** CPS violations. Merging extends durations and lowers CPS naturally.

### Timing drift (if `drift_errors` is non-empty)

A `drift_errors` entry means consecutive NL cues have start times that deviate significantly from the nearest EN source cue — the translator computed a timestamp instead of copying from the source (typically after a long gap in the EN).

To fix: identify the affected cue range and offset from the error message, then shift those cues:

```python
import re

SHIFT_MS = <offset_in_ms>   # positive = shift forward, negative = shift back
FIRST_CUE = <first_cue_num>
LAST_CUE  = <last_cue_num>

with open('draft-fixed.nl.srt', 'r') as f:
    content = f.read()

def ts(ms):
    h,m,s,ms_r = ms//3600000,(ms%3600000)//60000,(ms%60000)//1000,ms%1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_r:03d}"

def shift(m):
    num = int(m.group(1))
    if not (FIRST_CUE <= num <= LAST_CUE):
        return m.group(0)
    def conv(h,mn,s,ms_r): return ((int(h)*60+int(mn))*60+int(s))*1000+int(ms_r)
    s = conv(m.group(2),m.group(3),m.group(4),m.group(5)) + SHIFT_MS
    e = conv(m.group(6),m.group(7),m.group(8),m.group(9)) + SHIFT_MS
    return f"{num}\n{ts(s)} --> {ts(e)}"

pat = re.compile(r'(\d+)\n(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})')
with open('draft-fixed.nl.srt', 'w') as f:
    f.write(pat.sub(shift, content))
```

After correcting timestamps, re-run Phase 3 to confirm `drift_errors` is empty before continuing.

---

## Phase 2b: Speaker Change Marker Pass (polish mode only)

When running in `--polish` mode (no Phase 2 translation), the NL draft has no `[SC]`/`[NM]` markers. The orchestrator runs a marker pass before Phase 3 to add them.

The marker pass reads EN source + NL draft side-by-side and prepends markers to NL cues:
- `[SC]` — different speaker from previous cue
- `[NM]` — ambiguous speaker continuity
- No marker — same speaker, eligible for merge

The pass uses Opus (`$MODEL_TRANSLATE`) — Sonnet produces too few markers. It does not modify text, timestamps, or cue structure.

This phase runs automatically via `orchestrate.sh` in polish mode. It is not needed for normal translations (Phase 2 adds markers during translation).

---

## Phase 4: Script-Based Merge

### How markers become output

The merge script (`auto_merge_cues.py`) consumes `[SC]`/`[NM]` markers placed during Phase 2 (or Phase 2b in polish mode):

- **`[SC]`** → adjacent cues are merged with `\n-` dash separation (dual-speaker formatting)
- **`[NM]`** → merge is blocked at this boundary (cues stay separate)
- **No marker** → cues are merged with space-joined text (same speaker)
- All markers are stripped from final output

See `references/translation-defaults.md` (Dual Speakers section) for worked examples.

The script handles merge decisions mechanically.

```bash
python3 scripts/auto_merge_cues.py draft-fixed.nl.srt \
  --gap-threshold ${GAP_THRESHOLD} \
  --max-duration ${MAX_DURATION} \
  --output merged.nl.srt \
  --report merge_report.json
```

Genre parameters (from checkpoint):

| Genre | --gap-threshold | --max-duration | Target ratio |
|-------|-----------------|----------------|--------------|
| documentary | 1000 | 7000 | 70-85% |
| drama | 1000 | 7000 | 60-75% |
| comedy | 800 | 6000 | 55-70% |
| fast-unscripted | 500 | 6000 | 50-65% |

After running, check ratio:
```bash
source_count=$(grep -c '^[0-9]' source.en.srt)
merged_count=$(grep -c '^[0-9]' merged.nl.srt)
echo "Ratio: $((merged_count * 100 / source_count))%"
```

### Post-merge verification: dual-speaker count

Count dual-speaker cues (those with `\n-` pattern) in the merged output:

```bash
python3 -c "
with open('merged.nl.srt') as f: content = f.read()
import re
blocks = re.split(r'\n\n+', content.strip())
dual = sum(1 for b in blocks if '\n-' in b)
total = len([b for b in blocks if re.search(r'\d+:\d+', b)])
print(f'Dual-speaker cues: {dual} / {total} ({dual*100//max(total,1)}%)')
"
```

**Expected ranges by genre:**
- Comedy / fast-unscripted: 15-40% of merged cues should be dual-speaker
- Drama: 10-25%
- Documentary: 0-10%

If dual-speaker count is **below the expected range**, the translator likely missed `[SC]` markers. Flag this in the log as a quality warning — the issue originates in Phase 2 and cannot be fully corrected in post-processing.

---

## Phase 4b: Trim to Speech

Pulls back cue end times that linger past speech boundaries. Uses VAD (same approach as Phase 9) to detect where speech actually ends and trims accordingly, guarded by CPS constraints.

```bash
scripts/run-venv.sh scripts/trim_to_speech.py \
    "$VIDEO_FILE" \
    merged.nl.srt \
    --output trimmed.nl.srt \
    --fps ${FRAMERATE} \
    --report trim_report.json \
    -v
```

**If the script fails:** Copy merged.nl.srt to trimmed.nl.srt and continue. Phase 9 will catch any lingering issues.

```bash
cp merged.nl.srt trimmed.nl.srt
```

---

## Phase 5: CPS Optimization (Post-Merge)

Validate CPS on the trimmed file:

```bash
python3 scripts/validate_srt.py trimmed.nl.srt --summary --report cps_validation.json
```

### Step 0: Close Small Gaps (Auteursbond)

Gaps shorter than 1 second should be closed by extending end times (Auteursbond: "aansluiten"):

```bash
python3 scripts/extend_end_times.py trimmed.nl.srt \
  --close-gaps 1000 --fps ${FRAMERATE} \
  -o trimmed.nl.srt
```

### Step 1: Extend End Times (ALL cues with CPS > CPS target)

**This is the primary CPS tool.** For EVERY cue with CPS above the CPS target (fps-dependent: 11 at 24fps, 12 at 25fps), extend the end time to fill the available gap before the next cue. Target CPS: **12** (25fps) / **11** (24fps).

```
For each cue where CPS > CPS target:
  available_gap = next_cue_start - current_cue_end
  if available_gap > ${MIN_GAP}ms:
    extend end time, leaving ${MIN_GAP}ms minimum gap
    recalculate CPS
```

This is a mechanical operation. Do it for ALL qualifying cues, not just outliers. The user's expectation is CPS 12-12.5 wherever display time permits.

### Step 2: Text Condensation (only for CPS still > CPS soft ceiling after extension)

After extending all end times, some cues will still exceed the CPS soft ceiling (fps-dependent: 15 at 24fps, 17 at 25fps) because there's no gap to extend into. Only THEN condense text:

- **CPS soft ceiling to hard limit (20):** condense if possible without losing meaning
- **CPS > hard limit (20):** must condense (emergency — meaning loss acceptable)

**Condensation priority order** (try each before the next):
1. **Drop trivial replies** — if a dual-speaker cue's second line is a trivial acknowledgment (`Ja.`, `Nee.`, `Oké.`, `Goed.`, `Precies.`, `Klopt.`, etc.), drop the second line and convert to single-speaker. The viewer hears these — subtitling them adds characters without information. This is the cheapest CPS reduction.
2. **Targeted re-merge** — if adjacent (gap ≤1000ms) and combined fits constraints, merge
3. **Delete filler** → compress phrases → rephrase
4. Only accept CPS 17-20 when proper nouns/terminology genuinely cannot be cut further

**Condensation quality rule:** Never replace common words with uncommon synonyms to save characters. Always use natural, everyday Dutch.

**Dual-speaker preservation:** When condensing a cue that has dual-speaker dash formatting (`\n-`), the condensed text MUST keep the dash format. Never collapse two speakers onto one line.
