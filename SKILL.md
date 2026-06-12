---
name: srt-translate
description: >
  Vertaal Engelse SRT ondertitelbestanden naar Nederlands, of review bestaande Nederlandse ondertiteling.
  Volgt Netflix Dutch Timed Text Style Guide + Modelrichtlijnen Nederlandse Ondertiteling (Auteursbond).
  Gebruik bij verzoeken om EN→NL ondertitelvertaling, SRT lokalisatie, of review/controle van bestaande NL ondertitels tegen EN bron.
  Niet voor algemene vertaling zonder SRT-bestand, niet voor ondertiteling in andere talen dan Nederlands, niet voor audio-transcriptie.
  Primaire methode: orchestrate.sh pipeline (script-gestuurd, headless).
  Alternatief: interactieve modus voor losse fasen of review.
metadata:
  author: Klaas
  version: 12.0
---

# Dutch Subtitle Translation

**You are a professional Dutch subtitle translator.**

## Compatibility

Requires `ffmpeg`, `ffprobe`, a C build toolchain for `webrtcvad`, and `python3` with `ffsubsync`, `webrtcvad`, and `pysubs2` installed in `scripts/venv/`. The automated orchestrator uses Claude Code's `claude` CLI by default. Pass `--agent codex` or `--codex` to run phase groups through `codex exec` instead.

## Primary Mode: Orchestrated Pipeline

For full translations, use the orchestrator script:

```bash
./scripts/orchestrate.sh /path/to/video.mkv
```

The orchestrator invokes an AI coding agent in headless mode per phase group, each with a fresh context containing only the relevant instructions. This prevents attention degradation on long translations. Claude is the default backend; Codex is opt-in with `--agent codex` or `--codex`. In Codex mode, Claude model aliases are ignored and the Codex CLI uses its configured default unless the user passes an explicit non-Claude model name.

| Flag | Effect |
|------|--------|
| `--resume` | Resume from last checkpoint |
| `--fresh` | Delete checkpoint and start from phase 0 |
| `--phase N` | Start from phase N (0=setup, 2=translate, 3=post) |
| `--speech-sync` | Also run Phase 10 after Phase 9 |
| `--polish` | Skip translation — post-process an existing `.nl.srt` instead |
| `--augment-missing` | Add only missing burned-in/title-card cues to an existing `.nl.srt` |
| `--source-srt PATH` | Use an external source subtitle instead of `VIDEO_BASE.en.srt` |
| `--source-language LANG` | Source subtitle language for non-English source runs |
| `--output-srt PATH` | Write final output to a custom path |
| `--source-ready` | Treat `--source-srt` as already synced; skip setup and start at translation |
| `--max-batches N` | Stop after N translation batches (useful for testing) |
| `--agent claude\|codex` | Choose the headless agent backend; default is `claude` |
| `--codex` | Convenience alias for `--agent codex` |

### Polish mode

`--polish` upgrades an existing Dutch subtitle without retranslating. Works on any `.nl.srt` — previous skill outputs, older versions, or third-party downloads (OpenSubtitles, Bazarr, etc.).

Runs setup (Phase 0–1) to sync the source and classify content, then seeds the pipeline with the existing `.nl.srt` as the draft, runs a speaker change marker pass (Opus) to enable safe merging, and executes all post-processing phases (3–9). Costs roughly **30% of the tokens** of a full retranslation.

### Augment missing mode

`--augment-missing` updates an existing Dutch subtitle by adding only missing burned-in/title-card cues. It runs setup/title-card detection, extracts detected `[TITLE CARD: ...]` cues, filters out cues already covered by the existing `.nl.srt`, translates only the remaining missing cues, and merges them into the existing file with a timestamped backup.

### External source mode

For a non-English source SRT that already contains the complete subtitle timing/content, use `--source-srt PATH --source-language LANG --source-ready --output-srt PATH`. The orchestrator skips extraction, sync, and title-card detection, writes a deterministic checkpoint, then translates from the declared source language to Dutch and runs post-processing.

### Phase Groups

| Group | Phases | Claude context loaded |
|-------|--------|----------------------|
| Setup | 0a, 0, 0b, 1 | shared-constraints + workflow-setup |
| Translation | 2 | shared-constraints + workflow-translate + translator + `references/exemplars/*` *(skipped in --polish)* |
| Post-processing | 3-9, LOG | shared-constraints + workflow-post + common-errors |

Each group runs in a separate Claude invocation = fresh context, zero attention debt.

## Interactive Mode: Single Phases

For review, fixes, or individual phases, load the relevant workflow file directly.

| User says | Load | Action |
|-----------|------|--------|
| "review" / "revisie" | `base/workflow-post-structural.md` + `base/workflow-post-review.md` + `base/workflow-post-finalize.md` | Phases 3-11 |
| "grammar" / "grammatica" | `base/workflow-post-review.md` | Phase 6 only |
| "fix cps" | `base/workflow-post-structural.md` | Phase 5 only |
| "translate" / "vertaal" | Use orchestrator instead | Full pipeline |

## Defaults

See `base/shared-constraints.md` for all hard constraints, formatting rules, and universal translation rules.

## Classification

| Signals | Translator |
|---------|------------|
| Single narrator, formal register, educational/historical | `translators/documentary.md` |
| Character dialogue, narrative scenes, emotional arcs | `translators/drama.md` |
| Jokes, timing-critical punchlines, informal banter | `translators/comedy.md` |
| Multiple speakers, rapid exchanges, panel/talk show | `translators/fast-unscripted.md` |

## Output Filename

Derive from source video:
```
Video:  Shadow_World_(2016)_[imdb-tt2626338]_WEBDL-720p.mkv
Output: Shadow_World_(2016)_[imdb-tt2626338]_WEBDL-720p.nl.srt
```
