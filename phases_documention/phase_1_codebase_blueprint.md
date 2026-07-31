# Phase 1 — Codebase Blueprint
## Secure Discovery, Pairing, and Encrypted LAN-First Transport

> **Scope**: One Android phone + one Linux laptop discover each other on the same LAN, pair securely, persist trust, and exchange signed/encrypted messages — all without Bluetooth.

---

## 1. Top-Level Folder Architecture

```
PC-mobile/
├── phases_documention/          # Existing roadmap docs (read-only reference)
│
├── protocol/                    # Shared protocol definitions (language-agnostic)
│   ├── schemas/                 # Packet schemas (Protobuf .proto files)
│   │   ├── common.proto         # Shared types: DeviceId, Timestamp, Version
│   │   ├── pairing.proto        # PairingRequest, PairingChallenge, PairingConfirm
│   │   ├── session.proto        # SessionInit, SessionAck, SessionRotate
│   │   ├── transport.proto      # Ping, Pong, DeviceInfo, Capabilities, Heartbeat
│   │   └── errors.proto         # ErrorCode, ErrorPayload
│   ├── docs/
│   │   ├── protocol_spec.md     # Full protocol specification
│   │   ├── threat_model.md      # Threat model & security analysis
│   │   ├── packet_flow.md       # Sequence diagrams for every flow
│   │   └── lock_screen_policy.md# Lock-state behavior spec for future phases
│   └── README.md
│
├── desktop/                     # Linux desktop application
│   ├── src/
│   │   ├── main.py              # Entry point, arg parsing, app bootstrap
│   │   ├── config.py            # Configuration loading & defaults
│   │   ├── discovery/
│   │   │   ├── __init__.py
│   │   │   ├── mdns_advertiser.py   # Zeroconf service advertisement
│   │   │   ├── mdns_browser.py      # (Optional) browse for other services
│   │   │   └── fallback.py          # Manual IP / direct-connect fallback
│   │   ├── pairing/
│   │   │   ├── __init__.py
│   │   │   ├── pairing_manager.py   # Orchestrates the full pairing flow
│   │   │   ├── code_generator.py    # Short-code generation & validation
│   │   │   └── ui_prompts.py        # Terminal / GUI prompts for approval
│   │   ├── crypto/
│   │   │   ├── __init__.py
│   │   │   ├── identity.py          # Ed25519 keypair generation & loading
│   │   │   ├── key_exchange.py      # X25519 ECDH session key derivation
│   │   │   ├── aead.py              # ChaCha20-Poly1305 encrypt/decrypt
│   │   │   ├── secure_storage.py    # OS-backed or encrypted-file keystore
│   │   │   └── replay_guard.py      # Nonce tracking & replay prevention
│   │   ├── transport/
│   │   │   ├── __init__.py
│   │   │   ├── tcp_server.py        # Async TCP listener (accepts connections)
│   │   │   ├── ws_server.py         # (Alt) WebSocket server variant
│   │   │   ├── framing.py           # Length-prefixed binary framing
│   │   │   ├── session_manager.py   # Session lifecycle, rotation, reconnect
│   │   │   └── packet_handler.py    # Dispatch inbound packets to handlers
│   │   ├── trust/
│   │   │   ├── __init__.py
│   │   │   ├── trust_store.py       # Persistent trusted device registry
│   │   │   └── device_record.py     # DeviceRecord model
│   │   ├── diagnostics/
│   │   │   ├── __init__.py
│   │   │   ├── logger.py            # Structured logging (JSON lines)
│   │   │   └── packet_log.py        # Packet-level capture log
│   │   └── ui/
│   │       ├── __init__.py
│   │       ├── tray_icon.py         # System tray integration (optional)
│   │       ├── status_window.py     # Connection & trust state display
│   │       └── cli.py               # CLI-only mode fallback
│   ├── tests/
│   │   ├── test_discovery.py
│   │   ├── test_pairing.py
│   │   ├── test_crypto.py
│   │   ├── test_transport.py
│   │   ├── test_trust_store.py
│   │   └── conftest.py              # Shared fixtures
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── README.md
│
├── android/                     # Android application
│   ├── app/
│   │   ├── src/main/
│   │   │   ├── AndroidManifest.xml
│   │   │   ├── java/com/linkable/
│   │   │   │   ├── LinkableApp.kt              # Application class
│   │   │   │   ├── MainActivity.kt              # Main entry activity
│   │   │   │   ├── discovery/
│   │   │   │   │   ├── NsdDiscoveryManager.kt   # Android NSD service discovery
│   │   │   │   │   ├── DiscoveredDevice.kt      # Device data model
│   │   │   │   │   └── DirectConnectHelper.kt   # Manual IP connect fallback
│   │   │   │   ├── pairing/
│   │   │   │   │   ├── PairingManager.kt        # Full pairing flow orchestrator
│   │   │   │   │   ├── PairingCodeUI.kt         # Short-code display fragment
│   │   │   │   │   └── PairingViewModel.kt      # Lifecycle-aware pairing state
│   │   │   │   ├── crypto/
│   │   │   │   │   ├── DeviceIdentity.kt        # Ed25519 keypair via AndroidKeyStore
│   │   │   │   │   ├── KeyExchange.kt           # X25519 ECDH session derivation
│   │   │   │   │   ├── AeadCipher.kt            # ChaCha20-Poly1305 wrapper
│   │   │   │   │   └── ReplayGuard.kt           # Nonce / counter replay protection
│   │   │   │   ├── transport/
│   │   │   │   │   ├── TcpClient.kt             # Async TCP client connection
│   │   │   │   │   ├── Framing.kt               # Length-prefixed binary framing
│   │   │   │   │   ├── SessionManager.kt        # Session lifecycle & reconnect
│   │   │   │   │   └── PacketDispatcher.kt      # Route packets to handlers
│   │   │   │   ├── trust/
│   │   │   │   │   ├── TrustStore.kt            # Encrypted SharedPrefs / Room DB
│   │   │   │   │   └── TrustedDevice.kt         # Device record entity
│   │   │   │   ├── service/
│   │   │   │   │   ├── ConnectionService.kt     # Foreground service for LAN session
│   │   │   │   │   └── BatteryOptimizer.kt      # Wake & battery measurement helpers
│   │   │   │   ├── diagnostics/
│   │   │   │   │   ├── AppLogger.kt             # Structured logging
│   │   │   │   │   └── DiagnosticsExporter.kt   # Export debug bundle
│   │   │   │   └── ui/
│   │   │   │       ├── screens/
│   │   │   │       │   ├── DiscoveryScreen.kt   # Discovered devices list
│   │   │   │       │   ├── PairingScreen.kt     # Code display & confirmation
│   │   │   │       │   └── StatusScreen.kt      # Connection / trust dashboard
│   │   │   │       └── theme/
│   │   │   │           └── Theme.kt             # Material3 theme definitions
│   │   │   └── res/
│   │   │       ├── layout/
│   │   │       ├── values/
│   │   │       └── drawable/
│   │   └── src/test/
│   │       ├── CryptoTest.kt
│   │       ├── PairingTest.kt
│   │       ├── TransportTest.kt
│   │       └── TrustStoreTest.kt
│   ├── build.gradle.kts
│   ├── gradle.properties
│   └── README.md
│
├── shared/                      # Cross-platform shared logic (optional)
│   ├── packet_types.md          # Human-readable packet catalog
│   └── test_vectors/            # Known-answer crypto test vectors
│       ├── ecdh_vectors.json
│       └── aead_vectors.json
│
├── scripts/                     # Development & CI helpers
│   ├── generate_proto.sh        # Compile .proto → Python + Kotlin stubs
│   ├── run_desktop.sh           # Launch desktop app in dev mode
│   ├── run_tests.sh             # Cross-project test runner
│   └── lint.sh                  # Linting / formatting
│
├── .gitignore
├── LICENSE
└── README.md                    # Project overview and quick-start
```

