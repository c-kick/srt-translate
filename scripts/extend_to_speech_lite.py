#!/usr/bin/env python3
"""
Extend subtitle end times to match actual speech end using WebRTC VAD.

Lightweight alternative to extend_to_speech.py - no PyTorch required.
Uses Google's WebRTC Voice Activity Detection.

Usage:
    python3 extend_to_speech_lite.py video.mkv subtitles.srt --output extended.srt

Requirements:
    pip install webrtcvad pysubs2

"""

import argparse
import subprocess
import tempfile
import os
import sys
import wave
import struct
from pathlib import Path
from collections import deque

try:
    import webrtcvad
except ImportError:
    print("Missing webrtcvad. Install with:")
    print("  pip install webrtcvad")
    sys.exit(1)

try:
    import pysubs2
except ImportError:
    print("Missing pysubs2. Install with:")
    print("  pip install pysubs2")
    sys.exit(1)


# WebRTC VAD operates on 10, 20, or 30ms frames
FRAME_DURATION_MS = 30
SAMPLE_RATE = 16000
SAMPLES_PER_FRAME = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)


def extract_audio(video_path: str, output_path: str) -> bool:
    """Extract audio from video file using ffmpeg."""
    cmd = [
        'ffmpeg', '-y', '-i', video_path,
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', str(SAMPLE_RATE),
        '-ac', '1',
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except FileNotFoundError:
        print("Error: ffmpeg not found. Install it with: apt install ffmpeg", file=sys.stderr)
        return False
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr.decode()}")
        return False


def read_wave(path: str) -> tuple[bytes, int]:
    """Read a wave file and return (audio_bytes, sample_rate)."""
    with wave.open(path, 'rb') as wf:
        assert wf.getnchannels() == 1, "Must be mono"
        assert wf.getsampwidth() == 2, "Must be 16-bit"
        sample_rate = wf.getframerate()
        audio = wf.readframes(wf.getnframes())
    return audio, sample_rate


def frame_generator(audio: bytes, frame_duration_ms: int, sample_rate: int):
    """Generate audio frames from raw audio bytes."""
    n = int(sample_rate * (frame_duration_ms / 1000.0) * 2)  # 2 bytes per sample
    offset = 0
    while offset + n <= len(audio):
        yield audio[offset:offset + n]
        offset += n


def ms_to_byte_offset(ms: int, sample_rate: int) -> int:
    """Convert milliseconds to byte offset in 16-bit mono audio."""
    return int(ms * sample_rate / 1000) * 2


def byte_offset_to_ms(offset: int, sample_rate: int) -> int:
    """Convert byte offset to milliseconds."""
    return int(offset / 2 * 1000 / sample_rate)


