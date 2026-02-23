#!/usr/bin/env python3
"""
Validate SRT file against Dutch subtitle style guide constraints.

Usage:
    python validate_srt.py <file_path> [--fix] [--summary] [--report FILE]

Output (JSON):
    {
        "valid": false,
        "total_cues": 250,
        "errors": [...],
        "warnings": [...],
        "stats": {...}
    }
"""

import sys
import json
import argparse
import re
from pathlib import Path
from srt_utils import parse_srt_file, Subtitle, write_srt, visible_length

from srt_constants import (
    MAX_LINES, MAX_CHARS_PER_LINE, CPS_SOFT_CEILING, MAX_DURATION_MS,
    NL_CPS_TARGET as CPS_TARGET,
    NL_CPS_HARD_LIMIT as CPS_HARD_LIMIT,
    NL_MIN_GAP_MS as MIN_GAP_MS,
    NL_MIN_DURATION_MS as MIN_DURATION_MS,
    get_constraints,
)

# Forbidden punctuation replacements
PUNCTUATION_FIXES = {
    '!': '.',  # Exclamation → period (per Dutch subtitle convention)
    ';': '.',  # Semicolon → period
}

# Smart ellipsis to three dots
SMART_ELLIPSIS = '…'
THREE_DOTS = '...'


def fix_punctuation(text: str) -> tuple[str, list[str]]:
    """Replace forbidden punctuation. Returns (fixed_text, list of fixes applied)."""
    fixes = []
    result = text
    for char, replacement in PUNCTUATION_FIXES.items():
        if char in result:
            count = result.count(char)
            result = result.replace(char, replacement)
            fixes.append(f"Replaced {count} '{char}' with '{replacement}'")
    return result, fixes


def fix_ellipsis(text: str) -> tuple[str, list[str]]:
    """Convert smart ellipsis (…) to three dots (...). Returns (fixed_text, list of fixes applied)."""
    fixes = []
    if SMART_ELLIPSIS in text:
        count = text.count(SMART_ELLIPSIS)
        text = text.replace(SMART_ELLIPSIS, THREE_DOTS)
        fixes.append(f"Converted {count} smart ellipsis '…' to '...'")
    return text, fixes


def fix_line_length(text: str, max_length: int = MAX_CHARS_PER_LINE) -> tuple[str, list[str]]:
    """
    Re-break lines that exceed max length.
    Attempts to break at word boundaries, preferring bottom-heavy pyramid.
    Will NOT break if doing so would exceed MAX_LINES (2) total.
    Returns (fixed_text, list of fixes applied).
    """
    fixes = []
    lines = text.split('\n')
    
    # Check if any line exceeds max_length
    needs_breaking = any(
        visible_length(re.sub(r'^-\s?', '', line)) > max_length for line in lines
    )
    
    if not needs_breaking:
        return text, fixes
    
    # If we already have 2 lines and need to break, we can't fix this
    if len(lines) >= MAX_LINES:
        # Can't break further without exceeding line limit
        return text, fixes
    
    new_lines = []
    
    for line in lines:
        # Preserve speaker dash (no-space format: -Text)
        dash_prefix = ''
        check_line = line
        if line.startswith('-'):
            dash_prefix = '-'
            check_line = line[1:].lstrip(' ')  # strip optional space for compat

        if visible_length(check_line) <= max_length:
            new_lines.append(line)
            continue
        
        # Check if breaking this line would exceed MAX_LINES total
        if len(new_lines) + 2 > MAX_LINES:
            # Can't break - would exceed line limit
            new_lines.append(line)
            continue
        
        # Need to break this line - find best break point
        words = check_line.split(' ')
        
        # Build lines by accumulating words
        line1_words = []
        line2_words = []
        
        current_len = 0
        for i, word in enumerate(words):
            test_len = current_len + len(word) + (1 if current_len > 0 else 0)
            
            # If we haven't exceeded max and we're in first half, add to line 1
            if test_len <= max_length and len(line2_words) == 0:
                line1_words.append(word)
                current_len = test_len
            else:
                # Start or continue line 2
                line2_words.append(word)
        
        line1 = dash_prefix + ' '.join(line1_words)
        line2 = ' '.join(line2_words)
        
        # For bottom-heavy: line1 should be shorter than line2
        if visible_length(re.sub(r'^-\s?', '', line1)) > visible_length(line2) and line2:
            # Try to rebalance by moving words from line1 to line2
            while line1_words and len(' '.join(line1_words)) > len(' '.join(line2_words)):
                line2_words.insert(0, line1_words.pop())
            line1 = dash_prefix + ' '.join(line1_words)
            line2 = ' '.join(line2_words)
        
        if line1.strip() and line1 != dash_prefix:
            new_lines.append(line1)
        if line2.strip():
            new_lines.append(line2)
        
        fixes.append(f"Re-broke line exceeding {max_length} chars")
    
    # Final check: if we ended up with >MAX_LINES, revert
    if len(new_lines) > MAX_LINES:
        return text, []  # Revert, no fix applied
    
    return '\n'.join(new_lines), fixes


