#!/usr/bin/env python3
"""Extend end times for cues with CPS > threshold to reach target CPS.

Also supports gap-closing (Auteursbond: gaps < 1s should be closed by
extending end times).
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srt_utils import parse_srt_file, write_srt

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file')
    parser.add_argument('--output', '-o', required=True)
    parser.add_argument('--target-cps', type=float, default=12.5)
    parser.add_argument('--min-gap', type=int, default=120)
    parser.add_argument('--max-duration', type=int, default=7000)
    parser.add_argument('--threshold', type=float, default=13.0)
    parser.add_argument('--close-gaps', type=int, default=0, metavar='MS',
                        help='Close gaps smaller than MS by extending end times (Auteursbond: 1000)')
    args = parser.parse_args()

    cues, errors = parse_srt_file(args.input_file)
    extended = 0
    gaps_closed = 0

    # Pass 1: Close small gaps (Auteursbond "aansluiten")
    if args.close_gaps > 0:
        for i in range(len(cues) - 1):
            gap = cues[i + 1].start_ms - cues[i].end_ms
            if 0 < gap < args.close_gaps:
                new_end = cues[i + 1].start_ms - args.min_gap
                if new_end > cues[i].end_ms and new_end - cues[i].start_ms <= args.max_duration:
                    cues[i].end_ms = new_end
                    gaps_closed += 1

    # Pass 2: CPS-based extension
    for i, cue in enumerate(cues):
        if cue.cps > args.threshold:
            if i + 1 < len(cues):
                next_start = cues[i + 1].start_ms
                available = next_start - cue.end_ms
                if available > args.min_gap:
                    needed_ms = int((cue.char_count / args.target_cps) * 1000)
                    max_end = next_start - args.min_gap
                    new_end = min(cue.start_ms + needed_ms, max_end)
                    if new_end - cue.start_ms > args.max_duration:
                        new_end = cue.start_ms + args.max_duration
                    if new_end > cue.end_ms:
                        cue.end_ms = new_end
                        extended += 1
            else:
                needed_ms = int((cue.char_count / args.target_cps) * 1000)
                new_end = cue.start_ms + min(needed_ms, args.max_duration)
                if new_end > cue.end_ms:
                    cue.end_ms = new_end
                    extended += 1

    write_srt(cues, args.output)
    parts = [f"Extended {extended} cues"]
    if args.close_gaps > 0:
        parts.append(f"closed {gaps_closed} gaps < {args.close_gaps}ms")
    print(", ".join(parts))

if __name__ == '__main__':
    main()
