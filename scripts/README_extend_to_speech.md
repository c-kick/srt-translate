# Extend to Speech Scripts

Extend subtitle end times to match when the speaker actually stops talking, solving the "slow speaker" problem where subtitles disappear before the speaker finishes.

## The Problem

```
Current:  "Ik sta hier vanavond voor u" ──────┐
                                              │ subtitle disappears
Speaker:  "Ik sta hier vanavond voor u" ──────┴──── still talking ────┘
```

## The Solution

Use Voice Activity Detection (VAD) to find where speech actually ends, then extend the subtitle.

## Two Versions

### 1. `extend_to_speech.py` (Recommended)

Uses **Silero VAD** - more accurate neural network-based detection.

```bash
# Install dependencies
pip install torch torchaudio silero-vad pysubs2

# Or with pipx/venv
python3 -m venv venv
source venv/bin/activate
pip install torch torchaudio silero-vad pysubs2

# Run
python3 extend_to_speech.py video.mkv subtitles.nl.srt -o extended.nl.srt -v
```

### 2. `extend_to_speech_lite.py` (Lightweight)

Uses **WebRTC VAD** - lighter, faster, no PyTorch required.

```bash
# Install dependencies
pip install webrtcvad pysubs2

# Run
python3 extend_to_speech_lite.py video.mkv subtitles.nl.srt -o extended.nl.srt -v
```

## Usage

```bash
# Basic usage
python3 extend_to_speech.py movie.mkv movie.nl.srt -o movie.extended.srt

# Verbose (show each extension)
python3 extend_to_speech.py movie.mkv movie.nl.srt -o extended.srt -v

# Custom parameters
python3 extend_to_speech.py movie.mkv movie.nl.srt -o extended.srt \
    --max-extension 2000 \      # Max 2s extension per cue
    --search-buffer 2000 \      # Search 2s past cue end
    --min-gap 125               # Keep 125ms gap before next cue

# Generate report
python3 extend_to_speech.py movie.mkv movie.nl.srt -o extended.srt \
    --report extensions.json
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--search-buffer` | 3000ms | How far past cue end to search for speech |
| `--max-extension` | 3000ms | Maximum extension per cue |
| `--min-gap` | 125ms | Minimum gap to maintain before next cue |
| `--aggressiveness` | 1 | (lite only) VAD sensitivity 0-3 |

## When to Use

- **Formal speeches** (politicians, ceremonies)
- **Elderly speakers** (slower pace)
- **Documentaries with deliberate narration**
- Any content where speakers talk slower than typical reading speed

## Integration with Workflow

This is an **optional post-processing step** after Phase 6 (Finalization):

```
Phase 6: Finalization
    ↓
[Optional] extend_to_speech.py
    ↓
Final output
```

Add to workflow when content has slow speakers:

```bash
# After finalization
python3 scripts/extend_to_speech.py "$VIDEO" final.nl.srt \
    -o "${VIDEO_BASENAME}.nl.srt" \
    --report logs/speech_extensions.json
```

## Output

```
Loading VAD model...
Extracting audio from video.mkv...
Loading audio...
Loading subtitles from subtitles.nl.srt...
Analyzing 1394 cues for speech boundaries...
Cue 42: +847ms (23490 → 24337)
Cue 43: +312ms (28255 → 28567)
...

Saved to extended.nl.srt

Summary:
  Total cues: 1394
  Extended: 127
  Average extension: 534ms
  Total extension: 67818ms
```
