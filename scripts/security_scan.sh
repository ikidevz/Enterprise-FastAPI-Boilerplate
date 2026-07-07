#!/usr/bin/env bash
set -euo pipefail

# Set SECURITY_SCAN_SOFT_FAIL=1 locally if you want to see findings without
# blocking your own commit; CI should never set this, so real findings gate
# the build.
SOFT_FAIL="${SECURITY_SCAN_SOFT_FAIL:-0}"

python -m pip install --upgrade pip >/dev/null
pip install safety bandit >/dev/null 2>&1
python -m compileall backend >/dev/null

status=0

echo "Running safety (dependency CVE scan)..."
if ! safety check --full-report; then
  status=1
fi

echo "Running bandit (static security lint)..."
if ! bandit -r backend -ll; then
  status=1
fi

if [ "$status" -ne 0 ] && [ "$SOFT_FAIL" != "1" ]; then
  echo "Security scan found issues — failing the build. Set SECURITY_SCAN_SOFT_FAIL=1 to override locally." >&2
  exit 1
fi

exit 0