---

## 2. Technology Stack

### 2.1 Shared / Protocol Layer

| Concern | Technology | Rationale |
|---|---|---|
| Packet serialization | **Protocol Buffers 3** | Language-neutral, compact binary wire format, versioned schemas |
| Schema language | `.proto` files | Single source of truth compiled to Python + Kotlin |
| Crypto primitives | **X25519** (ECDH), **Ed25519** (signing), **ChaCha20-Poly1305** (AEAD) | Modern, fast, constant-time — available on both platforms |
| Nonce / replay | Monotonic 64-bit counter per session direction | Simple, deterministic, no clock dependency |

### 2.2 Linux Desktop

| Concern | Technology | Rationale |
|---|---|---|
| Language | **Python 3.10+** | Rapid iteration, rich ecosystem, cross-distro availability |
| Async runtime | **asyncio** | Native to Python, no extra dependency for TCP/WS |
| mDNS / Zeroconf | **zeroconf** (PyPI) | Pure-Python, no Avahi daemon dependency |
| Cryptography | **PyNaCl** (libsodium binding) | Audited, high-level API for X25519 / Ed25519 / AEAD |
| Protobuf codegen | **grpcio-tools** or **protoc** | Generates Python dataclasses from `.proto` |
| Secure storage | **keyring** (PyPI) + encrypted JSON fallback | Uses Secret Service / KWallet when available |
| GUI (optional) | **PyQt6** or **GTK4** via **PyGObject** | Tray icon + status window; CLI fallback for headless |
| Logging | **structlog** | JSON-structured logs, filterable diagnostics |
| Testing | **pytest** + **pytest-asyncio** | Async test support, fixtures, clear output |
| Packaging | **PyInstaller** → AppImage / Flatpak / native pkg | Single-binary or distro package; no user-facing pip |

### 2.3 Android