def fix_overlap(sub: Subtitle, prev_sub: Subtitle) -> tuple[int, str | None]:
    """
    Fix overlap by adjusting previous subtitle's end time.
    Returns (new_end_ms for prev_sub, fix description or None).
    """
    gap = sub.start_ms - prev_sub.end_ms
    if gap < 0:
        # Overlap - adjust prev_sub end time
        new_end = max(0, sub.start_ms - MIN_GAP_MS)
        if new_end <= prev_sub.start_ms:
            # Can't fix: would create zero/negative duration for prev cue
            return prev_sub.end_ms, f"WARNING: Unfixable overlap at cue {sub.index} (prev cue {prev_sub.index} would get non-positive duration)"
        return new_end, f"Adjusted end time from {prev_sub.end_ms}ms to {new_end}ms (was overlapping by {-gap}ms)"
    elif gap < MIN_GAP_MS:
        # Gap too short - adjust prev_sub end time
        new_end = max(0, sub.start_ms - MIN_GAP_MS)
        if new_end <= prev_sub.start_ms:
            return prev_sub.end_ms, f"WARNING: Can't enforce min gap at cue {sub.index} (prev cue {prev_sub.index} too short)"
        return new_end, f"Adjusted end time from {prev_sub.end_ms}ms to {new_end}ms (gap was {gap}ms, minimum {MIN_GAP_MS}ms)"
    return prev_sub.end_ms, None


def fix_speaker_dash(text: str) -> tuple[str, list[str]]:
    """
    Normalize speaker dash formatting (Auteursbond: no space after dash).
    Correct format for two speakers in one cue:
        Speaker A text
        -Speaker B text

    NOT:
        - Speaker A text
        - Speaker B text

    Returns (fixed_text, list of fixes applied).
    """
    fixes = []
    lines = text.split('\n')

    if len(lines) == 2:
        line1 = lines[0]
        line2 = lines[1]

        # If both lines start with dash, remove from first line
        if line1.startswith('-'):
            stripped = line1.lstrip('-').lstrip()
            if line2.strip().startswith('-'):
                lines[0] = stripped
                fixes.append("Removed dash from first speaker (correct format: only second speaker gets dash)")

        # Normalize second line to -Text (no space after dash)
        if line2.strip().startswith('-'):
            stripped = line2.lstrip('-').lstrip()
            if lines[1] != '-' + stripped:
                lines[1] = '-' + stripped
                fixes.append("Normalized second speaker dash to '-Text' (no space)")

    return '\n'.join(lines), fixes


def fix_subtitle(sub: Subtitle, prev_sub: Subtitle | None) -> tuple[Subtitle, list[str]]:
    """
    Apply all applicable fixes to a single subtitle.
    Returns (fixed_subtitle, list of all fixes applied).
    """
    all_fixes = []
    text = sub.text
    
    # Fix punctuation
    text, fixes = fix_punctuation(text)
    all_fixes.extend(fixes)
    
    # Fix ellipsis format
    text, fixes = fix_ellipsis(text)
    all_fixes.extend(fixes)
    
    # Fix line length
    text, fixes = fix_line_length(text)
    all_fixes.extend(fixes)
    
    # Fix speaker dash formatting
    text, fixes = fix_speaker_dash(text)
    all_fixes.extend(fixes)
    
    # Update subtitle text
    sub.text = text
    
    # Fix overlap/gap with previous subtitle
    if prev_sub:
        new_end, fix_desc = fix_overlap(sub, prev_sub)
        if fix_desc:
            prev_sub.end_ms = new_end
            all_fixes.append(fix_desc)
    
    return sub, all_fixes


