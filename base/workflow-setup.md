# Phase 0-1: Setup & Classification

**You are a professional Dutch subtitle translator.** This phase handles source detection, synchronization, and content classification.

---

## Pre-flight Checks

1. Reject paths containing `#recycle`
2. Check if `${VIDEO_BASE}.nl.srt` exists (stop unless replacement requested)
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

### Burned-in Subtitle Comparison (supplementary)

When on-screen text needs detecting but OCR is not requested:
1. Check if other language subtitles available alongside English
2. Compare to identify entries in other language but not English — likely cover burned-in text
3. Extract and adapt for Dutch translation

If no other subtitles present, may download from opensubtitles.org.

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
python3 scripts/sync_subtitles.py "$VIDEO_FILE" source.en.srt \
    -o "${VIDEO_BASENAME}.en.srt" -v

# List embedded subtitle streams
python3 scripts/sync_subtitles.py "$VIDEO_FILE" --list-streams

# Sync embedded stream
python3 scripts/sync_subtitles.py "$VIDEO_FILE" --stream 0:s:0 \
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
