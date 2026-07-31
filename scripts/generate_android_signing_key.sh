#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SIGNING_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/linkable/signing"
KEYSTORE="${SIGNING_DIR}/linkable-release.p12"
ENV_FILE="${SIGNING_DIR}/release.env"
KEY_ALIAS="linkable"

if ! command -v keytool >/dev/null 2>&1; then
  echo "error: keytool is required; install jdk17-openjdk first" >&2
  exit 1
fi
if [[ -e "${KEYSTORE}" || -e "${ENV_FILE}" ]]; then
  echo "error: refusing to replace existing signing material in ${SIGNING_DIR}" >&2
  exit 1
fi

umask 077
mkdir -p "${SIGNING_DIR}"
PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export LINKABLE_GENERATED_KEY_PASSWORD="${PASSWORD}"

keytool -genkeypair \
  -keystore "${KEYSTORE}" \
  -storetype PKCS12 \
  -alias "${KEY_ALIAS}" \
  -keyalg RSA \
  -keysize 4096 \
  -validity 10000 \
  -dname "CN=Linkable Local Release, OU=Android, O=Linkable" \
  -storepass:env LINKABLE_GENERATED_KEY_PASSWORD \
  -keypass:env LINKABLE_GENERATED_KEY_PASSWORD \
  -noprompt

{
  printf 'export LINKABLE_ANDROID_KEYSTORE=%q\n' "${KEYSTORE}"
  printf 'export LINKABLE_ANDROID_KEY_ALIAS=%q\n' "${KEY_ALIAS}"
  printf 'export LINKABLE_ANDROID_STORE_PASSWORD=%q\n' "${PASSWORD}"
  printf 'export LINKABLE_ANDROID_KEY_PASSWORD=%q\n' "${PASSWORD}"
} > "${ENV_FILE}"
chmod 0600 "${KEYSTORE}" "${ENV_FILE}"
unset LINKABLE_GENERATED_KEY_PASSWORD PASSWORD

cat <<EOF
Created private Android signing material:
  ${KEYSTORE}
  ${ENV_FILE}

Back up both files securely. Every future update must use the same key.
Load it only for a release build:
  source ${ENV_FILE}
  ${ROOT_DIR}/scripts/build_android_release.sh
EOF
