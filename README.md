# srt-translate

A [Claude Code](https://claude.ai/code) skill for translating English SRT subtitle files to broadcast-quality Dutch. Follows the [Netflix Dutch Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/214969868) and [Modelrichtlijnen Nederlandse Ondertiteling](https://www.auteursbond.nl/) (Auteursbond).

## Architecture

Claude handles translation craft. Python scripts handle everything mechanical.

| Claude (linguistic) | Scripts (mechanical) |
|---|---|
| Translation quality | CPS calculation and extension |
| Merge decisions | Gap enforcement |
| Register, idiom, V2 word order | Timecode arithmetic |
| Line breaks | Structural validation and renumbering |

The pipeline runs in phase groups, each in a fresh Claude invocation to prevent attention degradation on long files.

## Requirements

- [Claude Code](https://claude.ai/code)
- `ffmpeg` and `ffprobe`
- Python 3 with venv (see setup below)

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/c-kick/srt-translate.git
```

### 2. Install the skill in Claude Code

Place or symlink the skill folder in your Claude Code skills directory:

```bash
ln -s /path/to/srt-translate ~/.claude/skills/srt-translate
```

### 3. Set up the Python venv

```bash
bash scripts/setup.sh
```

This installs `ffsubsync`, `webrtcvad`, `pysubs2`, and other dependencies into `scripts/venv/`.

## Usage

### Full pipeline (recommended)

```bash
./scripts/orchestrate.sh /path/to/video.mkv
```

| Flag | Effect | Default |
|---|---|---|
| `--resume` | Resume from last checkpoint without prompting | off — prompts if a checkpoint exists |
| `--fresh` | Delete checkpoint and start from phase 0 | off |
| `--polish` | Skip translation — post-process an existing `.nl.srt` (see below) | off — full pipeline |
| `--phase N` | Start from phase N | off — runs from phase 0 |
| `--speech-sync` | Also run Phase 10 (VAD speech sync) after Phase 9 | off — Phase 10 is skipped |
| `--keep-sdh` | Keep SDH cues in the output | off — Claude removes SDH during translation |
| `--keep-work` | Preserve work dir after completion (debugging) | off — work dir deleted on success |
| `--max-batches N` | Limit translation to N batches (testing) | 0 (unlimited) |
| `--effort LEVEL` | Thinking effort per invocation: `low`, `medium`, `high`, `xhigh`, `max` | `medium` (pinned — not inherited from CLI default) |
| `--budget-cap-usd AMOUNT` | Hard cost cap applied **per Claude invocation**. If exceeded, that invocation aborts and the phase fails. Scope: setup = 1 invocation, translation = 1 invocation per group of up to 6 batches (~1200 cues), post-processing = 3 invocations. Historical per-invocation costs are in `logs/srt-translate/cost_log.jsonl`. | **uncapped** |
| `--model MODEL` | Override the model for all phases. Per-phase control via `MODEL_SETUP`, `MODEL_TRANSLATE`, `MODEL_POST` env vars. | `sonnet` (setup/post), `opus` (translation) |

### Polish mode — upgrade an existing Dutch subtitle

`--polish` skips Phase 2 (translation) entirely and runs post-processing on an existing `.nl.srt` file. It works with any Dutch subtitle — previous translations made with this skill, older versions, or subtitles downloaded from third-party sources like OpenSubtitles or Bazarr.

```bash
./scripts/orchestrate.sh /path/to/video.mkv --polish
```

What it does:
1. Runs setup (Phase 0–1): syncs the English source, runs title card detection, classifies content
2. Seeds the work pipeline with the existing `.nl.srt` as the translation draft
3. Runs a **speaker change marker pass** (Opus): reads the EN source and NL draft side-by-side, adds `[SC]`/`[NM]` markers to NL cues where speaker changes occur — no text changes, only markers. This ensures the merge script (Phase 4) doesn't produce false merges across speaker boundaries.
4. Runs all post-processing phases (3–9): structural fix, cue merging, CPS optimization, linguistic review, finalization, line balance QC, VAD timing

What you gain: merging, timing quality, CPS compliance, grammar fixes, line balance — at roughly **30% of the token cost** of a full retranslation. Translation accuracy issues may persist where they existed in the original, but the linguistic review phase (Phase 6) catches the most egregious errors using the English source as reference.

### Interactive mode

For individual phases or review tasks, invoke Claude directly with the relevant workflow file loaded.

## Pipeline overview

| Phase | What happens | Model |
|---|---|---|
| 0a | OCR extraction (optional, for burned-in subs) | — |
| 0 | Source sync via ffsubsync + WebRTC VAD | — |
| 0b | Title card detection — downloads foreign subtitle from OpenSubtitles, identifies burned-in cues missing from the English source (requires `OPENSUBTITLES_API_KEY`) | — |
| 1 | Content classification (documentary / drama / comedy / fast-unscripted) | Sonnet |
| 2 | Translation — Claude translates in batches of 200 cues, removes SDH by default *(skipped in `--polish` mode)* | **Opus** |
| 3 | Structural fix (line length, overlaps, gap violations) | Sonnet |
| 4 | Script-based cue merging | — |
| 4b | Trim-to-speech — pulls back cue end times that linger past speech using VAD | — |
| 5 | CPS optimization (end-time extension + text condensation) | Sonnet |
| 6 | Linguistic review — grammar, naturalness, register (uses English source as reference) | Sonnet |
| 7 | Finalization, renumbering, credit cue | — |
| 8 | Line balance QC (orphan words, top-heavy pyramids) | Sonnet |
| 9 | VAD timing QC against source audio | Sonnet |
| 10 | Speech sync extension (optional) | — |

Models are configurable via env vars: `MODEL_SETUP` (phases 0–1), `MODEL_TRANSLATE` (phase 2), `MODEL_POST` (phases 3–10).

## Standards

- Max 42 characters per line
- Max 2 lines per cue
- CPS optimal: 11 (24fps) / 12 (25fps) — hard limit: 15 (24fps) / 17 (25fps) — emergency max: 20
- Minimum cue gap: 125ms (24fps) / 120ms (25fps) — always 3 frames
- 24-hour time format, metric units, imperial conversion
- No semicolons or exclamation marks (per Auteursbond)
- Dual-speaker cues: second speaker line only gets a dash

## License

[MIT](LICENSE) — © 2026 c_kick/Klaas Leussink
