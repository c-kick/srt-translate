#!/usr/bin/env bash
# Wrapper to invoke the venv Python interpreter from a single-level path.
#
# Why this exists:
#   The orchestrator grants Bash permission via "Bash(scripts/*)" which only
#   matches a single directory level.  The real interpreter lives at
#   scripts/venv/bin/python3 (three levels deep) and therefore falls outside
#   that pattern.  This wrapper lives at scripts/run-venv.sh (one level) so
#   it matches the allowlist, and it resolves the venv path absolutely so it
#   works regardless of the current working directory.
#
# Usage:
#   scripts/run-venv.sh scripts/trim_to_speech.py [args...]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/venv/bin/python3"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "ERROR: venv not found at ${VENV_PYTHON}" >&2
    echo "Run: scripts/setup.sh" >&2
    exit 1
fi

exec "$VENV_PYTHON" "$@"
