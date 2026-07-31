#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/desktop_env.sh"

if [[ "${1:-}" != "--background-service" ]] && command -v systemctl >/dev/null 2>&1; then
  if systemctl --user --quiet is-active linkable-desktop.service 2>/dev/null; then
    echo "Stopping linkable-desktop.service so the foreground window can own the Linkable port..." >&2
    systemctl --user stop linkable-desktop.service || true
  fi
fi

if [[ "${1:-}" != "--background-service" ]] && ! "${LINKABLE_DESKTOP_PYTHON}" -c "import PyQt6" >/dev/null 2>&1; then
  cat >&2 <<'EOF'
PyQt6 is not installed in the Linkable desktop environment.

Install GUI dependencies without touching system Python:

  cd /path/to/Linkable
  ./scripts/setup_desktop_venv.sh
  source ./scripts/desktop_env.sh
  python -m pip install -r desktop/requirements.txt -r desktop/requirements-ui.txt

Then rerun:

  ./scripts/run_desktop_gui.sh
EOF
  exit 2
fi

PYTHONPATH="${ROOT_DIR}/desktop/src${PYTHONPATH:+:${PYTHONPATH}}" \
  "${LINKABLE_DESKTOP_PYTHON}" -m linkable_desktop.ui_pyqt.app "$@"
