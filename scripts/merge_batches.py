#!/usr/bin/env python3
"""
Safely merge SRT batch files without boundary corruption.

Usage:
    python merge_batches.py batch1.srt batch2.srt batch3.srt --output merged.srt
    python merge_batches.py batch*.srt --output merged.srt
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srt_utils import parse_srt, write_srt


def merge_batches(input_files: list[str], output_file: str) -> dict:
    """
    Merge multiple SRT batch files into one, renumbering cues sequentially.

    Returns stats dict with cue counts.
    """
    all_subs = []
    stats = {'input_files': len(input_files), 'cues_per_file': []}

    for filepath in input_files:
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except (UnicodeDecodeError, OSError) as e:
            print(f"Error reading {filepath}: {e}", file=sys.stderr)
            sys.exit(1)

        subs, errors = parse_srt(content)
        stats['cues_per_file'].append((filepath, len(subs)))
        all_subs.extend(subs)

    # Renumber sequentially
    for i, sub in enumerate(all_subs, 1):
        sub.index = i

    write_srt(all_subs, output_file)

    stats['total_cues'] = len(all_subs)
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Safely merge SRT batch files without boundary corruption'
    )
    parser.add_argument(
        'inputs',
        nargs='+',
        help='Input SRT batch files in order'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='Output merged SRT file'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print merge statistics'
    )

    args = parser.parse_args()

    # Validate inputs exist
    for f in args.inputs:
        if not Path(f).exists():
            print(f"ERROR: Input file not found: {f}", file=sys.stderr)
            sys.exit(1)

    stats = merge_batches(args.inputs, args.output)

    if args.verbose:
        print(f"Merged {stats['input_files']} files:")
        for filepath, count in stats['cues_per_file']:
            print(f"  {filepath}: {count} cues")
        print(f"Total: {stats['total_cues']} cues → {args.output}")
    else:
        print(f"Merged {stats['total_cues']} cues → {args.output}")


if __name__ == '__main__':
    main()