| Concern | Technology | Rationale |
|---|---|---|
| Language | **Kotlin** | First-class Android language, null safety, coroutines |
| Min SDK | **API 26** (Android 8.0) | Covers 95%+ devices; needed for foreground service channels |
| Build system | **Gradle (Kotlin DSL)** | Standard Android build toolchain |
| Async | **Kotlin Coroutines + Flow** | Structured concurrency, lifecycle-aware streams |
| NSD discovery | **android.net.nsd.NsdManager** | Built-in API, no third-party dependency |
| Cryptography | **AndroidKeyStore** + **Tink** or raw JCA | Hardware-backed key generation + AEAD primitives |
| Protobuf codegen | **protobuf-kotlin-lite** | Lightweight Protobuf runtime for Android |
| Networking | **Ktor Client** (CIO engine) or raw **NIO SocketChannel** | Lightweight async TCP without OkHttp overhead |
| UI framework | **Jetpack Compose + Material 3** | Modern declarative UI, theming |
| Local persistence | **EncryptedSharedPreferences** or **Room + SQLCipher** | Encrypted trust store |
| Testing | **JUnit 5** + **MockK** + **Turbine** (Flow testing) | Standard Android test stack |
| Battery profiling | **Battery Historian** + custom wake counters | Measure background cost from day one |

---

## 3. Program Architecture

### 3.1 Architecture Pattern

Both platforms follow **Clean Architecture** with three layers:

```
┌──────────────────────────────────────────────────┐
│                   Presentation                   │
│   (UI screens, CLI, tray icon, view models)      │
├──────────────────────────────────────────────────┤
│                    Domain                        │
│   (Use-cases: Discover, Pair, SendPacket, ...)   │
│   (Interfaces: ICryptoProvider, ITrustStore, ...) │
├──────────────────────────────────────────────────┤
│                 Infrastructure                   │
│   (TCP/WS transport, mDNS/NSD, file keystore,   │
│    AndroidKeyStore, Protobuf codec, logging)     │
└──────────────────────────────────────────────────┘
```

- **Domain** defines interfaces; **Infrastructure** implements them.
- **Presentation** consumes domain use-cases and never touches raw sockets or crypto directly.

### 3.2 Key Data Flow

```
Android                                         Linux Desktop
──────                                         ─────────────
NsdDiscoveryManager                            ZeroconfAdvertiser
      │  discovers service                           │  publishes _linkable._tcp
      ▼                                              │
PairingManager ── TCP connect ──────────────► TcpServer (accepts)
      │                                              │
      │  ── PairingRequest (device name, pubkey) ──► │
      │  ◄── PairingChallenge (short code) ───────── │
      │                                              │
  User confirms code on phone              User confirms code on laptop
      │                                              │
      │  ── PairingConfirm (signed proof) ────────► │
      │  ◄── PairingConfirm (signed proof) ──────── │
      │                                              │
  TrustStore.save(device)                 TrustStore.save(device)
      │                                              │
      │  ── SessionInit (ephemeral X25519 pub) ───► │
      │  ◄── SessionAck  (ephemeral X25519 pub) ─── │
      │                                              │
  Derive shared AEAD key                   Derive shared AEAD key
      │                                              │
      │  ◄═══ Encrypted AEAD channel ═══════════►   │
      │       Ping, DeviceInfo, Capabilities,       │
      │       Heartbeat, Error                      │
```

---

## 4. Milestone Blueprints

---

### Milestone 1 — Protocol Draft & Threat Model

#### Goal
Produce the complete protocol specification, Protobuf schemas, and threat model document **before** any networking code is written.

#### Deliverables

| Artifact | Location | Purpose |
|---|---|---|
| `common.proto` | `protocol/schemas/` | Shared types: `DeviceId`, `Timestamp`, `ProtocolVersion` |
| `pairing.proto` | `protocol/schemas/` | `PairingRequest`, `PairingChallenge`, `PairingConfirm`, `PairingReject` |
| `session.proto` | `protocol/schemas/` | `SessionInit`, `SessionAck`, `SessionRotate`, `SessionClose` |
| `transport.proto` | `protocol/schemas/` | `Ping`, `Pong`, `DeviceInfo`, `Capabilities`, `Heartbeat` |
| `errors.proto` | `protocol/schemas/` | `ErrorCode` enum, `ErrorPayload` message |
| `protocol_spec.md` | `protocol/docs/` | Full protocol specification with state machines |
| `threat_model.md` | `protocol/docs/` | Threat coverage analysis |
| `packet_flow.md` | `protocol/docs/` | Sequence diagrams for every flow |
| `lock_screen_policy.md`| `protocol/docs/` | Lock-state behavior spec for future phases |
| `generate_proto.sh` | `scripts/` | Automates `.proto` → Python + Kotlin stub generation |

#### Tech Stack in Action

| Activity | Tool / Library |
|---|---|
| Write `.proto` schemas | Protobuf 3 language |
| Compile to Python | `protoc` + `grpcio-tools` |
| Compile to Kotlin | `protoc` + `protobuf-kotlin-lite` plugin |
| Diagram sequence flows | Mermaid in Markdown |
| Threat model framework | STRIDE methodology |

