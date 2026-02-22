#!/usr/bin/env python3
"""
Validate SRT file against Netflix English (USA) Timed Text Style Guide.

Usage:
    python validate_srt_en.py <file_path> [--content-type adult|children] [--fix] [--verbose]

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
from srt_utils import parse_srt_file, Subtitle, write_srt

from srt_constants import (
    MAX_LINES, MAX_CHARS_PER_LINE, CPS_SOFT_CEILING, MAX_DURATION_MS,
    EN_CPS_TARGET as CPS_TARGET,
    EN_CPS_HARD_LIMIT as CPS_HARD_LIMIT,
    EN_MIN_GAP_MS as MIN_GAP_MS,
    EN_MIN_DURATION_MS as MIN_DURATION_MS,
)

# Typography
SMART_ELLIPSIS = '\u2026'  # …
THREE_DOTS = '...'
EN_DASH = '\u2013'  # –
EM_DASH = '\u2014'  # —

# Common British → US spelling patterns
BRITISH_SPELLINGS = {
    'colour': 'color',
    'favour': 'favor',
    'honour': 'honor',
    'behaviour': 'behavior',
    'neighbour': 'neighbor',
    'labour': 'labor',
    'flavour': 'flavor',
    'humour': 'humor',
    'rumour': 'rumor',
    'savour': 'savor',
    'tumour': 'tumor',
    'vapour': 'vapor',
    'armour': 'armor',
    'harbour': 'harbor',
    'favourite': 'favorite',
    'coloured': 'colored',
    'honoured': 'honored',
    'favoured': 'favored',
    'honourable': 'honorable',
    'favourable': 'favorable',
    'neighbouring': 'neighboring',
    'centre': 'center',
    'theatre': 'theater',
    'metre': 'meter',
    'litre': 'liter',
    'fibre': 'fiber',
    'sombre': 'somber',
    'defence': 'defense',
    'offence': 'offense',
    'licence': 'license',
    'practise': 'practice',
    'analyse': 'analyze',
    'apologise': 'apologize',
    'organise': 'organize',
    'realise': 'realize',
    'recognise': 'recognize',
    'specialise': 'specialize',
    'capitalise': 'capitalize',
    'categorise': 'categorize',
    'criticise': 'criticize',
    'emphasise': 'emphasize',
    'finalise': 'finalize',
    'generalise': 'generalize',
    'hospitalise': 'hospitalize',
    'legalise': 'legalize',
    'localise': 'localize',
    'maximise': 'maximize',
    'memorise': 'memorize',
    'minimise': 'minimize',
    'modernise': 'modernize',
    'normalise': 'normalize',
    'optimise': 'optimize',
    'prioritise': 'prioritize',
    'standardise': 'standardize',
    'summarise': 'summarize',
    'symbolise': 'symbolize',
    'sympathise': 'sympathize',
    'utilise': 'utilize',
    'travelling': 'traveling',
    'traveller': 'traveler',
    'cancelled': 'canceled',
    'cancelling': 'canceling',
    'modelling': 'modeling',
    'labelling': 'labeling',
    'grey': 'gray',
    'judgement': 'judgment',
    'ageing': 'aging',
    'aeroplane': 'airplane',
    'aluminium': 'aluminum',
    'catalogue': 'catalog',
    'cheque': 'check',
    'dialogue': 'dialog',
    'draught': 'draft',
    'enquiry': 'inquiry',
    'gaol': 'jail',
    'kerb': 'curb',
    'maths': 'math',
    'mould': 'mold',
    'plough': 'plow',
    'programme': 'program',
    'pyjamas': 'pajamas',
    'sceptical': 'skeptical',
    'storey': 'story',
    'tyre': 'tire',
}

# Smart quote pairs
LEFT_SINGLE_QUOTE = '\u2018'   # '
RIGHT_SINGLE_QUOTE = '\u2019'  # '
LEFT_DOUBLE_QUOTE = '\u201c'   # "
RIGHT_DOUBLE_QUOTE = '\u201d'  # "


def fix_ellipsis(text: str) -> tuple[str, list[str]]:
    """Convert three dots to smart ellipsis (…). Returns (fixed_text, fixes)."""
    fixes = []
    if THREE_DOTS in text:
        count = text.count(THREE_DOTS)
        text = text.replace(THREE_DOTS, SMART_ELLIPSIS)
        fixes.append(f"Converted {count} three-dot sequence(s) to smart ellipsis '\u2026'")
    return text, fixes


def fix_dashes(text: str) -> tuple[str, list[str]]:
    """Replace en/em dashes with double hyphens or remove. Returns (fixed_text, fixes)."""
    fixes = []
    # Em dash used as interruption → --
    if EM_DASH in text:
        count = text.count(EM_DASH)
        text = text.replace(EM_DASH, '--')
        fixes.append(f"Replaced {count} em dash(es) with '--'")
    # En dash used as interruption → --
    if EN_DASH in text:
        count = text.count(EN_DASH)
        text = text.replace(EN_DASH, '--')
        fixes.append(f"Replaced {count} en dash(es) with '--'")
    return text, fixes


def fix_smart_quotes(text: str) -> tuple[str, list[str]]:
    """Convert straight quotes to smart quotes (context-aware). Returns (fixed_text, fixes)."""
    fixes = []
    result = []
    in_double_quote = False
    in_single_quote = False
    fix_count = 0

    i = 0
    while i < len(text):
        ch = text[i]

        if ch == '"':
            fix_count += 1
            if not in_double_quote:
                result.append(LEFT_DOUBLE_QUOTE)
                in_double_quote = True
            else:
                result.append(RIGHT_DOUBLE_QUOTE)
                in_double_quote = False
        elif ch == "'":
            # Detect contractions: letter before AND letter after → apostrophe (right single quote)
            prev_is_letter = i > 0 and text[i - 1].isalpha()
            next_is_letter = i + 1 < len(text) and text[i + 1].isalpha()
            if prev_is_letter and next_is_letter:
                # Contraction (don't, it's, etc.) — use right single quote as apostrophe
                fix_count += 1
                result.append(RIGHT_SINGLE_QUOTE)
            elif prev_is_letter and not next_is_letter:
                # Trailing apostrophe (students', o'clock end) — right single quote
                fix_count += 1
                result.append(RIGHT_SINGLE_QUOTE)
            elif not in_single_quote:
                fix_count += 1
                result.append(LEFT_SINGLE_QUOTE)
                in_single_quote = True
            else:
                fix_count += 1
                result.append(RIGHT_SINGLE_QUOTE)
                in_single_quote = False
        else:
            result.append(ch)
        i += 1

    new_text = ''.join(result)
    if fix_count > 0 and new_text != text:
        fixes.append(f"Converted {fix_count} straight quote(s) to smart quotes")
    return new_text, fixes


def fix_speaker_dash(text: str) -> tuple[str, list[str]]:
    """
    Normalize dual-speaker dash formatting to Netflix EN style:
    Both lines get a hyphen without space: -Text

    Returns (fixed_text, fixes).
    """
    fixes = []
    lines = text.split('\n')

    if len(lines) != 2:
        return text, fixes

    line1 = lines[0]
    line2 = lines[1]

    # Detect if this is a dual-speaker cue
    is_dual = False
    # Both lines have dashes
    if (line1.strip().startswith('-') and line2.strip().startswith('-')):
        is_dual = True
    # Only second line has dash (Dutch style)
    elif line2.strip().startswith('-') and not line1.strip().startswith('-'):
        is_dual = True

    if not is_dual:
        return text, fixes

    # Normalize both lines to -Text format (no space after dash)
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('- '):
            # Dash with space → remove space
            new_line = '-' + stripped[2:]
            new_lines.append(new_line)
            fixes.append("Removed space after speaker dash (Netflix EN: -Text)")
        elif stripped.startswith('-'):
            # Already correct format
            new_lines.append(stripped)
        else:
            # First line without dash in Dutch style → add dash
            new_line = '-' + stripped
            new_lines.append(new_line)
            fixes.append("Added dash to first speaker (Netflix EN: both lines get -)")

    return '\n'.join(new_lines), fixes


def fix_line_length(text: str, max_length: int = MAX_CHARS_PER_LINE) -> tuple[str, list[str]]:
    """
    Re-break lines that exceed max length.
    Bottom-heavy pyramid preferred. Won't exceed MAX_LINES.
    Returns (fixed_text, fixes).
    """
    fixes = []
    lines = text.split('\n')

    needs_breaking = any(
        len(re.sub(r'^-', '', line)) > max_length for line in lines
    )

    if not needs_breaking:
        return text, fixes

    if len(lines) >= MAX_LINES:
        return text, fixes

    new_lines = []
    for line in lines:
        dash_prefix = ''
        check_line = line
        if line.startswith('-'):
            dash_prefix = '-'
            check_line = line[1:]

        if len(check_line) <= max_length:
            new_lines.append(line)
            continue

        if len(new_lines) + 2 > MAX_LINES:
            new_lines.append(line)
            continue

        words = check_line.split(' ')
        line1_words = []
        line2_words = []
        current_len = 0

        for word in words:
            test_len = current_len + len(word) + (1 if current_len > 0 else 0)
            if test_len <= max_length and len(line2_words) == 0:
                line1_words.append(word)
                current_len = test_len
            else:
                line2_words.append(word)

        line1 = dash_prefix + ' '.join(line1_words)
        line2 = ' '.join(line2_words)

        # Bottom-heavy rebalancing
        if len(re.sub(r'^-', '', line1)) > len(line2) and line2:
            while line1_words and len(' '.join(line1_words)) > len(' '.join(line2_words)):
                line2_words.insert(0, line1_words.pop())
            line1 = dash_prefix + ' '.join(line1_words)
            line2 = ' '.join(line2_words)

        if line1.strip() and line1 != dash_prefix:
            new_lines.append(line1)
        if line2.strip():
            new_lines.append(line2)

        fixes.append(f"Re-broke line exceeding {max_length} chars")

    if len(new_lines) > MAX_LINES:
        return text, []

    return '\n'.join(new_lines), fixes


def fix_overlap(sub: Subtitle, prev_sub: Subtitle) -> tuple[int, str | None]:
    """Fix overlap by adjusting previous subtitle's end time."""
    gap = sub.start_ms - prev_sub.end_ms
    if gap < 0:
        new_end = sub.start_ms - MIN_GAP_MS
        return new_end, f"Adjusted end time from {prev_sub.end_ms}ms to {new_end}ms (was overlapping by {-gap}ms)"
    elif gap < MIN_GAP_MS:
        new_end = sub.start_ms - MIN_GAP_MS
        return new_end, f"Adjusted end time from {prev_sub.end_ms}ms to {new_end}ms (gap was {gap}ms, minimum {MIN_GAP_MS}ms)"
    return prev_sub.end_ms, None


