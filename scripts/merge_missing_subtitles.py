#!/usr/bin/env python3
"""
Merge translated missing subtitle cues into an existing translated SRT.

Usage:
    python3 merge_missing_subtitles.py EXISTING_NL_SRT MISSING_NL_SRT

The existing file is backed up and updated in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from srt_utils import Subtitle, backup_if_exists, parse_srt_file, write_srt

MIN_GAP_MS = 120


def enforce_min_gaps(subtitles: list[Subtitle], min_gap_ms: int = MIN_GAP_MS) -> None:
    for previous, current in zip(subtitles, subtitles[1:]):
        earliest_start = previous.end_ms + min_gap_ms
        if current.start_ms >= earliest_start:
            continue
        if earliest_start < current.end_ms:
            current.start_ms = earliest_start


def merge_missing_subtitles(existing_srt: str | Path, missing_srt: str | Path) -> int:
    existing, existing_errors = parse_srt_file(str(existing_srt))
    missing, missing_errors = parse_srt_file(str(missing_srt))
    if existing_errors:
        raise ValueError(f"Existing SRT parse errors: {'; '.join(existing_errors[:3])}")
    if missing_errors:
        raise ValueError(f"Missing SRT parse errors: {'; '.join(missing_errors[:3])}")

    merged = list(existing)
    inserted = 0
    existing_keys = {
        (cue.start_ms, cue.end_ms, " ".join(cue.text.split()).casefold())
        for cue in existing
    }

    for cue in missing:
        text = cue.text.strip()
        if not text:
            continue
        key = (cue.start_ms, cue.end_ms, " ".join(text.split()).casefold())
        if key in existing_keys:
            continue
        merged.append(Subtitle(index=0, start_ms=cue.start_ms, end_ms=cue.end_ms, text=text))
        inserted += 1

    if inserted == 0:
        return 0

    merged.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.text))
    enforce_min_gaps(merged)
    for index, cue in enumerate(merged, start=1):
        cue.index = index

    backup_if_exists(str(existing_srt))
    write_srt(merged, str(existing_srt))
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge missing translated cues into an existing SRT")
    parser.add_argument("existing_srt", help="Existing translated SRT to update in place")
    parser.add_argument("missing_srt", help="Translated missing cues to insert")
    args = parser.parse_args()

    try:
        count = merge_missing_subtitles(args.existing_srt, args.missing_srt)
    except Exception as e:
        print(f"ERROR: Failed to merge missing subtitles: {e}", file=sys.stderr)
        return 2

    print(f"Merged {count} missing cue(s) into {args.existing_srt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
