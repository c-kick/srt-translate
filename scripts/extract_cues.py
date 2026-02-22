#!/usr/bin/env python3
"""
Extract specific cues from an SRT file by index.

Usage:
    # Range extraction (preferred for batch processing):
    python extract_cues.py input.srt --start 1 --end 200 --output batch1.srt
    python extract_cues.py input.srt --start 201 --end 400 --output batch2.srt
    
    # Comma-separated indices:
    python extract_cues.py input.srt --indices 1,5,10,487 --output selected.srt
    
    # Indices from file:
    python extract_cues.py input.srt --indices-file unfixable.txt --output needs_fix.srt
    
For batch translation workflow:
    1. Extract batch: python extract_cues.py source.en.srt --start 1 --end 200 --output batch1_source.srt
    2. Translate batch
    3. Verify cue count matches
    4. Repeat for next batch
    
For revision workflow:
    1. Run: python validate_srt.py translation.nl.srt --fix --unfixable-indices > unfixable.json
    2. Get indices that need retranslation
    3. Run: python extract_cues.py source.en.srt --indices-file unfixable.json --output needs_retranslation.srt
    4. Retranslate only those cues
    5. Merge back into fixed NL file
"""

import argparse
import json
import sys
from pathlib import Path
from srt_utils import parse_srt_file, write_srt


def extract_cues(file_path: str, indices: list[int], output_path: str | None = None) -> dict:
    """
    Extract specific cues from an SRT file.
    
    Args:
        file_path: Path to input SRT file
        indices: List of cue indices to extract (1-based)
        output_path: Optional output file path
    
    Returns:
        Dict with extraction results
    """
    subtitles, parse_errors = parse_srt_file(file_path)
    
    if parse_errors:
        return {'error': f'Parse errors: {parse_errors}', 'success': False}
    
    # Build index lookup
    index_to_sub = {sub.index: sub for sub in subtitles}
    
    # Extract requested cues
    extracted = []
    not_found = []
    
    for idx in sorted(indices):
        if idx in index_to_sub:
            extracted.append(index_to_sub[idx])
        else:
            not_found.append(idx)
    
    result = {
        'success': True,
        'requested': len(indices),
        'extracted': len(extracted),
        'not_found': not_found if not_found else None
    }
    
    if output_path:
        write_srt(extracted, output_path)
        result['output_file'] = output_path
    else:
        # Output cues as structured data
        result['cues'] = [
            {
                'index': sub.index,
                'start': sub.start_ms,
                'end': sub.end_ms,
                'text': sub.text
            }
            for sub in extracted
        ]
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Extract specific cues from an SRT file',
        epilog='Part of the srt-translate skill revision workflow'
    )
    parser.add_argument('file_path', help='Path to SRT file')
    parser.add_argument('--indices', '-i', help='Comma-separated list of cue indices to extract')
    parser.add_argument('--indices-file', '-f', help='File containing indices (one per line, or JSON array)')
    parser.add_argument('--start', '-s', type=int, help='Start cue index (inclusive) - use with --end for range extraction')
    parser.add_argument('--end', '-e', type=int, help='End cue index (inclusive) - use with --start for range extraction')
    parser.add_argument('--output', '-o', help='Output SRT file path (if not specified, outputs JSON)')
    args = parser.parse_args()
    
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)
    
    # Parse indices
    indices = []
    
    # Handle --start/--end range extraction (preferred for batch processing)
    if args.start is not None and args.end is not None:
        if args.start > args.end:
            print(json.dumps({'error': f'Invalid range: start ({args.start}) > end ({args.end})'}))
            sys.exit(1)
        indices = list(range(args.start, args.end + 1))
    elif args.start is not None or args.end is not None:
        print(json.dumps({'error': 'Both --start and --end must be specified together'}))
        sys.exit(1)
    
    if args.indices:
        try:
            indices = [int(x.strip()) for x in args.indices.split(',')]
        except ValueError:
            print(json.dumps({'error': 'Invalid indices format. Use comma-separated integers: --indices 1,5,10'}))
            sys.exit(1)
    
    if args.indices_file:
        indices_path = Path(args.indices_file)
        if not indices_path.exists():
            print(json.dumps({'error': f'Indices file not found: {indices_path}'}))
            sys.exit(1)
        
        content = indices_path.read_text().strip()
        try:
            # Try JSON first
            data = json.loads(content)
            if isinstance(data, list):
                indices.extend(int(x) for x in data)
            elif isinstance(data, dict) and 'unfixable_cue_indices' in data:
                indices.extend(data['unfixable_cue_indices'])
        except json.JSONDecodeError:
            # Fall back to line-by-line
            for line in content.split('\n'):
                line = line.strip()
                if line and line.isdigit():
                    indices.append(int(line))
    
    if not indices:
        print(json.dumps({'error': 'No indices specified. Use --indices or --indices-file'}))
        sys.exit(1)
    
    # Remove duplicates and sort
    indices = sorted(set(indices))
    
    result = extract_cues(str(file_path), indices, args.output)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get('success', False) else 1)


if __name__ == '__main__':
    main()
