# Phase 0-1: Setup & Classification

**You are a professional Dutch subtitle translator.** This phase handles source detection, synchronization, and content classification.

---

## Pre-flight Checks

1. Reject paths containing `#recycle`
2. Check if `${VIDEO_BASE}.nl.srt` exists — if running via orchestrator, overwrite is pre-approved (continue without asking). Only stop in interactive mode if replacement was not requested.
3. Validate source file exists and is readable

---

## Phase 0a: OCR Extraction (optional)

**When:** User mentions burned-in subtitles, hardcoded text, or OCR — or no text-based English subs exist and the video has burned-in English text.

```bash
cd ~/video-subtitle-extractor && ~/vse-env/bin/python extract_burned_subs.py \
    "$VIDEO_FILE" \
    --output "${VIDEO_BASENAME}.ocr.en.srt" \
    --lang en \
    --interval 1
```

| Flag | Default | Description |
|------|---------|-------------|
| `--lang` | `en` | OCR language |
| `--interval` | `1` | Sampling interval in seconds |
| `--start` / `--end` | - | Limit to time range (seconds) |
| `--y1 --y2` | bottom 25% of frame (1080p) | Subtitle region Y coordinates |

**Performance:** ~3.7 fps on CPU (i3-13100T). A 100-min video takes ~27 minutes.

**After OCR completes:**
- Review output — OCR picks up scene text (logos, credits) as noise. Remove non-subtitle entries.
- **If OCR is primary source** (no text-based English subs): use `.ocr.en.srt` for Phase 2. **Skip Phase 0** — OCR timestamps are frame-accurate.
- **If OCR supplements existing source**: translate regular source normally, translate OCR'd entries separately, merge into final `.nl.srt`.

---

## Source Detection

**Embedded text-based (not VOBSUB) subtitles preferred** (correct timing):
```bash
ffprobe -v error -select_streams s -show_entries stream=index,codec_name:stream_tags=language -of json "$VIDEO_FILE"
ffmpeg -i "$VIDEO_FILE" -map 0:s:0 -c:s srt source.en.srt
python3 scripts/validate_srt.py source.en.srt --verbose
```

If no embedded subtitles, use external `.en.srt` file.

---

## Phase 0b: Title Card Detection (automatic)

**Always run** after Phase 0 sync, before Phase 1 classification.

Documentaries and historical films often have burned-in English title cards (dates, locations, names) that are absent from the English SRT but present in foreign-language subtitles. This phase detects them by downloading a foreign subtitle from OpenSubtitles and comparing timestamps.

```bash
scripts/run-venv.sh scripts/fetch_title_cards.py \
    "${VIDEO_BASENAME}.en.srt" \
    "$VIDEO_FILE" \
    --output "${WORK_DIR}/title_cards.srt" \
    --timeout 15
```

**Exit codes:**
| Code | Meaning | Action |
|------|---------|--------|
| 0 | Title cards found → `title_cards.srt` written | Merge into source (see below) |
| 1 | No title cards found / no foreign sub available | Continue without changes |
| 2 | Skipped (no API key, network error, timeout) | Continue without changes; log warning |

**Requires:** `OPENSUBTITLES_API_KEY` env var, or `~/.config/srt-translate/os_api_key` file.
If neither is present the script exits with code 2 and the phase is silently skipped.

### If title cards found (exit code 0):

Merge the title card cues into the synced English SRT by inserting each cue at the correct timecode position with a `[TITLE CARD]` prefix:

```python
# Each cue in title_cards.srt: insert into .en.srt at its timecode
# with text: [TITLE CARD: "<foreign text>"]
# The foreign text is a hint — translator reads the actual on-screen English,
# uses the foreign text as a reference to understand what it says.
python3 -c "
import pysubs2, sys
en = pysubs2.load('${VIDEO_BASENAME}.en.srt')
tc = pysubs2.load('${WORK_DIR}/title_cards.srt')
for c in tc:
    import pysubs2 as p
    ev = p.SSAEvent(start=c.start, end=c.end, text='[TITLE CARD: \"' + c.plaintext.replace('\"','') + '\"]')
    en.append(ev)
en.sort()
en.save('${VIDEO_BASENAME}.en.srt')
print(f'Merged {len(tc)} title card(s) into source SRT')
"
```

**Note in checkpoint:**
```
- **Title cards:** N found and merged into source (from [lang] subtitle)
```

