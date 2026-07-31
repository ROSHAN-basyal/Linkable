# Phase 1 Prerequisites

This note captures the prerequisites that should be in place before generating the Phase 1 codebase, with Milestone 1 as the immediate target.

## Scope

- Phase 1 target: secure discovery, pairing, and encrypted LAN-first transport
- Immediate implementation target: Milestone 1 only
- Milestone 1 output: shared protocol schemas, protocol docs, threat model, packet flow, lock-screen policy, and stub generation tooling

## Current Local Environment

### Available

- OS: Arch Linux
- Python: `3.14.4`
- `pip`: available for Python 3.14
- Java runtime: OpenJDK `17.0.18`
- Java compiler: `javac 17.0.18`
- Protocol Buffers compiler: `protoc 34.1`
- Git: available

### Missing or Not Configured

- `gradle`: not installed globally
- `adb`: not installed
- `sdkmanager`: not installed
- `ANDROID_SDK_ROOT`: not set
- `ANDROID_HOME`: not set
- `JAVA_HOME`: not set
- `pytest`: not installed globally
- `ruff`: not installed globally

## What Is Actually Required For Milestone 1

Milestone 1 does not need the full Android runtime stack yet. It can be implemented if the project can:

- create the repository structure
- write `.proto` schemas
- write protocol and security documentation
- generate Python and Kotlin protobuf stubs
- run schema compilation checks

Because `protoc` is already present, the main missing prerequisite for Milestone 1 is not raw compilation capability. The remaining prerequisites are mostly project decisions and dependency-management choices.

## Hard Prerequisites Before Code Generation

### 1. Dependency Installation Permission

Even Milestone 1 will likely need a few installable dependencies for a practical, testable codebase:

- Python protobuf runtime and development tools
- Python test tooling such as `pytest`
- Optional Python linting and formatting tools
- Android protobuf plugin or Gradle wrapper setup for Kotlin stub generation

If dependency installation is allowed in the next prompt, code generation can be done cleanly instead of leaving parts unverified.

### 2. Android Build Toolchain

For Milestone 1 alone, the Android SDK is not strictly required if the goal is limited to source generation and documentation. For the broader Phase 1 codebase, it becomes mandatory.

Recommended minimum Android prerequisites for later prompts:

- Android command-line tools
- Android SDK Platform for the chosen compile SDK
- Android build-tools package
- Platform-tools including `adb`
- A configured `ANDROID_SDK_ROOT`

### 3. Gradle Strategy

A global `gradle` installation is missing. The better approach is to generate and use a checked-in Gradle wrapper instead of relying on a system Gradle install.

That means the next code-generation prompt should assume:

- Gradle wrapper will be committed into the repo
- Java 17 will be used as the baseline JDK

### 4. Repository Generation Scope

There is a meaningful difference between:

- generating only Milestone 1
- generating the full Phase 1 codebase skeleton
- generating a fully runnable Phase 1 implementation

Milestone 1 is feasible immediately.
Full Phase 1 implementation will require additional dependencies and likely Android SDK access.

## Recommended Technical Adjustments Before Generation

These are the main places where the blueprint should be treated carefully:

### Pairing Flow

The current blueprint pairing flow has a contradiction around where the short code is generated and how the phone displays it. The generated codebase should correct that before implementation begins.

### Android Cryptography

The blueprint assumes Ed25519 and X25519 are straightforward across older Android targets. That should not be treated as solved. For Milestone 1, this only affects protocol design and documentation, not runtime code, so the protocol should stay algorithm-aware without pretending the implementation choice is fully settled.

### LAN-Only Milestone 1

Milestone 1 should stay completely LAN-first and Bluetooth-free. No Bluetooth scaffolding is needed yet.

## Ready Status

### Ready Now

- protocol folder creation
- `.proto` schema authoring
- protocol documentation
- threat model
- packet flow diagrams in Markdown
- lock-screen policy document
- basic stub-generation scripts using `protoc`

### Not Ready Yet For End-to-End Validation

- Android build and run validation
- Android emulator or physical-device debugging
- full automated Python test execution without installing test dependencies
- full Kotlin stub generation through a verified Gradle project

## Recommended Next Step

If you want the next prompt to generate Milestone 1 cleanly, the prompt should authorize code generation with these assumptions:

- generate only Phase 1 Milestone 1
- use a Gradle wrapper rather than system Gradle
- keep Android build validation partial if the SDK is still unavailable
- prioritize a robust protocol design over strict adherence to every blueprint detail

## Verification Baseline For The Next Prompt

After generation, the minimum useful checks for Milestone 1 should be:

- `protoc` compiles all `.proto` files successfully
- generated Python protobuf files are created
- generated Kotlin protobuf files are created or the generation path is wired correctly
- protocol documents reference the same packet set as the schemas
- threat model covers spoofing, tampering, repudiation, information disclosure, denial of service, and elevation of privilege

