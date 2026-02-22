#!/usr/bin/env python3
"""
Synchronize subtitles to video audio using ffsubsync.

Aligns out-of-sync subtitles by matching speech patterns in the audio
track with subtitle timing. Run this BEFORE translation if source
subtitles appear misaligned with the audio.

Supports both external SRT files and embedded subtitle streams.

Usage:
    # Sync external SRT
    python3 sync_subtitles.py video.mkv subtitles.en.srt --output synced.en.srt

    # Sync embedded subtitle stream
    python3 sync_subtitles.py video.mkv --stream 0:s:0 --output synced.en.srt

    # List available subtitle streams
    python3 sync_subtitles.py video.mkv --list-streams

Requirements:
    pip install ffsubsync

"""

import argparse
import os
import subprocess
import sys
import shutil
import json
import tempfile
from pathlib import Path


def get_ffsubsync_path() -> str:
    """Get path to ffsubsync executable, checking venv first."""
    # Check if we're in a venv - look for ffsubsync next to python
    python_path = Path(sys.executable)
    venv_ffsubsync = python_path.parent / 'ffsubsync'
    if venv_ffsubsync.exists():
        return str(venv_ffsubsync)

    # Fall back to PATH
    return 'ffsubsync'


def check_ffsubsync() -> bool:
    """Check if ffsubsync is available."""
    try:
        result = subprocess.run(
            [get_ffsubsync_path(), '--version'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def list_subtitle_streams(video_path: str) -> list[dict]:
    """List subtitle streams in a video file."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 's',
        '-show_entries', 'stream=index,codec_name:stream_tags=language,title',
        '-of', 'json',
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = []
        for i, stream in enumerate(data.get('streams', [])):
            tags = stream.get('tags', {})
            streams.append({
                'index': stream.get('index'),
                'stream_specifier': f"0:s:{i}",
                'codec': stream.get('codec_name', 'unknown'),
                'language': tags.get('language', 'und'),
                'title': tags.get('title', ''),
            })
        return streams
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Error probing video: {e}", file=sys.stderr)
        return []


def extract_embedded_subtitle(video_path: str, stream: str, output_path: str, verbose: bool = False) -> tuple[bool, str]:
    """
    Extract embedded subtitle stream using ffmpeg.

    Args:
        video_path: Path to video file
        stream: Stream specifier (e.g., "0:s:0")
        output_path: Path to output SRT file
        verbose: Print detailed output

    Returns:
        Tuple of (success, message)
    """
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-map', stream,
        '-c:s', 'srt',
        output_path
    ]

    if verbose:
        print(f"Extracting: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            # Check for common errors
            if "codec not currently supported" in error_msg.lower():
                return False, f"Cannot extract stream {stream}: bitmap subtitles (DVD/PGS) cannot be converted to SRT"
            return False, f"ffmpeg extraction failed: {error_msg}"

        if not Path(output_path).exists():
            return False, "ffmpeg did not create output file"

        return True, f"Extracted to {output_path}"

    except subprocess.TimeoutExpired:
        return False, "ffmpeg extraction timed out"
    except Exception as e:
        return False, f"Error extracting subtitle: {e}"


def sync_subtitles(
    video_path: str,
    srt_path: str | None,
    output_path: str,
    stream: str | None = None,
    vad: str = 'auto',
    verbose: bool = False
) -> tuple[bool, str]:
    """
    Sync subtitles to video using ffsubsync.

    Args:
        video_path: Path to video file
        srt_path: Path to input SRT file (None if using embedded stream)
        output_path: Path to output synced SRT file
        stream: Embedded stream specifier (e.g., "0:s:0") - if provided, extracts first then syncs
        verbose: Print detailed output

    Returns:
        Tuple of (success, message)
    """
    video = Path(video_path)
    output = Path(output_path)

    # Validate inputs
    if not video.exists():
        return False, f"Video file not found: {video}"

    if srt_path:
        srt = Path(srt_path)
        if not srt.exists():
            return False, f"Subtitle file not found: {srt}"

    # If using embedded stream, extract it first
    temp_srt = None
    if stream:
        # Create temp file for extracted subtitle
        temp_fd, temp_srt = tempfile.mkstemp(suffix='.srt')
        os.close(temp_fd)

        if verbose:
            print(f"Step 1: Extracting embedded stream {stream}...")

        success, message = extract_embedded_subtitle(video_path, stream, temp_srt, verbose)
        if not success:
            Path(temp_srt).unlink(missing_ok=True)
            return False, message

        srt_to_sync = temp_srt
        if verbose:
            print(f"Step 2: Syncing extracted subtitle...")
    else:
        srt_to_sync = srt_path

    # Build ffsubsync command
    cmd = [
        get_ffsubsync_path(),
        str(video),
        '-i', str(srt_to_sync),
        '-o', str(output),
    ]

    # Determine VAD method
    # For embedded streams, default to audio-only VAD to avoid comparing subtitle to itself
    # (embedded subtitles may be muxed from a different source than the video/audio)
    if vad == 'auto':
        if stream:
            cmd.extend(['--vad', 'webrtc'])
        # else: let ffsubsync use its default (subs_then_webrtc)
    else:
        cmd.extend(['--vad', vad])

    if verbose:
        print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for long videos
        )

        # Clean up temp file if used
        if temp_srt:
            Path(temp_srt).unlink(missing_ok=True)

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            return False, f"ffsubsync failed: {error_msg}"

        if not output.exists():
            return False, "ffsubsync did not create output file"

        # Parse offset from ffsubsync output if available
        offset_info = ""
        for line in result.stdout.split('\n'):
            if 'offset' in line.lower():
                offset_info = line.strip()
                break

        if offset_info:
            return True, f"Sync complete. {offset_info}"
        return True, f"Sync complete. Output: {output}"

    except subprocess.TimeoutExpired:
        if temp_srt:
            Path(temp_srt).unlink(missing_ok=True)
        return False, "ffsubsync timed out (>10 minutes)"
    except Exception as e:
        if temp_srt:
            Path(temp_srt).unlink(missing_ok=True)
        return False, f"Error running ffsubsync: {e}"


def main():
    parser = argparse.ArgumentParser(
        description='Synchronize subtitles to video audio using ffsubsync',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Sync external SRT file
    python3 sync_subtitles.py movie.mkv movie.en.srt -o movie.synced.en.srt

    # List embedded subtitle streams
    python3 sync_subtitles.py movie.mkv --list-streams

    # Sync embedded subtitle stream (first subtitle track)
    python3 sync_subtitles.py movie.mkv --stream 0:s:0 -o synced.en.srt

    # Sync in place (overwrites original)
    python3 sync_subtitles.py movie.mkv movie.en.srt --in-place

    # Verbose output
    python3 sync_subtitles.py movie.mkv movie.en.srt -o synced.srt -v
"""
    )

    parser.add_argument('video', nargs='?', help='Video file path')
    parser.add_argument('srt', nargs='?', help='Input SRT subtitle file (optional if using --stream)')
    parser.add_argument('-o', '--output', help='Output SRT file path')
    parser.add_argument('--stream', metavar='SPEC',
                        help='Extract and sync embedded subtitle stream (e.g., 0:s:0 for first subtitle)')
    parser.add_argument('--vad', choices=['auto', 'webrtc', 'auditok'],
                        default='auto',
                        help='VAD method: auto (webrtc for embedded, default for external), '
                             'webrtc (audio-only), auditok (audio-only alternative)')
    parser.add_argument('--list-streams', action='store_true',
                        help='List available subtitle streams in the video')
    parser.add_argument('--in-place', action='store_true',
                        help='Overwrite input file with synced version')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')
    parser.add_argument('--check', action='store_true',
                        help='Only check if ffsubsync is available')

    args = parser.parse_args()

    # Check mode
    if args.check:
        if check_ffsubsync():
            print("ffsubsync is available")
            sys.exit(0)
        else:
            print("ffsubsync is NOT available. Install with:")
            print("  pip install ffsubsync")
            sys.exit(1)

    # List streams mode
    if args.list_streams:
        if not args.video:
            parser.error("video argument is required for --list-streams")
        streams = list_subtitle_streams(args.video)
        if not streams:
            print("No subtitle streams found.")
            sys.exit(0)
        print(f"Subtitle streams in {Path(args.video).name}:")
        print()
        for s in streams:
            lang = s['language'].upper() if s['language'] != 'und' else '???'
            title = f" - {s['title']}" if s['title'] else ''
            print(f"  {s['stream_specifier']}  [{lang}] {s['codec']}{title}")
        print()
        print("Use --stream SPEC to sync an embedded stream, e.g.:")
        print(f"  python3 {sys.argv[0]} \"{args.video}\" --stream {streams[0]['stream_specifier']} -o synced.srt")
        sys.exit(0)

    # Require video for sync operations
    if not args.video:
        parser.error("video argument is required")

    # Validate arguments for sync mode
    if args.stream:
        # Using embedded stream - no SRT file needed
        if not args.output:
            parser.error("--output is required when using --stream")
        if args.in_place:
            parser.error("--in-place cannot be used with --stream (no input file to replace)")
    else:
        # Using external SRT file
        if not args.srt:
            parser.error("srt argument is required (or use --stream for embedded subtitles)")
        if not args.output and not args.in_place:
            parser.error("Either --output or --in-place is required")
        if args.output and args.in_place:
            parser.error("Cannot use both --output and --in-place")

    # Check ffsubsync availability
    if not check_ffsubsync():
        print("Error: ffsubsync not found. Install with:")
        print("  pip install ffsubsync")
        sys.exit(1)

    # Run sync
    if args.stream:
        # Sync embedded stream
        success, message = sync_subtitles(
            args.video, None, args.output,
            stream=args.stream, vad=args.vad, verbose=args.verbose
        )
        if success:
            print(message)
        else:
            print(f"Error: {message}", file=sys.stderr)
            sys.exit(1)
    elif args.in_place:
        # Sync external SRT in place
        output_path = str(Path(args.srt).with_suffix('.synced.srt'))
        success, message = sync_subtitles(
            args.video, args.srt, output_path,
            vad=args.vad, verbose=args.verbose
        )
        if success:
            shutil.move(output_path, args.srt)
            print(f"Synced in place: {args.srt}")
        else:
            print(f"Error: {message}", file=sys.stderr)
            sys.exit(1)
    else:
        # Sync external SRT to output file
        success, message = sync_subtitles(
            args.video, args.srt, args.output,
            vad=args.vad, verbose=args.verbose
        )
        if success:
            print(message)
        else:
            print(f"Error: {message}", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
