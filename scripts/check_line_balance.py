#!/usr/bin/env python3
"""
Line Balance QC — Detect and fix unbalanced subtitle line breaks.

Checks two-line cues for:
- Orphan words (1-2 short words alone on a line)
- Top-heavy pyramids (top line significantly longer than bottom)
- Grammatically bad break points (splits article+noun, verb+negation, etc.)

Suggests linguistically valid rebalancing using Dutch grammar rules.

Usage:
    python3 scripts/check_line_balance.py FILE.srt [options]

Examples:
    # Report only
    python3 scripts/check_line_balance.py movie.nl.srt

    # Apply fixes
    python3 scripts/check_line_balance.py movie.nl.srt --fix --output balanced.nl.srt

    # Stricter ratio threshold
    python3 scripts/check_line_balance.py movie.nl.srt --ratio 1.2
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srt_utils import parse_srt_file, write_srt, visible_length, is_dual_speaker
from srt_constants import CPS_SOFT_CEILING, MAX_CHARS_PER_LINE


# ---------------------------------------------------------------------------
# Dutch grammar rules for line breaking
# ---------------------------------------------------------------------------

# Words you should NEVER break AFTER (they bind to the next word)
BIND_FORWARD = {
    # Articles
    'de', 'het', 'een',
    # Demonstratives
    'deze', 'die', 'dit', 'dat',
    # Possessives
    'mijn', 'jouw', 'zijn', 'haar', 'ons', 'onze', 'hun',
    "z'n", "d'r", "m'n",
    # Negation
    'niet', 'geen', 'noch', 'nooit',
    # Reflexive pronouns (when preceding verb)
    'zich',
    # Quantifiers that bind to nouns
    'alle', 'elk', 'elke', 'iedere', 'veel', 'weinig',
    'enkele', 'sommige', 'meer', 'meeste', 'vele',
}

# Words that are GOOD break points BEFORE (break before these)
BREAK_BEFORE = {
    # Coordinating conjunctions
    'en', 'of', 'maar', 'want', 'dus', 'noch',
    # Subordinating conjunctions
    'dat', 'die', 'wie', 'wat', 'waar', 'omdat', 'hoewel',
    'terwijl', 'als', 'toen', 'nadat', 'voordat', 'zodra',
    'tenzij', 'mits', 'wanneer', 'waardoor', 'waarmee',
    'waarin', 'waarop', 'waarbij', 'zodat', 'doordat',
    'aangezien', 'ofschoon', 'alhoewel', 'totdat',
    # Prepositions
    'in', 'op', 'aan', 'bij', 'met', 'van', 'voor', 'naar',
    'over', 'door', 'uit', 'onder', 'tussen', 'tegen', 'tot',
    'om', 'zonder', 'achter', 'langs', 'binnen', 'buiten',
    'boven', 'beneden', 'tijdens', 'sinds', 'vanaf', 'wegens',
    'ondanks', 'behalve', 'volgens', 'naast', 'rondom',
    # Relative pronouns
    'waarvan', 'waarvoor', 'waaruit', 'waarover',
}

# Minimum word count on a line before it's considered an orphan
ORPHAN_MIN_WORDS = 2
ORPHAN_MIN_CHARS = 8

# Multi-word units that must not be split across lines
KEEP_TOGETHER = [
    'New Deal', 'Sovjet-Unie', 'Eerste Wereldoorlog',
    'Tweede Wereldoorlog', 'Mein Kampf', 'Rode Kruis',
    'Rode Leger', 'Derde Rijk', 'Heilige Stoel',
    'Verenigde Staten', 'Verenigd Koninkrijk',
    'Europese Unie', 'Verenigde Naties',
]
KEEP_TOGETHER_LOWER = [p.lower() for p in KEEP_TOGETHER]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def check_balance(text_lines):
    """
    Check if a two-line cue is well-balanced.
    Returns list of issues (empty = OK).
    """
    if len(text_lines) != 2:
        return []

    # Skip dual-speaker cues — their line breaks are semantically mandated
    if is_dual_speaker('\n'.join(text_lines)):
        return []

    top = text_lines[0].rstrip()
    bot = text_lines[1].rstrip()
    top_len = len(top)
    bot_len = len(bot)
    top_words = top.split()
    bot_words = bot.split()

    issues = []

    # --- Orphan detection ---
    if len(top_words) == 1 and top_len < ORPHAN_MIN_CHARS:
        issues.append({
            'type': 'orphan_top',
            'severity': 'high',
            'detail': f'Single short word on top line: "{top}" ({top_len} chars)',
        })
    elif len(top_words) <= ORPHAN_MIN_WORDS and top_len < ORPHAN_MIN_CHARS and bot_len > 25:
        issues.append({
            'type': 'orphan_top',
            'severity': 'medium',
            'detail': f'Very short top line: "{top}" ({top_len} chars vs {bot_len})',
        })

    if len(bot_words) == 1 and bot_len < ORPHAN_MIN_CHARS:
        issues.append({
            'type': 'orphan_bottom',
            'severity': 'high',
            'detail': f'Single short word on bottom line: "{bot}" ({bot_len} chars)',
        })
    elif len(bot_words) <= ORPHAN_MIN_WORDS and bot_len < ORPHAN_MIN_CHARS and top_len > 25:
        issues.append({
            'type': 'orphan_bottom',
            'severity': 'medium',
            'detail': f'Very short bottom line: "{bot}" ({bot_len} chars vs {top_len})',
        })

    # --- Top-heavy detection ---
    if top_len > 0 and bot_len > 0:
        ratio = top_len / bot_len
        if ratio > 1.5 and top_len - bot_len > 10:
            issues.append({
                'type': 'top_heavy',
                'severity': 'high' if ratio > 2.0 else 'medium',
                'detail': f'Top-heavy: {top_len}/{bot_len} chars (ratio {ratio:.1f})',
            })

    # --- Bad break point detection ---
    # Check if top line ends with a word that binds forward
    if top_words:
        last_top = top_words[-1].rstrip('.,;:!?…').lower()
        if last_top in BIND_FORWARD:
            issues.append({
                'type': 'bad_break',
                'severity': 'high',
                'detail': f'Line break after "{top_words[-1]}" splits grammatical unit',
            })

    return issues


def find_best_break(full_text, max_chars=MAX_CHARS_PER_LINE):
    """
    Find the best line break position for a subtitle text.

    Returns (top, bottom) or None if single line is better.
    Prefers bottom-heavy pyramid with linguistically valid breaks.
    """
    # If it fits on one line, no break needed
    if len(full_text) <= max_chars:
        return None

    words = full_text.split()
    if len(words) < 2:
        return None

    candidates = []
    full_text_lower = full_text.lower()

    # Try every word boundary as a potential break point
    for i in range(1, len(words)):
        top = ' '.join(words[:i])
        bot = ' '.join(words[i:])

        # Hard constraint: neither line > max_chars
        if len(top) > max_chars or len(bot) > max_chars:
            continue

        score = 0

        # --- Balance score (prefer bottom-heavy) ---
        ratio = len(top) / len(bot) if len(bot) > 0 else 99
        if 0.6 <= ratio <= 0.9:
            score += 3  # Ideal bottom-heavy
        elif 0.9 < ratio <= 1.1:
            score += 2  # Roughly equal, acceptable
        elif 0.4 <= ratio < 0.6:
            score += 1  # Very bottom-heavy but OK
        elif ratio > 1.1:
            score -= 1  # Top-heavy, penalize
        if ratio > 1.5:
            score -= 3  # Very top-heavy, strongly penalize

        # --- Orphan penalty ---
        if len(top.split()) == 1 and len(top) < ORPHAN_MIN_CHARS:
            score -= 5
        if len(bot.split()) == 1 and len(bot) < ORPHAN_MIN_CHARS:
            score -= 5

        # --- Linguistic break quality ---
        last_top_word = words[i - 1].rstrip('.,;:!?…')
        first_bot_word = words[i]
        first_bot_clean = first_bot_word.lstrip('-').rstrip('.,;:!?…').lower()

        # Breaking after punctuation is excellent
        if words[i - 1][-1] in '.,;:!?':
            score += 4

        # Breaking before conjunction/preposition is good
        if first_bot_clean in BREAK_BEFORE:
            score += 2

        # Breaking after a bind-forward word is forbidden
        if last_top_word.lower() in BIND_FORWARD:
            score -= 10

        # Breaking inside a multi-word proper noun is forbidden
        for phrase_lower in KEEP_TOGETHER_LOWER:
            if phrase_lower in full_text_lower:
                # Check if this break point splits the phrase
                if phrase_lower not in top.lower() and phrase_lower not in bot.lower():
                    score -= 10

        candidates.append((score, top, bot))

    if not candidates:
        return None

    # Sort by score descending, then by closest-to-balanced
    candidates.sort(key=lambda x: (-x[0], abs(len(x[1]) - len(x[2]))))
    best_score, best_top, best_bot = candidates[0]

    # Don't suggest a break that scores terribly
    if best_score < -5:
        return None

    return (best_top, best_bot)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Line Balance QC — detect and fix unbalanced subtitle line breaks',
    )
    parser.add_argument('srt_file', help='SRT file to check')
    parser.add_argument(
        '--fix', action='store_true',
        help='Apply suggested fixes (otherwise report only)',
    )
    parser.add_argument(
        '--output', '-o',
        help='Output file (default: overwrite input when --fix)',
    )
    parser.add_argument(
        '--ratio', type=float, default=1.5,
        help='Top/bottom ratio threshold for top-heavy detection (default: 1.5)',
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show all checked cues, not just issues',
    )
    parser.add_argument('--fps', type=int, choices=[24, 25],
                        help='Override CPS soft ceiling for specific framerate (24 or 25)')
    args = parser.parse_args()

    if args.fps:
        global CPS_SOFT_CEILING
        from srt_constants import get_constraints
        c = get_constraints(args.fps, 'nl')
        CPS_SOFT_CEILING = c['cps_hard_limit']

    cues, _errors = parse_srt_file(args.srt_file)
    two_line = [c for c in cues if len(c.text.split('\n')) == 2
                and not is_dual_speaker(c.text)]

    max_chars = MAX_CHARS_PER_LINE
    flagged = []
    fixed = 0
    unbroken = 0
    unfixable = 0
    skipped_cps = 0

    for cue in cues:
        text_lines = cue.text.split('\n')
        if len(text_lines) != 2 or is_dual_speaker(cue.text):
            continue

        issues = check_balance(text_lines)

        # Check if this two-line cue fits on a single line
        full_text = ' '.join(line.rstrip() for line in text_lines)
        can_unbreak = len(full_text) <= max_chars

        if not issues and not can_unbreak:
            continue

        if can_unbreak:
            if not any(i['type'] == 'unbreak' for i in issues):
                issues.insert(0, {
                    'type': 'unbreak',
                    'severity': 'medium',
                    'detail': f'Fits on one line ({len(full_text)} chars ≤ {max_chars})',
                })

        # Try to find a better break (returns None if single line is better)
        suggestion = find_best_break(full_text, max_chars)

        # Discard suggestion if it's identical to what's already there
        if suggestion and list(suggestion) == [l.rstrip() for l in text_lines]:
            suggestion = None

        entry = {
            'cue_num': str(cue.index),
            'current': text_lines,
            'issues': issues,
            'suggestion': full_text if can_unbreak else suggestion,
        }
        flagged.append(entry)

        if args.fix and can_unbreak:
            cue.text = full_text
            unbroken += 1
        elif args.fix and suggestion:
            # CPS guard: don't rebalance if it would push CPS over the limit
            new_char_count = visible_length(suggestion[0]) + visible_length(suggestion[1])
            duration_s = cue.duration_ms / 1000 if cue.duration_ms > 0 else 1
            new_cps = new_char_count / duration_s
            if new_cps > CPS_SOFT_CEILING:
                skipped_cps += 1
            else:
                cue.text = '\n'.join(suggestion)
                fixed += 1
        elif args.fix and not suggestion and not can_unbreak:
            unfixable += 1

    # --- Output ---
    print(f'Checked: {len(two_line)} two-line cues (of {len(cues)} total)')
    print(f'Flagged: {len(flagged)} with balance issues\n')

    if args.fix:
        output_path = args.output or args.srt_file
        write_srt(cues, output_path)
        print(f'Rebalanced: {fixed}, unbroken: {unbroken}, unfixable: {unfixable}, skipped (CPS): {skipped_cps}')
        print(f'Written to: {output_path}')
        return

    high = [f for f in flagged if any(i['severity'] == 'high' for i in f['issues'])]
    medium = [f for f in flagged if f not in high]

    def print_entry(e):
        cur = ' | '.join(line.rstrip() for line in e['current'])
        print(f'  Cue {e["cue_num"]:>3s}  "{cur}"')
        for issue in e['issues']:
            sev = '!!' if issue['severity'] == 'high' else '! '
            print(f'       {sev}  {issue["detail"]}')
        if isinstance(e['suggestion'], str):
            print(f'       >>  "{e["suggestion"]}"  (single line)')
        elif e['suggestion']:
            print(f'       >>  "{e["suggestion"][0]}"')
            print(f'           "{e["suggestion"][1]}"')
        else:
            print(f'       >>  (no auto-fix — manual review needed)')
        print()

    if high:
        print(f'── HIGH ({len(high)}) ──')
        for e in high:
            print_entry(e)

    if medium:
        print(f'── MEDIUM ({len(medium)}) ──')
        for e in medium:
            print_entry(e)


if __name__ == '__main__':
    main()
