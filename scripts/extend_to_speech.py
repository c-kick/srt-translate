#!/usr/bin/env python3
"""
Extend subtitle end times to match actual speech end using Voice Activity Detection.

Uses Silero VAD for accurate speech boundary detection. Useful for slow speakers
where the subtitle disappears before they finish talking.

Usage:
    python3 extend_to_speech.py video.mkv subtitles.srt --output extended.srt

Requirements:
    pip install torch torchaudio silero-vad pysubs2

Note: First run will download the Silero VAD model (~2MB).
"""

import argparse
import subprocess
import tempfile
import os
import sys
from pathlib import Path

try:
    import torch
    import torchaudio
    from silero_vad import load_silero_vad, get_speech_timestamps, read_audio
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install torch torchaudio silero-vad")
    sys.exit(1)

try:
    import pysubs2
except ImportError:
    print("Missing pysubs2. Install with:")
    print("  pip install pysubs2")
    sys.exit(1)


def extract_audio(video_path: str, output_path: str, sample_rate: int = 16000) -> bool:
    """Extract audio from video file using ffmpeg."""
    cmd = [
        'ffmpeg', '-y', '-i', video_path,
        '-vn',  # No video
        '-acodec', 'pcm_s16le',  # 16-bit PCM
        '-ar', str(sample_rate),  # Sample rate
        '-ac', '1',  # Mono
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr.decode()}")
        return False


def ms_to_samples(ms: int, sample_rate: int) -> int:
    """Convert milliseconds to audio samples."""
    return int(ms * sample_rate / 1000)


def samples_to_ms(samples: int, sample_rate: int) -> int:
    """Convert audio samples to milliseconds."""
    return int(samples * 1000 / sample_rate)


def find_speech_end(
    audio: torch.Tensor,
    vad_model,
    cue_start_ms: int,
    cue_end_ms: int,
    sample_rate: int = 16000,
    search_buffer_ms: int = 3000,
    min_silence_ms: int = 300
) -> int:
    """
    Find when speech actually ends after a cue's current end time.

    Returns the timestamp (in ms) where speech ends, or the original
    cue_end_ms if speech ends before/at that point.
    """
    # Define search window: from cue start to cue end + buffer
    search_start = ms_to_samples(cue_start_ms, sample_rate)
    search_end = ms_to_samples(cue_end_ms + search_buffer_ms, sample_rate)

    # Clamp to audio bounds
    search_start = max(0, search_start)
    search_end = min(len(audio), search_end)

    if search_start >= search_end:
        return cue_end_ms

    # Extract segment
    segment = audio[search_start:search_end]

    # Get speech timestamps in this segment
    speech_timestamps = get_speech_timestamps(
        segment,
        vad_model,
        sampling_rate=sample_rate,
        min_silence_duration_ms=min_silence_ms,
        speech_pad_ms=30
    )

    if not speech_timestamps:
        # No speech detected in segment
        return cue_end_ms

    # Find the last speech segment that overlaps with or follows the cue
    cue_end_in_segment = ms_to_samples(cue_end_ms, sample_rate) - search_start

    last_speech_end = 0
    for ts in speech_timestamps:
        segment_speech_end = ts['end']
        # If this speech segment ends after our current cue end
        if segment_speech_end > cue_end_in_segment:
            last_speech_end = segment_speech_end
        elif segment_speech_end > last_speech_end:
            last_speech_end = segment_speech_end

    if last_speech_end <= cue_end_in_segment:
        # Speech ends before or at current cue end
        return cue_end_ms

    # Convert back to absolute milliseconds
    speech_end_ms = samples_to_ms(search_start + last_speech_end, sample_rate)

    return speech_end_ms


