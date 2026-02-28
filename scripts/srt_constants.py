"""
Shared subtitle constraints — single source of truth.

This file is the canonical definition of all constraint values.
Both Python scripts and shared-constraints.md consume these values.

To regenerate the markdown table in shared-constraints.md:
    python3 scripts/srt_constants.py --sync
"""

# === Shared constraints (all languages) ===
MAX_LINES = 2
MAX_CHARS_PER_LINE = 42
CPS_SOFT_CEILING = 17  # 25fps hard limit (kept for backwards compat)
MAX_DURATION_MS = 8000

# === Dutch (NL) — Dutch Professional 25fps (flat constants for backwards compat) ===
NL_CPS_TARGET = 12
NL_CPS_HARD_LIMIT = 20
NL_MIN_GAP_MS = 120          # 3 frames at 25fps
NL_MIN_DURATION_MS = 830
NL_MAX_WORDS_PER_MIN = 180
NL_UNBREAK_THRESHOLD = 40    # unbreak subtitles shorter than this

# === English (EN) — Netflix English (USA) Timed Text Style Guide ===
EN_CPS_TARGET = 15
EN_CPS_HARD_LIMIT = 20
EN_MIN_GAP_MS = 125          # 3 frames at 24fps
EN_MIN_DURATION_MS = 1000

# === CPS reporting thresholds (lenient, for diagnostic use) ===
CPS_REPORT_HARD_SCRIPTED = 25
CPS_REPORT_HARD_UNSCRIPTED = 35

# === Framerate-aware constraint dicts ===

_NL_CONSTRAINTS = {
    24: {
        'cps_optimal': 11,
        'cps_hard_limit': 15,
        'cps_emergency_max': 20,
        'max_chars_per_line': 42,
        'max_duration_ms': 7007,
        'min_duration_ms': 1400,
        'min_gap_ms': 125,        # 3 frames at 23.976/24fps
        'max_words_per_min': 180,
        'max_lines': 2,
        'unbreak_threshold': 40,
    },
    25: {
        'cps_optimal': 12,
        'cps_hard_limit': 17,
        'cps_emergency_max': 20,
        'max_chars_per_line': 42,
        'max_duration_ms': 7000,
        'min_duration_ms': 830,
        'min_gap_ms': 120,        # 3 frames at 25fps
        'max_words_per_min': 180,
        'max_lines': 2,
        'unbreak_threshold': 40,
    },
}

_EN_CONSTRAINTS = {
    24: {
        'cps_optimal': 15,
        'cps_hard_limit': 20,
        'cps_emergency_max': 20,
        'max_chars_per_line': 42,
        'max_duration_ms': 7007,
        'min_duration_ms': 1000,
        'min_gap_ms': 125,
        'max_words_per_min': 180,
        'max_lines': 2,
    },
    25: {
        'cps_optimal': 15,
        'cps_hard_limit': 20,
        'cps_emergency_max': 20,
        'max_chars_per_line': 42,
        'max_duration_ms': 7000,
        'min_duration_ms': 1000,
        'min_gap_ms': 120,
        'max_words_per_min': 180,
        'max_lines': 2,
    },
}


def classify_fps(raw_fps) -> int:
    """Classify a raw framerate value into 24 or 25.

    Accepts float, int, or fraction string like '24000/1001'.
    Returns 24 or 25.
    """
    if isinstance(raw_fps, str) and '/' in raw_fps:
        num, den = raw_fps.split('/')
        fps = float(num) / float(den)
    else:
        fps = float(raw_fps)
    return 24 if fps < 24.5 else 25


def get_constraints(fps, language='nl'):
    """Return constraint dict for a given fps and language.

    Args:
        fps: Raw framerate (float, int, or fraction string).
             Classified into 24 or 25.
        language: 'nl' or 'en'

    Returns:
        Dict of constraint values.
    """
    bucket = classify_fps(fps) if not isinstance(fps, int) or fps not in (24, 25) else fps
    if language == 'en':
        return dict(_EN_CONSTRAINTS[bucket])
    return dict(_NL_CONSTRAINTS[bucket])


def generate_markdown_table():
    """Generate the NL constraints markdown table from the canonical dicts."""
    nl24 = _NL_CONSTRAINTS[24]
    nl25 = _NL_CONSTRAINTS[25]

    rows = [
        ('CPS Optimal',          str(nl24['cps_optimal']),      str(nl25['cps_optimal'])),
        ('CPS Hard Limit',       str(nl24['cps_hard_limit']),   str(nl25['cps_hard_limit'])),
        ('CPS Emergency Maximum', str(nl24['cps_emergency_max']), str(nl25['cps_emergency_max'])),
        ('Characters per line',  str(nl24['max_chars_per_line']), str(nl25['max_chars_per_line'])),
        ('Maximum cue duration', f"{nl24['max_duration_ms']}ms", f"{nl25['max_duration_ms']}ms"),
        ('Minimum cue duration', f"{nl24['min_duration_ms']}ms", f"{nl25['min_duration_ms']}ms"),
        ('Minimum cue gap',     f"{nl24['min_gap_ms']}ms (3 frames)", f"{nl25['min_gap_ms']}ms (3 frames)"),
        ('Max words/min',       str(nl24['max_words_per_min']), str(nl25['max_words_per_min'])),
        ('Max lines per cue',   str(nl24['max_lines']),         str(nl25['max_lines'])),
        ('CPS calculation',     'All characters (incl. spaces); `...` counts as 1 char',
                                'All characters (incl. spaces); `...` counts as 1 char'),
        ('Merge lines shorter than', f"{nl24['unbreak_threshold']} chars", f"{nl25['unbreak_threshold']} chars"),
    ]

    lines = ['| Constraint | 23.976 / 24 fps | 25 fps |', '|---|---|---|']
    for label, v24, v25 in rows:
        lines.append(f'| {label} | {v24} | {v25} |')
    return '\n'.join(lines)


def sync_constraints_md():
    """Regenerate the constraints table in shared-constraints.md."""
    import os
    md_path = os.path.join(os.path.dirname(__file__), '..', 'base', 'shared-constraints.md')
    md_path = os.path.normpath(md_path)

    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    begin = '<!-- BEGIN GENERATED CONSTRAINTS -->'
    end = '<!-- END GENERATED CONSTRAINTS -->'

    if begin not in content or end not in content:
        print(f'ERROR: Marker comments not found in {md_path}')
        print(f'Expected {begin} and {end}')
        return False

    before = content[:content.index(begin) + len(begin)]
    after = content[content.index(end):]

    new_content = before + '\n' + generate_markdown_table() + '\n' + after

    if new_content == content:
        print('shared-constraints.md is already up to date.')
        return True

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'Updated {md_path}')
    return True


if __name__ == '__main__':
    import sys
    if '--sync' in sys.argv:
        success = sync_constraints_md()
        sys.exit(0 if success else 1)
    elif '--markdown' in sys.argv:
        print(generate_markdown_table())
    else:
        print('Usage: python3 srt_constants.py [--sync | --markdown]')
        print('  --sync      Regenerate constraints table in shared-constraints.md')
        print('  --markdown  Print the constraints table to stdout')
        sys.exit(1)
