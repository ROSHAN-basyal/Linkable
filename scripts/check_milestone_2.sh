#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

"${SCRIPT_DIR}/check_milestone_1.sh"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/desktop_env.sh"

PYTHONPATH="${ROOT_DIR}/desktop/src${PYTHONPATH:+:${PYTHONPATH}}" \
  "${LINKABLE_DESKTOP_PYTHON}" -m unittest discover -s "${ROOT_DIR}/desktop/tests" -p "test_*.py"

"${LINKABLE_DESKTOP_PYTHON}" -m compileall -q "${ROOT_DIR}/desktop/src"

required_android_files=(
  "${ROOT_DIR}/android/settings.gradle.kts"
  "${ROOT_DIR}/android/build.gradle.kts"
  "${ROOT_DIR}/android/app/build.gradle.kts"
  "${ROOT_DIR}/android/app/src/main/AndroidManifest.xml"
  "${ROOT_DIR}/android/app/src/main/java/com/linkable/MainActivity.kt"
  "${ROOT_DIR}/android/app/src/main/java/com/linkable/discovery/NsdDiscoveryManager.kt"
  "${ROOT_DIR}/android/app/src/main/java/com/linkable/ui/screens/DiscoveryScreen.kt"
)

for path in "${required_android_files[@]}"; do
  [[ -f "${path}" ]] || { echo "missing required Android file: ${path}" >&2; exit 1; }
done

if [[ -f "${SCRIPT_DIR}/android_env.sh" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/android_env.sh"
fi

echo
echo "Milestone 2 desktop checks passed."
echo "Android project files are present."

if [[ -n "${ANDROID_SDK_ROOT:-}" ]]; then
  echo "Detected Android SDK: ${ANDROID_SDK_ROOT}"
else
  echo "Android SDK not exported; use 'source ./scripts/android_env.sh' before Android checks."
fi

if [[ -n "${LINKABLE_GRADLE_BIN:-}" ]]; then
  echo "Detected local Gradle binary: ${LINKABLE_GRADLE_BIN}"
  echo "Optional Android validation:"
  echo "  source ./scripts/android_env.sh"
  echo "  \"\${LINKABLE_GRADLE_BIN}\" -p android testDebugUnitTest"
else
  echo "No local Gradle binary detected automatically."
fi
