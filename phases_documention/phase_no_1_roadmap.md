# Phase 1 Roadmap: Secure Discovery, Pairing, and Encrypted LAN-First Transport

## Phase Goal
Build the first working connection between the Android app and the Linux desktop app on the same LAN, authenticate both devices securely, and exchange simple encrypted data packets reliably while treating LAN as the primary transport and Bluetooth as optional only if later proven necessary.

## Suggested Duration
3 to 5 weeks

## Primary Outcome
By the end of this phase, one Android phone and one Linux laptop can discover each other on the same LAN, complete a user-approved pairing flow, persist trust locally, and exchange signed and encrypted messages over a stable local session using a desktop codebase that remains Linux-friendly across distributions and an Android client that stays lightweight in background operation.

## Scope

### In Scope
- Local network discovery between phone and laptop
- Device identity generation and secure key storage
- Pairing flow using a short code or one-time verification token
- Mutual authentication after first pairing
- Encrypted LAN-first transport for simple request/response packets
- Basic session management, reconnect, and trust persistence
- Packet types for heartbeat, ping, device info, and capability exchange
- Logging and diagnostics for pairing and transport failures
- Linux-first desktop runtime constraints and distro-friendly dependency choices
- Lightweight Android service model with low memory, battery, and background overhead
- Definition of lock-screen behavior requirements for later message and call features

### Out of Scope
- Notification mirroring
- Message reply
- File transfer UI
- Call pickup or dialing
- Bluetooth setup or usage beyond proof-of-necessity research

## Recommended Technical Direction
- Discovery: Android NSD and desktop mDNS or compatible local service discovery
- Trust model: local-only pairing with user confirmation and persistent device identity
- Cryptography: X25519 or equivalent ECDH for session agreement, Ed25519 or device-bound signing for trust, AEAD encryption for transport
- Transport: TCP or WebSocket over LAN with application-level framing and no Bluetooth dependency in the core protocol
- Pairing UX: mobile shows a one-time code, laptop enters it, both sides confirm matched device names
- Storage: Android Keystore on phone, OS-backed secure storage or encrypted file on laptop
- Desktop baseline: Linux-first codebase with minimal distro-specific assumptions and packaging paths that can later target AppImage, Flatpak, and native packages
- Android baseline: lightweight background components only, with strict attention to battery cost, wakeups, and foreground service usage

## Core Workstreams

### 1. Protocol and Security Foundation
- Define packet schema and versioning
- Define pairing protocol and reconnection rules
- Decide session rotation and replay protection rules
- Document failure states such as stale keys, duplicate devices, and LAN change
- Define lock-state policy for future operations that must work while the phone is locked

### 2. Android Foundation
- Generate device identity and store secrets safely
- Scan LAN for laptop services
- Show discovered devices and connect flow
- Send and receive test packets after pairing
- Keep background behavior lightweight and measurable

### 3. Laptop Foundation
- Advertise service on LAN
- Accept pairing requests only with user approval
- Store trusted phone identity
- Show connection state, trust state, and packet logs
- Avoid desktop implementation choices that tie the app to a single Linux distro or desktop environment

### 4. Reliability and Diagnostics
- Retry strategy for discovery and reconnect
- Human-readable error states for auth failure and session timeout
- Structured logs for packet flow and handshake steps

## Milestones

### Milestone 1: Protocol Draft and Threat Model
- Define packet types, pairing sequence, and trust persistence
- Identify threat coverage: spoofing, replay, untrusted device on same LAN, stale session reuse
- Define how trusted commands will be handled when the Android device is locked in later phases

### Milestone 2: Discovery and Device Listing
- Phone discovers laptop on LAN
- Laptop advertises service with device name and capability metadata
- Desktop discovery flow works on a Linux-first baseline without distro-specific networking assumptions

### Milestone 3: Pairing and Trust Persistence
- One-time code flow works end to end
- Trusted devices can reconnect without repeating full pairing
- Reconnect behavior supports later lock-screen-safe operations without re-pairing

### Milestone 4: Encrypted Test Transport
- Simple commands such as `ping`, `device_info`, and `capabilities` work reliably
- Session survives normal Wi-Fi interruption and reconnect
- Transport remains fully functional without requiring Bluetooth

## Deliverables
- Android prototype with device discovery and connect screen
- Linux desktop prototype with pairing acceptance and connection status
- Transport protocol note or markdown spec
- Working encrypted data exchange demo
- Trust store implementation on both sides
- Lock-state behavior note for message and call features in later phases

## Risks and Mitigations
- LAN discovery inconsistency across networks
  - Mitigation: keep direct IP fallback and manual connect option
- Weak pairing flow could allow accidental pairing
  - Mitigation: require visible device name plus short code confirmation on both sides
- Session bugs may create hard-to-debug failures
  - Mitigation: log every handshake stage and define explicit error codes
- Linux packaging or runtime differences may fragment behavior across distros
  - Mitigation: keep the desktop baseline Linux-first, avoid narrow desktop-environment dependencies, and validate on more than one distro family early
- Lightweight Android operation may conflict with persistent connectivity expectations
  - Mitigation: measure battery and wake behavior from the start and keep background components minimal
- Bluetooth may later be required for some telephony controls
  - Mitigation: keep capability negotiation in the protocol from the start, but do not make Bluetooth part of the default data path

## Exit Criteria
- Devices discover each other on the same LAN
- Pairing requires explicit user action and succeeds securely
- Trust is persisted and reconnect works
- Simple encrypted packets are exchanged bidirectionally
- Core transport works entirely over LAN without Bluetooth
- Desktop baseline is validated as Linux-friendly
- Failure states are visible and recoverable without reinstalling the apps

## Phase 1 Decision Gate for Next Phase
Before Phase 2 starts, confirm:
- Whether notification, SMS reply, and file transfer can remain LAN-only
- Whether message read and reply features can be executed while the phone is locked using Android-supported mechanisms
- Whether any telephony feature truly requires Bluetooth pairing or a separate Android integration path
- Which Linux packaging targets to support first without changing the shared desktop codebase
