#!/usr/bin/env python3
"""
Analyze gold-standard EN→NL subtitle pairs to extract translation patterns.

Aligns EN and NL cues by timestamp overlap, identifies N:M mappings,
and extracts exemplar translation patterns for skill training.

Usage:
    python3 pair_analyzer.py <en.srt> <nl.srt> [--output analysis.md] [--exemplars exemplars.md]
"""

import argparse
import os
import sys
import re
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# Add script directory to path for srt_utils import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from srt_utils import Subtitle, parse_srt_file


@dataclass
class AlignedGroup:
    """A group of aligned EN and NL cues that correspond to each other."""
    en_cues: List[Subtitle]
    nl_cues: List[Subtitle]

    @property
    def en_text(self) -> str:
        return ' '.join(c.text.replace('\n', ' ') for c in self.en_cues)

    @property
    def nl_text(self) -> str:
        return ' '.join(c.text.replace('\n', ' ') for c in self.nl_cues)

    @property
    def en_char_count(self) -> int:
        return sum(c.char_count for c in self.en_cues)

    @property
    def nl_char_count(self) -> int:
        return sum(c.char_count for c in self.nl_cues)

    @property
    def condensation_ratio(self) -> float:
        """How much shorter NL is vs EN (1.0 = same, 0.5 = half the chars)."""
        if self.en_char_count == 0:
            return 1.0
        return self.nl_char_count / self.en_char_count

    @property
    def merge_type(self) -> str:
        """Describe the N:M mapping type."""
        n, m = len(self.en_cues), len(self.nl_cues)
        if n == 1 and m == 1:
            return "1:1"
        elif n > 1 and m == 1:
            return f"{n}:1 merge"
        elif n == 1 and m > 1:
            return f"1:{m} split"
        else:
            return f"{n}:{m} remap"

    @property
    def time_span_ms(self) -> int:
        start = min(c.start_ms for c in self.en_cues + self.nl_cues)
        end = max(c.end_ms for c in self.en_cues + self.nl_cues)
        return end - start

    @property
    def en_first_index(self) -> int:
        return self.en_cues[0].index if self.en_cues else 0

    @property
    def nl_first_index(self) -> int:
        return self.nl_cues[0].index if self.nl_cues else 0