#### Methodology

1. **Define packet taxonomy** — enumerate every packet type Phase 1 needs. Assign each a uint32 type ID in `common.proto`.
2. **Write Protobuf schemas** — one `.proto` per concern. Use `oneof` for polymorphic payloads inside a top-level `Envelope` message.
3. **Define the Envelope framing** — every wire message is:
   ```
   [4 bytes: payload length][N bytes: Envelope protobuf]
   ```
4. **Write protocol state machine** — for pairing and session establishment, draw explicit state diagrams with allowed transitions and timeout rules.
5. **Conduct STRIDE threat analysis** on the pairing + transport flow:
   - **Spoofing** → mitigated by Ed25519 device identity
   - **Tampering** → mitigated by AEAD integrity
   - **Repudiation** → structured packet logs
   - **Information Disclosure** → ChaCha20-Poly1305 encryption
   - **Denial of Service** → rate limiting, connection caps
   - **Elevation of Privilege** → capability-based command set
6. **Define lock-screen policy** — document which future commands (notification reply, call accept) must work while the phone is locked, and which Android mechanisms enable that.
7. **Generate stubs** — run `generate_proto.sh` to produce Python and Kotlin code; commit generated files or add them to `.gitignore` (project preference).

#### Exit Criteria
- [ ] All `.proto` schemas compile cleanly for both platforms
- [ ] `protocol_spec.md` covers every packet type, state transition, and timeout
- [ ] `threat_model.md` addresses all six STRIDE categories
- [ ] `lock_screen_policy.md` is written and reviewed
- [ ] Stub code generates without errors on both platforms

---

### Milestone 2 — Discovery & Device Listing

#### Goal
Phone discovers laptop on LAN; laptop advertises itself. Both sides show discovered devices in their UI.

#### Deliverables

| Artifact | Location | Purpose |
|---|---|---|
| `mdns_advertiser.py` | `desktop/src/discovery/` | Publishes `_linkable._tcp.local.` service via Zeroconf |
| `mdns_browser.py` | `desktop/src/discovery/` | (Optional) browse for other desktop instances |
| `fallback.py` | `desktop/src/discovery/` | Manual IP direct-connect |
| `NsdDiscoveryManager.kt` | `android/.../discovery/` | Uses `NsdManager` to find `_linkable._tcp` |
| `DiscoveredDevice.kt` | `android/.../discovery/` | Data class for discovered device info |
| `DirectConnectHelper.kt` | `android/.../discovery/` | Manual IP entry fallback |
| `DiscoveryScreen.kt` | `android/.../ui/screens/` | Jetpack Compose list of discovered devices |
| `cli.py` or `status_window.py` | `desktop/src/ui/` | Show discovered devices on desktop |

#### Tech Stack in Action

| Activity | Tool / Library |
|---|---|
| Service advertisement (desktop) | `zeroconf` PyPI package, asyncio integration |
| Service discovery (Android) | `android.net.nsd.NsdManager` (built-in API) |
| Service type | `_linkable._tcp.local.` with TXT records for device name, version |
| UI (Android) | Jetpack Compose `LazyColumn` + Material 3 |
| UI (Desktop) | CLI table or PyQt6 list widget |
| Fallback | Raw TCP socket connect to user-entered `IP:port` |

#### Methodology

1. **Desktop — Advertise service**
   - On startup, `mdns_advertiser.py` registers a Zeroconf `ServiceInfo` on port `TCP/7734` (configurable).
   - TXT record carries: `device_name`, `protocol_version`, `device_id` (public key fingerprint).
   - Service type: `_linkable._tcp.local.`
   - Handles network interface changes (Wi-Fi reconnect) by re-registering.

2. **Android — Discover service**
   - `NsdDiscoveryManager` calls `NsdManager.discoverServices("_linkable._tcp", ...)`.
   - On each `onServiceFound`, resolve hostname + port + TXT records.
   - Emit `Flow<List<DiscoveredDevice>>` to the UI layer.
   - On `onServiceLost`, remove from the list.

3. **Fallback — Direct connect**
   - Both platforms offer a "Connect by IP" option.
   - User enters `ip:port`; the app attempts a raw TCP connection, reads a protocol handshake banner, and promotes it to a discovered device.

4. **UI rendering**
   - Android: `DiscoveryScreen` shows a `LazyColumn` with device name, IP, and a "Connect" button.
   - Desktop: `cli.py` prints a numbered list; `status_window.py` shows a live-updating list widget.

5. **Testing**
   - Unit: mock `NsdManager` / Zeroconf callbacks; verify device list updates correctly.
   - Integration: run desktop advertiser and Android emulator on the same LAN segment; confirm discovery within 5 seconds.
   - Edge case: test behavior when Wi-Fi drops mid-discovery and when multiple desktops advertise simultaneously.

