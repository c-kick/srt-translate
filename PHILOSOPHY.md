# Design Philosophy

Read this before modifying the skill, filing issues, or proposing changes.

---

## What this skill does

Translates English SRT subtitles into Dutch following professional broadcast standards (Netflix Dutch Timed Text Style Guide + Auteursbond). The translator is Claude. The pipeline is orchestrated by a shell script that invokes Claude in isolated phases with fresh context.

## Core principle: judgment vs. mechanics

The system is split into two domains with a hard boundary between them.

**Claude handles judgment.** Translation, condensation, register, idiom, speaker change detection, SDH identification — anything that requires understanding language, context, or intent. These tasks have been tried as heuristic scripts and failed. Claude's contextual understanding is the only reliable tool for them.

**Scripts handle mechanics.** CPS calculation, timecode arithmetic, gap enforcement, renumbering, merge execution, VAD timing — anything deterministic, repetitive, or requiring frame-accurate precision. These must not involve Claude's judgment because they need to be reproducible and verifiable.

**The contract between them is the `[SC]`/`[NM]` marker system.** Claude places markers during translation. Scripts consume them during merge. Markers are boolean flags — they carry no payload beyond "change" or "don't merge."

## Speaker change detection: changes, not identity

The system detects **speaker changes** — that a different person is now speaking. It does **not** detect **speaker identity** — who that person is.

This is by design. Reliable speaker identification from text alone is not feasible. The system went through audio diarization (too slow on CPU), heuristic script detection (too aggressive), and keyword matching (too brittle) before arriving at the current approach: Claude reads the dialogue contextually and marks where speakers change. That's it.

- `[SC]` means "different speaker from previous cue" — a boolean, not a name.
- `[NM]` means "don't merge across this boundary" — used when even the change/same-speaker question is ambiguous.
- No marker means "same speaker, eligible for merge."
- Character names appearing in batch context notes are informational — written by one Claude instance for the next to maintain dialogue flow. They are never parsed by scripts.

Any proposed change that assumes the system tracks named speakers is based on a misunderstanding.

## Why things are done by Claude, not by script

Several tasks look like they could be automated but cannot:

- **SDH removal.** Keyword lists miss context-dependent cases and over-remove. Claude identifies SDH by understanding what is dialogue and what is description.
- **Speaker detection.** Dashes in source cues tell you "two speakers here" but not who. Continuation markers tell you "same speaker continues." Everything else requires reading the dialogue. Claude does this during translation.
- **Register (je/u).** Depends on character relationships, scene formality, genre conventions, and era. No rule set captures this — Claude decides per utterance.
- **Condensation.** Which words to cut depends on meaning, emphasis, and what the viewer can hear. Scripts can measure CPS; only Claude can decide what to remove.

If you're considering moving one of these into a script, check `git log` for whether a script-based approach was already tried and removed. Multiple scripts for SDH removal, speaker detection, and CPS condensation were built, tested, and deleted because they couldn't match Claude's contextual judgment.

## Batch isolation and its consequences

Long translations are split into batches of ~100 cues, processed sequentially. Each batch has context from previous batches via a batch context file. At invocation boundaries (every 6 batches / 600 cues), context resets entirely — the next Claude invocation starts fresh.

This means:
- Terminology, register, and speaker flow must be captured in batch context files, because they don't survive in Claude's memory.
- Batch context is ephemeral and unvalidated. Any field can be missing or wrong. Downstream phases must be resilient to this.
- Translation batches must never run in parallel. Each batch depends on context from the previous one.

## Post-processing is not re-translation

Phases 3–11 are mechanical. They fix structure (Phase 3), merge (Phase 4), trim timing (Phase 4b), optimize CPS (Phase 5), review grammar (Phase 6), finalize (Phase 7), rebalance lines (Phase 8), QC against audio (Phase 9), optionally extend to speech (Phase 10), and do a final grammar scan (Phase 11).

Phase 6 (linguistic review) and Phase 11 (final grammar scan) are the post-processing phases where Claude makes creative decisions — but they edit text only, never timecodes, and never change merge decisions or cue count. Phase 11 is intentionally the last step before the log: it catches anything introduced or missed by all preceding phases.

## Conservative merging

An unmerged cue is invisible to the viewer. An incorrectly merged dual-speaker cue — two characters' dialogue mashed together without a dash — is a visible, jarring error.

The system is biased toward caution: `[SC]` should be placed liberally, `[NM]` when uncertain, and no marker only when confidently the same speaker. A missed `[SC]` is far worse than an unnecessary one.

## Constraints belong in code, not prose

Prose instructions drift. When a constraint must hold (CPS limits, line length, gap minimums), it should be enforced by a validator script, not trusted to the translator. `validate_srt.py` is the backstop — if a rule matters, it should be checked there.

`shared-constraints.md` is auto-generated from `srt_constants.py` via `--sync`. Do not edit it directly.

## Exemplars teach reasoning

Exemplar files use EN → NL → WHY format. The WHY column is the point — it teaches the translator *why* a translation choice was made, not just what the output should be. An exemplar without reasoning is a lookup table; an exemplar with reasoning transfers a skill.