def fix_subtitle(sub: Subtitle, prev_sub: Subtitle | None) -> tuple[Subtitle, list[str]]:
    """Apply all applicable fixes to a single subtitle. Returns (fixed_subtitle, fixes)."""
    all_fixes = []
    text = sub.text

    # Fix ellipsis (three dots → smart ellipsis)
    text, fixes = fix_ellipsis(text)
    all_fixes.extend(fixes)

    # Fix en/em dashes → --
    text, fixes = fix_dashes(text)
    all_fixes.extend(fixes)

    # Fix straight quotes → smart quotes
    text, fixes = fix_smart_quotes(text)
    all_fixes.extend(fixes)

    # Fix line length
    text, fixes = fix_line_length(text)
    all_fixes.extend(fixes)

    # Fix speaker dash formatting (Netflix EN style)
    text, fixes = fix_speaker_dash(text)
    all_fixes.extend(fixes)

    sub.text = text

    # Fix overlap/gap with previous subtitle
    if prev_sub:
        new_end, fix_desc = fix_overlap(sub, prev_sub)
        if fix_desc:
            prev_sub.end_ms = new_end
            all_fixes.append(fix_desc)

    return sub, all_fixes


def fix_srt(file_path: str, output_path: str | None = None, content_type: str = 'adult') -> dict:
    """Fix all auto-fixable violations. Returns dict with results."""
    cps_hard_limit = CPS_HARD_LIMIT
    subtitles, parse_errors = parse_srt_file(file_path)

    if parse_errors:
        return {'error': f'Parse errors: {parse_errors}', 'fixed': False}

    all_fixes = []
    unfixable = []

    # Temporal reorder
    original_order = [sub.index for sub in subtitles]
    subtitles.sort(key=lambda s: s.start_ms)
    new_order = [sub.index for sub in subtitles]
    if original_order != new_order:
        all_fixes.append("Reordered cues by temporal sequence")

    prev_sub = None
    for sub in subtitles:
        sub, fixes = fix_subtitle(sub, prev_sub)
        for fix in fixes:
            all_fixes.append(f"Cue {sub.index}: {fix}")

        # Check for unfixable issues
        if sub.duration_seconds > 0 and sub.cps > cps_hard_limit:
            unfixable.append(f"Cue {sub.index}: CPS {sub.cps:.1f} exceeds limit {cps_hard_limit} (requires text condensation)")

        if sub.line_count > MAX_LINES:
            unfixable.append(f"Cue {sub.index}: {sub.line_count} lines exceeds max {MAX_LINES}")

        for i, line in enumerate(sub.text.split('\n')):
            check_line = re.sub(r'^-', '', line)
            if len(check_line) > MAX_CHARS_PER_LINE:
                unfixable.append(f"Cue {sub.index} line {i+1}: {len(check_line)} chars exceeds {MAX_CHARS_PER_LINE}")

        prev_sub = sub

    # Renumber sequentially
    for i, sub in enumerate(subtitles, 1):
        if sub.index != i:
            all_fixes.append(f"Renumbered cue {sub.index} to {i}")
            sub.index = i

    out_path = output_path or file_path
    write_srt(subtitles, out_path)

    return {
        'fixed': True,
        'output_file': out_path,
        'total_cues': len(subtitles),
        'content_type': content_type,
        'cps_hard_limit': cps_hard_limit,
        'fixes_applied': len(all_fixes),
        'fixes': all_fixes,
        'unfixable_count': len(unfixable),
        'unfixable': unfixable
    }