#### Exit Criteria
- [ ] Desktop advertises on LAN; Android discovers it within seconds
- [ ] Device name, IP, port, and version display correctly on both sides
- [ ] Direct-connect fallback works when mDNS fails
- [ ] Discovery works on at least two Linux distro families (e.g., Ubuntu + Fedora)
- [ ] Battery impact of continuous NSD scanning is measured and acceptable

---

### Milestone 3 — Pairing & Trust Persistence

#### Goal
Implement the full one-time pairing flow, persist trust on both devices, and allow trusted devices to reconnect without re-pairing.

#### Deliverables

| Artifact | Location | Purpose |
|---|---|---|
| `identity.py` | `desktop/src/crypto/` | Generate & load Ed25519 keypair |
| `key_exchange.py` | `desktop/src/crypto/` | X25519 ECDH derivation |
| `secure_storage.py` | `desktop/src/crypto/` | Store identity key securely |
| `pairing_manager.py` | `desktop/src/pairing/` | Orchestrate pairing state machine |
| `code_generator.py` | `desktop/src/pairing/` | 6-digit code generation & validation |
| `trust_store.py` | `desktop/src/trust/` | Persist trusted device records |
| `DeviceIdentity.kt` | `android/.../crypto/` | Ed25519 via AndroidKeyStore |
| `KeyExchange.kt` | `android/.../crypto/` | X25519 ECDH |
| `PairingManager.kt` | `android/.../pairing/` | Pairing orchestrator |
| `TrustStore.kt` | `android/.../trust/` | EncryptedSharedPrefs / Room DB |
| `PairingScreen.kt` | `android/.../ui/screens/` | Code display & confirmation UI |

#### Tech Stack in Action

| Activity | Tool / Library |
|---|---|
| Ed25519 key generation (desktop) | `PyNaCl` → `nacl.signing.SigningKey` |
| Ed25519 key generation (Android) | `AndroidKeyStore` or `libsodium` via JNI |
| X25519 ECDH (desktop) | `PyNaCl` → `nacl.public.PrivateKey` |
| X25519 ECDH (Android) | `Tink` or JCA `XDHKeyAgreement` (API 31+), fallback to `libsodium` |
| Short-code | Cryptographically random 6-digit numeric code derived from shared nonce |
| Trust storage (desktop) | `keyring` library + `json` file with per-device record |
| Trust storage (Android) | `EncryptedSharedPreferences` or `Room` + `SQLCipher` |

#### Methodology

1. **Identity generation (first launch)**
   - Desktop: generate Ed25519 keypair → store private key in OS keyring (Secret Service / KWallet) or encrypted JSON at `~/.config/linkable/identity.key`.
   - Android: generate Ed25519 keypair in AndroidKeyStore (hardware-backed where available).
   - Both derive a `device_id` = SHA-256 fingerprint of the public key (first 8 bytes, base32-encoded).

2. **Pairing flow — step by step**
   ```
   State: IDLE → INITIATED → CODE_DISPLAYED → CONFIRMED → TRUSTED
   ```
   | Step | Android (Initiator) | Desktop (Acceptor) |
   |---|---|---|
   | 1 | User taps "Connect" on discovered device | — |
   | 2 | Send `PairingRequest{device_name, ed25519_pub}` over TCP | Receive request |
   | 3 | — | Show prompt: "Phone X wants to pair. Allow?" |
   | 4 | — | User clicks "Allow" → generate 6-digit code from `HKDF(android_pub ‖ desktop_pub ‖ random)` |
   | 5 | — | Send `PairingChallenge{code_hash, desktop_ed25519_pub}` |
   | 6 | Display code on screen. User reads code, types into desktop prompt | — |
   | 7 | — | User enters code on desktop; desktop verifies `code == expected` |
   | 8 | Both sign `"PAIR_CONFIRM" ‖ android_pub ‖ desktop_pub ‖ code` with their Ed25519 key | — |
   | 9 | Exchange `PairingConfirm{signature}` | Verify signature with peer's public key |
   | 10 | Save `TrustedDevice{name, ed25519_pub, device_id, paired_at}` to TrustStore | Same |

3. **Reconnect after pairing**
   - On reconnect, the initiator sends `SessionInit{device_id, ephemeral_x25519_pub, signature}`.
   - The acceptor looks up `device_id` in TrustStore, verifies the Ed25519 signature, and responds with `SessionAck`.
   - No short-code is needed again.

4. **Trust revocation**
   - Either side can remove a device from TrustStore.
   - "Forget device" action in UI → deletes record → next connection from that device triggers full re-pairing.

5. **Testing**
   - Unit: test code generation determinism, signature verification, trust store CRUD.
   - Integration: full pairing flow between emulator and desktop on localhost loopback.
   - Security: attempt pairing with wrong code → verify rejection. Attempt reconnect with unknown device_id → verify rejection.

