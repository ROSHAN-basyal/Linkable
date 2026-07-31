# Protocol

This directory defines the wire protocol shared by the Android and Linux
applications.

## Contents

- `schemas/`: protobuf schema files
- `docs/`: protocol specification, packet flow, lock-screen policy, and threat
  model

Generated Android sources are produced by Gradle during a build. Generated
desktop Python modules are committed under
`desktop/src/linkable_desktop/generated_proto` so a source installation does
not require `protoc`.

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

This developer command requires `protoc`. Normal Android and desktop builds do
not.