### If no title cards / skipped:

Note in checkpoint:
```
- **Title cards:** none detected / skipped
```

---

## Framerate Detection

Detect source framerate before starting any phase:

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$VIDEO_FILE"
```

Classify: `< 24.5` → **24**, `≥ 24.5` → **25**. Include in checkpoint.

---

## Phase 0: Source Sync

**Always run sync.** Ensures source is aligned with audio before translation.

```bash
# Sync external SRT
scripts/run-venv.sh scripts/sync_subtitles.py "$VIDEO_FILE" source.en.srt \
    -o "${VIDEO_BASENAME}.en.srt" -v

# List embedded subtitle streams
scripts/run-venv.sh scripts/sync_subtitles.py "$VIDEO_FILE" --list-streams

# Sync embedded stream
scripts/run-venv.sh scripts/sync_subtitles.py "$VIDEO_FILE" --stream 0:s:0 \
    -o "${VIDEO_BASENAME}.en.srt" -v
```

**Output:** Synced file uses video basename (e.g., `Shadow World (2016).en.srt`), becomes both:
1. Improved English subtitle for the video
2. Source for Dutch translation in Phase 2

**Interpreting results:**
- Offset ~0ms: already in sync
- Offset >500ms: timing was corrected

**Embedded streams:** Script automatically uses `--vad webrtc` for embedded subtitles.

---

## Phase 1: Analysis & Classification

Read first 50-100 cues. Analyze for:
- Speaker count and patterns
- Register (formal/informal)
- Dialogue vs narration ratio
- Timing characteristics

### Classification Table

| Signals | Translator |
|---------|------------|
| Single narrator, formal register, educational/historical | `documentary` |
| Character dialogue, narrative scenes, emotional arcs | `drama` |
| Jokes, timing-critical punchlines, informal banter | `comedy` |
| Multiple speakers, rapid exchanges, panel/talk show | `fast-unscripted` |

### Examples

| Content | Classification |
|---------|----------------|
| Nature documentary | documentary |
| WWII documentary with interviews | documentary |
| Breaking Bad | drama |
| The Office | comedy |
| Ghostbusters | comedy |
| Talk show | fast-unscripted |
| Stand-up special | comedy |

**If no translator exists for this classification, STOP and inform user.**

---

## Phase 1b: Subject Research

Before translating, familiarize yourself with the subject. This applies to all genres.

- **Look up the title** (show, film, or documentary) to understand its premise, setting, era, and tone.
- **Identify recurring proper nouns** from the first 50–100 cues: character names, locations, organizations, technical terms. Check Dutch Wikipedia (`nl.wikipedia.org`) for established Dutch equivalents where relevant (e.g. "charades" → "Hints", period-specific place names, scientific terminology).
- **Recognize quotes or speeches** — if you recognize a fragment as a known speech, historical quote, or famous line, look it up to translate with the correct connotation and register.
- **Note the era and domain** — a 1940s war film, a medical drama, and a tech startup comedy each require different vocabulary. Identify the domain now so you can apply the right register and jargon consistently throughout.
- **Cultural references** — note any references (games, TV shows, idioms, slang) that may need Dutch equivalents. Flag ones that need localization research when you encounter them during translation.

Add any established terms to the **Terminology** section of the checkpoint.

---

## Output Filename

Derive from source video:
```
Video:  Shadow_World_(2016)_[imdb-tt2626338]_WEBDL-720p.mkv
Output: Shadow_World_(2016)_[imdb-tt2626338]_WEBDL-720p.nl.srt
```

---

## Write Checkpoint

After classification, write checkpoint to `$CHECKPOINT_FILE`:

```markdown
# Translation Checkpoint

## Video
- **File:** [full path to video]
- **Source:** [full path to .en.srt]
- **Output:** [full path to .nl.srt]

## Progress
- **Current phase:** 1 (classification complete)
- **Next phase:** 2 (translation)

## Phase 1 Results
- **Framerate:** [24 or 25]
- **Classification:** [documentary/drama/comedy/fast-unscripted]
- **Source cues:** [count]
- **OCR used:** [yes/no]
- **Sync offset:** [Nms]

## Terminology
- [initial key terms if identified]

## Register
- [initial register choices if identified]
```

**This checkpoint is read by the orchestrator to determine translator and exemplar loading for Phase 2.**
