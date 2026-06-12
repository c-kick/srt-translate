#!/bin/bash
set -euo pipefail

# Create and populate the scripts venv.
#
# webrtcvad is a C extension. On Python versions without a matching wheel, pip
# must compile it locally, so fail early with a useful message if no compiler is
# available.
if ! command -v x86_64-linux-gnu-gcc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1; then
    echo "ERROR: C compiler not found; required to build webrtcvad." >&2
    echo "Install the build toolchain, then rerun this script:" >&2
    echo "  sudo apt-get update" >&2
    echo "  sudo apt-get install build-essential" >&2
    exit 1
fi

python3 -m venv scripts/venv
scripts/venv/bin/pip install --upgrade pip
scripts/venv/bin/pip install -r scripts/requirements.txt
