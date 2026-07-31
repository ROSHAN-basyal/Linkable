#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/desktop_env.sh"

echo "Running desktop tests..."
PYTHONPATH="${ROOT_DIR}/desktop/src${PYTHONPATH:+:${PYTHONPATH}}" \
  "${LINKABLE_DESKTOP_PYTHON}" -m unittest discover \
    -s "${ROOT_DIR}/desktop/tests" \
    -p "test_*.py"

echo "Checking desktop Python syntax..."
"${LINKABLE_DESKTOP_PYTHON}" -m compileall -q "${ROOT_DIR}/desktop/src"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/android_env.sh"

if [[ -x "${ROOT_DIR}/android/gradlew" && -n "${ANDROID_SDK_ROOT:-}" ]]; then
  echo "Running Android lint, unit tests, and debug build..."
  "${ROOT_DIR}/android/gradlew" -p "${ROOT_DIR}/android" \
    lintDebug testDebugUnitTest assembleDebug
else
  echo "Android SDK not found; skipped Android checks." >&2
  echo "Install the SDK or set ANDROID_SDK_ROOT, then run this script again." >&2
fi

echo "Linkable checks completed."
