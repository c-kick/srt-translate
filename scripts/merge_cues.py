#!/usr/bin/env python3
"""
Merge retranslated cues back into a main SRT file.

Usage:
    python merge_cues.py main.srt retranslated.srt --output merged.srt
    python merge_cues.py main.srt retranslated.srt --in-place
    
For revision workflow:
    1. Run auto-fix: python validate_srt.py translation.nl.srt --fix
    2. Get unfixable indices: python validate_srt.py translation.nl.srt --fix --unfixable-indices
    3. Extract EN cues: python extract_cues.py source.en.srt --indices 487 -o needs_retranslation.srt
    4. Retranslate those cues manually or with LLM
    5. Merge: python merge_cues.py translation.nl.srt retranslated.srt --in-place
    6. Final validation: python validate_srt.py translation.nl.srt

The merge matches cues by INDEX (not by timecode). Retranslated cues replace
the corresponding cues in the main file. Timecodes from the main file are preserved
unless --use-retranslated-times is specified.
"""

import argparse
import json
import sys
from pathlib import Path
from srt_utils import parse_srt_file, write_srt, Subtitle


def merge_cues(main_path: str, retranslated_path: str, 
               output_path: str | None = None,
               preserve_main_times: bool = True) -> dict:
    """
    Merge retranslated cues into main SRT file.
    
    Args:
        main_path: Path to main SRT file
        retranslated_path: Path to file with retranslated cues
        output_path: Output path (default: overwrite main)
        preserve_main_times: Keep timecodes from main file (default: True)
    
    Returns:
        Dict with merge results
    """
    main_subs, main_errors = parse_srt_file(main_path)
    retrans_subs, retrans_errors = parse_srt_file(retranslated_path)
    
    if main_errors:
        return {'error': f'Main file parse errors: {main_errors}', 'success': False}
    if retrans_errors:
        return {'error': f'Retranslated file parse errors: {retrans_errors}', 'success': False}
    
    # Build lookup for main subs
    main_by_index = {sub.index: sub for sub in main_subs}
    
    # Track what we merged
    merged_indices = []
    not_found = []
    
    for retrans_sub in retrans_subs:
        idx = retrans_sub.index
        if idx in main_by_index:
            main_sub = main_by_index[idx]
            
            # Replace text
            main_sub.text = retrans_sub.text
            
            # Optionally replace timecodes
            if not preserve_main_times:
                main_sub.start_ms = retrans_sub.start_ms
                main_sub.end_ms = retrans_sub.end_ms
            
            merged_indices.append(idx)
        else:
            not_found.append(idx)
    
    # Write output
    out_path = output_path or main_path
    write_srt(main_subs, out_path)
    
    return {
        'success': True,
        'output_file': out_path,
        'total_main_cues': len(main_subs),
        'retranslated_cues': len(retrans_subs),
        'merged': len(merged_indices),
        'merged_indices': merged_indices,
        'not_found_in_main': not_found if not_found else None
    }


def main():
    parser = argparse.ArgumentParser(
        description='Merge retranslated cues back into main SRT file',
        epilog='Part of the srt-translate skill revision workflow'
    )
    parser.add_argument('main_file', help='Path to main SRT file')
    parser.add_argument('retranslated_file', help='Path to file with retranslated cues')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--in-place', action='store_true', help='Modify main file in place')
    parser.add_argument('--use-retranslated-times', action='store_true',
                        help='Use timecodes from retranslated file instead of main file')
    args = parser.parse_args()
    
    main_path = Path(args.main_file)
    retrans_path = Path(args.retranslated_file)
    
    if not main_path.exists():
        print(json.dumps({'error': f'Main file not found: {main_path}'}))
        sys.exit(1)
    if not retrans_path.exists():
        print(json.dumps({'error': f'Retranslated file not found: {retrans_path}'}))
        sys.exit(1)
    
    # Determine output path
    if args.in_place:
        output_path = str(main_path)
    elif args.output:
        output_path = args.output
    else:
        print(json.dumps({'error': 'Specify --output or --in-place'}))
        sys.exit(1)
    
    result = merge_cues(
        str(main_path),
        str(retrans_path),
        output_path,
        preserve_main_times=not args.use_retranslated_times
    )
    
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get('success', False) else 1)


if __name__ == '__main__':
    main()
