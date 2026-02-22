#!/usr/bin/env python3
"""
Add credit cue at the end of an SRT file.

Usage:
    python add_credit.py <file_path> [--credit "text"] [--gap 3000] [--duration 3000] [--cps 12] [--in-place]

Default credit: "Ondertiteling: c_kick/Claude"
Default gap: 3000ms (3 seconds after last cue)
Default duration: 3000ms

Best placement would be the cue timestamp of the original credit line in the English source, and if not present: 3 seconds after the last subtitle cue ended.

Output (JSON):
    {
        "added": true,
        "credit_text": "Ondertiteling: c_kick & Claude",
        "cue_index": 251,
        "output_file": "subtitle.srt"
    }
"""

import sys
import json
import argparse
from pathlib import Path
from srt_utils import parse_srt_file, write_srt, Subtitle

DEFAULT_CREDIT = "Ondertiteling: c_kick & Claude"
DEFAULT_GAP_MS = 3000
DEFAULT_DURATION_MS = 3000
DEFAULT_CPS = 12


def add_credit_cue(
    file_path: str,
    credit_text: str = DEFAULT_CREDIT,
    gap_ms: int = DEFAULT_GAP_MS,
    duration_ms: int = DEFAULT_DURATION_MS,
    output_path: str | None = None,
    in_place: bool = False
) -> dict:
    """Add credit cue to end of SRT file."""
    subtitles, parse_errors = parse_srt_file(file_path)
    
    if parse_errors:
        return {'error': f'Parse errors: {parse_errors}'}
    
    if not subtitles:
        return {'error': 'No subtitles found in file'}
    
    # Check if credit already exists
    last_sub = subtitles[-1]
    if credit_text.lower() in last_sub.text.lower():
        return {
            'added': False,
            'reason': 'Credit cue already exists',
            'output_file': file_path
        }
    
    # Calculate timing for credit cue
    start_ms = last_sub.end_ms + gap_ms
    end_ms = start_ms + duration_ms
    
    # Create credit cue
    credit_cue = Subtitle(
        index=len(subtitles) + 1,
        start_ms=start_ms,
        end_ms=end_ms,
        text=credit_text
    )
    
    subtitles.append(credit_cue)
    
    # Determine output path
    if in_place:
        out_file = file_path
    elif output_path:
        out_file = output_path
    else:
        out_file = file_path  # Default to in-place for this operation
    
    write_srt(subtitles, out_file)
    
    return {
        'added': True,
        'credit_text': credit_text,
        'cue_index': credit_cue.index,
        'start_time': f"{start_ms // 1000}.{start_ms % 1000:03d}s",
        'output_file': out_file
    }


def main():
    parser = argparse.ArgumentParser(description='Add credit cue to SRT file')
    parser.add_argument('file_path', help='Path to SRT file')
    parser.add_argument('--credit', default=DEFAULT_CREDIT, help='Credit text')
    parser.add_argument('--gap', type=int, default=DEFAULT_GAP_MS, help='Gap after last cue (ms)')
    parser.add_argument('--duration', type=int, default=DEFAULT_DURATION_MS, help='Credit duration (ms)')
    parser.add_argument('--cps', type=float, default=None,
                        help=f'Calculate duration from CPS (overrides --duration). Default: {DEFAULT_CPS}')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--in-place', '-i', action='store_true', help='Modify file in place')
    args = parser.parse_args()
    
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)
    
    # Calculate duration from CPS if requested
    duration = args.duration
    if args.cps is not None:
        char_count = len(args.credit.replace('\n', ''))
        duration = int(char_count / args.cps * 1000)

    result = add_credit_cue(
        str(file_path),
        credit_text=args.credit,
        gap_ms=args.gap,
        duration_ms=duration,
        output_path=args.output,
        in_place=args.in_place
    )
    
    if 'error' in result:
        print(json.dumps(result))
        sys.exit(1)
    
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == '__main__':
    main()
