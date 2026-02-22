#!/usr/bin/env python3
"""
Renumber SRT cues sequentially starting from 1.

Usage:
    python renumber_cues.py <file_path> [--output <output_path>] [--in-place]

Output (JSON):
    {
        "original_count": 250,
        "final_count": 250,
        "renumbered": true,
        "gaps_found": 3,
        "output_file": "subtitle.srt"
    }
"""

import sys
import json
import argparse
from pathlib import Path
from srt_utils import parse_srt_file, write_srt


def renumber_srt(file_path: str, output_path: str | None = None, in_place: bool = False) -> dict:
    """Renumber all cues sequentially."""
    subtitles, parse_errors = parse_srt_file(file_path)
    
    if parse_errors:
        return {'error': f'Parse errors: {parse_errors}'}
    
    # Check for gaps/duplicates
    original_indices = [sub.index for sub in subtitles]
    expected_indices = list(range(1, len(subtitles) + 1))
    gaps_found = sum(1 for i, (orig, exp) in enumerate(zip(original_indices, expected_indices)) if orig != exp)
    
    # Renumber
    for i, sub in enumerate(subtitles, 1):
        sub.index = i
    
    # Determine output path
    if in_place:
        out_file = file_path
    elif output_path:
        out_file = output_path
    else:
        p = Path(file_path)
        out_file = str(p.parent / f"{p.stem}_renumbered{p.suffix}")
    
    write_srt(subtitles, out_file)
    
    return {
        'original_count': len(subtitles),
        'final_count': len(subtitles),
        'renumbered': True,
        'gaps_found': gaps_found,
        'output_file': out_file
    }


def main():
    parser = argparse.ArgumentParser(description='Renumber SRT cues sequentially')
    parser.add_argument('file_path', help='Path to SRT file')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--in-place', '-i', action='store_true', help='Modify file in place')
    args = parser.parse_args()
    
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)
    
    result = renumber_srt(str(file_path), args.output, args.in_place)
    
    if 'error' in result:
        print(json.dumps(result))
        sys.exit(1)
    
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == '__main__':
    main()
