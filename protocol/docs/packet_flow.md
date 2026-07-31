# Packet Flows

This document captures the Phase 1 / Milestone 1 flows as sequence diagrams.

## 1. Discovery Overview

```mermaid
sequenceDiagram
    participant Android
    participant LAN
    participant LinuxDesktop

    LinuxDesktop->>LAN: Advertise _linkable._tcp.local. with device_name, protocol_version, device_id
    Android->>LAN: Browse for _linkable._tcp.local.
    LAN-->>Android: Resolved device metadata
    Android->>Android: Render discovered device list
```

## 2. Direct Connect Fallback

```mermaid
sequenceDiagram
    participant Android
    participant LinuxDesktop

    Android->>Android: User enters ip:port
    Android->>LinuxDesktop: Open TCP connection
    LinuxDesktop-->>Android: Accept connection
    Android->>Android: Treat peer as connectable candidate
```

## 3. Pairing Success Flow

```mermaid
sequenceDiagram
    participant Phone as Android Phone
    participant Laptop as Linux Laptop

    Phone->>Laptop: PairingRequest(initiator, pairing_nonce, direct_connect)
    Laptop->>Laptop: Validate version and request user approval
    Laptop-->>Phone: PairingChallenge(acceptor, challenge_nonce, verification_code_length, code_derivation_label)
    Phone->>Phone: Derive verification code locally
    Laptop->>Laptop: Derive verification code locally
    Phone->>User: Display derived code
    User->>Laptop: Enter code shown on phone
    Laptop->>Laptop: Verify local entry matches local derivation
    Phone->>Laptop: PairingConfirm(confirmer, transcript_hash, signature)
    Laptop->>Phone: PairingConfirm(confirmer, transcript_hash, signature)
    Laptop-->>Phone: PairingComplete(trusted_peer, paired_at)
    Phone->>Phone: Persist trust
    Laptop->>Laptop: Persist trust
```

## 4. Pairing Rejection Flow

```mermaid
sequenceDiagram
    participant Phone as Android Phone
    participant Laptop as Linux Laptop

    Phone->>Laptop: PairingRequest(...)
    Laptop->>Laptop: Reject request or time out
    Laptop-->>Phone: PairingReject(reason, detail)
    Phone->>Phone: Clear pending pairing state
```

## 5. Trusted Session Establishment

```mermaid
sequenceDiagram
    participant Phone as Android Phone
    participant Laptop as Linux Laptop

    Phone->>Laptop: SessionInit(initiator, ephemeral_public_key, identity_signature, issued_at)
    Laptop->>Laptop: Verify trusted device_id and signature
    Laptop-->>Phone: SessionAck(acceptor, ephemeral_public_key, identity_signature, issued_at)
    Phone->>Phone: Derive shared secret and directional keys
    Laptop->>Laptop: Derive shared secret and directional keys
    Note over Phone,Laptop: Encrypted session can now carry Ping, DeviceInfo, Capabilities, Heartbeat, Error
```

## 6. Session Rotation

```mermaid
sequenceDiagram
    participant PeerA
    participant PeerB

    PeerA->>PeerB: SessionRotate(requested_by, next_ephemeral_public_key, rotation_epoch, signature)
    PeerB->>PeerB: Validate rotation request
    Note over PeerA,PeerB: Both sides derive fresh directional keys and reset counters
```

## 7. Session Close

```mermaid
sequenceDiagram
    participant PeerA
    participant PeerB

    PeerA->>PeerB: SessionClose(reason, detail)
    PeerA->>PeerA: Zero session material
    PeerB->>PeerB: Zero session material
```

