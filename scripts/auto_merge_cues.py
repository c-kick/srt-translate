#!/usr/bin/env python3
"""
Automatically merge adjacent subtitle cues based on gap and duration thresholds.

This script handles all timecode math mechanically, removing merge responsibility
from the translation phase. Claude translates 1:1, this script merges.

Merge control markers (added during translation, stripped from output):
    [SC] = Speaker Change - merge with dual-speaker formatting (dash on line 2)
    [NM] = No Merge - do not merge this cue with the previous one

Usage:
    python3 auto_merge_cues.py input.srt \
        --gap-threshold 1000 \
        --max-duration 7000 \
        --output merged.srt \
        --report merge_report.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from srt_utils import parse_srt_file, write_srt, Subtitle, visible_length, is_dual_speaker


def detect_merge_marker(text: str) -> tuple[str, str]:
    """
    Check for merge control markers and strip them.

    Markers:
        [SC] = Speaker Change - merge with dual-speaker formatting
        [NM] = No Merge - do not merge this cue with previous

    Returns:
        Tuple of (marker_type, cleaned_text)
        marker_type is "SC", "NM", or "" (no marker)
    """
    stripped = text.lstrip()
    if stripped.startswith('[SC]'):
        cleaned = stripped[4:].lstrip()
        return "SC", cleaned
    if stripped.startswith('[NM]'):
        cleaned = stripped[4:].lstrip()
        return "NM", cleaned
    return "", text


def wrap_text(text: str, max_chars: int, max_lines: int) -> tuple[bool, str]:
    """
    Word-wrap text to fit within line constraints.

    Args:
        text: Text to wrap (may contain newlines, will be collapsed)
        max_chars: Maximum characters per line
        max_lines: Maximum number of lines

    Returns:
        Tuple of (success, wrapped_text)
    """
    # Collapse any existing newlines to spaces
    collapsed = ' '.join(text.split())
    words = collapsed.split()

    if not words:
        return True, ""

    lines = []
    current_line = []
    current_len = 0

    for word in words:
        word_len = len(word)

        # Check if word alone exceeds max_chars (can't split words)
        if word_len > max_chars:
            return False, ""

        if current_len + (1 if current_line else 0) + word_len <= max_chars:
            current_line.append(word)
            current_len += (1 if current_len > 0 else 0) + word_len
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
            current_len = word_len

    if current_line:
        lines.append(' '.join(current_line))

    if len(lines) <= max_lines and all(visible_length(l) <= max_chars for l in lines):
        return True, '\n'.join(lines)
    return False, ""


def can_merge_text(text1: str, text2: str, max_lines: int, max_chars: int,
                   is_speaker_change: bool = False) -> tuple[bool, str]:
    """
    Check if two texts can be merged within constraints.

    Args:
        text1: First text
        text2: Second text
        max_lines: Maximum lines in merged result
        max_chars: Maximum characters per line
        is_speaker_change: If True, format as dual-speaker with dash on line 2

    Returns:
        Tuple of (can_merge, merged_text)
    """
    # Handle dual-speaker format: keep separate with dash prefix on line 2
    if is_speaker_change:
        # For speaker changes, don't collapse - preserve both as distinct lines
        text1_clean = text1.strip()
        text2_clean = text2.strip()

        # Remove any existing dash prefix from text2 (we'll add our own)
        if text2_clean.startswith('-'):
            text2_clean = text2_clean[1:].lstrip(' ')

        merged = f"{text1_clean}\n-{text2_clean}"
        lines = merged.split('\n')

        if len(lines) <= max_lines and all(visible_length(l) <= max_chars for l in lines):
            return True, merged
        return False, ""

    # Don't collapse text that already contains dual-speaker formatting
    if is_dual_speaker(text1) or is_dual_speaker(text2):
        return False, ""

    # For same-speaker: collapse both texts and rewrap together
    collapsed1 = ' '.join(text1.split())
    collapsed2 = ' '.join(text2.split())

    # Strip continuation ellipses at the merge boundary.
    # Trailing "..." on cue 1 = sentence continues in next cue.
    # Leading "..." on cue 2 = sentence started in previous cue.
    # Once merged, these are no longer needed.
    if collapsed1.endswith('...'):
        collapsed1 = collapsed1[:-3].rstrip()
    if collapsed2.startswith('...'):
        collapsed2 = collapsed2[3:].lstrip()

    combined = f"{collapsed1} {collapsed2}"

    return wrap_text(combined, max_chars, max_lines)


def merge_cues(
    subtitles: list[Subtitle],
    gap_threshold_ms: int,
    max_duration_ms: int,
    max_lines: int = 2,
    max_chars: int = 42
) -> tuple[list[Subtitle], list[dict]]:
    """
    Merge adjacent cues based on thresholds.

    Args:
        subtitles: List of Subtitle objects
        gap_threshold_ms: Max gap between cues to consider merging (ms)
        max_duration_ms: Max combined duration for merged cue (ms)
        max_lines: Max lines in merged cue
        max_chars: Max characters per line

    Returns:
        Tuple of (merged_subtitles, merge_report)
    """
    if not subtitles:
        return [], []

    merged = []
    report = []

    i = 0
    new_index = 1

    while i < len(subtitles):
        current = subtitles[i]

        # Look ahead to see if we can merge with next cue(s)
        merge_candidates = [current]
        j = i + 1

        while j < len(subtitles):
            next_cue = subtitles[j]
            prev_cue = merge_candidates[-1]

            # Calculate gap
            gap = next_cue.start_ms - prev_cue.end_ms

            # Check gap threshold
            if gap > gap_threshold_ms:
                break

            # Calculate combined duration (from first candidate's start to this cue's end)
            combined_duration = next_cue.end_ms - merge_candidates[0].start_ms

            # Check duration threshold
            if combined_duration > max_duration_ms:
                break

            # Check for merge control markers
            marker, next_text_clean = detect_merge_marker(next_cue.text)

            # [NM] = don't merge this cue at all
            if marker == "NM":
                break

            # [SC] = speaker change, only merge if this would be the 2nd cue
            # (dual-speaker format only works for exactly 2 speakers)
            is_speaker_change = (marker == "SC")
            if is_speaker_change and len(merge_candidates) > 1:
                break

            # Check if text can be merged
            combined_text = merge_candidates[0].text
            # Strip marker from first cue if present
            _, combined_text = detect_merge_marker(combined_text)

            merge_failed = False
            for idx, mc in enumerate(merge_candidates[1:]):
                # Check for marker on this cue
                mc_marker, mc_text_clean = detect_merge_marker(mc.text)
                sc = (mc_marker == "SC")
                can_merge, combined_text = can_merge_text(combined_text, mc_text_clean, max_lines, max_chars, sc)
                if not can_merge:
                    merge_failed = True
                    break

            if merge_failed:
                break

            can_merge, new_text = can_merge_text(combined_text, next_text_clean, max_lines, max_chars, is_speaker_change)

            if not can_merge:
                break

            # Can merge this cue
            merge_candidates.append(next_cue)
            j += 1

        # Create merged cue
        if len(merge_candidates) == 1:
            # No merge, just copy (but strip any markers)
            _, clean_text = detect_merge_marker(current.text)
            merged_cue = Subtitle(
                index=new_index,
                start_ms=current.start_ms,
                end_ms=current.end_ms,
                text=clean_text,
                original_text=current.original_text
            )
        else:
            # Merge multiple cues
            combined_text = merge_candidates[0].text
            # Strip marker from first cue if present
            _, combined_text = detect_merge_marker(combined_text)

            for idx, mc in enumerate(merge_candidates[1:]):
                # Check for marker on this cue
                mc_marker, mc_text_clean = detect_merge_marker(mc.text)
                sc = (mc_marker == "SC")
                _, combined_text = can_merge_text(combined_text, mc_text_clean, max_lines, max_chars, sc)

            merged_cue = Subtitle(
                index=new_index,
                start_ms=merge_candidates[0].start_ms,
                end_ms=merge_candidates[-1].end_ms,
                text=combined_text,
                original_text=combined_text
            )

            # Record merge in report
            report.append({
                "output_index": new_index,
                "output_start_ms": merge_candidates[0].start_ms,
                "output_end_ms": merge_candidates[-1].end_ms,
                "source_indices": [mc.index for mc in merge_candidates],
                "source_timecodes": [
                    {"start_ms": mc.start_ms, "end_ms": mc.end_ms}
                    for mc in merge_candidates
                ],
                "source_count": len(merge_candidates),
                "gap_ms": merge_candidates[1].start_ms - merge_candidates[0].end_ms if len(merge_candidates) > 1 else 0,
                "combined_duration_ms": merged_cue.duration_ms,
                "text": combined_text
            })

        merged.append(merged_cue)
        new_index += 1
        i = j if len(merge_candidates) > 1 else i + 1

    return merged, report


def main():
    parser = argparse.ArgumentParser(
        description='Automatically merge adjacent subtitle cues',
        epilog='Part of the srt-translate skill - Phase 4 merge automation'
    )

    parser.add_argument('input', help='Input SRT file')
    parser.add_argument('--output', '-o', help='Output SRT file (default: stdout)')
    parser.add_argument('--gap-threshold', type=int, default=1000,
                        help='Max gap between cues to merge (ms, default: 1000)')
    parser.add_argument('--max-duration', type=int, default=7000,
                        help='Max combined duration for merged cue (ms, default: 7000)')
    parser.add_argument('--max-lines', type=int, default=2,
                        help='Max lines per cue (default: 2)')
    parser.add_argument('--max-chars', type=int, default=42,
                        help='Max characters per line (default: 42)')
    parser.add_argument('--report', help='Output JSON merge report to this file')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print statistics to stderr')

    args = parser.parse_args()

    # Parse input
    subtitles, parse_errors = parse_srt_file(args.input)

    if parse_errors:
        for err in parse_errors:
            print(f"Parse error: {err}", file=sys.stderr)
        if not subtitles:
            sys.exit(1)

    source_count = len(subtitles)

    # Merge cues
    merged, report = merge_cues(
        subtitles,
        args.gap_threshold,
        args.max_duration,
        args.max_lines,
        args.max_chars
    )

    output_count = len(merged)
    merge_count = len(report)
    ratio = (output_count / source_count * 100) if source_count > 0 else 100

    # Write output
    if args.output:
        write_srt(merged, args.output)
    else:
        for i, sub in enumerate(merged):
            if i > 0:
                print()
            print(sub.to_srt_block(), end='')

    # Write report
    if args.report:
        report_data = {
            "source_file": args.input,
            "output_file": args.output or "stdout",
            "parameters": {
                "gap_threshold_ms": args.gap_threshold,
                "max_duration_ms": args.max_duration,
                "max_lines": args.max_lines,
                "max_chars": args.max_chars
            },
            "statistics": {
                "source_cues": source_count,
                "output_cues": output_count,
                "merges_performed": merge_count,
                "cues_merged": sum(m["source_count"] for m in report),
                "ratio_percent": round(ratio, 1)
            },
            "merges": report
        }

        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

    # Verbose output
    if args.verbose:
        print(f"Source cues: {source_count}", file=sys.stderr)
        print(f"Output cues: {output_count}", file=sys.stderr)
        print(f"Merges performed: {merge_count}", file=sys.stderr)
        print(f"Ratio: {ratio:.1f}%", file=sys.stderr)

    # Return summary as JSON to stdout if no output file specified
    if not args.output and not args.verbose:
        summary = {
            "source_cues": source_count,
            "output_cues": output_count,
            "ratio_percent": round(ratio, 1),
            "merges": merge_count
        }
        # Don't print if we already printed the SRT
        pass


if __name__ == '__main__':
    main()
