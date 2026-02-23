"""
Shared subtitle constraints — single source of truth.

SKILL.md is the authoritative reference for Claude during translation.
These constants mirror SKILL.md and are used by all validation/analysis scripts.
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
