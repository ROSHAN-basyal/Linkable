# Protocol Specification

Linkable uses Protocol Buffers over a mutually authenticated, encrypted TCP
session. The schema files under `protocol/schemas` are the source of truth.

## Discovery

The desktop advertises `_linkable._tcp.local.` through mDNS with:

- `device_name`
- `device_id`
- `protocol_version`
- service port

Discovery metadata is untrusted. It identifies a connection candidate but
never authorizes one. Direct `host:port` connection is supported as a fallback
and follows the same pairing and authentication flow.

## Framing

Unencrypted handshake packets use:

```text
[4-byte big-endian envelope length][protobuf Envelope]
```

An `Envelope` contains the protocol version, packet type, sequence number, and
serialized packet payload. Receivers reject invalid lengths, unknown required
packet types, and incompatible major protocol versions.

After session establishment, each frame contains:

```text
[4-byte big-endian encrypted-frame length][8-byte counter][AES-GCM ciphertext]
```

The counter is part of the nonce construction. Duplicate counters are rejected
to prevent replay within a session.

## Identity And Pairing

Each device owns a persistent P-256 ECDSA identity key. Its device ID is a
fingerprint of the public key.

Pairing proceeds as follows:

1. The phone sends `PairingRequest` with its descriptor and a fresh nonce.
2. The desktop returns `PairingChallenge` with its descriptor and a fresh
   nonce.
3. Both peers derive the same six-digit code using HKDF-SHA-256 over the nonces
   and identity public keys.
4. The phone displays the code; the user enters it on the desktop.
5. Both peers sign the pairing transcript and exchange `PairingConfirm`.
6. The desktop sends `PairingComplete` only after code and signature
   verification succeeds.
7. Both peers pin the other identity key for trusted reconnect.

The pairing code is never transmitted. Pairing requests are time-limited and
rate-limited.

## Trusted Sessions

A trusted reconnect exchanges `SessionInit` and `SessionAck`. Each peer signs
its ephemeral P-256 ECDH key and session timestamp with its pinned identity.
Fresh timestamps limit replay of handshake messages.

The ECDH secret is expanded with HKDF-SHA-256 into independent client-to-server
and server-to-client 256-bit keys. Application envelopes are protected with
AES-256-GCM. Heartbeats provide liveness; a closed or failed session discards
its ephemeral keys and counters.

## Packet Families

The complete numeric registry is the `PacketType` enum in
`protocol/schemas/common.proto`. Packet families cover:

- pairing and trusted sessions
- liveness, device information, and capabilities
- notifications, replies, and notification actions
- file transfer and lazy phone-storage browsing
- ringing, SIM calls, app-call actions, contacts, and dialing
- Bluetooth status and desktop input control
- shared applications
- camera capability, lifecycle, heartbeat, and frame transport
- mobile clipboard updates
- structured protocol errors

Adding a packet requires updating `common.proto`, adding its payload schema,
regenerating desktop modules, and implementing both sender and receiver.

## Operational Defaults

- service type: `_linkable._tcp.local.`
- service port: `37891`, configurable
- protocol version: `1.0.0`
- pairing code: 6 digits
- pairing window: 120 seconds
- heartbeat interval: 15 seconds
- maximum frame size: 1 MiB

Safe Wi-Fi policy is an additional user-controlled boundary. Cryptographic peer
authentication remains mandatory whether that policy is enabled or disabled.
