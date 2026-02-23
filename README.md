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

| Flag | Effect |
|---|---|
| `--resume` | Resume from last checkpoint |
| `--fresh` | Delete checkpoint and start from phase 0 |
| `--phase N` | Start from phase N |
| `--speech-sync` | Also run Phase 10 (VAD speech sync) |
| `--keep-sdh` | Keep SDH cues (default: Claude removes them during translation) |

### Interactive mode

For individual phases or review tasks, invoke Claude directly with the relevant workflow file loaded.

## Pipeline overview

| Phase | What happens |
|---|---|
| 0a | OCR extraction (optional, for burned-in subs) |
| 0 | Source sync via ffsubsync + WebRTC VAD |
| 1 | Content classification (documentary / drama / comedy / fast-unscripted) |
| 2 | Translation — Claude translates in batches of 100 cues, removes SDH by default |
| 3 | Structural fix (line length, overlaps, gap violations) |
| 4 | Script-based cue merging |
| 5 | CPS optimization (end-time extension + text condensation) |
| 6 | Linguistic review — grammar, naturalness, register |
| 7 | Finalization, renumbering, credit cue |
| 8 | Line balance QC (orphan words, top-heavy pyramids) |
| 9 | VAD timing QC against source audio |
| 10 | Speech sync extension (optional) |

## Standards

- Max 42 characters per line
- Max 2 lines per cue
- CPS optimal: 11 (24fps) / 12 (25fps) — hard limit: 15 (24fps) / 17 (25fps) — emergency max: 20
- Minimum cue gap: 125ms (24fps) / 120ms (25fps) — always 3 frames
- 24-hour time format, metric units, imperial conversion
- No semicolons or exclamation marks (per Auteursbond)
- Dual-speaker cues: second speaker line only gets a dash

## License

Private — not for redistribution.
