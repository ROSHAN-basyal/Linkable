#!/usr/bin/env bash
set -euo pipefail

LABEL="Linkable Camera"
VIDEO_NR="${LINKABLE_CAMERA_VIDEO_NR:-10}"
STOP_DROIDCAM=0
PERSIST=0

usage() {
  cat <<'EOF'
Usage: ./scripts/setup_linkable_camera.sh [--persist] [--stop-droidcam]

Creates the Linkable Camera v4l2loopback device for the current boot.

Options:
  --persist        Also install /etc/modules-load.d and /etc/modprobe.d config
                   so Linkable Camera is recreated after reboot.
  --stop-droidcam  Unload DroidCam's loopback module first.
EOF
}

run_as_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
    return
  fi
  if [[ -t 0 ]]; then
    sudo "$@"
    return
  fi
  if sudo -n true 2>/dev/null; then
    sudo "$@"
    return
  fi
  echo "Root permission is required. Run this command manually:" >&2
  printf '  sudo' >&2
  printf ' %q' "$@" >&2
  printf '\n' >&2
  exit 1
}

write_root_file() {
  local path="$1"
  local content="$2"
  run_as_root sh -c 'printf "%s\n" "$1" > "$2"' sh "${content}" "${path}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --persist)
      PERSIST=1
      ;;
    --stop-droidcam)
      STOP_DROIDCAM=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "${STOP_DROIDCAM}" -eq 1 ]]; then
  echo "Stopping DroidCam loopback module if it is loaded."
  run_as_root modprobe -r v4l2loopback_dc || true
fi

install_persistent_config() {
  echo "Installing persistent Linkable Camera module configuration."
  run_as_root install -d /etc/modules-load.d /etc/modprobe.d
  write_root_file /etc/modules-load.d/linkable-camera.conf "v4l2loopback"
  write_root_file /etc/modprobe.d/linkable-camera.conf \
    "options v4l2loopback video_nr=${VIDEO_NR} card_label=\"${LABEL}\" exclusive_caps=1"
  echo "Persistent config installed:"
  echo "  /etc/modules-load.d/linkable-camera.conf"
  echo "  /etc/modprobe.d/linkable-camera.conf"
}

if command -v v4l2-ctl >/dev/null 2>&1 && v4l2-ctl --list-devices | grep -qi "${LABEL}"; then
  echo "${LABEL} already exists."
  if [[ "${PERSIST}" -eq 1 ]]; then
    install_persistent_config
  fi
  v4l2-ctl --list-devices
  exit 0
fi

if ! modinfo v4l2loopback >/dev/null 2>&1; then
  cat >&2 <<'EOF'
v4l2loopback is not installed.

Arch:
  sudo pacman -S v4l2loopback-dkms v4l-utils ffmpeg

Debian/Ubuntu:
  sudo apt install v4l2loopback-dkms v4l-utils ffmpeg

Fedora:
  sudo dnf install v4l2loopback v4l-utils ffmpeg
EOF
  exit 1
fi

while [[ -e "/dev/video${VIDEO_NR}" ]]; do
  VIDEO_NR=$((VIDEO_NR + 1))
done

echo "Creating ${LABEL} at /dev/video${VIDEO_NR}."
run_as_root modprobe v4l2loopback "video_nr=${VIDEO_NR}" "card_label=${LABEL}" "exclusive_caps=1"

if [[ "${PERSIST}" -eq 1 ]]; then
  install_persistent_config
fi

if command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl --list-devices
else
  echo "Install v4l-utils to verify camera names with v4l2-ctl."
fi
