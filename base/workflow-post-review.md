# Phase 6: Linguistic Review

**You are a professional Dutch subtitle translator.** This phase handles linguistic review of merged subtitle cues.

---

## Phase 6: Linguistic Review

Review **all cues** for grammar, naturalness, and linguistic quality. **Fix text only — never touch timecodes.**

### Working Method

Work through the full `.nl.srt` in chunks of ~80 cues:

```bash
python3 scripts/extract_cues.py merged.nl.srt --start 1 --end 80 --output review_chunk.srt
```

Also load `merge_report.json` to know which cues were merged.

### Review Checklist (every chunk)

**Grammar:**
- d/t/dt verb endings correct?
- de/het articles correct?
- V2 word order after fronted elements?
- Subordinate clause word order (verb-final)?
- er/daar/hier compounds correct?

**Naturalness:**
- No English syntax calques?
- No literal translations where Dutch idiom exists?
- Word order feels native, not translated?

**Punctuation:**
- Correct `...` use (end-of-cue continuation only)?
- No semicolons or exclamation marks?

**Register:**
- je/u consistent per character relationship? (See `dutch-patterns.md` for rules — spouses/family/friends are ALWAYS je, never u)
- Register appropriate for speaker and context?

**Merged cues** (from `merge_report.json`) — these are the highest-priority items. The merge script joins text mechanically (strips `...`, joins with space). Claude must verify every merge boundary reads as correct Dutch:

1. **Capitalization at join point:** If the merged text has an uppercase letter mid-sentence (from cue-initial capitalization), lowercase it. Example: `het blauwe In de la` → `het blauwe in de la`.
2. **Missing punctuation at join point:** If two clauses were joined without proper punctuation, add it. Example: `Ik ben alleen Duitsers komen morgen` → `Ik ben alleen, de Duitsers komen morgen` (comma + article).
3. **Orphaned fragments:** If a merged cue ends with a fragment that doesn't flow (`De soldaten marcheerden. Naar het front.`), rewrite as one sentence (`De soldaten marcheerden naar het front.`).
4. **Parallel constructions:** If merged rhetorical questions or lists lost their separators, add commas. Example: `Groeit die nog steeds woekert die zich naar het bot` → `Groeit die nog steeds, woekert die zich naar het bot`.

Read `merge_report.json`, find every `output_index` with `source_count > 1`, and verify the merged text at that cue number.

### Fix Rules

- **Edit text only.** Do NOT touch timecodes.
- Do NOT change merge decisions or cue count.
- **Preserve dual-speaker formatting:** If a cue has dash formatting (`\n-`), any rewrite MUST keep the two-speaker structure with the dash. Never merge two speakers' text into flowing prose.
- Apply fixes in batch (collect all issues in a chunk, fix together).
- Reference `references/common-errors.md` for known patterns.

### Merge Artifact Example

After script merge:
```
Cue 5: "De soldaten marcheerden. Naar het front."
```
Review: "Naar het front." is orphaned fragment.
Fix: "De soldaten marcheerden naar het front."
