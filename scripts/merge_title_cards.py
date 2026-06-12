#!/usr/bin/env python3
"""
Merge detected title-card cues into an English source SRT.

Usage:
    python3 merge_title_cards.py SOURCE_EN_SRT TITLE_CARDS_SRT

The source file is updated in place. Each inserted cue is written as:
    [TITLE CARD: "foreign cue text"]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from srt_utils import Subtitle, parse_srt_file, write_srt


def normalize_title_text(text: str) -> str:
    return " ".join(text.replace('"', "").split())


def merge_title_cards(source_srt: str | Path, title_cards_srt: str | Path) -> int:
    source, source_errors = parse_srt_file(str(source_srt))
    title_cards, title_errors = parse_srt_file(str(title_cards_srt))
    if source_errors:
        raise ValueError(f"Source SRT parse errors: {'; '.join(source_errors[:3])}")
    if title_errors:
        raise ValueError(f"Title-card SRT parse errors: {'; '.join(title_errors[:3])}")

    existing_title_starts = {
        cue.start_ms
        for cue in source
        if cue.text.strip().startswith("[TITLE CARD:")
    }

    merged = list(source)
    inserted = 0
    for cue in title_cards:
        if cue.start_ms in existing_title_starts:
            continue
        text = normalize_title_text(cue.text)
        if not text:
            continue
        merged.append(
            Subtitle(
                index=0,
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                text=f'[TITLE CARD: "{text}"]',
            )
        )
        inserted += 1

    if inserted == 0:
        return 0

    merged.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.text))
    for index, cue in enumerate(merged, start=1):
        cue.index = index

    write_srt(merged, str(source_srt))
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge title-card cues into an English source SRT")
    parser.add_argument("source_srt", help="English source SRT to update in place")
    parser.add_argument("title_cards_srt", help="Detected title-card SRT")
    args = parser.parse_args()

    try:
        count = merge_title_cards(args.source_srt, args.title_cards_srt)
    except Exception as e:
        print(f"ERROR: Failed to merge title cards: {e}", file=sys.stderr)
        return 2

    print(f"Merged {count} title card(s) into {args.source_srt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
