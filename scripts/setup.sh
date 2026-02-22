#!/bin/bash
# Create and populate the scripts venv
python3 -m venv scripts/venv
scripts/venv/bin/pip install --upgrade pip
scripts/venv/bin/pip install ffsubsync webrtcvad pysubs2
