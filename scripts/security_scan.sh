#!/usr/bin/env bash
set -euo pipefail
python -m pip install --upgrade pip >/dev/null
pip install safety bandit >/dev/null 2>&1 || true
python -m compileall backend >/dev/null
if command -v safety >/dev/null 2>&1; then
  safety check --full-report || true
fi
if command -v bandit >/dev/null 2>&1; then
  bandit -r backend || true
fi
