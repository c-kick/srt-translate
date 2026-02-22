---
name: srt-translate
description: >
  Vertaal Engelse SRT ondertitelbestanden naar Nederlands, of review bestaande Nederlandse ondertiteling.
  Volgt Netflix Dutch Timed Text Style Guide + Modelrichtlijnen Nederlandse Ondertiteling (Auteursbond).
  Gebruik bij verzoeken om EN→NL ondertitelvertaling, SRT lokalisatie, of review/controle van bestaande NL ondertitels tegen EN bron.
  Niet voor algemene vertaling zonder SRT-bestand, niet voor ondertiteling in andere talen dan Nederlands, niet voor audio-transcriptie.
  Primaire methode: orchestrate.sh pipeline (script-gestuurd, headless).
  Alternatief: interactieve modus voor losse fasen of review.
compatibility: >
  Requires ffmpeg, ffprobe, python3 with venv (ffsubsync, webrtcvad, pysubs2) in scripts/venv/.
  CPU-only system. Claude Code only.
metadata:
  author: Klaas
  version: 12.0
---

# Dutch Subtitle Translation

**You are a professional Dutch subtitle translator.**

## Primary Mode: Orchestrated Pipeline

For full translations, use the orchestrator script:

```bash
./scripts/orchestrate.sh /path/to/video.mkv
```

The orchestrator invokes Claude in headless mode per phase group, each with a fresh context containing only the relevant instructions. This prevents attention degradation on long translations.

| Flag | Effect |
|------|--------|
| `--resume` | Resume from last checkpoint |
| `--phase N` | Start from phase N (0=setup, 2=translate, 3=post) |
| `--speech-sync` | Also run Phase 10 after Phase 9 |

### Phase Groups

| Group | Phases | Claude context loaded |
|-------|--------|----------------------|
| Setup | 0a, 0, 1 | shared-constraints + workflow-setup |
| Translation | 2 | shared-constraints + workflow-translate + translator + exemplars |
| Post-processing | 3-9, LOG | shared-constraints + workflow-post + common-errors |

Each group runs in a separate Claude invocation = fresh context, zero attention debt.

## Interactive Mode: Single Phases

For review, fixes, or individual phases, load the relevant workflow file directly.

| User says | Load | Action |
|-----------|------|--------|
| "review" / "revisie" | `base/workflow-post.md` | Phases 3-9 |
| "grammar" / "grammatica" | `base/workflow-post.md` | Phase 6 only |
| "fix cps" | `base/workflow-post.md` | Phase 5 only |
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
