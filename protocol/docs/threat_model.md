# Threat Model

Linkable assumes the local network can contain malicious devices. Discovery,
device names, IP addresses, and Bluetooth names are never treated as proof of
identity.

## Protected Assets

- persistent device identity keys
- pinned trusted-peer records and per-device settings
- pairing and session transcripts
- notification, call, clipboard, file, input, and camera data
- session keys and packet counters

## Main Threats And Controls

### Spoofing

An attacker can advertise a similar mDNS service or reuse a device name.
Linkable derives the device ID from a persistent public key, confirms initial
pairing with a locally derived code, pins the peer key, and requires signed
trusted-session handshakes.

### Tampering And Replay

Pairing confirmations and session handshakes are signed. Application traffic is
protected by AES-256-GCM with directional keys and per-session counters.
Duplicate counters, stale handshakes, malformed frames, and oversized payloads
are rejected.

### Information Disclosure

Application payloads are sent only inside the encrypted session. Identity and
trust files use private filesystem permissions on Linux; Android private keys
use Android Keystore. Android backup excludes Linkable trust and configuration.
Logs must not contain private keys, session keys, full pairing codes, or
unnecessary sensitive payloads.

### Denial Of Service

Unauthenticated clients can still reach the listening TCP port. Connection
counts, frame sizes, pairing windows, retries, and handshake timeouts are
bounded. The firewall should expose Linkable only on a trusted LAN zone.

### Privilege Abuse

Trust does not override platform permissions. Commands are accepted only from
an authenticated session and remain subject to Android permissions, per-device
settings, lock-state restrictions, and source-app capabilities. Notification
actions execute only Android-provided `PendingIntent` or `RemoteInput` actions.

## Residual Risks

- A user can approve the wrong peer during pairing.
- A stable mDNS device ID can enable LAN-local correlation.
- Compromise of either endpoint can expose data available to that endpoint.
- OEM Android policies and third-party notification actions can behave
  inconsistently.
- LAN-local resource exhaustion cannot be eliminated completely.

Safe Wi-Fi reduces accidental exposure on unknown networks but does not replace
cryptographic authentication.
