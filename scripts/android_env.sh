#!/usr/bin/env bash

__linkable_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
__linkable_root_dir="$(cd -- "${__linkable_script_dir}/.." && pwd)"

__linkable_find_gradle() {
  find "${HOME}/.gradle/wrapper/dists" -type f -path '*/gradle-*/bin/gradle' 2>/dev/null | sort -V | tail -n 1
}

if [[ -z "${ANDROID_SDK_ROOT:-}" && -d "${HOME}/Android/Sdk" ]]; then
  export ANDROID_SDK_ROOT="${HOME}/Android/Sdk"
fi

if [[ -z "${ANDROID_HOME:-}" && -n "${ANDROID_SDK_ROOT:-}" ]]; then
  export ANDROID_HOME="${ANDROID_SDK_ROOT}"
fi

if [[ -z "${JAVA_HOME:-}" ]]; then
  JAVAC_BIN="$(command -v javac || true)"
  if [[ -n "${JAVAC_BIN}" ]]; then
    export JAVA_HOME="$(cd -- "$(dirname -- "${JAVAC_BIN}")/.." && pwd)"
  fi
fi

if [[ -z "${PATH:-}" ]]; then
  export PATH=""
fi

if [[ -n "${ANDROID_SDK_ROOT:-}" ]]; then
  case ":${PATH}:" in
    *":${ANDROID_SDK_ROOT}/platform-tools:"*) ;;
    *) export PATH="${ANDROID_SDK_ROOT}/platform-tools:${PATH}" ;;
  esac
fi

LINKABLE_GRADLE_BIN="$(__linkable_find_gradle || true)"
if [[ -n "${LINKABLE_GRADLE_BIN:-}" ]]; then
  export LINKABLE_GRADLE_BIN
fi

if [[ -z "${GRADLE_USER_HOME:-}" ]]; then
  export GRADLE_USER_HOME="${__linkable_root_dir}/.gradle-session"
fi
