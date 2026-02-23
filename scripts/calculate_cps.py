#!/usr/bin/env python3
"""
Calculate CPS (Characters Per Second) for each cue in an SRT file.

Usage:
    python calculate_cps.py <file_path> [--limit N] [--violations-only] [--content-type scripted|unscripted]

Output (JSON):
    {
        "file": "subtitle.srt",
        "total_cues": 250,
        "stats": {...},
        "violations": [...],
        "cues": [...]  // if not --violations-only
    }
"""

import sys
import json
import argparse
from pathlib import Path
from srt_utils import parse_srt_file

from srt_constants import (
    CPS_SOFT_CEILING,
    CPS_REPORT_HARD_SCRIPTED as CPS_HARD_SCRIPTED,
    CPS_REPORT_HARD_UNSCRIPTED as CPS_HARD_UNSCRIPTED,
    get_constraints,
)


def analyze_cps(file_path: str, content_type: str = 'scripted') -> dict:
    """Analyze CPS for all cues in file."""
    subtitles, parse_errors = parse_srt_file(file_path)
    
    if parse_errors:
        return {'error': f'Parse errors: {parse_errors}'}
    
    cps_limit = CPS_HARD_SCRIPTED if content_type == 'scripted' else CPS_HARD_UNSCRIPTED
    
    cues_data = []
    violations = []
    cps_values = []
    
    for sub in subtitles:
        cps = sub.cps if sub.duration_seconds > 0 else 0
        
        cue_info = {
            'index': sub.index,
            'cps': round(cps, 1),
            'chars': sub.char_count,
            'duration_ms': sub.duration_ms,
            'text_preview': sub.text[:50] + '...' if len(sub.text) > 50 else sub.text
        }
        cues_data.append(cue_info)
        
        if sub.duration_seconds > 0:
            cps_values.append(cps)
        
        if cps > cps_limit:
            violations.append({
                'index': sub.index,
                'cps': round(cps, 1),
                'limit': cps_limit,
                'severity': 'error',
                'text': sub.text
            })
        elif cps > CPS_SOFT_CEILING:
            violations.append({
                'index': sub.index,
                'cps': round(cps, 1),
                'limit': CPS_SOFT_CEILING,
                'severity': 'warning',
                'text': sub.text
            })
    
    # Calculate statistics
    stats = {}
    if cps_values:
        sorted_cps = sorted(cps_values)
        stats = {
            'avg': round(sum(cps_values) / len(cps_values), 1),
            'min': round(min(cps_values), 1),
            'max': round(max(cps_values), 1),
            'median': round(sorted_cps[len(sorted_cps) // 2], 1),
            'p90': round(sorted_cps[int(len(sorted_cps) * 0.9)], 1),
            'p95': round(sorted_cps[int(len(sorted_cps) * 0.95)], 1),
            'above_soft_ceiling': sum(1 for c in cps_values if c > CPS_SOFT_CEILING),
            'above_hard_limit': sum(1 for c in cps_values if c > cps_limit),
        }
    
    return {
        'file': str(file_path),
        'content_type': content_type,
        'cps_limit': cps_limit,
        'total_cues': len(subtitles),
        'stats': stats,
        'violations': violations,
        'cues': cues_data
    }


def main():
    parser = argparse.ArgumentParser(description='Calculate CPS for SRT file')
    parser.add_argument('file_path', help='Path to SRT file')
    parser.add_argument('--content-type', choices=['scripted', 'unscripted'],
                        default='scripted', help='Content type for CPS limits')
    parser.add_argument('--limit', type=int, default=None, 
                        help='Limit number of cues in output')
    parser.add_argument('--violations-only', action='store_true',
                        help='Only output violations')
    parser.add_argument('--stats-only', action='store_true',
                        help='Only output statistics')
    parser.add_argument('--fps', type=int, choices=[24, 25],
                        help='Override CPS soft ceiling for specific framerate (24 or 25)')
    args = parser.parse_args()

    if args.fps:
        global CPS_SOFT_CEILING
        c = get_constraints(args.fps, 'nl')
        CPS_SOFT_CEILING = c['cps_hard_limit']

    file_path = Path(args.file_path)
    if not file_path.exists():
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)
    
    result = analyze_cps(str(file_path), args.content_type)
    
    if 'error' in result:
        print(json.dumps(result))
        sys.exit(1)
    
    # Filter output based on flags
    if args.stats_only:
        output = {
            'file': result['file'],
            'total_cues': result['total_cues'],
            'stats': result['stats']
        }
    elif args.violations_only:
        output = {
            'file': result['file'],
            'total_cues': result['total_cues'],
            'violation_count': len(result['violations']),
            'violations': result['violations']
        }
    else:
        output = result
        if args.limit:
            output['cues'] = output['cues'][:args.limit]
    
    print(json.dumps(output, indent=2))
    sys.exit(0)


if __name__ == '__main__':
    main()
