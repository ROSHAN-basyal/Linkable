#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/desktop_env.sh"

"${LINKABLE_DESKTOP_PYTHON}" -m py_compile "${SCRIPT_DIR}/validate_milestone_1.py"
"${LINKABLE_DESKTOP_PYTHON}" -m compileall -q "${ROOT_DIR}/desktop/src"
"${LINKABLE_DESKTOP_PYTHON}" -m compileall -q "${ROOT_DIR}/desktop/tests"

echo "Basic Milestone 2 desktop lint pass completed."

if [[ -f "${ROOT_DIR}/scripts/android_env.sh" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/scripts/android_env.sh"
  if [[ -n "${LINKABLE_GRADLE_BIN:-}" ]]; then
    echo "Detected local Gradle binary at ${LINKABLE_GRADLE_BIN}"
  fi
fi
