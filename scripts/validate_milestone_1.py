#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def require(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"missing required path: {path}")


def parse_packet_ids(common_proto: Path) -> dict[str, int]:
    text = common_proto.read_text(encoding="utf-8")
    matches = re.findall(r"(PACKET_TYPE_[A-Z0-9_]+)\s*=\s*(\d+)\s*;", text)
    if not matches:
        raise SystemExit("no packet types found in common.proto")

    packet_ids: dict[str, int] = {}
    reverse: dict[int, str] = {}
    for name, raw_value in matches:
        value = int(raw_value)
        if name in packet_ids:
            raise SystemExit(f"duplicate packet name: {name}")
        if value in reverse:
            raise SystemExit(
                f"duplicate packet id {value}: {name} conflicts with {reverse[value]}"
            )
        packet_ids[name] = value
        reverse[value] = name
    return packet_ids


def ensure_doc_mentions(packet_names: list[str], protocol_spec: Path) -> None:
    text = protocol_spec.read_text(encoding="utf-8")
    missing = [
        name
        for name in packet_names
        if not name.endswith("_UNSPECIFIED") and name not in text
    ]
    if missing:
        raise SystemExit(
            "protocol_spec.md is missing packet references: " + ", ".join(missing)
        )


def ensure_stride_coverage(threat_model: Path) -> None:
    text = threat_model.read_text(encoding="utf-8").lower()
    required = [
        "spoofing",
        "tampering",
        "repudiation",
        "information disclosure",
        "denial of service",
        "elevation of privilege",
    ]
    missing = [term for term in required if term not in text]
    if missing:
        raise SystemExit(
            "threat_model.md is missing STRIDE coverage for: " + ", ".join(missing)
        )


def ensure_lockscreen_policy(lock_doc: Path) -> None:
    text = lock_doc.read_text(encoding="utf-8")
    required = [
        "message_reply_while_locked",
        "call_control_while_locked",
        "dial_while_locked",
        "screen_lock_state_reporting",
    ]
    missing = [term for term in required if term not in text]
    if missing:
        raise SystemExit(
            "lock_screen_policy.md is missing capability flags: " + ", ".join(missing)
        )


def ensure_generated_outputs() -> None:
    python_dir = ROOT / "protocol/generated/python"
    java_dir = ROOT / "protocol/generated/android-java"
    desc_file = ROOT / "protocol/generated/descriptor/linkable_phase1.desc"

    require(python_dir)
    require(java_dir)
    require(desc_file)

    py_files = sorted(python_dir.rglob("*_pb2.py"))
    java_files = sorted(java_dir.rglob("*.java"))
    if not py_files:
        raise SystemExit("no generated Python protobuf files found")
    if not java_files:
        raise SystemExit("no generated Android Java protobuf files found")
    if desc_file.stat().st_size == 0:
        raise SystemExit("descriptor set is empty")

    for path in py_files:
        py_compile.compile(str(path), doraise=True)


def main() -> int:
    required_files = [
        ROOT / "protocol/schemas/common.proto",
        ROOT / "protocol/schemas/pairing.proto",
        ROOT / "protocol/schemas/session.proto",
        ROOT / "protocol/schemas/transport.proto",
        ROOT / "protocol/schemas/errors.proto",
        ROOT / "protocol/docs/protocol_spec.md",
        ROOT / "protocol/docs/threat_model.md",
        ROOT / "protocol/docs/packet_flow.md",
        ROOT / "protocol/docs/lock_screen_policy.md",
    ]

    for path in required_files:
        require(path)

    packet_ids = parse_packet_ids(ROOT / "protocol/schemas/common.proto")
    ensure_doc_mentions(sorted(packet_ids), ROOT / "protocol/docs/protocol_spec.md")
    ensure_stride_coverage(ROOT / "protocol/docs/threat_model.md")
    ensure_lockscreen_policy(ROOT / "protocol/docs/lock_screen_policy.md")
    ensure_generated_outputs()

    print("Milestone 1 validation passed.")
    print(f"Packet registry count: {len(packet_ids)}")
    print("Generated Python and Android Java outputs are present and syntactically valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