#### Exit Criteria
- [ ] Pairing flow works end to end with user confirmation on both sides
- [ ] Trusted devices reconnect without re-pairing
- [ ] Wrong code is rejected; unknown device is rejected
- [ ] Trust persists across app restarts on both platforms
- [ ] Identity keys survive app updates (AndroidKeyStore / OS keyring)

---

### Milestone 4 — Encrypted Test Transport

#### Goal
Establish an AEAD-encrypted session and exchange operational test packets (`ping`, `device_info`, `capabilities`, `heartbeat`) reliably, including reconnect after Wi-Fi interruption.

#### Deliverables

| Artifact | Location | Purpose |
|---|---|---|
| `aead.py` | `desktop/src/crypto/` | ChaCha20-Poly1305 encrypt/decrypt |
| `replay_guard.py` | `desktop/src/crypto/` | Monotonic nonce tracking |
| `tcp_server.py` | `desktop/src/transport/` | Async TCP listener |
| `framing.py` | `desktop/src/transport/` | Length-prefixed binary framing |
| `session_manager.py` | `desktop/src/transport/` | Session lifecycle, rotation, reconnect |
| `packet_handler.py` | `desktop/src/transport/` | Dispatch inbound packets to handlers |
| `AeadCipher.kt` | `android/.../crypto/` | ChaCha20-Poly1305 wrapper |
| `ReplayGuard.kt` | `android/.../crypto/` | Nonce tracking |
| `TcpClient.kt` | `android/.../transport/` | Async TCP client |
| `Framing.kt` | `android/.../transport/` | Binary framing |
| `SessionManager.kt` | `android/.../transport/` | Session lifecycle |
| `PacketDispatcher.kt` | `android/.../transport/` | Packet routing |
| `ConnectionService.kt` | `android/.../service/` | Foreground service for LAN session |
| `logger.py` | `desktop/src/diagnostics/` | Structured logging |
| `packet_log.py` | `desktop/src/diagnostics/` | Packet capture log |

#### Tech Stack in Action

| Activity | Tool / Library |
|---|---|
| AEAD encryption (desktop) | `PyNaCl` → `nacl.secret.SecretBox` or `nacl.aead` |
| AEAD encryption (Android) | `Tink` AEAD primitive or `javax.crypto.Cipher` with ChaCha20-Poly1305 |
| TCP server (desktop) | `asyncio.start_server` |
| TCP client (Android) | `kotlinx.coroutines` + `java.nio.channels.SocketChannel` or Ktor CIO |
| Framing | Custom: `[4-byte big-endian length][protobuf Envelope]` |
| Session key derivation | `HKDF-SHA256(X25519_shared_secret, info="linkable-session-v1")` → 32-byte key |
| Heartbeat | Bidirectional, every 15 seconds; 3 missed → session timeout |
| Structured logging | `structlog` (desktop), `Timber` (Android) |

#### Methodology

1. **Session key establishment**
   - After `SessionInit` / `SessionAck` exchange, both sides have the peer's ephemeral X25519 public key.
   - Compute `shared_secret = X25519(my_ephemeral_priv, peer_ephemeral_pub)`.
   - Derive two keys via HKDF:
     - `client_to_server_key = HKDF(shared_secret, info="c2s")`
     - `server_to_client_key = HKDF(shared_secret, info="s2c")`
   - Each direction has its own nonce counter starting at 0.

2. **Encrypted framing**
   ```
   Wire format per message:
   ┌────────────────────┬──────────────────────────────────┐
   │ 4 bytes: length    │ AEAD(nonce, plaintext_envelope)  │
   └────────────────────┴──────────────────────────────────┘
   
   plaintext_envelope = Envelope protobuf {
     uint32 type_id
     uint64 sequence_number
     bytes  payload  (inner protobuf per type)
   }
   ```

3. **Packet handlers**
   - `Ping` → respond with `Pong` (latency measurement).
   - `DeviceInfo` → respond with device name, OS version, battery level, screen state.
   - `Capabilities` → exchange feature flags (for future phase negotiation).
   - `Heartbeat` → reset the session timeout timer.
   - `Error` → log error code + message; take action if fatal.

4. **Session lifecycle**
   ```
   States: DISCONNECTED → CONNECTING → HANDSHAKING → ACTIVE → RECONNECTING → CLOSED
   ```
   - **ACTIVE**: packets flow normally; heartbeat timer runs.
   - **RECONNECTING**: TCP broke; retry with exponential backoff (1s, 2s, 4s, …, max 30s). Use the same session keys if within the rotation window; otherwise, perform a new `SessionInit`.
   - **Session rotation**: after N packets or T minutes (configurable), initiate `SessionRotate` to derive fresh keys without a full re-handshake.

5. **Android foreground service**
   - `ConnectionService` runs as a foreground service with a persistent notification ("Connected to Laptop X").
   - Uses `WakeLock` only during active packet exchange; releases during idle periods.
   - Battery cost is logged via custom wakeup counter and reviewed each milestone.

