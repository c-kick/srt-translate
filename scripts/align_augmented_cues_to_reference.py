#!/usr/bin/env python3
"""
Build a separate Dutch subtitle with augmented cues aligned to reference timings.

Usage:
    python3 align_augmented_cues_to_reference.py BASE_NL_SRT REFERENCE_SRT TRANSLATED_MISSING_NL_SRT --output OUTPUT_DUT_SRT

BASE_NL_SRT is left untouched. REFERENCE_SRT supplies timing. TRANSLATED_MISSING_NL_SRT
supplies text for the added cues.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from srt_utils import Subtitle, parse_srt_file, write_srt

MIN_GAP_MS = 120


def align_augmented_cues(
    base_srt: str | Path,
    reference_srt: str | Path,
    translated_srt: str | Path,
    output_path: str | Path,
    min_gap_ms: int = MIN_GAP_MS,
) -> int:
    base, base_errors = parse_srt_file(str(base_srt))
    reference, reference_errors = parse_srt_file(str(reference_srt))
    translated, translated_errors = parse_srt_file(str(translated_srt))
    if base_errors:
        raise ValueError(f"Base SRT parse errors: {'; '.join(base_errors[:3])}")
    if reference_errors:
        raise ValueError(f"Reference SRT parse errors: {'; '.join(reference_errors[:3])}")
    if translated_errors:
        raise ValueError(f"Translated SRT parse errors: {'; '.join(translated_errors[:3])}")
    if len(reference) != len(translated):
        raise ValueError(
            f"Reference/translated cue count mismatch: {len(reference)} vs {len(translated)}"
        )

    merged: list[tuple[Subtitle, bool]] = [
        (Subtitle(index=0, start_ms=cue.start_ms, end_ms=cue.end_ms, text=cue.text), False)
        for cue in base
    ]

    for ref_cue, translated_cue in zip(reference, translated):
        text = translated_cue.text.strip()
        if not text:
            continue
        merged.append(
            (
                Subtitle(
                    index=0,
                    start_ms=ref_cue.start_ms,
                    end_ms=ref_cue.end_ms,
                    text=text,
                ),
                True,
            )
        )

    merged.sort(key=lambda item: (item[0].start_ms, item[0].end_ms, item[0].text))

    for idx, (cue, is_inserted) in enumerate(merged):
        if not is_inserted:
            continue
        if idx > 0:
            previous, previous_inserted = merged[idx - 1]
            latest_previous_end = cue.start_ms - min_gap_ms
            if not previous_inserted and previous.end_ms > latest_previous_end > previous.start_ms:
                previous.end_ms = latest_previous_end
        if idx + 1 < len(merged):
            next_cue, next_inserted = merged[idx + 1]
            earliest_next_start = cue.end_ms + min_gap_ms
            if not next_inserted and next_cue.start_ms < earliest_next_start < next_cue.end_ms:
                next_cue.start_ms = earliest_next_start

    output = [cue for cue, _is_inserted in merged]
    for index, cue in enumerate(output, start=1):
        cue.index = index

    write_srt(output, str(output_path))
    return len(translated)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a separate Dutch SRT with augmented cues aligned to reference timings"
    )
    parser.add_argument("base_srt", help="Existing/base Dutch SRT to use without modifying it")
    parser.add_argument("reference_srt", help="Reference SRT whose timings should be used")
    parser.add_argument("translated_srt", help="Translated missing cues whose text should be used")
    parser.add_argument("--output", required=True, help="Output .dut.srt path")
    args = parser.parse_args()

    try:
        count = align_augmented_cues(args.base_srt, args.reference_srt, args.translated_srt, args.output)
    except Exception as e:
        print(f"ERROR: Failed to align augmented cues: {e}", file=sys.stderr)
        return 2

    print(f"Wrote {count} aligned cue(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
