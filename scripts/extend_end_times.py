#!/usr/bin/env python3
"""Extend end times for cues with CPS > threshold to reach target CPS."""
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
    args = parser.parse_args()

    cues, errors = parse_srt_file(args.input_file)
    extended = 0

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
    print(f"Extended {extended} cues")

if __name__ == '__main__':
    main()