def fix_srt(file_path: str, output_path: str | None = None) -> dict:
    """
    Fix all auto-fixable violations in SRT file.
    
    Args:
        file_path: Path to input SRT file
        output_path: Path for output (default: overwrite input)
    
    Returns:
        Dict with fix results
    """
    subtitles, parse_errors = parse_srt_file(file_path)
    
    if parse_errors:
        return {'error': f'Parse errors: {parse_errors}', 'fixed': False}
    
    all_fixes = []
    unfixable = []
    
    # Check and fix temporal order first
    original_order = [sub.index for sub in subtitles]
    subtitles.sort(key=lambda s: s.start_ms)
    new_order = [sub.index for sub in subtitles]
    if original_order != new_order:
        all_fixes.append(f"Reordered cues by temporal sequence (was out of order)")
    
    prev_sub = None
    for sub in subtitles:
        # Apply fixes
        sub, fixes = fix_subtitle(sub, prev_sub)
        for fix in fixes:
            all_fixes.append(f"Cue {sub.index}: {fix}")
        
        # Check for unfixable issues (CPS too high)
        if sub.duration_seconds > 0 and sub.cps > CPS_HARD_LIMIT:
            unfixable.append(f"Cue {sub.index}: CPS {sub.cps:.1f} exceeds limit {CPS_HARD_LIMIT} (requires manual condensation)")
        
        # Check line count (unfixable without semantic understanding)
        if sub.line_count > MAX_LINES:
            unfixable.append(f"Cue {sub.index}: {sub.line_count} lines exceeds max {MAX_LINES} (requires manual restructuring)")
        
        # Check line length (unfixable if already at 2 lines)
        for i, line in enumerate(sub.text.split('\n')):
            check_line = re.sub(r'^-\s?', '', line)
            vlen = visible_length(check_line)
            if vlen > MAX_CHARS_PER_LINE:
                unfixable.append(f"Cue {sub.index} line {i+1}: {vlen} chars exceeds {MAX_CHARS_PER_LINE} (requires manual condensation)")
        
        prev_sub = sub
    
    # Renumber sequentially
    for i, sub in enumerate(subtitles, 1):
        if sub.index != i:
            all_fixes.append(f"Renumbered cue {sub.index} to {i}")
            sub.index = i
    
    # Write output
    out_path = output_path or file_path
    write_srt(subtitles, out_path)
    
    return {
        'fixed': True,
        'output_file': out_path,
        'total_cues': len(subtitles),
        'fixes_applied': len(all_fixes),
        'fixes': all_fixes,
        'unfixable_count': len(unfixable),
        'unfixable': unfixable
    }


