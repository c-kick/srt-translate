#!/usr/bin/env python3
"""
Safely merge SRT batch files without boundary corruption.

Usage:
    python merge_batches.py batch1.srt batch2.srt batch3.srt --output merged.srt
    python merge_batches.py batch*.srt --output merged.srt
"""

import sys
import re
import argparse
from pathlib import Path


def parse_srt_cues(content: str) -> list[dict]:
    """Parse SRT content into list of cue dictionaries."""
    cues = []
    
    # Normalize line endings and split into blocks
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n\n+', content.strip())
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
            
        lines = block.split('\n')
        if len(lines) < 3:
            continue
            
        # Validate structure: number, timestamp, text
        if not lines[0].strip().isdigit():
            continue
        if '-->' not in lines[1]:
            continue
            
        cues.append({
            'timestamp': lines[1].strip(),
            'text': '\n'.join(lines[2:])
        })
    
    return cues


def merge_batches(input_files: list[str], output_file: str) -> dict:
    """
    Merge multiple SRT batch files into one, renumbering cues sequentially.
    
    Returns stats dict with cue counts.
    """
    all_cues = []
    stats = {'input_files': len(input_files), 'cues_per_file': []}
    
    for filepath in input_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        cues = parse_srt_cues(content)
        stats['cues_per_file'].append((filepath, len(cues)))
        all_cues.extend(cues)
    
    # Write merged file with sequential numbering
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, cue in enumerate(all_cues, 1):
            f.write(f"{i}\n")
            f.write(f"{cue['timestamp']}\n")
            f.write(f"{cue['text']}\n")
            f.write("\n")
    
    stats['total_cues'] = len(all_cues)
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
