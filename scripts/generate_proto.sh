#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SCHEMA_DIR="${ROOT_DIR}/protocol/schemas"
GENERATED_DIR="${ROOT_DIR}/protocol/generated"
PYTHON_OUT="${GENERATED_DIR}/python"
DESKTOP_PYTHON_OUT="${ROOT_DIR}/desktop/src/linkable_desktop/generated_proto"
ANDROID_JAVA_OUT="${GENERATED_DIR}/android-java"
DESCRIPTOR_OUT="${GENERATED_DIR}/descriptor"

PROTOC_BIN="${PROTOC:-$(command -v protoc || true)}"
if [[ -z "${PROTOC_BIN}" ]]; then
  echo "error: protoc not found" >&2
  exit 1
fi

mkdir -p "${PYTHON_OUT}" "${ANDROID_JAVA_OUT}" "${DESCRIPTOR_OUT}" "${DESKTOP_PYTHON_OUT}"

mapfile -t PROTO_FILES < <(find "${SCHEMA_DIR}" -maxdepth 1 -type f -name "*.proto" | sort)
if [[ "${#PROTO_FILES[@]}" -eq 0 ]]; then
  echo "error: no .proto files found in ${SCHEMA_DIR}" >&2
  exit 1
fi

echo "Using protoc: ${PROTOC_BIN}"
echo "Schema dir: ${SCHEMA_DIR}"
echo "Python output: ${PYTHON_OUT}"
echo "Android Java Lite output: ${ANDROID_JAVA_OUT}"

"${PROTOC_BIN}" \
  --proto_path="${SCHEMA_DIR}" \
  --python_out="${PYTHON_OUT}" \
  --java_out=lite:"${ANDROID_JAVA_OUT}" \
  --descriptor_set_out="${DESCRIPTOR_OUT}/linkable_phase1.desc" \
  --include_imports \
  --include_source_info \
  "${PROTO_FILES[@]}"

find "${DESKTOP_PYTHON_OUT}" -maxdepth 1 -type f -name "*_pb2.py" -delete
cp "${PYTHON_OUT}"/*_pb2.py "${DESKTOP_PYTHON_OUT}/"
touch "${DESKTOP_PYTHON_OUT}/__init__.py"

echo "Generated:"
echo "  - Python protobuf modules"
echo "  - Packaged desktop Python protobuf modules"
echo "  - Android-consumable Java Lite protobuf classes"
echo "  - Descriptor set at ${DESCRIPTOR_OUT}/linkable_phase1.desc"
