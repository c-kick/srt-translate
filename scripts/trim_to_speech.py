#!/usr/bin/env python3
"""
Trim subtitle end times to match actual speech boundaries using WebRTC VAD.

Pulls back cue end times that linger past speech, guarded by CPS constraints,
minimum gap, and minimum duration. Designed as Phase 4b in the srt-translate
pipeline (between merge and CPS optimization).

Can also be used standalone on any existing .nl.srt file.

Usage:
    python3 trim_to_speech.py video.mkv merged.nl.srt --output trimmed.nl.srt --fps 25
    python3 trim_to_speech.py video.mkv merged.nl.srt -o trimmed.nl.srt --dry-run -v

Requirements:
    pip install webrtcvad
"""

import argparse
import bisect
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srt_utils import parse_srt_file, write_srt, ms_to_timecode, visible_length
from srt_constants import get_constraints


def find_nearest(transitions, target_ms, search_range=2000):
    """Find the transition nearest to target_ms within search_range.

    Duplicated from vad_timing_check.py to avoid importing webrtcvad at
    module level (which breaks unit tests in environments without it).
    The VAD-heavy imports happen in main() only.
    """
    if not transitions:
        return None
    idx = bisect.bisect_left(transitions, target_ms)
    best = None
    best_dist = float('inf')
    for i in (idx - 1, idx):
        if 0 <= i < len(transitions):
            dist = abs(transitions[i] - target_ms)
            if dist < best_dist and dist <= search_range:
                best_dist = dist
                best = transitions[i]
    return best


# ---------------------------------------------------------------------------
# Trim decision logic
# ---------------------------------------------------------------------------

def compute_trim(cue, speech_ends, search_range, comfort_buffer, min_trim,
                 cps_soft_ceiling, cps_hard_limit, min_duration_ms, min_gap_ms,
                 next_cue=None):
    """
    Decide whether and how to trim a single cue.

    Returns dict with:
        action: 'trim', 'partial_trim', or 'skip'
        reason: why skipped (if skip)
        new_end: proposed new end_ms (if trim/partial_trim)
        trim_ms: amount trimmed
        new_cps: CPS after trim
        method: 'full' or 'partial'
    """
    result = {
        'cue_num': cue.index,
        'old_end': cue.end_ms,
        'action': 'skip',
        'reason': None,
        'new_end': None,
        'trim_ms': 0,
        'new_cps': cue.cps,
        'method': None,
    }

    # Find nearest speech end within search range
    nearest_end = find_nearest(speech_ends, cue.end_ms, search_range)

    if nearest_end is None:
        result['reason'] = 'no_transition'
        return result

    # Speech extends past cue end — cue is too short, not too long
    if nearest_end > cue.end_ms:
        result['reason'] = 'speech_extends_past_cue'
        return result

    linger = cue.end_ms - nearest_end

    if linger < min_trim:
        result['reason'] = 'below_min_trim'
        return result

    # Proposed new end
    new_end = nearest_end + comfort_buffer

    # Don't extend past current end (buffer shouldn't push end later)
    if new_end >= cue.end_ms:
        result['reason'] = 'buffer_exceeds_current_end'
        return result

    # Enforce min_duration
    if new_end - cue.start_ms < min_duration_ms:
        result['reason'] = 'min_duration'
        return result

    # Enforce min_gap to next cue
    if next_cue is not None:
        max_allowed = next_cue.start_ms - min_gap_ms
        if new_end > max_allowed:
            new_end = max_allowed
        # Re-check min_duration after clamping
        if new_end - cue.start_ms < min_duration_ms:
            result['reason'] = 'min_duration_after_gap_clamp'
            return result

    # CPS check
    char_count = cue.char_count
    new_duration_s = (new_end - cue.start_ms) / 1000.0
    if new_duration_s <= 0:
        result['reason'] = 'zero_duration'
        return result

    new_cps = char_count / new_duration_s

    if new_cps <= cps_soft_ceiling:
        # Full trim — CPS is fine
        result['action'] = 'trim'
        result['new_end'] = new_end
        result['trim_ms'] = cue.end_ms - new_end
        result['new_cps'] = round(new_cps, 1)
        result['method'] = 'full'
        return result

    if new_cps > cps_hard_limit:
        # Even current CPS might be over hard limit — check if ANY trim is safe
        # Find the end time where CPS = cps_soft_ceiling
        target_end = cue.start_ms + int((char_count / cps_soft_ceiling) * 1000)
        if target_end >= cue.end_ms:
            result['reason'] = 'cps_hard_limit'
            return result
        # Check if partial trim is still meaningful (> comfort_buffer from speech)
        partial_trim = cue.end_ms - target_end
        if partial_trim < min_trim:
            result['reason'] = 'partial_trim_too_small'
            return result
        # Apply partial trim
        partial_end = target_end
        # Enforce min_gap on partial too
        if next_cue is not None:
            max_allowed = next_cue.start_ms - min_gap_ms
            if partial_end > max_allowed:
                partial_end = max_allowed
        if partial_end - cue.start_ms < min_duration_ms:
            result['reason'] = 'min_duration_partial'
            return result
        partial_cps = char_count / ((partial_end - cue.start_ms) / 1000.0)
        result['action'] = 'partial_trim'
        result['new_end'] = partial_end
        result['trim_ms'] = cue.end_ms - partial_end
        result['new_cps'] = round(partial_cps, 1)
        result['method'] = 'partial'
        return result

    # CPS between soft ceiling and hard limit — partial trim to soft ceiling
    target_end = cue.start_ms + int((char_count / cps_soft_ceiling) * 1000)
    if target_end >= cue.end_ms:
        result['reason'] = 'cps_soft_ceiling'
        return result
    partial_trim_amount = cue.end_ms - target_end
    if partial_trim_amount < min_trim:
        result['reason'] = 'partial_trim_too_small'
        return result
    partial_end = target_end
    if next_cue is not None:
        max_allowed = next_cue.start_ms - min_gap_ms
        if partial_end > max_allowed:
            partial_end = max_allowed
    if partial_end - cue.start_ms < min_duration_ms:
        result['reason'] = 'min_duration_partial'
        return result
    partial_cps = char_count / ((partial_end - cue.start_ms) / 1000.0)
    result['action'] = 'partial_trim'
    result['new_end'] = partial_end
    result['trim_ms'] = cue.end_ms - partial_end
    result['new_cps'] = round(partial_cps, 1)
    result['method'] = 'partial'
    return result