def overlap_ms(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    """Calculate overlap in ms between two time ranges."""
    overlap_start = max(a_start, b_start)
    overlap_end = min(a_end, b_end)
    return max(0, overlap_end - overlap_start)


def align_cues(en_subs: List[Subtitle], nl_subs: List[Subtitle],
               min_overlap_ratio: float = 0.1) -> List[AlignedGroup]:
    """
    Align EN and NL cues by timestamp overlap.

    Uses a greedy approach: for each EN cue, find all NL cues with significant
    temporal overlap. Then groups connected components.
    """
    # Build overlap mapping: en_idx -> [nl_idx, ...]
    en_to_nl = {i: [] for i in range(len(en_subs))}
    nl_to_en = {j: [] for j in range(len(nl_subs))}

    nl_idx_start = 0  # Optimization: track where to start searching NL cues
    for i, en in enumerate(en_subs):
        for j in range(nl_idx_start, len(nl_subs)):
            nl = nl_subs[j]

            # NL cue is entirely after EN cue — stop searching
            if nl.start_ms > en.end_ms + 2000:
                break

            # NL cue is entirely before EN cue — advance start pointer
            if nl.end_ms < en.start_ms - 2000:
                if j == nl_idx_start:
                    nl_idx_start = j + 1
                continue

            ol = overlap_ms(en.start_ms, en.end_ms, nl.start_ms, nl.end_ms)
            en_dur = en.end_ms - en.start_ms
            nl_dur = nl.end_ms - nl.start_ms
            min_dur = min(en_dur, nl_dur) if min(en_dur, nl_dur) > 0 else 1

            if ol / min_dur >= min_overlap_ratio:
                en_to_nl[i].append(j)
                nl_to_en[j].append(i)

    # Build connected components using union-find
    groups = []
    en_visited = set()
    nl_visited = set()

    for i in range(len(en_subs)):
        if i in en_visited:
            continue

        # BFS to find all connected EN and NL cues
        en_group = set()
        nl_group = set()
        en_queue = [i]

        while en_queue:
            ei = en_queue.pop(0)
            if ei in en_visited:
                continue
            en_visited.add(ei)
            en_group.add(ei)

            for nj in en_to_nl.get(ei, []):
                if nj not in nl_visited:
                    nl_visited.add(nj)
                    nl_group.add(nj)
                    # Also find other EN cues linked to this NL cue
                    for ei2 in nl_to_en.get(nj, []):
                        if ei2 not in en_visited:
                            en_queue.append(ei2)

        if en_group or nl_group:
            groups.append(AlignedGroup(
                en_cues=sorted([en_subs[i] for i in en_group], key=lambda s: s.start_ms),
                nl_cues=sorted([nl_subs[j] for j in nl_group], key=lambda s: s.start_ms)
            ))

    # Also capture any unmatched NL cues (additions in translation)
    for j in range(len(nl_subs)):
        if j not in nl_visited:
            groups.append(AlignedGroup(en_cues=[], nl_cues=[nl_subs[j]]))

    # Sort by time
    groups.sort(key=lambda g: (g.en_cues[0].start_ms if g.en_cues else
                               g.nl_cues[0].start_ms if g.nl_cues else 0))

    return groups


def detect_dual_speaker(text: str) -> bool:
    """Check if a cue contains dual-speaker formatting."""
    lines = text.split('\n')
    return len(lines) == 2 and lines[1].startswith('-')


def detect_idiom_candidate(en_text: str, nl_text: str) -> bool:
    """Heuristic: likely idiom adaptation if texts are very different structurally."""
    en_words = set(en_text.lower().split())
    nl_words = set(nl_text.lower().split())
    # If almost no words overlap and texts are similar length, likely idiom
    if len(en_words) < 3 or len(nl_words) < 3:
        return False
    overlap = en_words & nl_words
    # Names and numbers might overlap, so filter those
    content_overlap = {w for w in overlap if not w[0].isupper() and not w.isdigit()}
    return len(content_overlap) <= 1 and abs(len(en_text) - len(nl_text)) < len(en_text) * 0.5


def detect_register(nl_text: str) -> Optional[str]:
    """Detect formality register from Dutch text."""
    lower = nl_text.lower()
    if any(w in lower for w in [' u ', ' uw ', 'mylord', 'meneer', 'mevrouw']):
        if any(w in lower for w in [' je ', ' jij ', ' jouw ']):
            return 'mixed'
        return 'formal'
    if any(w in lower for w in [' je ', ' jij ', ' jouw ', " m'n ", " z'n "]):
        return 'informal'
    return None


def categorize_group(group: AlignedGroup) -> List[str]:
    """Assign pattern categories to an aligned group."""
    cats = []

    # Merge patterns
    if len(group.en_cues) >= 2 and len(group.nl_cues) == 1:
        cats.append('merge')
    if len(group.en_cues) >= 3 and len(group.nl_cues) <= 2:
        cats.append('heavy-merge')

    # Condensation
    ratio = group.condensation_ratio
    if 0.4 <= ratio <= 0.65:
        cats.append('strong-condensation')
    elif 0.65 < ratio <= 0.8:
        cats.append('condensation')

    # Expansion (NL longer than EN — unusual, interesting)
    if ratio > 1.15 and group.en_char_count > 10:
        cats.append('expansion')

    # Dual speaker
    for nl in group.nl_cues:
        if detect_dual_speaker(nl.text):
            cats.append('dual-speaker')
            break

    # Idiom candidate
    if len(group.en_cues) <= 2 and len(group.nl_cues) <= 2:
        if detect_idiom_candidate(group.en_text, group.nl_text):
            cats.append('idiom-candidate')

    # Register
    reg = detect_register(group.nl_text)
    if reg:
        cats.append(f'register-{reg}')

    # V2 inversion detection (simple heuristic)
    nl_text = group.nl_text
    # Check for fronted time/place adverbs followed by verb-subject
    v2_patterns = [
        r'\b(Toen|Nu|Daar|Hier|Daarom|Dus|Zo|Toch|Echter|Bovendien|Daarna|Gisteren|Vandaag)\s+\w+\s+(ik|hij|zij|wij|ze|we|je|u)\b',
    ]
    for pat in v2_patterns:
        if re.search(pat, nl_text):
            cats.append('v2-inversion')
            break

    # Continuation (ellipsis usage)
    if '...' in group.nl_text:
        cats.append('continuation')

    return cats


def format_ms(ms: int) -> str:
    """Format milliseconds as HH:MM:SS."""
    s = ms // 1000
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def generate_analysis(groups: List[AlignedGroup], en_total: int, nl_total: int,
                      source_name: str) -> str:
    """Generate the full analysis report."""
    lines = []
    lines.append(f"# Pair Analysis: {source_name}")
    lines.append("")

    # Global stats
    merge_ratio = nl_total / en_total if en_total > 0 else 0
    lines.append("## Global Statistics")
    lines.append(f"- EN cues: {en_total}")
    lines.append(f"- NL cues: {nl_total}")
    lines.append(f"- Merge ratio: {merge_ratio:.1%} ({nl_total}/{en_total})")
    lines.append(f"- Aligned groups: {len(groups)}")

    # Mapping type distribution
    type_counts = {}
    for g in groups:
        t = g.merge_type
        type_counts[t] = type_counts.get(t, 0) + 1
    lines.append("")
    lines.append("## Mapping Distribution")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {t}: {count} ({count/len(groups):.0%})")

    # Category distribution
    cat_counts = {}
    for g in groups:
        for cat in categorize_group(g):
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
    lines.append("")
    lines.append("## Pattern Categories")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {cat}: {count}")

    # Condensation stats
    ratios = [g.condensation_ratio for g in groups
              if g.en_char_count > 20 and g.nl_char_count > 0]
    if ratios:
        lines.append("")
        lines.append("## Condensation Statistics")
        lines.append(f"- Mean ratio: {sum(ratios)/len(ratios):.2f} (NL/EN chars)")
        lines.append(f"- Median: {sorted(ratios)[len(ratios)//2]:.2f}")
        lines.append(f"- Min: {min(ratios):.2f}")
        lines.append(f"- Max: {max(ratios):.2f}")

    return '\n'.join(lines)


def generate_exemplars(groups: List[AlignedGroup], source_name: str,
                       max_per_category: int = 30) -> str:
    """Generate categorized exemplar pairs for skill training."""
    lines = []
    lines.append(f"# Exemplar Pairs: {source_name}")
    lines.append("")
    lines.append("Each entry shows EN source → NL translation with pattern analysis.")
    lines.append("")

    # Collect examples per category
    categorized = {}
    for g in groups:
        cats = categorize_group(g)
        if not cats:
            continue
        # Skip very short or trivial cues
        if g.en_char_count < 15 and 'dual-speaker' not in cats:
            continue
        for cat in cats:
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(g)

    # Category display order and descriptions
    cat_info = {
        'heavy-merge': ('Heavy Merge (3+ EN → 1-2 NL)', 'Multiple source cues condensed into one or two target cues'),
        'merge': ('Merge (2 EN → 1 NL)', 'Two source cues merged into a single target cue'),
        'strong-condensation': ('Strong Condensation', 'Significant text reduction while preserving meaning'),
        'condensation': ('Condensation', 'Moderate text reduction'),
        'idiom-candidate': ('Idiom Adaptation', 'English expression replaced with Dutch equivalent'),
        'dual-speaker': ('Dual Speaker Formatting', 'Multiple speakers in a single cue'),
        'v2-inversion': ('V2 Word Order', 'Dutch verb-second inversion after fronted elements'),
        'register-formal': ('Formal Register', 'Use of u/uw, formal phrasing'),
        'register-informal': ('Informal Register', 'Use of je/jij, contractions'),
        'register-mixed': ('Mixed Register', 'Both formal and informal in same group'),
        'continuation': ('Continuation (Ellipsis)', 'Use of ... for continuation across cues'),
        'expansion': ('Expansion (NL > EN)', 'Dutch translation longer than English source'),
    }

    for cat_key in ['heavy-merge', 'merge', 'strong-condensation', 'condensation',
                    'idiom-candidate', 'dual-speaker', 'v2-inversion',
                    'register-formal', 'register-informal', 'continuation', 'expansion']:
        examples = categorized.get(cat_key, [])
        if not examples:
            continue

        title, desc = cat_info.get(cat_key, (cat_key, ''))
        lines.append(f"## {title}")
        lines.append(f"*{desc}*")
        lines.append("")

        # Sort by "interestingness": prefer higher condensation, longer texts
        if 'condensation' in cat_key or 'merge' in cat_key:
            examples.sort(key=lambda g: g.condensation_ratio)
        elif cat_key == 'expansion':
            examples.sort(key=lambda g: -g.condensation_ratio)

        shown = 0
        for g in examples:
            if shown >= max_per_category:
                break

            # Format EN cues
            en_parts = []
            for c in g.en_cues:
                en_parts.append(f"  [{c.index}] {c.text.replace(chr(10), ' / ')}")
            en_display = '\n'.join(en_parts)

            # Format NL cues
            nl_parts = []
            for c in g.nl_cues:
                nl_parts.append(f"  [{c.index}] {c.text.replace(chr(10), ' / ')}")
            nl_display = '\n'.join(nl_parts)

            lines.append(f"### {format_ms(g.en_cues[0].start_ms if g.en_cues else g.nl_cues[0].start_ms)} | {g.merge_type} | ratio {g.condensation_ratio:.2f}")
            lines.append(f"**EN** ({g.en_char_count} chars):")
            lines.append(en_display)
            lines.append(f"**NL** ({g.nl_char_count} chars):")
            lines.append(nl_display)
            lines.append("")

            shown += 1

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Analyze EN→NL subtitle pair')
    parser.add_argument('en_srt', help='English SRT file')
    parser.add_argument('nl_srt', help='Dutch SRT file')
    parser.add_argument('--output', '-o', help='Analysis output file (default: stdout)')
    parser.add_argument('--exemplars', '-e', help='Exemplar pairs output file')
    parser.add_argument('--max-per-category', type=int, default=30,
                        help='Max exemplars per category (default: 30)')
    parser.add_argument('--source-name', '-n', help='Source name for report header')
    args = parser.parse_args()

    # Parse both files
    en_subs, en_errors = parse_srt_file(args.en_srt)
    nl_subs, nl_errors = parse_srt_file(args.nl_srt)

    if en_errors:
        print(f"Warning: {len(en_errors)} parse errors in EN file", file=sys.stderr)
    if nl_errors:
        print(f"Warning: {len(nl_errors)} parse errors in NL file", file=sys.stderr)

    print(f"Parsed {len(en_subs)} EN cues, {len(nl_subs)} NL cues", file=sys.stderr)

    # Derive source name
    source_name = args.source_name
    if not source_name:
        source_name = os.path.basename(args.en_srt).split('.')[0]
        # Clean up common patterns
        for pat in [' [imdb-', ' [Bluray-', ' [HDTV-']:
            if pat in source_name:
                source_name = source_name[:source_name.index(pat)]

    # Align cues
    groups = align_cues(en_subs, nl_subs)
    print(f"Aligned into {len(groups)} groups", file=sys.stderr)

    # Generate analysis
    analysis = generate_analysis(groups, len(en_subs), len(nl_subs), source_name)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(analysis)
        print(f"Analysis written to {args.output}", file=sys.stderr)
    else:
        print(analysis)

    # Generate exemplars
    if args.exemplars:
        exemplars = generate_exemplars(groups, source_name, args.max_per_category)
        with open(args.exemplars, 'w', encoding='utf-8') as f:
            f.write(exemplars)
        print(f"Exemplars written to {args.exemplars}", file=sys.stderr)


if __name__ == '__main__':
    main()
