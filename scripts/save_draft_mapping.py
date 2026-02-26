#!/usr/bin/env python3
"""
Save a timecode-based mapping from draft NL cues to EN source cues.

Run BEFORE Phase 3 (validate_srt --fix) to capture the NL→EN correspondence
established during Phase 2 translation, before post-processing renumbers cues.

Matching uses start-time proximity: draft NL cues inherit their source EN
cue's start time, making temporal matching reliable even when cue indices
are non-deterministic.

Usage:
    python3 save_draft_mapping.py draft.nl.srt source.en.srt \
        --output draft_mapping.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srt_utils import parse_srt_file


def build_mapping(nl_cues, en_cues, tolerance_ms=500, fallback_ms=1000):
    """
    Match each draft NL cue to EN source cue(s) by start-time proximity.

    Args:
        nl_cues: Parsed NL subtitle cues (pre-Phase-3 draft)
        en_cues: Parsed EN source subtitle cues
        tolerance_ms: Primary match window (ms)
        fallback_ms: Extended window for nearest-match fallback (ms)

    Returns:
        List of mapping dicts with NL and EN timecodes.
    """
    mappings = []
    for nl_cue in nl_cues:
        # Find all EN cues within tolerance of this NL cue's start time
        matched_en = [en for en in en_cues
                      if abs(en.start_ms - nl_cue.start_ms) <= tolerance_ms]

        # Fallback: nearest EN cue within extended tolerance
        if not matched_en:
            best = min(en_cues, key=lambda e: abs(e.start_ms - nl_cue.start_ms))
            if abs(best.start_ms - nl_cue.start_ms) <= fallback_ms:
                matched_en = [best]

        mappings.append({
            "nl_start_ms": nl_cue.start_ms,
            "nl_end_ms": nl_cue.end_ms,
            "en_indices": [e.index for e in matched_en],
            "en_start_ms": matched_en[0].start_ms if matched_en else None,
            "en_end_ms": matched_en[-1].end_ms if matched_en else None,
        })

    return mappings


def main():
    parser = argparse.ArgumentParser(
        description='Save draft NL→EN timecode mapping before Phase 3 renumbering',
    )
    parser.add_argument('nl_srt', help='Draft NL subtitle file (pre-Phase-3)')
    parser.add_argument('en_srt', help='Source EN subtitle file')
    parser.add_argument('--output', '-o', required=True,
                        help='Output JSON mapping file')
    parser.add_argument('--tolerance', type=int, default=500,
                        help='Primary match tolerance (ms, default: 500)')
    parser.add_argument('--fallback', type=int, default=1000,
                        help='Fallback match tolerance (ms, default: 1000)')
    args = parser.parse_args()

    nl_cues, nl_errors = parse_srt_file(args.nl_srt)
    en_cues, en_errors = parse_srt_file(args.en_srt)

    if not nl_cues:
        print(f"Error: No cues parsed from {args.nl_srt}", file=sys.stderr)
        sys.exit(1)
    if not en_cues:
        print(f"Error: No cues parsed from {args.en_srt}", file=sys.stderr)
        sys.exit(1)

    mappings = build_mapping(nl_cues, en_cues, args.tolerance, args.fallback)

    matched = sum(1 for m in mappings if m['en_start_ms'] is not None)
    unmatched = len(mappings) - matched

    output = {
        "source_nl": args.nl_srt,
        "source_en": args.en_srt,
        "parameters": {
            "tolerance_ms": args.tolerance,
            "fallback_ms": args.fallback,
        },
        "statistics": {
            "nl_cues": len(nl_cues),
            "en_cues": len(en_cues),
            "matched": matched,
            "unmatched": unmatched,
        },
        "mappings": mappings,
    }

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Draft mapping: {matched}/{len(nl_cues)} NL cues matched to EN "
          f"({unmatched} unmatched) → {args.output}")


if __name__ == '__main__':
    main()