def validate_subtitle(sub: Subtitle, prev_sub: Subtitle | None) -> tuple[list, list]:
    """Validate a single subtitle cue. Returns (errors, warnings)."""
    errors = []
    warnings = []
    
    # Line count
    if sub.line_count > MAX_LINES:
        errors.append(f"Cue {sub.index}: {sub.line_count} lines (max {MAX_LINES})")
    
    # Line length
    lines = sub.text.split('\n')
    for i, line in enumerate(lines):
        # Strip speaker dash for length calculation
        check_line = re.sub(r'^-\s?', '', line)
        vlen = visible_length(check_line)
        if vlen > MAX_CHARS_PER_LINE:
            errors.append(f"Cue {sub.index} line {i+1}: {vlen} chars (limit {MAX_CHARS_PER_LINE})")
    
    # CPS
    if sub.duration_seconds > 0:
        cps = sub.cps
        if cps > CPS_HARD_LIMIT:
            errors.append(f"Cue {sub.index}: CPS {cps:.1f} exceeds limit {CPS_HARD_LIMIT}")
        elif cps > CPS_SOFT_CEILING:
            warnings.append(f"Cue {sub.index}: CPS {cps:.1f} exceeds soft ceiling {CPS_SOFT_CEILING}")
    
    # Duration
    if sub.duration_ms < MIN_DURATION_MS:
        warnings.append(f"Cue {sub.index}: Duration {sub.duration_ms}ms below minimum {MIN_DURATION_MS}ms")
    if sub.duration_ms > MAX_DURATION_MS:
        warnings.append(f"Cue {sub.index}: Duration {sub.duration_ms}ms exceeds maximum {MAX_DURATION_MS}ms")
    
    # Negative or zero duration
    if sub.duration_ms <= 0:
        errors.append(f"Cue {sub.index}: Invalid duration {sub.duration_ms}ms")
    
    # Gap from previous
    if prev_sub:
        gap = sub.start_ms - prev_sub.end_ms
        if gap < 0:
            errors.append(f"Cue {sub.index}: Overlaps with previous cue by {-gap}ms")
        elif gap < MIN_GAP_MS:
            warnings.append(f"Cue {sub.index}: Gap {gap}ms below minimum {MIN_GAP_MS}ms")
        
        # Temporal order check
        if sub.start_ms < prev_sub.start_ms:
            errors.append(f"Cue {sub.index}: Out of temporal order (starts at {sub.start_ms}ms, before previous cue's start at {prev_sub.start_ms}ms)")
    
    # Punctuation
    if '!' in sub.text:
        warnings.append(f"Cue {sub.index}: Contains forbidden exclamation mark. Could be left to aid in providing context.")
    if ';' in sub.text:
        errors.append(f"Cue {sub.index}: Contains forbidden semicolon")
    
    # Ellipsis format (should be three dots, not smart ellipsis)
    if SMART_ELLIPSIS in sub.text:
        warnings.append(f"Cue {sub.index}: Contains smart ellipsis '…' (should be '...')")
    
    # Ellipsis continuation pair validation
    if prev_sub:
        prev_text = prev_sub.text.rstrip()
        curr_text = sub.text.lstrip()
        prev_ends_ellipsis = prev_text.endswith(THREE_DOTS) or prev_text.endswith(SMART_ELLIPSIS)
        curr_starts_ellipsis = curr_text.startswith(THREE_DOTS) or curr_text.startswith(SMART_ELLIPSIS)
        curr_starts_capital = curr_text[:1].isupper() if curr_text else False
        curr_starts_dash = curr_text.startswith('-')  # Different speaker
        
        # If previous cue ends with ellipsis, current should start with ellipsis OR capital OR dash
        if prev_ends_ellipsis and not (curr_starts_ellipsis or curr_starts_capital or curr_starts_dash):
            warnings.append(
                f"Cue {sub.index}: Previous cue ends with '...' but this cue doesn't "
                f"start with '...', capital letter, or speaker dash"
            )
        
        # If current starts with ellipsis but previous didn't end with ellipsis
        if curr_starts_ellipsis and not prev_ends_ellipsis:
            warnings.append(f"Cue {sub.index}: Starts with '...' but previous cue doesn't end with '...'")
    
    # Check for orphaned short words (single word ≤5 chars alone on a line)
    for i, line in enumerate(lines):
        stripped = re.sub(r'^-\s?', '', line).strip()
        if len(stripped) <= 5 and ' ' not in stripped and stripped:
            # It's a very short line - might be orphan
            if len(lines) > 1:
                warnings.append(f"Cue {sub.index} line {i+1}: Possible orphaned word '{stripped}'")
    
    # Speaker dash formatting
    if len(lines) == 2:
        if lines[1].strip().startswith('-'):
            if not lines[1].startswith('- ') and not lines[1].startswith('-'):
                # Has dash but wrong format
                pass  # Hard to validate without more context
        # First line should NOT have dash (unless fast dialog exception)
        if lines[0].strip().startswith('-'):
            warnings.append(f"Cue {sub.index}: First line starts with dash (should be second speaker only)")

    # Duplicate/near-duplicate text with adjacent cue
    if prev_sub:
        curr_clean = re.sub(r'[.\s]', '', sub.text.lower())
        prev_clean = re.sub(r'[.\s]', '', prev_sub.text.lower())
        if curr_clean and prev_clean:
            if curr_clean == prev_clean:
                errors.append(
                    f"Cue {sub.index}: Exact duplicate text of cue {prev_sub.index}"
                )
            elif len(curr_clean) >= 15 and len(prev_clean) >= 15:
                if curr_clean in prev_clean:
                    errors.append(
                        f"Cue {sub.index}: Text is substring of cue {prev_sub.index} "
                        f"(content pulled forward?)"
                    )
                elif prev_clean in curr_clean:
                    errors.append(
                        f"Cue {sub.index}: Text contains all of cue {prev_sub.index} "
                        f"(content pulled forward?)"
                    )

    return errors, warnings


