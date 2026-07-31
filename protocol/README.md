# Protocol

This directory contains the complete Milestone 1 protocol surface for Phase 1.

## Contents

- `schemas/`: protobuf schema files
- `docs/`: protocol specification and security notes
- `generated/`: generated outputs from `scripts/generate_proto.sh`

## Schema Strategy

The wire format uses:

- a length-prefixed frame
- a top-level `Envelope`
- a typed `payload` stored as raw bytes
- per-packet protobuf messages defined in separate schema files

This keeps the transport layer simple and prevents schema family files from depending on one another recursively.

## Generation

Generate all outputs with:

```bash
./scripts/generate_proto.sh
```

