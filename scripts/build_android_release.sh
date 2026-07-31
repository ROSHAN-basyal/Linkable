#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ANDROID_DIR="${ROOT_DIR}/android"
OUTPUT_DIR="${ROOT_DIR}/dist"
VERSION_NAME="$(
  sed -n 's/^[[:space:]]*versionName = "\([^"]*\)"/\1/p' \
    "${ANDROID_DIR}/app/build.gradle.kts" | head -n 1
)"

required=(
  LINKABLE_ANDROID_KEYSTORE
  LINKABLE_ANDROID_KEY_ALIAS
  LINKABLE_ANDROID_STORE_PASSWORD
  LINKABLE_ANDROID_KEY_PASSWORD
)
for variable in "${required[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    echo "error: ${variable} is not set" >&2
    echo "Generate/load a private release key with scripts/generate_android_signing_key.sh." >&2
    exit 1
  fi
done
if [[ ! -f "${LINKABLE_ANDROID_KEYSTORE}" ]]; then
  echo "error: keystore not found: ${LINKABLE_ANDROID_KEYSTORE}" >&2
  exit 1
fi
if [[ -z "${VERSION_NAME}" ]]; then
  echo "error: could not read Android versionName" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/android_env.sh"
if [[ -z "${ANDROID_SDK_ROOT:-}" ]]; then
  echo "error: ANDROID_SDK_ROOT is not set and ~/Android/Sdk was not found" >&2
  exit 1
fi

"${ANDROID_DIR}/gradlew" -p "${ANDROID_DIR}" testDebugUnitTest assembleRelease

SOURCE_APK="${ANDROID_DIR}/app/build/outputs/apk/release/app-release.apk"
TARGET_APK="${OUTPUT_DIR}/Linkable-v${VERSION_NAME}.apk"
if [[ ! -f "${SOURCE_APK}" ]]; then
  echo "error: signed release APK was not produced" >&2
  exit 1
fi

APKSIGNER="$(
  find "${ANDROID_SDK_ROOT}/build-tools" -type f -name apksigner 2>/dev/null |
    sort -V |
    tail -n 1
)"
if [[ -z "${APKSIGNER}" ]]; then
  echo "error: apksigner was not found under ${ANDROID_SDK_ROOT}/build-tools" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
cp "${SOURCE_APK}" "${TARGET_APK}"
"${APKSIGNER}" verify --verbose --print-certs "${TARGET_APK}"
(
  cd "${OUTPUT_DIR}"
  sha256sum "$(basename "${TARGET_APK}")" > "$(basename "${TARGET_APK}").sha256"
)

echo "Release APK: ${TARGET_APK}"
echo "Checksum:    ${TARGET_APK}.sha256"
