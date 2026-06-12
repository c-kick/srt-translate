# srt-translate

AI-based deterministic subtitle-translation system for translating timed SRT subtitles to broadcast-quality Dutch. It can be installed as a Claude Code or Codex skill for interactive use, but the primary interface is the scripted `scripts/orchestrate.sh` pipeline. It follows the [Netflix Dutch Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/214969868) and [Modelrichtlijnen Nederlandse Ondertiteling](https://www.auteursbond.nl/) (Auteursbond).

## Example output

A dense dialogue stretch from `I Swear (2025)` shows the pipeline preserving context while tightening the Dutch output for subtitle pacing.

Source EN:

```srt
776
00:53:35,762 --> 00:53:38,677
- How are you doing, Irene?
- Yeah, all right, thanks.

777
00:53:38,678 --> 00:53:41,802
- Is, um, Tommy already in?
- He's in the hall.

778
00:53:41,803 --> 00:53:45,427
Right, well, he's a bit nervous,
so he might be more extreme.

779
00:53:45,428 --> 00:53:46,845
- Hello!
- But you'll get used to it.

780
00:53:46,970 --> 00:53:51,052
- Understood.
- How are you? How you doing?
```

Output NL:

```srt
559
00:53:35,832 --> 00:53:38,623
Alles goed, Irene?
- Ja, prima.

560
00:53:38,748 --> 00:53:41,748
Is Tommy er al?
- Hij is in de zaal.

561
00:53:41,873 --> 00:53:45,373
Hij is wat zenuwachtig,
dus het kan heftiger zijn.

562
00:53:45,498 --> 00:53:48,112
Maar je went eraan.
- Begrepen.

563
00:53:48,237 --> 00:53:50,998
Hoe gaat het?
```

## Architecture

The AI agent handles translation craft. Python scripts handle mechanical subtitle operations.

| AI agent (linguistic) | Scripts (mechanical) |
|---|---|
| Translation quality | CPS calculation and extension |
| Merge decisions | Gap enforcement |
| Register, idiom, V2 word order | Timecode arithmetic |
| Line breaks | Structural validation and renumbering |

The pipeline runs in phase groups, each in a fresh agent invocation to prevent attention degradation on long files.

## Requirements

- [Claude Code](https://claude.ai/code) for the default automated orchestrator backend
- Codex CLI for the optional `--agent codex` automated backend or interactive skill use
- `ffmpeg` and `ffprobe`
- Python 3 with venv (see setup below)
- C build toolchain for `webrtcvad` when no matching wheel is available (`sudo apt-get install build-essential` on Debian/Ubuntu)

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/c-kick/srt-translate.git
```

### 2. Optional: install as a skill

The orchestrator can run directly from the cloned repository. Skill installation is only needed when you want Claude Code or Codex to discover `$srt-translate` for interactive phase work.

#### Claude Code

Place or symlink the skill folder in your Claude Code skills directory:

```bash
ln -s /path/to/srt-translate ~/.claude/skills/srt-translate
```

#### Codex

Place or symlink the skill folder in your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
ln -s /path/to/srt-translate ~/.codex/skills/srt-translate
```

Codex discovers the skill from `SKILL.md`. The optional `agents/openai.yaml` file provides UI-facing metadata for Codex surfaces that display installed skills.

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

The full pipeline uses the `claude` CLI by default. To run the same phase groups through Codex instead, pass `--agent codex` or the `--codex` shortcut. Claude-specific options such as `--effort` and `--budget-cap-usd` are ignored by the Codex backend. Claude model aliases like `sonnet` and `opus` are not mapped to GPT names; in Codex mode they display as `codex default` and no `--model` flag is passed unless you explicitly provide a non-Claude model name.

| Flag | Effect | Default |
|---|---|---|
| `--resume` | Resume from last checkpoint without prompting | off — prompts if a checkpoint exists |
| `--fresh` | Delete checkpoint and start from phase 0 | off |
| `--polish` | Skip translation — post-process an existing `.nl.srt` (see below) | off — full pipeline |
| `--augment-missing` | Add only missing burned-in/title-card cues to an existing `.nl.srt` (see below) | off — full pipeline |
| `--phase N` | Start from phase N | off — runs from phase 0 |
| `--speech-sync` | Also run Phase 10 (VAD speech sync) after Phase 9 | off — Phase 10 is skipped |
| `--keep-sdh` | Keep SDH cues in the output | off — SDH-only cues are removed during translation |
| `--keep-work` | Preserve work dir after completion (debugging) | off — work dir deleted on success |
| `--no-embedded` | Skip embedded subtitle extraction; use the existing external `.en.srt` only. Use when the video has burn-in subs or embedded subs covering only foreign-language parts (not the main dialogue). | off — embedded subs preferred when present |
| `--source-srt PATH` | Use this subtitle as source instead of `VIDEO_BASE.en.srt` | unset |
| `--source-language LANG` | Tell the translator what language the source subtitle is in | `English` |
| `--output-srt PATH` | Write the final Dutch subtitle somewhere other than `VIDEO_BASE.nl.srt` | unset |
| `--source-ready` | Treat `--source-srt` as already synced and classified; skip setup and start at translation | off |
| `--max-batches N` | Limit translation to N batches (testing) | 0 (unlimited) |
| `--agent claude\|codex` | Choose the headless agent backend | `claude` |
| `--codex` | Shortcut for `--agent codex` | off |
| `--effort LEVEL` | Thinking effort per invocation: `low`, `medium`, `high`, `xhigh`, `max`. Ignored by Codex. | `medium` (pinned — not inherited from CLI default) |
| `--budget-cap-usd AMOUNT` | Hard cost cap applied **per Claude invocation**. Ignored by Codex. If exceeded, that invocation aborts and the phase fails. Scope: setup = 1 invocation, translation = 1 invocation per group of up to 6 batches (~1200 cues), post-processing = 3 invocations. Historical per-invocation costs are in `logs/srt-translate/cost_log.jsonl`. | **uncapped** |
| `--model MODEL` | Override the model for all phases. In Claude mode, accepts aliases (`sonnet`, `opus`, `haiku`) or a pinned Claude model ID. In Codex mode, pass an actual Codex/OpenAI model name; Claude aliases are ignored and Codex uses its configured default. Per-phase control via `MODEL_SETUP`, `MODEL_TRANSLATE`, `MODEL_POST` env vars or the per-phase flags below. | `sonnet` (setup/post), `opus` (translation) for Claude; `codex default` for Codex |
| `--model-setup MODEL` | Override the model for Phases 0–1 only. Wins over `--model` and the `MODEL_SETUP` env var. | unset — falls back to `--model` / env / default |
| `--model-translation MODEL` | Override the model for Phase 2 (translation) only. Wins over `--model` and the `MODEL_TRANSLATE` env var. | unset — falls back to `--model` / env / default |
| `--model-post MODEL` | Override the model for Phases 3–10 (post-processing) only. Wins over `--model` and the `MODEL_POST` env var. | unset — falls back to `--model` / env / default |

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

What you gain: merging, timing quality, CPS compliance, grammar fixes, and line balance without running the full translation phase again. Translation accuracy issues may persist where they existed in the original, but the linguistic review phase (Phase 6) checks the Dutch subtitle against the source.

### Augment missing mode — add burned-in subtitles to an existing Dutch subtitle

`--augment-missing` updates an existing `.nl.srt` by adding only missing burned-in/title-card cues. It runs setup and title-card detection, extracts detected `[TITLE CARD: ...]` cues from the synced English source, filters out cues already covered by the existing Dutch subtitle, translates only the remaining missing cues, then merges them into the existing `.nl.srt` in time order.

```bash
./scripts/orchestrate.sh /path/to/video.mkv --augment-missing
```

This mode creates a timestamped backup of the existing `.nl.srt` before merging. It intentionally does not run the full post-processing stack, so the existing translation is not rewritten beyond inserted missing cues.

### External source mode — translate from almost any timed SRT to Dutch

Use `--source-srt`, `--source-language`, `--output-srt`, and `--source-ready` when the best source subtitle is an external SRT in another language, such as a Portuguese, Spanish, French, German, or Italian full subtitle that already includes burned-in/on-screen text. This mode makes the source language explicit in the translation prompt.

```bash
./scripts/orchestrate.sh /path/to/video.mkv \
  --source-srt /path/to/source.pt.utf8.srt \
  --source-language Portuguese \
  --source-ready \
  --output-srt /path/to/video.dut.srt \
  --agent codex
```

`--source-ready` means the source subtitle is the timing/content authority: setup extraction, sync, and title-card detection are skipped. The pipeline writes a deterministic checkpoint from the source cue count and video framerate, then runs translation and post-processing normally. Use this when the external source subtitle is already synced well enough to the video.

Supported shape:

- Source can be any language the selected agent/model can translate reliably.
- Target is still Dutch; this is not a general arbitrary-target-language pipeline.
- Source must be an SRT file with usable cue numbers and timestamps.
- Source should be UTF-8. Convert legacy encodings first, for example:

```bash
iconv -f ISO-8859-1 -t UTF-8 source.pt.srt -o source.pt.utf8.srt
```

Recommended safety pattern:

```bash
./scripts/orchestrate.sh "/path/to/movie.mkv" \
  --source-srt "/path/to/source.es.utf8.srt" \
  --source-language Spanish \
  --source-ready \
  --output-srt "/path/to/movie.es-nl.srt" \
  --agent codex \
  --keep-work
```

Always use `--output-srt` for external source experiments so existing `.nl.srt` files are not replaced. The work directory is useful for inspecting the draft, merge reports, glossary, and batch context.

Do not use `--source-ready` when the external subtitle is visibly out of sync. In that case, sync or repair the source SRT first, then run the source-ready pipeline.

### Interactive mode

For individual phases or review tasks, invoke your agent directly with the relevant workflow file loaded. In Codex, start with `$srt-translate` and ask for the specific phase or review task; the skill will point Codex to the relevant `base/`, `references/`, and `translators/` files. For the scripted pipeline, use `./scripts/orchestrate.sh /path/to/video.mkv --agent codex`.

## Pipeline overview

| Phase | What happens | Default Claude model |
|---|---|---|
| 0a | OCR extraction (optional, for burned-in subs) | — |
| 0 | Source sync via ffsubsync + WebRTC VAD | — |
| 0b | Title card detection — fetches a foreign subtitle from OpenSubtitles by IMDb ID only, then compares it with the English source locally (requires `OPENSUBTITLES_API_KEY`) | — |
| 1 | Content classification (documentary / drama / comedy / fast-unscripted) | Sonnet |
| 2 | Translation — the selected agent translates in batches of 200 cues and removes SDH by default *(skipped in `--polish` mode)* | **Opus** |
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

### OpenSubtitles privacy boundary

Title-card detection is split into two steps so approval reviewers can judge the data flow correctly:

- `scripts/fetch_foreign_subtitle.py` is the only OpenSubtitles network step. It receives only an IMDb ID, language filters, the API key, and OpenSubtitles file IDs. It does not accept local video or subtitle paths.
- `scripts/detect_title_cards.py` is local-only. It reads the synced English SRT and the downloaded foreign SRT, compares cue timings, and writes `title_cards.srt`.

## Standards

- Max 42 characters per line
- Max 2 lines per cue
- CPS optimal: 11 (24fps) / 12 (25fps) — hard limit: 15 (24fps) / 17 (25fps) — emergency max: 20
- Minimum cue gap: 125ms (24fps) / 120ms (25fps) — always 3 frames
- 24-hour time format, metric units, imperial conversion
- No semicolons or exclamation marks (per Auteursbond)
- Dual-speaker cues: second speaker line only gets a dash

## Troubleshooting

### Setup phase finishes but no checkpoint file is written

Symptom: the orchestrator logs a normal `Cost:` line for the Setup phase, then aborts with `ERROR: Setup phase did not write checkpoint file`. The Claude output contains a sentence like *"The write requires your permission — please approve the prompt to write the checkpoint file to ..."*.

Cause: this is not a real permission error. The orchestrator passes `--allowedTools` that already includes `Write`, so file writes are auto-approved in headless mode. The message is text Claude *wrote as its final response* instead of actually calling the `Write` tool — i.e. the model hallucinated a permission prompt rather than executing the write.

This has been observed with `--model claude-sonnet-4-6`. Sonnet is weaker at this pipeline in general (fewer `[SC]` markers, weaker idioms, occasional tool-call defects).

Fix: drop the `--model` flag and let Opus run (the default), or pass `--model claude-opus-4-7` explicitly. Re-run with `--fresh` or `--resume` as appropriate.

### `claude -p` returns a session-limit error or no output

The default `claude` backend still invokes Claude Code through `claude -p --output-format json`. If a run fails before doing work, test the backend directly:

```bash
printf '%s\n' 'Return exactly OK.' | env -u CLAUDECODE claude -p --output-format json
```

Observed failure on Claude Code `2.1.175`: the command can return JSON with `api_error_status: 429`, `is_error: true`, and a result like `You've hit your session limit`. In that case the CLI path exists, but the Claude account/session quota is blocking the backend. Wait for the reset or run the pipeline with Codex:

```bash
./scripts/orchestrate.sh "<video>" --agent codex
```

If `claude -p` produces 0 bytes of output and exits silently, check whether the orchestrator was launched with `nohup`. This repository has an older observed failure where `nohup` broke `claude -p` around CLI `2.1.87`. Prefer plain backgrounding:

```bash
env -u CLAUDECODE bash orchestrate.sh "<video>" [flags] > /tmp/job.log 2>&1 &
```

### Timestamp drift between EN source and NL output

`validate_srt.py --source <en.srt>` compares NL timestamps to the source. Phase 3 and Phase 7 run this automatically. If `drift_errors` is non-empty, restore the timestamps from the source before continuing; see the Phase 3 recovery steps in `base/workflow-post-structural.md`.

## License

[MIT](LICENSE) — © 2026 c_kick/Klaas Leussink
