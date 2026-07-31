#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-desktop"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/desktop/requirements.txt" -r "${ROOT_DIR}/desktop/requirements-ui.txt"

cat <<EOF
Desktop virtual environment is ready:
  ${VENV_DIR}

Activate it with:
  source "${VENV_DIR}/bin/activate"

Or just run:
  source ./scripts/desktop_env.sh
EOF
