#!/usr/bin/env python3
"""
Identify likely burned-in title-card cues by comparing local subtitle files.

Privacy boundary: this script is local-only. It reads a synced English SRT and
a previously downloaded foreign SRT, compares cue timings, and writes matching
title-card candidates. It does not perform network requests.

Usage:
    python3 detect_title_cards.py EN_SRT FOREIGN_SRT --output title_cards.srt

Exit codes:
    0  Title cards found and written
    1  No title cards found
    2  Input or parse error
"""

from __future__ import annotations

import argparse
import bisect
import statistics
import sys
from pathlib import Path

from srt_utils import Subtitle, parse_srt_file, write_srt

# A foreign cue is a title card candidate if no EN cue starts within this window.
TITLE_CARD_GAP_MS = 1500
# Ignore very short cues, which are usually parser noise or music fragments.
MIN_DURATION_MS = 400
# Estimate a global offset by clustering plausible EN/foreign start deltas.
ALIGNMENT_BIN_MS = 500
MAX_GLOBAL_OFFSET_MS = 120000
MIN_PRIMARY_CLUSTER_SIZE = 2


def strongest_delta_cluster(deltas: list[int], alignment_bin_ms: int) -> list[int]:
    clusters: dict[int, list[int]] = {}
    for delta in deltas:
        bucket = round(delta / alignment_bin_ms)
        clusters.setdefault(bucket, []).append(delta)

    return max(
        clusters.values(),
        key=lambda values: (len(values), -abs(statistics.median(values))),
    )


def estimate_timeline_offset(
    english_cues: list[Subtitle],
    foreign_cues: list[Subtitle],
    alignment_bin_ms: int = ALIGNMENT_BIN_MS,
    max_offset_ms: int = MAX_GLOBAL_OFFSET_MS,
) -> int | None:
    """Return the ms offset to add to foreign cues to align them to English."""
    en_starts = sorted(cue.start_ms for cue in english_cues)
    nearest_deltas: list[int] = []

    for cue in foreign_cues:
        if cue.duration_ms < MIN_DURATION_MS or not cue.text.strip():
            continue
        idx = bisect.bisect_left(en_starts, cue.start_ms)
        nearby = en_starts[max(0, idx - 1): idx + 2]
        if nearby:
            nearest = min(nearby, key=lambda start: abs(start - cue.start_ms))
            delta = nearest - cue.start_ms
            if abs(delta) <= max_offset_ms:
                nearest_deltas.append(delta)

    if nearest_deltas:
        best_cluster = strongest_delta_cluster(nearest_deltas, alignment_bin_ms)
        if len(best_cluster) >= MIN_PRIMARY_CLUSTER_SIZE:
            offset = round(statistics.median(best_cluster))
            if abs(offset) > max_offset_ms:
                return None
            return offset

    all_pair_deltas: list[int] = []
    for cue in foreign_cues:
        if cue.duration_ms < MIN_DURATION_MS or not cue.text.strip():
            continue
        min_start = cue.start_ms - max_offset_ms
        max_start = cue.start_ms + max_offset_ms
        left = bisect.bisect_left(en_starts, min_start)
        right = bisect.bisect_right(en_starts, max_start)
        for start in en_starts[left:right]:
            all_pair_deltas.append(start - cue.start_ms)

    if not all_pair_deltas:
        return None

    best_cluster = strongest_delta_cluster(all_pair_deltas, alignment_bin_ms)
    offset = round(statistics.median(best_cluster))
    if abs(offset) > max_offset_ms:
        return None
    return offset


def shift_cue(cue: Subtitle, offset_ms: int) -> Subtitle:
    start_ms = max(0, cue.start_ms + offset_ms)
    end_ms = max(start_ms + 1, cue.end_ms + offset_ms)
    return Subtitle(index=cue.index, start_ms=start_ms, end_ms=end_ms, text=cue.text)


def has_matching_english_cue(
    english_cues: list[Subtitle],
    cue: Subtitle,
    padding_ms: int,
) -> bool:
    for english in english_cues:
        if english.end_ms < cue.start_ms - padding_ms:
            continue
        if english.start_ms > cue.end_ms + padding_ms:
            return False
        return True
    return False


def find_title_cards(
    english_cues: list[Subtitle],
    foreign_cues: list[Subtitle],
    gap_ms: int = TITLE_CARD_GAP_MS,
    min_duration_ms: int = MIN_DURATION_MS,
) -> list[Subtitle]:
    offset_ms = estimate_timeline_offset(english_cues, foreign_cues)
    if offset_ms is None:
        return []

    english_by_start = sorted(english_cues, key=lambda cue: cue.start_ms)
    candidates: list[Subtitle] = []

    for cue in foreign_cues:
        if cue.duration_ms < min_duration_ms:
            continue
        if not cue.text.strip():
            continue

        shifted = shift_cue(cue, offset_ms)
        if not has_matching_english_cue(english_by_start, shifted, gap_ms):
            candidates.append(shifted)

    return candidates


def detect_title_cards(
    english_srt: str | Path,
    foreign_srt: str | Path,
    output_path: str | Path,
    gap_ms: int = TITLE_CARD_GAP_MS,
    min_duration_ms: int = MIN_DURATION_MS,
) -> int:
    english_cues, english_errors = parse_srt_file(str(english_srt))
    foreign_cues, foreign_errors = parse_srt_file(str(foreign_srt))
    if english_errors:
        raise ValueError(f"English SRT parse errors: {'; '.join(english_errors[:3])}")
    if foreign_errors:
        raise ValueError(f"Foreign SRT parse errors: {'; '.join(foreign_errors[:3])}")

    candidates = find_title_cards(english_cues, foreign_cues, gap_ms, min_duration_ms)
    if not candidates:
        return 0

    output_cues = [
        Subtitle(index=i, start_ms=cue.start_ms, end_ms=cue.end_ms, text=cue.text)
        for i, cue in enumerate(candidates, start=1)
    ]
    write_srt(output_cues, str(output_path))
    return len(output_cues)


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect title-card cues from local subtitle files")
    parser.add_argument("english_srt", metavar="EN_SRT", help="Path to the synced English SRT")
    parser.add_argument("foreign_srt", metavar="FOREIGN_SRT", help="Path to the downloaded foreign SRT")
    parser.add_argument("--output", default="title_cards.srt", help="Output SRT path")
    parser.add_argument("--gap-ms", type=int, default=TITLE_CARD_GAP_MS, help="Nearby English cue window in ms")
    parser.add_argument("--min-duration-ms", type=int, default=MIN_DURATION_MS, help="Minimum cue duration in ms")
    args = parser.parse_args()

    try:
        count = detect_title_cards(
            args.english_srt,
            args.foreign_srt,
            args.output,
            args.gap_ms,
            args.min_duration_ms,
        )
    except Exception as e:
        print(f"SKIP: Failed to detect title cards: {e}", file=sys.stderr)
        return 2

    if count == 0:
        print("No title cards detected (all foreign cues have matching EN cues nearby).")
        return 1

    print(f"Found {count} title card cue(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