6. **Diagnostics**
   - Every handshake step, packet send/receive, and error is logged as a structured JSON line.
   - `packet_log.py` / `DiagnosticsExporter.kt` can dump the last N minutes of logs for debugging.

7. **Testing**
   - Unit: AEAD encrypt → decrypt round-trip; replay guard rejects duplicate nonces; framing correctly encodes/decodes.
   - Integration: full `ping` round-trip over encrypted session.
   - Chaos: kill TCP mid-session → verify reconnect within 10 seconds. Toggle Wi-Fi on phone → verify reconnect.
   - Cross-platform crypto: use shared test vectors from `shared/test_vectors/` to verify both implementations produce identical ciphertext.

#### Exit Criteria
- [ ] Encrypted `ping`/`pong` works bidirectionally
- [ ] `device_info` and `capabilities` exchange succeeds
- [ ] Heartbeat keeps sessions alive; 3 missed heartbeats trigger timeout
- [ ] Session survives Wi-Fi interruption and reconnects automatically
- [ ] Replay of captured packets is detected and rejected
- [ ] No Bluetooth dependency in the transport layer
- [ ] Battery impact of foreground service is measured and documented
- [ ] Logs provide full visibility into every handshake step and failure

---

## 5. Development Workflow & Methodology

### 5.1 Branching Strategy

```
main
 ├── develop
 │    ├── feature/protocol-schemas
 │    ├── feature/desktop-discovery
 │    ├── feature/android-discovery
 │    ├── feature/desktop-pairing
 │    ├── feature/android-pairing
 │    ├── feature/desktop-transport
 │    ├── feature/android-transport
 │    └── feature/diagnostics
 └── release/phase-1
```

- All feature branches merge into `develop` via PR with code review.
- `develop` → `release/phase-1` at each milestone completion.
- `release/phase-1` → `main` after Phase 1 exit criteria are met.

### 5.2 Event Sequence During Development

| Week | Event | Activities |
|---|---|---|
| **W1** | **Kickoff + M1 start** | Set up repo structure, write `.proto` schemas, produce `protocol_spec.md` and `threat_model.md`, run `generate_proto.sh` for both platforms |
| **W1-end** | **M1 gate** | Review protocol spec and threat model; approve or iterate |
| **W2** | **M2 start** | Desktop: implement `mdns_advertiser.py`. Android: implement `NsdDiscoveryManager.kt`. Build discovery UIs on both sides. Write unit tests |
| **W2-end** | **M2 gate** | Demo: Android discovers desktop on LAN; fallback works; measured on 2+ distros |
| **W3** | **M3 start** | Desktop: implement `identity.py`, `pairing_manager.py`, `trust_store.py`. Android: implement `DeviceIdentity.kt`, `PairingManager.kt`, `TrustStore.kt`. Build pairing UIs. Write unit + integration tests |
| **W3-end** | **M3 gate** | Demo: full pairing flow end to end; reconnect works; wrong-code rejected |
| **W4** | **M4 start** | Desktop: implement `aead.py`, `tcp_server.py`, `session_manager.py`. Android: implement `AeadCipher.kt`, `TcpClient.kt`, `SessionManager.kt`, `ConnectionService.kt`. Cross-platform crypto validation with test vectors |
| **W4-5** | **M4 hardening** | Chaos testing (Wi-Fi toggle, kill processes), reconnect validation, battery profiling, diagnostics review |
| **W5-end** | **Phase 1 gate** | All exit criteria met; decision gate questions answered for Phase 2 |

### 5.3 Testing Strategy Per Layer

| Layer | Test Type | Tools | Frequency |
|---|---|---|---|
| Proto schemas | Compilation check | `protoc` | Every schema change |
| Crypto | Unit + known-answer vectors | `pytest` / `JUnit` + `shared/test_vectors/` | Every crypto change |
| Discovery | Unit (mocked) + integration (real LAN) | `pytest` / Android instrumented tests | Per commit + nightly |
| Pairing | Unit (state machine) + integration (E2E) | `pytest` / `JUnit` + `MockK` | Per commit |
| Transport | Unit (framing, AEAD) + chaos (network disruption) | `pytest-asyncio` / `Turbine` | Per commit + weekly chaos |
| Battery | Profiling | `Battery Historian`, custom counters | Weekly |

### 5.4 CI Pipeline Events

```
On every push to develop:
  1. Lint (Python: ruff/black, Kotlin: ktlint)
  2. Compile protobufs
  3. Run desktop unit tests
  4. Run Android unit tests
  5. (Optional) Run integration tests on CI LAN emulation

On milestone tag:
  6. Build desktop binary (PyInstaller)
  7. Build Android APK (release variant)
  8. Run cross-platform crypto vector validation
  9. Generate test coverage report
```

### 5.5 Error Handling Methodology

Every module follows this pattern:

