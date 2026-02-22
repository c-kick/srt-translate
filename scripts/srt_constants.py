"""
Shared subtitle constraints — single source of truth.

SKILL.md is the authoritative reference for Claude during translation.
These constants mirror SKILL.md and are used by all validation/analysis scripts.
"""

# === Shared constraints (all languages) ===
MAX_LINES = 2
MAX_CHARS_PER_LINE = 42
CPS_SOFT_CEILING = 17
MAX_DURATION_MS = 8000

# === Dutch (NL) — Dutch Professional 25fps ===
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
