#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/desktop_env.sh"

PYTHONPATH="${ROOT_DIR}/desktop/src${PYTHONPATH:+:${PYTHONPATH}}" \
  "${LINKABLE_DESKTOP_PYTHON}" -m unittest discover -s "${ROOT_DIR}/desktop/tests"

if [[ -f "${ROOT_DIR}/scripts/android_env.sh" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/scripts/android_env.sh"
  if [[ -n "${LINKABLE_GRADLE_BIN:-}" ]]; then
    "${LINKABLE_GRADLE_BIN}" -p "${ROOT_DIR}/android" testDebugUnitTest
  else
    echo "LINKABLE_GRADLE_BIN was not detected; skipping Android checks." >&2
  fi
fi