def check_british_spelling(text: str, cue_index: int) -> list[str]:
    """Check for British spellings in text. Returns warnings."""
    warnings = []
    text_lower = text.lower()
    words = re.findall(r"[a-z']+", text_lower)
    for word in words:
        if word in BRITISH_SPELLINGS:
            warnings.append(
                f"Cue {cue_index}: British spelling '{word}' \u2192 U.S. '{BRITISH_SPELLINGS[word]}'"
            )
    return warnings


def check_ok_spelling(text: str, cue_index: int) -> list[str]:
    """Check for non-standard 'OK' variants. Returns warnings."""
    warnings = []
    # Match standalone OK, O.K., ok but not words containing ok (like "book", "look")
    if re.search(r'\bO\.?K\.?\b', text):
        warnings.append(f'Cue {cue_index}: "OK"/"O.K." should be "okay"')
    return warnings


def validate_subtitle(sub: Subtitle, prev_sub: Subtitle | None, cps_hard_limit: int) -> tuple[list, list]:
    """Validate a single subtitle cue. Returns (errors, warnings)."""
    errors = []
    warnings = []

    # Line count
    if sub.line_count > MAX_LINES:
        errors.append(f"Cue {sub.index}: {sub.line_count} lines (max {MAX_LINES})")

    # Line length
    lines = sub.text.split('\n')
    for i, line in enumerate(lines):
        check_line = re.sub(r'^-', '', line)
        if len(check_line) > MAX_CHARS_PER_LINE:
            errors.append(f"Cue {sub.index} line {i+1}: {len(check_line)} chars (limit {MAX_CHARS_PER_LINE})")

    # CPS
    if sub.duration_seconds > 0:
        cps = sub.cps
        if cps > cps_hard_limit:
            errors.append(f"Cue {sub.index}: CPS {cps:.1f} exceeds limit {cps_hard_limit}")
        elif cps > CPS_SOFT_CEILING:
            warnings.append(f"Cue {sub.index}: CPS {cps:.1f} exceeds soft ceiling {CPS_SOFT_CEILING}")

    # Duration
    if sub.duration_ms < MIN_DURATION_MS:
        warnings.append(f"Cue {sub.index}: Duration {sub.duration_ms}ms below minimum {MIN_DURATION_MS}ms")
    if sub.duration_ms > MAX_DURATION_MS:
        warnings.append(f"Cue {sub.index}: Duration {sub.duration_ms}ms exceeds maximum {MAX_DURATION_MS}ms")
    if sub.duration_ms <= 0:
        errors.append(f"Cue {sub.index}: Invalid duration {sub.duration_ms}ms")

    # Gap from previous
    if prev_sub:
        gap = sub.start_ms - prev_sub.end_ms
        if gap < 0:
            errors.append(f"Cue {sub.index}: Overlaps with previous cue by {-gap}ms")
        elif gap < MIN_GAP_MS:
            warnings.append(f"Cue {sub.index}: Gap {gap}ms below minimum {MIN_GAP_MS}ms")
        if sub.start_ms < prev_sub.start_ms:
            errors.append(f"Cue {sub.index}: Out of temporal order")

    # Ellipsis: three dots should be smart ellipsis
    if THREE_DOTS in sub.text:
        warnings.append(f"Cue {sub.index}: Contains three dots '...' (should be smart ellipsis '\u2026')")

    # En/em dashes: forbidden
    if EN_DASH in sub.text:
        errors.append(f"Cue {sub.index}: Contains en dash '\u2013' (use '--' for interruptions)")
    if EM_DASH in sub.text:
        errors.append(f"Cue {sub.index}: Contains em dash '\u2014' (use '--' for interruptions)")

    # Straight quotes
    if '"' in sub.text:
        warnings.append(f"Cue {sub.index}: Contains straight double quotes (suggest smart quotes)")
    # Only flag straight single quotes that aren't likely contractions
    for m in re.finditer(r"(?<![a-zA-Z])'|'(?![a-zA-Z])", sub.text):
        warnings.append(f"Cue {sub.index}: Contains straight single quote (suggest smart quotes)")
        break  # One warning per cue

    # Semicolons: warn
    if ';' in sub.text:
        warnings.append(f"Cue {sub.index}: Contains semicolon (suggest rephrasing)")

    # British spellings
    warnings.extend(check_british_spelling(sub.text, sub.index))

    # "OK" vs "okay"
    warnings.extend(check_ok_spelling(sub.text, sub.index))

    # Dual speaker dash formatting (Netflix EN: both lines -Text, no space)
    if len(lines) == 2:
        l1 = lines[0].strip()
        l2 = lines[1].strip()
        # Detect dual-speaker cue
        if l2.startswith('-'):
            # Check Netflix EN format: both lines should start with - (no space)
            if not l1.startswith('-'):
                warnings.append(f"Cue {sub.index}: Dual speaker — first line missing dash (Netflix EN: both lines get -)")
            if l1.startswith('- ') or l2.startswith('- '):
                warnings.append(f"Cue {sub.index}: Dual speaker — space after dash (Netflix EN: -Text, no space)")

    # Ellipsis continuation validation
    if prev_sub:
        prev_text = prev_sub.text.rstrip()
        curr_text = sub.text.lstrip()
        prev_ends_ellipsis = prev_text.endswith(SMART_ELLIPSIS) or prev_text.endswith(THREE_DOTS)
        curr_starts_ellipsis = curr_text.startswith(SMART_ELLIPSIS) or curr_text.startswith(THREE_DOTS)
        curr_starts_capital = curr_text[:1].isupper() if curr_text else False
        curr_starts_dash = curr_text.startswith('-')

        if prev_ends_ellipsis and not (curr_starts_ellipsis or curr_starts_capital or curr_starts_dash):
            warnings.append(
                f"Cue {sub.index}: Previous cue ends with ellipsis but this cue doesn't "
                f"start with ellipsis, capital letter, or speaker dash"
            )

    return errors, warnings


