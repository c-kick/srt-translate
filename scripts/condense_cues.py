#!/usr/bin/env python3
"""Apply text condensation edits to specific cues by index."""
import sys
import json
import argparse

sys.path.insert(0, '/mnt/nas/video/.claude/skills/srt-translate/scripts')
from srt_utils import parse_srt_file, write_srt

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file')
    parser.add_argument('--edits', required=True, help='JSON file with edits: {index: new_text}')
    parser.add_argument('--output', '-o', required=True)
    args = parser.parse_args()

    cues, _ = parse_srt_file(args.input_file)

    with open(args.edits, 'r') as f:
        edits = json.load(f)

    applied = 0
    for cue in cues:
        key = str(cue.index)
        if key in edits:
            cue.text = edits[key]
            applied += 1

    write_srt(cues, args.output)
    print(f"Applied {applied} edits out of {len(edits)} requested")

if __name__ == '__main__':
    main()