```python
# Desktop example
class PairingError(Exception):
    """Base class for pairing errors."""

class CodeMismatchError(PairingError):
    code = "PAIR_CODE_MISMATCH"

class DeviceNotTrustedError(PairingError):
    code = "PAIR_DEVICE_NOT_TRUSTED"

class PairingTimeoutError(PairingError):
    code = "PAIR_TIMEOUT"
```

```kotlin
// Android example
sealed class PairingResult {
    data class Success(val device: TrustedDevice) : PairingResult()
    data class CodeMismatch(val attemptsLeft: Int) : PairingResult()
    data class Timeout(val durationMs: Long) : PairingResult()
    data class Rejected(val reason: String) : PairingResult()
}
```

Error codes map to `errors.proto` → displayed as human-readable messages in UI → logged as structured diagnostics.

### 5.6 Configuration Management

```python
# desktop/src/config.py — defaults
DEFAULT_CONFIG = {
    "service_port": 7734,
    "service_type": "_linkable._tcp.local.",
    "heartbeat_interval_sec": 15,
    "heartbeat_miss_limit": 3,
    "session_rotation_minutes": 60,
    "session_rotation_packets": 100_000,
    "reconnect_backoff_max_sec": 30,
    "pairing_code_length": 6,
    "pairing_timeout_sec": 120,
    "log_level": "INFO",
}
```

Config is loaded from `~/.config/linkable/config.json` on desktop, and from `SharedPreferences` on Android. Missing keys fall back to defaults.

---

## 6. Security Event Lifecycle

```
1. FIRST LAUNCH
   └─▶ Generate Ed25519 identity keypair
   └─▶ Store in OS secure storage
   └─▶ Derive device_id from public key fingerprint

2. DISCOVERY
   └─▶ Advertise / browse with device_id in TXT record
   └─▶ No secrets are exchanged during discovery

3. PAIRING (one-time per device pair)
   └─▶ Exchange Ed25519 public keys
   └─▶ Generate + verify short code (human-in-the-loop confirmation)
   └─▶ Exchange signed proofs (mutual authentication)
   └─▶ Persist TrustedDevice record

4. SESSION ESTABLISHMENT (every connection)
   └─▶ Generate ephemeral X25519 keypair
   └─▶ Exchange ephemeral public keys (signed with Ed25519 identity)
   └─▶ Derive shared secret via ECDH
   └─▶ Derive directional AEAD keys via HKDF
   └─▶ Initialize nonce counters to 0

5. ENCRYPTED TRANSPORT
   └─▶ Every packet: AEAD encrypt with directional key + incrementing nonce
   └─▶ Receiver: verify AEAD tag, check nonce monotonicity, reject replays
   └─▶ Heartbeat every 15s; timeout after 3 misses

6. SESSION ROTATION
   └─▶ After N packets or T minutes: generate new ephemeral keys
   └─▶ Derive fresh AEAD keys; reset nonce counters
   └─▶ Old keys are securely zeroed

7. DISCONNECTION
   └─▶ Send SessionClose
   └─▶ Zero all session keys from memory
   └─▶ Trust record remains for future reconnect
```

---

## 7. Dependency Summary

### Desktop (`requirements.txt`)

```
zeroconf>=0.131.0        # mDNS advertisement & browsing
PyNaCl>=1.5.0            # X25519, Ed25519, ChaCha20-Poly1305
protobuf>=5.27.0         # Protobuf runtime
keyring>=25.2.0          # OS secret storage
structlog>=24.2.0        # Structured logging
PyQt6>=6.7.0             # GUI (optional; CLI works without it)
pytest>=8.2.0            # Testing
pytest-asyncio>=0.23.0   # Async test support
```

### Android (`build.gradle.kts` dependencies)

```kotlin
dependencies {
    // Core
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    
    // Protobuf
    implementation("com.google.protobuf:protobuf-kotlin-lite:4.27.0")
    
    // Crypto
    implementation("com.google.crypto.tink:tink-android:1.13.0")
    // OR: implementation("com.goterl:lazysodium-android:5.1.0")
    
    // Networking
    implementation("io.ktor:ktor-network:2.3.11")
    
    // UI
    implementation("androidx.compose.material3:material3:1.2.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.0")
    
    // Storage
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    
    // Logging
    implementation("com.jakewharton.timber:timber:5.0.1")
    
    // Testing
    testImplementation("junit:junit:5.10.2")
    testImplementation("io.mockk:mockk:1.13.11")
    testImplementation("app.cash.turbine:turbine:1.1.0")
}
```

---

## 8. Phase 1 Completion Checklist

- [ ] **M1**: Protocol schemas compile; spec + threat model reviewed
- [ ] **M2**: Discovery works on LAN; fallback works; tested on 2+ Linux distros
- [ ] **M3**: Pairing flow secure end to end; trust persists; reconnect works
- [ ] **M4**: Encrypted packets exchanged; reconnect survives Wi-Fi drop; battery profiled
- [ ] **Exit**: All exit criteria from `phase_no_1_roadmap.md` are satisfied
- [ ] **Gate**: Decision gate questions for Phase 2 are answered