def validate_srt(file_path: str, content_type: str = 'adult') -> dict:
    """Validate entire SRT file against Netflix EN constraints."""
    cps_hard_limit = CPS_HARD_LIMIT
    subtitles, parse_errors = parse_srt_file(file_path)

    all_errors = list(parse_errors)
    all_warnings = []
    cps_values = []
    exclamation_count = 0

    prev_sub = None
    for sub in subtitles:
        errors, warnings = validate_subtitle(sub, prev_sub, cps_hard_limit)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

        if sub.duration_seconds > 0:
            cps_values.append(sub.cps)

        exclamation_count += sub.text.count('!')
        prev_sub = sub

    # Exclamation mark check: warn if >3 in entire file
    if exclamation_count > 3:
        all_warnings.append(f"File contains {exclamation_count} exclamation marks (Netflix: shouting/surprise only)")

    # Sequential numbering
    for i, sub in enumerate(subtitles):
        if sub.index != i + 1:
            all_warnings.append(f"Cue {sub.index}: Non-sequential index (expected {i + 1})")
            break

    # Stats
    stats = {
        'total_cues': len(subtitles),
        'total_chars': sum(sub.char_count for sub in subtitles),
        'total_duration_ms': sum(sub.duration_ms for sub in subtitles),
        'content_type': content_type,
        'cps_hard_limit': cps_hard_limit,
    }

    if cps_values:
        stats['cps_avg'] = round(sum(cps_values) / len(cps_values), 1)
        stats['cps_max'] = round(max(cps_values), 1)
        stats['cps_min'] = round(min(cps_values), 1)
        stats['cps_above_soft'] = sum(1 for c in cps_values if c > CPS_SOFT_CEILING)
        stats['cps_above_hard'] = sum(1 for c in cps_values if c > cps_hard_limit)

    if exclamation_count > 0:
        stats['exclamation_marks'] = exclamation_count

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
    parser = argparse.ArgumentParser(description='Validate SRT file against Netflix English (USA) style guide')
    parser.add_argument('file_path', help='Path to SRT file')
    parser.add_argument('--content-type', choices=['adult', 'children'], default='adult',
                        help='Content type for CPS limit (adult=20, children=17)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show all warnings')
    parser.add_argument('--fix', action='store_true', help='Auto-fix violations (modifies file in-place)')
    parser.add_argument('--output', '-o', help='Output path for fixed file (default: overwrite input)')
    parser.add_argument('--unfixable-indices', action='store_true',
                        help='After --fix, output only cue indices that need manual editing')
    args = parser.parse_args()

    file_path = Path(args.file_path)
    if not file_path.exists():
        print(json.dumps({'error': f'File not found: {file_path}'}))
        sys.exit(1)

    if args.fix:
        result = fix_srt(str(file_path), args.output, args.content_type)

        if args.unfixable_indices:
            indices = []
            for msg in result.get('unfixable', []):
                match = re.match(r'Cue (\d+)', msg)
                if match:
                    indices.append(int(match.group(1)))
            print(json.dumps({
                'unfixable_cue_indices': sorted(set(indices)),
                'count': len(set(indices)),
                'requires_manual_edit': len(indices) > 0
            }, indent=2))
        else:
            print(json.dumps(result, indent=2))
        sys.exit(0 if result.get('fixed', False) else 1)
    else:
        result = validate_srt(str(file_path), args.content_type)

        if not args.verbose and len(result['warnings']) > 10:
            result['warnings'] = result['warnings'][:10] + [
                f"... and {len(result['warnings']) - 10} more warnings"
            ]

        print(json.dumps(result, indent=2))
        sys.exit(0 if result['valid'] else 1)


if __name__ == '__main__':
    main()
