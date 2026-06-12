#!/usr/bin/env python3
"""
Extract title-card cues from a source SRT.

Usage:
    python3 extract_title_cards.py SOURCE_SRT --output title_cards.srt

The input cues are expected to use the marker format inserted by
merge_title_cards.py:
    [TITLE CARD: "foreign cue text"]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from srt_utils import Subtitle, parse_srt_file, write_srt

TITLE_CARD_RE = re.compile(r'^\[TITLE CARD:\s*["“]?(.*?)["”]?\]$', re.DOTALL)


def extract_title_card_text(text: str) -> str | None:
    normalized = " ".join(text.strip().split())
    match = TITLE_CARD_RE.match(normalized)
    if not match:
        return None
    extracted = match.group(1).strip()
    return extracted or None


def extract_title_cards(source_srt: str | Path, output_path: str | Path) -> int:
    source, errors = parse_srt_file(str(source_srt))
    if errors:
        raise ValueError(f"Source SRT parse errors: {'; '.join(errors[:3])}")

    output_cues: list[Subtitle] = []
    for cue in source:
        title_text = extract_title_card_text(cue.text)
        if title_text is None:
            continue
        output_cues.append(
            Subtitle(
                index=len(output_cues) + 1,
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                text=title_text,
            )
        )

    if not output_cues:
        return 0

    write_srt(output_cues, str(output_path))
    return len(output_cues)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract marked title-card cues from a source SRT")
    parser.add_argument("source_srt", help="Source SRT containing [TITLE CARD: ...] cues")
    parser.add_argument("--output", required=True, help="Output SRT path")
    args = parser.parse_args()

    try:
        count = extract_title_cards(args.source_srt, args.output)
    except Exception as e:
        print(f"ERROR: Failed to extract title cards: {e}", file=sys.stderr)
        return 2

    if count == 0:
        print("No title card cues found.")
        return 1

    print(f"Extracted {count} title card cue(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