def validate_srt(file_path: str) -> dict:
    """Validate entire SRT file against unified constraints."""
    subtitles, parse_errors = parse_srt_file(file_path)
    
    all_errors = list(parse_errors)
    all_warnings = []
    
    cps_values = []
    
    prev_sub = None
    for sub in subtitles:
        errors, warnings = validate_subtitle(sub, prev_sub)
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        
        if sub.duration_seconds > 0:
            cps_values.append(sub.cps)
        
        prev_sub = sub
    
    # Check sequential numbering
    for i, sub in enumerate(subtitles):
        if sub.index != i + 1:
            all_warnings.append(f"Cue {sub.index}: Non-sequential index (expected {i + 1})")
            break  # Only report first occurrence
    
    # Calculate stats
    stats = {
        'total_cues': len(subtitles),
        'total_chars': sum(sub.char_count for sub in subtitles),
        'total_duration_ms': sum(sub.duration_ms for sub in subtitles),
    }
    
    if cps_values:
        stats['cps_avg'] = sum(cps_values) / len(cps_values)
        stats['cps_max'] = max(cps_values)
        stats['cps_min'] = min(cps_values)
        stats['cps_above_soft'] = sum(1 for c in cps_values if c > CPS_SOFT_CEILING)
        stats['cps_above_hard'] = sum(1 for c in cps_values if c > CPS_HARD_LIMIT)
    
    return {
        'valid': len(all_errors) == 0,
        'total_cues': len(subtitles),
        'errors': all_errors,
        'warnings': all_warnings,
        'error_count': len(all_errors),
        'warning_count': len(all_warnings),
        'stats': stats
    }


def main():
    parser = argparse.ArgumentParser(description='Validate SRT file against style guide')
    parser.add_argument('file_path', help='Path to SRT file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show all warnings')
    parser.add_argument('--fix', action='store_true', help='Auto-fix violations (modifies file in-place)')
    parser.add_argument('--output', '-o', help='Output path for fixed file (default: overwrite input)')
    parser.add_argument('--unfixable-indices', action='store_true',
                        help='After --fix, output only the cue indices that need retranslation (for revision workflow)')
    parser.add_argument('--summary', '-s', action='store_true',
                        help='Show only aggregate stats (suppress individual violations)')
    parser.add_argument('--report', '-r', metavar='FILE',
                        help='Write full validation report to JSON file')
    parser.add_argument('--fps', type=int, choices=[24, 25],
                        help='Framerate (24 or 25). Overrides default constraint values.')
    args = parser.parse_args()
    
    # Override module-level constants if --fps is provided
    global CPS_TARGET, CPS_HARD_LIMIT, MIN_GAP_MS, MIN_DURATION_MS, CPS_SOFT_CEILING, MAX_DURATION_MS
    if args.fps:
        c = get_constraints(args.fps, 'nl')
        CPS_TARGET = c['cps_optimal']
        CPS_SOFT_CEILING = c['cps_hard_limit']
        CPS_HARD_LIMIT = c['cps_emergency_max']
        MIN_GAP_MS = c['min_gap_ms']
        MIN_DURATION_MS = c['min_duration_ms']
        MAX_DURATION_MS = c['max_duration_ms']

    file_path = Path(args.file_path)
    if not file_path.exists():
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)

    if args.fix:
        # Fix mode
        result = fix_srt(str(file_path), args.output)
        
        if args.unfixable_indices:
            # Extract just the cue indices from unfixable messages
            indices = []
            for msg in result.get('unfixable', []):
                match = re.match(r'Cue (\d+)', msg)
                if match:
                    indices.append(int(match.group(1)))
            print(json.dumps({
                'unfixable_cue_indices': sorted(set(indices)),
                'count': len(set(indices)),
                'requires_retranslation': len(indices) > 0
            }, indent=2))
        else:
            print(json.dumps(result, indent=2))
        sys.exit(0 if result.get('fixed', False) else 1)
    else:
        # Validate mode
        result = validate_srt(str(file_path))

        # Write full report to file if requested
        if args.report:
            report_path = Path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        if args.summary:
            # Summary mode: only aggregate stats, no individual violations
            summary = {
                'valid': result['valid'],
                'total_cues': result['total_cues'],
                'error_count': result['error_count'],
                'warning_count': result['warning_count'],
                'stats': result.get('stats', {})
            }
            print(json.dumps(summary, indent=2))
        else:
            if not args.verbose and len(result['warnings']) > 10:
                result['warnings'] = result['warnings'][:10] + [f"... and {len(result['warnings']) - 10} more warnings"]

            print(json.dumps(result, indent=2))

        sys.exit(0 if result['valid'] else 1)


if __name__ == '__main__':
    main()