def extend_subtitles(
    subs: pysubs2.SSAFile,
    audio: torch.Tensor,
    vad_model,
    sample_rate: int = 16000,
    search_buffer_ms: int = 3000,
    min_gap_ms: int = 125,
    max_extension_ms: int = 3000,
    verbose: bool = False
) -> tuple[pysubs2.SSAFile, dict]:
    """
    Extend subtitle end times to match speech end.

    Returns modified subtitles and a report dict.
    """
    report = {
        'total_cues': len(subs),
        'extended_cues': 0,
        'total_extension_ms': 0,
        'extensions': []
    }

    for i, cue in enumerate(subs):
        # Determine the latest we can extend to (respecting next cue)
        if i + 1 < len(subs):
            max_end = subs[i + 1].start - min_gap_ms
        else:
            max_end = cue.end + max_extension_ms

        # Don't extend past maximum extension
        max_end = min(max_end, cue.end + max_extension_ms)

        # Skip if no room to extend
        if max_end <= cue.end:
            continue

        # Find actual speech end
        speech_end = find_speech_end(
            audio,
            vad_model,
            cue.start,
            cue.end,
            sample_rate,
            search_buffer_ms=min(search_buffer_ms, max_end - cue.end + 500)
        )

        # Extend if speech continues past current end
        if speech_end > cue.end:
            new_end = min(speech_end + 100, max_end)  # +100ms padding
            extension = new_end - cue.end

            if extension > 50:  # Only report meaningful extensions
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
        description='Extend subtitle end times to match actual speech end.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage
    python3 extend_to_speech.py movie.mkv movie.nl.srt -o movie.extended.srt

    # With verbose output
    python3 extend_to_speech.py movie.mkv movie.nl.srt -o extended.srt -v

    # Custom parameters
    python3 extend_to_speech.py movie.mkv movie.nl.srt -o extended.srt \\
        --max-extension 2000 --search-buffer 2000
        """
    )

    parser.add_argument('video', help='Video file (mkv, mp4, etc.)')
    parser.add_argument('subtitles', help='SRT subtitle file')
    parser.add_argument('-o', '--output', required=True, help='Output SRT file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show each extension')
    parser.add_argument('--search-buffer', type=int, default=3000,
                        help='How far past cue end to search for speech (ms, default: 3000)')
    parser.add_argument('--max-extension', type=int, default=3000,
                        help='Maximum extension per cue (ms, default: 3000)')
    parser.add_argument('--min-gap', type=int, default=125,
                        help='Minimum gap to maintain before next cue (ms, default: 125)')
    parser.add_argument('--keep-audio', action='store_true',
                        help='Keep extracted audio file (for debugging)')
    parser.add_argument('--report', help='Write JSON report to file')

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.video):
        print(f"Error: Video file not found: {args.video}")
        sys.exit(1)

    if not os.path.exists(args.subtitles):
        print(f"Error: Subtitle file not found: {args.subtitles}")
        sys.exit(1)

    print(f"Loading VAD model...")
    vad_model = load_silero_vad()

    # Extract audio to temp file
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

        print(f"Loading audio...")
        audio = read_audio(audio_path)
        sample_rate = 16000  # Silero expects 16kHz

        print(f"Loading subtitles from {args.subtitles}...")
        subs = pysubs2.load(args.subtitles)

        print(f"Analyzing {len(subs)} cues for speech boundaries...")
        subs, report = extend_subtitles(
            subs,
            audio,
            vad_model,
            sample_rate=sample_rate,
            search_buffer_ms=args.search_buffer,
            min_gap_ms=args.min_gap,
            max_extension_ms=args.max_extension,
            verbose=args.verbose
        )

        # Save output
        subs.save(args.output)
        print(f"\nSaved to {args.output}")

        # Print summary
        print(f"\nSummary:")
        print(f"  Total cues: {report['total_cues']}")
        print(f"  Extended: {report['extended_cues']}")
        if report['extended_cues'] > 0:
            avg_ext = report['total_extension_ms'] / report['extended_cues']
            print(f"  Average extension: {avg_ext:.0f}ms")
            print(f"  Total extension: {report['total_extension_ms']}ms")

        # Save report if requested
        if args.report:
            import json
            with open(args.report, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"  Report saved to {args.report}")

    finally:
        if not args.keep_audio and os.path.exists(audio_path):
            os.unlink(audio_path)


if __name__ == '__main__':
    main()