def trim_all(cues, speech_ends, search_range, comfort_buffer, min_trim,
             cps_soft_ceiling, cps_hard_limit, min_duration_ms, min_gap_ms,
             dry_run=False, verbose=False):
    """
    Process all cues and apply trims.

    Returns list of trim result dicts.
    """
    results = []

    for idx, cue in enumerate(cues):
        next_cue = cues[idx + 1] if idx + 1 < len(cues) else None

        decision = compute_trim(
            cue, speech_ends, search_range, comfort_buffer, min_trim,
            cps_soft_ceiling, cps_hard_limit, min_duration_ms, min_gap_ms,
            next_cue=next_cue,
        )
        results.append(decision)

        if decision['action'] in ('trim', 'partial_trim') and not dry_run:
            cue.end_ms = decision['new_end']

        if verbose and decision['action'] in ('trim', 'partial_trim'):
            tag = 'TRIM' if decision['method'] == 'full' else 'PARTIAL'
            print(f'  Cue {cue.index:>3d}: {tag} -{decision["trim_ms"]}ms '
                  f'(end {ms_to_timecode(decision["old_end"])} → '
                  f'{ms_to_timecode(decision["new_end"])}  '
                  f'CPS {decision["new_cps"]})')

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Trim subtitle end times to match speech boundaries (VAD).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Pipeline usage (Phase 4b)
    python3 trim_to_speech.py movie.mkv merged.nl.srt -o trimmed.nl.srt --fps 25

    # Standalone fix of existing translation
    python3 trim_to_speech.py movie.mkv movie.nl.srt -o movie-trimmed.nl.srt -v

    # Dry run — see what would change
    python3 trim_to_speech.py movie.mkv merged.nl.srt -o trimmed.nl.srt --dry-run -v
        """,
    )

    parser.add_argument('video', help='Video file (for audio extraction)')
    parser.add_argument('srt', help='Input SRT subtitle file')
    parser.add_argument('-o', '--output', required=True,
                        help='Output SRT file (must differ from input)')
    parser.add_argument('--fps', type=float, default=25,
                        help='Framerate for constraint lookup (default: 25)')
    parser.add_argument('--comfort-buffer', type=int, default=250,
                        help='ms to keep after speech end (default: 250)')
    parser.add_argument('--min-trim', type=int, default=400,
                        help='Minimum trim amount in ms (default: 400)')
    parser.add_argument('--aggressiveness', type=int, default=2,
                        choices=[0, 1, 2, 3],
                        help='VAD aggressiveness: 0=lenient 3=strict (default: 2)')
    parser.add_argument('--hangover', type=int, default=210,
                        help='Smooth silence gaps shorter than this ms (default: 210)')
    parser.add_argument('--report', metavar='FILE',
                        help='Write JSON report to file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be trimmed without modifying')
    parser.add_argument('--no-cache', action='store_true',
                        help='Re-extract audio from video')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print per-cue trim decisions')

    args = parser.parse_args()

    # Late imports — VAD dependencies only needed at runtime, not for unit tests
    from vad_timing_check import (
        load_audio, build_speech_map, smooth_speech_map, find_transitions,
    )
    import webrtcvad

    # Safety: don't overwrite input
    input_abs = os.path.abspath(args.srt)
    output_abs = os.path.abspath(args.output)
    if input_abs == output_abs:
        print('Error: output file must differ from input file.', file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.video):
        print(f'Error: video not found: {args.video}', file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.srt):
        print(f'Error: SRT not found: {args.srt}', file=sys.stderr)
        sys.exit(1)

    # Load constraints
    constraints = get_constraints(args.fps)
    cps_soft_ceiling = constraints['cps_soft_ceiling']
    cps_hard_limit = constraints['cps_hard_limit']
    min_duration_ms = constraints['min_duration_ms']
    min_gap_ms = constraints['min_gap_ms']

    print(f'Constraints (fps={args.fps}): CPS ceiling={cps_soft_ceiling}, '
          f'hard limit={cps_hard_limit}, min_gap={min_gap_ms}ms, '
          f'min_duration={min_duration_ms}ms')

    # Load audio and build speech map
    frame_ms = 30
    hangover_frames = max(1, args.hangover // frame_ms)

    audio, sr = load_audio(args.video, args.no_cache)
    audio_dur = len(audio) / 2 / sr
    print(f'Audio: {audio_dur:.0f}s ({audio_dur / 60:.1f} min), {sr} Hz')

    vad = webrtcvad.Vad(args.aggressiveness)
    print(f'Running VAD (aggressiveness={args.aggressiveness}, '
          f'hangover={hangover_frames * frame_ms}ms)...')

    raw_map = build_speech_map(audio, sr, vad, frame_ms)
    smoothed = smooth_speech_map(raw_map, hangover_frames)
    speech_starts, speech_ends = find_transitions(smoothed, frame_ms)
    print(f'VAD: {len(speech_starts)} speech segments detected')

    # Parse SRT
    cues, errors = parse_srt_file(args.srt)
    if errors:
        print(f'Warning: {len(errors)} parse errors in {args.srt}')
    print(f'Cues: {len(cues)}')

    # Run trim
    search_range = 2000
    if args.dry_run:
        print(f'\n=== DRY RUN (no changes will be written) ===\n')

    results = trim_all(
        cues, speech_ends, search_range,
        comfort_buffer=args.comfort_buffer,
        min_trim=args.min_trim,
        cps_soft_ceiling=cps_soft_ceiling,
        cps_hard_limit=cps_hard_limit,
        min_duration_ms=min_duration_ms,
        min_gap_ms=min_gap_ms,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    # Summary
    trimmed = [r for r in results if r['action'] == 'trim']
    partial = [r for r in results if r['action'] == 'partial_trim']
    skipped = [r for r in results if r['action'] == 'skip']

    skip_reasons = {}
    for r in skipped:
        reason = r['reason']
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    total_trim_ms = sum(r['trim_ms'] for r in trimmed + partial)

    print(f'\n── Summary ──')
    print(f'Total cues:    {len(cues)}')
    print(f'Full trims:    {len(trimmed)}')
    print(f'Partial trims: {len(partial)}')
    print(f'Skipped:       {len(skipped)}')
    print(f'Total trimmed: {total_trim_ms}ms ({total_trim_ms / 1000:.1f}s)')
    if total_trim_ms and (trimmed or partial):
        avg = total_trim_ms / (len(trimmed) + len(partial))
        print(f'Avg trim:      {avg:.0f}ms')

    if skip_reasons and args.verbose:
        print(f'\nSkip reasons:')
        for reason, count in sorted(skip_reasons.items(), key=lambda x: -x[1]):
            print(f'  {reason}: {count}')

    # Write output
    if not args.dry_run:
        write_srt(cues, args.output)
        print(f'\nOutput: {args.output}')
    else:
        print(f'\nDry run complete. No files written.')

    # JSON report
    if args.report:
        report = {
            'video': os.path.basename(args.video),
            'srt': os.path.basename(args.srt),
            'settings': {
                'fps': args.fps,
                'comfort_buffer_ms': args.comfort_buffer,
                'min_trim_ms': args.min_trim,
                'aggressiveness': args.aggressiveness,
                'hangover_ms': args.hangover,
                'cps_soft_ceiling': cps_soft_ceiling,
                'cps_hard_limit': cps_hard_limit,
                'min_gap_ms': min_gap_ms,
                'min_duration_ms': min_duration_ms,
                'dry_run': args.dry_run,
            },
            'summary': {
                'total_cues': len(cues),
                'full_trims': len(trimmed),
                'partial_trims': len(partial),
                'skipped': len(skipped),
                'total_trim_ms': total_trim_ms,
                'skip_reasons': skip_reasons,
            },
            'trims': [r for r in results if r['action'] in ('trim', 'partial_trim')],
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f'Report: {args.report}')


if __name__ == '__main__':
    main()
