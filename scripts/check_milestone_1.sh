#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

"${SCRIPT_DIR}/generate_proto.sh"
python3 "${SCRIPT_DIR}/validate_milestone_1.py"

echo
echo "Milestone 1 check completed successfully."
echo "Root: ${ROOT_DIR}"
echo "Generated outputs:"
echo "  - ${ROOT_DIR}/protocol/generated/python"
echo "  - ${ROOT_DIR}/protocol/generated/android-java"
echo "  - ${ROOT_DIR}/protocol/generated/descriptor/linkable_phase1.desc"

