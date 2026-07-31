# Threat Model

This document applies STRIDE to the Milestone 1 protocol.

## Security Goals

- only explicitly trusted peers may reconnect after pairing
- on-LAN attackers must not be able to silently impersonate a trusted device
- packet tampering and replay must be detectable
- protocol failures must be diagnosable
- future privileged actions must be capability-gated and policy-driven

## Assets

- long-lived device identity keys
- trusted-device records
- pairing transcript integrity
- session ephemeral keys
- session AEAD keys
- packet sequence integrity
- diagnostic logs

## Trust Boundaries

- local device UI versus network input
- discovery metadata versus authenticated peer identity
- pre-pairing state versus trusted state
- session transport versus persisted trust store

## Assumptions

- the user confirms the intended peer during pairing
- secure local storage is available on both platforms
- LAN discovery is unauthenticated and therefore untrusted by default
- the network can be observed or manipulated by other devices on the same LAN

## STRIDE Analysis

### Spoofing

Threats:

- attacker advertises a fake service on the LAN
- attacker reuses a known device name
- attacker claims a trusted `device_id` without proving identity ownership

Mitigations:

- discovery never implies trust
- pairing stores the peer identity public key, not only the device name
- reconnect requires signature validation over the session-init transcript
- device identifiers are fingerprints of long-lived identity keys

Residual risk:

- users may still approve the wrong device if naming is misleading

Operational recommendation:

- always display device name and a shortened device fingerprint during pairing UI

### Tampering

Threats:

- network attacker modifies pairing or session packets
- attacker changes payload bytes in flight
- attacker changes discovery metadata before direct connect

Mitigations:

- pairing confirmation signs a shared transcript hash
- session establishment signs ephemeral key material
- later transport packets are protected by AEAD
- protocol version and packet type are explicit and validated

Residual risk:

- discovery metadata remains tamperable until authenticated pairing begins

### Repudiation

Threats:

- a peer denies sending a pairing confirmation
- a peer denies initiating a session rotation or close

Mitigations:

- pairing confirmations include transcript hashes and signatures
- session establishment includes signed ephemeral-key authorizations
- structured logs should record packet type, sequence number, peer id, and timestamp

Residual risk:

- local logs can be deleted or tampered with by a device owner

### Information Disclosure

Threats:

- LAN observer learns sensitive payload contents
- stable discovery identifiers leak pairing history
- diagnostic logs expose sensitive fields

Mitigations:

- later transport uses AEAD-protected sessions
- discovery publishes only non-secret metadata
- logs should avoid storing raw secrets, derived keys, or full sensitive payloads

Residual risk:

- `device_id` in discovery metadata is still a stable identifier and creates a privacy tradeoff

Decision:

- Milestone 1 keeps `device_id` advertisement because it simplifies troubleshooting and peer continuity, but this should remain revisitable in later hardening.

### Denial Of Service

Threats:

- attacker floods pairing requests
- attacker sends malformed frames or oversized payload lengths
- attacker opens repeated session attempts to consume resources

Mitigations:

- rate-limit pairing attempts per source address
- cap maximum frame size
- reject malformed envelopes before deeper parsing
- bound simultaneous unauthenticated connections
- enforce pairing and handshake timeouts

Residual risk:

- LAN-local resource exhaustion is still possible at the transport layer

### Elevation Of Privilege

Threats:

- unpaired device invokes future privileged commands
- paired device invokes commands not supported by the platform or policy
- future lock-screen operations bypass explicit user or policy rules

Mitigations:

- trust is established only after successful pairing confirmation
- capabilities are explicit protocol data, not assumptions
- lock-screen policy is documented separately and must be enforced by later milestones
- session reconnect validates stored trust before honoring privileged traffic

Residual risk:

- later Android APIs may vary by OEM and lock-state behavior

## Security Decisions Made In Milestone 1

- protocol stays LAN-first with no Bluetooth dependency
- pairing code is locally derived on both sides rather than transmitted
- opaque `Envelope.payload` keeps transport independent from packet-family evolution
- Android build-time complexity is reduced by generating Java Lite protobuf classes

## Open Security Questions For Later Milestones

- whether `device_id` should remain visible in discovery metadata
- exact Android cryptography provider strategy for Ed25519 and X25519
- how lock-screen-sensitive actions should be audited and surfaced to users
- whether session tickets or resumable trust metadata are worth adding

