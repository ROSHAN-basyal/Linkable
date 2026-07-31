# Packet Flows

## Pairing

```mermaid
sequenceDiagram
    participant Phone
    participant Desktop
    Phone->>Desktop: PairingRequest(phone identity, nonce)
    Desktop-->>Phone: PairingChallenge(desktop identity, nonce)
    Phone->>Phone: Derive and display six-digit code
    Desktop->>Desktop: Derive code and validate user entry
    Phone->>Desktop: Signed PairingConfirm
    Desktop-->>Phone: Signed PairingConfirm
    Desktop-->>Phone: PairingComplete
    Phone->>Phone: Pin desktop identity
    Desktop->>Desktop: Pin phone identity
```

## Trusted Reconnect

```mermaid
sequenceDiagram
    participant Phone
    participant Desktop
    Phone->>Desktop: SessionInit(signed ephemeral key, timestamp)
    Desktop->>Desktop: Verify pinned identity and freshness
    Desktop-->>Phone: SessionAck(signed ephemeral key, timestamp)
    Phone->>Phone: Derive directional session keys
    Desktop->>Desktop: Derive directional session keys
    Phone->>Desktop: Encrypted heartbeat and events
    Desktop-->>Phone: Encrypted commands and acknowledgements
```

## Notification

```mermaid
sequenceDiagram
    participant Android
    participant Desktop
    participant LinuxNotifications
    Android->>Desktop: NotificationPosted
    Desktop->>LinuxNotifications: Show native notification
    Desktop-->>Android: NotificationReplyRequest or NotificationActionRequest
    Android->>Android: Execute current app-provided action
    Android-->>Desktop: Action result
```

## Camera Session

```mermaid
sequenceDiagram
    participant Desktop
    participant Android
    Desktop->>Android: CameraStreamStartRequest
    Android-->>Desktop: User-approved start result
    Android->>Desktop: Encrypted frames
    Desktop-->>Android: CameraStreamAck heartbeat
    Desktop->>Android: CameraStreamStopRequest
    Android-->>Desktop: Stop result and resource release
```

Direct connection changes only endpoint discovery. It does not bypass pairing
or trusted-session authentication.
