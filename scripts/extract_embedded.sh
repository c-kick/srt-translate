#!/bin/bash
#
# Extract embedded subtitles from video file using ffmpeg.
#
# Usage:
#     ./extract_embedded.sh <video_path> [--list-only] [--track N] [--output <path>]
#
# Dependencies: ffprobe, ffmpeg
#
# Output (JSON):
#     {
#         "video_file": "movie.mkv",
#         "subtitle_tracks": [...],
#         "extracted": "movie.en.srt",
#         "error": null
#     }

set -e

VIDEO_PATH=""
LIST_ONLY=false
TRACK_NUM=""
OUTPUT_PATH=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --list-only)
            LIST_ONLY=true
            shift
            ;;
        --track)
            TRACK_NUM="$2"
            shift 2
            ;;
        --output)
            OUTPUT_PATH="$2"
            shift 2
            ;;
        *)
            if [[ -z "$VIDEO_PATH" ]]; then
                VIDEO_PATH="$1"
            fi
            shift
            ;;
    esac
done

# Check video path
if [[ -z "$VIDEO_PATH" ]]; then
    echo '{"error": "No video path provided"}'
    exit 1
fi

if [[ ! -f "$VIDEO_PATH" ]]; then
    echo "{\"error\": \"Video file not found: $VIDEO_PATH\"}"
    exit 1
fi

# Check ffprobe
if ! command -v ffprobe &> /dev/null; then
    echo '{"error": "ffprobe not found. Install ffmpeg."}'
    exit 1
fi

# Get subtitle track info
SUBTITLE_INFO=$(ffprobe -v quiet -print_format json -show_streams -select_streams s "$VIDEO_PATH" 2>/dev/null || echo '{"streams":[]}')

# Parse subtitle tracks
TRACKS=$(echo "$SUBTITLE_INFO" | python3 -c "
import sys, json
data = json.load(sys.stdin)
tracks = []
for i, stream in enumerate(data.get('streams', [])):
    track = {
        'index': stream.get('index'),
        'stream_index': i,
        'codec': stream.get('codec_name'),
        'language': stream.get('tags', {}).get('language', 'und'),
        'title': stream.get('tags', {}).get('title', '')
    }
    tracks.append(track)
print(json.dumps(tracks))
")

# If list only, output tracks and exit
if [[ "$LIST_ONLY" == true ]]; then
    echo "{\"video_file\": \"$VIDEO_PATH\", \"subtitle_tracks\": $TRACKS, \"extracted\": null}"
    exit 0
fi

# Check if any tracks exist
TRACK_COUNT=$(echo "$TRACKS" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")

if [[ "$TRACK_COUNT" -eq 0 ]]; then
    echo "{\"video_file\": \"$VIDEO_PATH\", \"subtitle_tracks\": [], \"extracted\": null, \"error\": \"No subtitle tracks found\"}"
    exit 0
fi

# Determine which track to extract
if [[ -z "$TRACK_NUM" ]]; then
    # Try to find English track first
    TRACK_NUM=$(echo "$TRACKS" | python3 -c "
import sys, json
tracks = json.load(sys.stdin)
for t in tracks:
    if t['language'] in ('eng', 'en', 'english'):
        print(t['stream_index'])
        sys.exit(0)
# Fall back to first track
if tracks:
    print(tracks[0]['stream_index'])
")
fi

# Determine output path
if [[ -z "$OUTPUT_PATH" ]]; then
    BASENAME="${VIDEO_PATH%.*}"
    OUTPUT_PATH="${BASENAME}.extracted.srt"
fi

# Check ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo '{"error": "ffmpeg not found"}'
    exit 1
fi

# Extract subtitle track
if ffmpeg -v quiet -y -i "$VIDEO_PATH" -map "0:s:$TRACK_NUM" -c:s srt "$OUTPUT_PATH" 2>/dev/null; then
    echo "{\"video_file\": \"$VIDEO_PATH\", \"subtitle_tracks\": $TRACKS, \"extracted\": \"$OUTPUT_PATH\", \"track_extracted\": $TRACK_NUM}"
    exit 0
else
    # Try with different codec
    if ffmpeg -v quiet -y -i "$VIDEO_PATH" -map "0:s:$TRACK_NUM" "$OUTPUT_PATH" 2>/dev/null; then
        echo "{\"video_file\": \"$VIDEO_PATH\", \"subtitle_tracks\": $TRACKS, \"extracted\": \"$OUTPUT_PATH\", \"track_extracted\": $TRACK_NUM}"
        exit 0
    else
        echo "{\"video_file\": \"$VIDEO_PATH\", \"subtitle_tracks\": $TRACKS, \"extracted\": null, \"error\": \"Failed to extract track $TRACK_NUM\"}"
        exit 1
    fi
fi