def find_speech_end_vad(
    audio: bytes,
    vad: webrtcvad.Vad,
    cue_start_ms: int,
    cue_end_ms: int,
    sample_rate: int,
    search_buffer_ms: int = 3000,
    min_silence_frames: int = 10  # ~300ms at 30ms frames
) -> int:
    """
    Find when speech ends after the cue's current end time.

    Uses a sliding window to detect when speech transitions to silence.
    """
    # Calculate byte offsets
    search_start = ms_to_byte_offset(cue_start_ms, sample_rate)
    search_end = ms_to_byte_offset(cue_end_ms + search_buffer_ms, sample_rate)

    # Clamp to audio bounds
    search_start = max(0, search_start)
    search_end = min(len(audio), search_end)

    # Align to frame boundaries
    frame_bytes = SAMPLES_PER_FRAME * 2
    search_start = (search_start // frame_bytes) * frame_bytes

    if search_start >= search_end:
        return cue_end_ms

    # Analyze frames
    cue_end_offset = ms_to_byte_offset(cue_end_ms, sample_rate)
    last_speech_offset = search_start
    silence_count = 0

    offset = search_start
    while offset + frame_bytes <= search_end:
        frame = audio[offset:offset + frame_bytes]

        try:
            is_speech = vad.is_speech(frame, sample_rate)
        except Exception:
            # Invalid frame, skip
            offset += frame_bytes
            continue

        if is_speech:
            last_speech_offset = offset + frame_bytes
            silence_count = 0
        else:
            silence_count += 1
            # If we're past the cue end and have enough silence, stop
            if offset > cue_end_offset and silence_count >= min_silence_frames:
                break

        offset += frame_bytes

    speech_end_ms = byte_offset_to_ms(last_speech_offset, sample_rate)

    return max(speech_end_ms, cue_end_ms)


def extend_subtitles(
    subs: pysubs2.SSAFile,
    audio: bytes,
    vad: webrtcvad.Vad,
    sample_rate: int,
    search_buffer_ms: int = 3000,
    min_gap_ms: int = 125,
    max_extension_ms: int = 3000,
    verbose: bool = False
) -> tuple[pysubs2.SSAFile, dict]:
    """Extend subtitle end times to match speech end."""

    report = {
        'total_cues': len(subs),
        'extended_cues': 0,
        'total_extension_ms': 0,
        'extensions': []
    }

    for i, cue in enumerate(subs):
        # Determine max end time
        if i + 1 < len(subs):
            max_end = subs[i + 1].start - min_gap_ms
        else:
            max_end = cue.end + max_extension_ms

        max_end = min(max_end, cue.end + max_extension_ms)

        if max_end <= cue.end:
            continue

        # Find speech end
        speech_end = find_speech_end_vad(
            audio,
            vad,
            cue.start,
            cue.end,
            sample_rate,
            search_buffer_ms=min(search_buffer_ms, max_end - cue.end + 500)
        )

        if speech_end > cue.end:
            new_end = min(speech_end + 100, max_end)
            extension = new_end - cue.end

            if extension > 50:
                report['extended_cues'] += 1
                report['total_extension_ms'] += extension
                report['extensions'].append({
                    'cue': i + 1,
                    'old_end': cue.end,
                    'new_end': new_end,
                    'extension_ms': extension,
                    'text': cue.text[:50] + ('...' if len(cue.text) > 50 else '')
                })

                if verbose:
                    print(f"Cue {i+1}: +{extension}ms ({cue.end} → {new_end})")

                cue.end = new_end

    return subs, report


def main():
    parser = argparse.ArgumentParser(
        description='Extend subtitle end times to match speech (lightweight version).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 extend_to_speech_lite.py movie.mkv movie.nl.srt -o extended.srt
    python3 extend_to_speech_lite.py movie.mkv movie.nl.srt -o extended.srt -v --aggressiveness 2
        """
    )

    parser.add_argument('video', help='Video file')
    parser.add_argument('subtitles', help='SRT subtitle file')
    parser.add_argument('-o', '--output', required=True, help='Output SRT file')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--aggressiveness', type=int, default=1, choices=[0, 1, 2, 3],
                        help='VAD aggressiveness (0=least, 3=most aggressive, default: 1)')
    parser.add_argument('--search-buffer', type=int, default=3000,
                        help='Search buffer past cue end (ms, default: 3000)')
    parser.add_argument('--max-extension', type=int, default=3000,
                        help='Max extension per cue (ms, default: 3000)')
    parser.add_argument('--min-gap', type=int, default=125,
                        help='Min gap before next cue (ms, default: 125)')
    parser.add_argument('--keep-audio', action='store_true')
    parser.add_argument('--report', help='Write JSON report to file')

    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video not found: {args.video}")
        sys.exit(1)

    if not os.path.exists(args.subtitles):
        print(f"Error: Subtitles not found: {args.subtitles}")
        sys.exit(1)

    print(f"Initializing VAD (aggressiveness={args.aggressiveness})...")
    vad = webrtcvad.Vad(args.aggressiveness)

    print(f"Extracting audio from {args.video}...")

    if args.keep_audio:
        audio_path = Path(args.video).stem + '_audio.wav'
    else:
        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        audio_path = tmp.name
        tmp.close()

    try:
        if not extract_audio(args.video, audio_path):
            print("Failed to extract audio")
            sys.exit(1)

        print("Loading audio...")
        audio, sample_rate = read_wave(audio_path)

        if sample_rate != SAMPLE_RATE:
            print(f"Warning: Expected {SAMPLE_RATE}Hz, got {sample_rate}Hz")

        print(f"Loading subtitles from {args.subtitles}...")
        subs = pysubs2.load(args.subtitles)

        print(f"Analyzing {len(subs)} cues...")
        subs, report = extend_subtitles(
            subs,
            audio,
            vad,
            sample_rate,
            search_buffer_ms=args.search_buffer,
            min_gap_ms=args.min_gap,
            max_extension_ms=args.max_extension,
            verbose=args.verbose
        )

        subs.save(args.output)
        print(f"\nSaved to {args.output}")

        print(f"\nSummary:")
        print(f"  Total cues: {report['total_cues']}")
        print(f"  Extended: {report['extended_cues']}")
        if report['extended_cues'] > 0:
            avg = report['total_extension_ms'] / report['extended_cues']
            print(f"  Average extension: {avg:.0f}ms")
            print(f"  Total extension: {report['total_extension_ms']}ms")

        if args.report:
            import json
            with open(args.report, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"  Report: {args.report}")

    finally:
        if not args.keep_audio and os.path.exists(audio_path):
            os.unlink(audio_path)


if __name__ == '__main__':
    main()
