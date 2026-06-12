#!/usr/bin/env python3
"""
Filter candidate subtitle cues down to cues not covered by an existing subtitle.

Usage:
    python3 filter_missing_subtitles.py CANDIDATES_SRT EXISTING_SRT --output missing.srt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from srt_utils import Subtitle, parse_srt_file, write_srt

MIN_OVERLAP_MS = 250
MIN_OVERLAP_RATIO = 0.5


def overlap_ms(left: Subtitle, right: Subtitle) -> int:
    return max(0, min(left.end_ms, right.end_ms) - max(left.start_ms, right.start_ms))


def is_covered(candidate: Subtitle, existing_cues: list[Subtitle]) -> bool:
    candidate_duration = max(1, candidate.duration_ms)
    for existing in existing_cues:
        overlap = overlap_ms(candidate, existing)
        if overlap >= MIN_OVERLAP_MS:
            return True
        if overlap / candidate_duration >= MIN_OVERLAP_RATIO:
            return True
    return False


def filter_missing_subtitles(
    candidates_srt: str | Path,
    existing_srt: str | Path,
    output_path: str | Path,
) -> int:
    candidates, candidate_errors = parse_srt_file(str(candidates_srt))
    existing, existing_errors = parse_srt_file(str(existing_srt))
    if candidate_errors:
        raise ValueError(f"Candidate SRT parse errors: {'; '.join(candidate_errors[:3])}")
    if existing_errors:
        raise ValueError(f"Existing SRT parse errors: {'; '.join(existing_errors[:3])}")

    missing = [
        Subtitle(index=0, start_ms=cue.start_ms, end_ms=cue.end_ms, text=cue.text)
        for cue in candidates
        if cue.text.strip() and not is_covered(cue, existing)
    ]

    if not missing:
        return 0

    missing.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.text))
    for index, cue in enumerate(missing, start=1):
        cue.index = index

    write_srt(missing, str(output_path))
    return len(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter missing subtitle candidates")
    parser.add_argument("candidates_srt", help="Candidate missing subtitle cues")
    parser.add_argument("existing_srt", help="Existing translated subtitle")
    parser.add_argument("--output", required=True, help="Output SRT path for missing cues")
    args = parser.parse_args()

    try:
        count = filter_missing_subtitles(args.candidates_srt, args.existing_srt, args.output)
    except Exception as e:
        print(f"ERROR: Failed to filter missing subtitles: {e}", file=sys.stderr)
        return 2

    if count == 0:
        print("No missing cues remain after filtering.")
        return 1

    print(f"Wrote {count} missing cue(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
