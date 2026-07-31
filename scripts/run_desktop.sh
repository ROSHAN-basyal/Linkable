#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/desktop_env.sh"

PYTHONPATH="${ROOT_DIR}/desktop/src${PYTHONPATH:+:${PYTHONPATH}}" \
  "${LINKABLE_DESKTOP_PYTHON}" "${ROOT_DIR}/desktop/src/main.py" "$@"
