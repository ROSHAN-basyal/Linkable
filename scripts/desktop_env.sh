#!/usr/bin/env bash

__linkable_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
__linkable_root_dir="$(cd -- "${__linkable_script_dir}/.." && pwd)"
__linkable_venv_dir="${__linkable_root_dir}/.venv-desktop"

if [[ -d "${__linkable_venv_dir}" ]]; then
  export VIRTUAL_ENV="${__linkable_venv_dir}"
  case ":${PATH:-}:" in
    *":${__linkable_venv_dir}/bin:"*) ;;
    *) export PATH="${__linkable_venv_dir}/bin:${PATH:-}" ;;
  esac
  export LINKABLE_DESKTOP_PYTHON="${__linkable_venv_dir}/bin/python"
  export LINKABLE_DESKTOP_PIP="${__linkable_venv_dir}/bin/pip"
else
  export LINKABLE_DESKTOP_PYTHON="$(command -v python3)"
  export LINKABLE_DESKTOP_PIP="$(command -v pip3 || command -v pip || true)"
fi

