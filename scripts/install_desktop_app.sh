#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE="${ROOT_DIR}/desktop/packaging/linkable.desktop.in"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
APP_DIR="${DATA_HOME}/applications"
APP_FILE="${APP_DIR}/linkable.desktop"
ICON_THEME_DIR="${DATA_HOME}/icons/hicolor"
ICON_FILE="${ICON_THEME_DIR}/512x512/apps/linkable.png"

mkdir -p "${APP_DIR}"
sed "s|@ROOT_DIR@|${ROOT_DIR}|g" "${TEMPLATE}" > "${APP_FILE}"
chmod 0644 "${APP_FILE}"
install -Dm644 "${ROOT_DIR}/Icons/linkable-app-icon.png" "${ICON_FILE}"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${APP_DIR}" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "${ICON_THEME_DIR}" >/dev/null 2>&1 || true
fi

rm -f "${XDG_CONFIG_HOME:-${HOME}/.config}/autostart/linkable.desktop"

if [[ "${1:-}" == "--autostart" ]]; then
  UNIT_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
  UNIT_FILE="${UNIT_DIR}/linkable-desktop.service"
  mkdir -p "${UNIT_DIR}"
  cat > "${UNIT_FILE}" <<EOF
[Unit]
Description=Linkable desktop background LAN service
After=graphical-session.target network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=${ROOT_DIR}/scripts/run_desktop_gui.sh --background-service
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload || true
  systemctl --user enable --now linkable-desktop.service
  echo "Installed Linkable launcher, app icon, and background-only systemd user service."
else
  echo "Installed Linkable launcher at ${APP_FILE} and icon at ${ICON_FILE}."
  echo "Run again with --autostart to start only the background LAN service after login."
fi
