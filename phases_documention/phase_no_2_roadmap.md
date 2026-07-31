# Phase 2 Roadmap: Notifications, Messaging, File Transfer, and Minimal-Bluetooth Operation

## Phase Goal
Expand the secure connection into a useful daily workflow by syncing selected phone notifications to the Linux laptop, enabling supported message read and reply actions even when the phone is locked where Android permits it, and adding secure file and media transfer. Bluetooth should remain excluded unless validation proves a specific workflow cannot be delivered over LAN.

## UI Pivot

Feature expansion is paused until the desktop and Android UI foundations are improved. The terminal-based desktop flow is no longer sufficient for notification reply, file transfer, diagnostics, and later call workflows.

See [ui_pivot_plan.md](/home/rsnb/Documents/My_projects/PC-mobile/phases_documention/ui_pivot_plan.md).

## Suggested Duration
4 to 6 weeks

## Primary Outcome
By the end of this phase, the laptop becomes a functional companion for the phone: it can receive approved notifications, surface message content, trigger supported quick replies while the phone stays locked where the Android APIs allow it, move files securely, ring the phone, and do so through a LAN-first architecture with no Bluetooth dependency unless explicitly justified.

## Scope

### In Scope
- Notification listener integration on Android
- Per-app allowlist or denylist for forwarded notifications
- Notification payload normalization for desktop display
- Desktop action handling for reply, dismiss, open, and custom intent routing where supported
- Reading and replying to supported messages while the phone remains locked
- Secure file and media transfer over LAN
- Ring-phone command from laptop
- Capability negotiation for optional Bluetooth requirement
- Linux-friendly desktop implementation and packaging strategy for broad distro coverage
- Lightweight Android execution budget for notification and transfer features

### Out of Scope
- Full call answering or dialing workflow
- Live call audio routing unless needed for technical validation
- Multi-device account sync or cloud relay
- Bluetooth usage as a default transport path

## Recommended Technical Direction
- Notification capture: Android Notification Listener Service
- Message reply: use notification actions where available so replies can work while the phone is locked when the originating app and Android expose remote input actions
- File transfer: chunked encrypted transfer over LAN with resumable metadata
- Phone finder: signed command from laptop to phone triggering ring/alarm locally
- Bluetooth: only enable if call control validation shows LAN-only is insufficient
- Desktop baseline: keep Linux as the first-class target and avoid dependencies tied to one distro family
- Android baseline: keep the app lightweight by minimizing persistent services, wakeups, and heavy background work

## Core Workstreams

### 1. Notification Pipeline
- Capture notifications on Android
- Filter by app, channel, and user preference
- Map notifications to a desktop-friendly schema
- Handle updates, removals, grouped notifications, and silent notifications
- Preserve enough metadata to support lock-screen-safe reply flows where available

### 2. Desktop Notification UX
- Display notifications with app name, title, body, and actions
- Support reply where Android exposes remote input actions
- Show delivery status, expiration, and unavailable actions clearly
- Keep the desktop implementation Linux-friendly across different desktop environments as much as possible

### 3. Secure File and Media Transfer
- Transfer files in both directions
- Show progress, cancellation, completion, and conflict handling
- Enforce transfer size limits and trusted-device-only policy

### 4. Device Utility Commands
- Ring phone from laptop
- Show battery, connectivity, and capability state on desktop

### 5. Optional Bluetooth Workstream
- Validate if call control requires Bluetooth pairing
- If required, guide or automate pairing where platform permissions allow
- Keep Bluetooth as a negotiated capability, not a hidden dependency
- Keep Bluetooth out of notification, messaging, file transfer, and phone-finder flows unless proven mandatory

## Milestones

### Milestone 1: Notification Capture and Filtering
- Android collects notifications from selected apps
- Desktop receives and renders normalized notification payloads
- Android implementation remains lightweight enough for daily background use

Current implementation status:
- Android registers a `NotificationListenerService` and captures posted/removed notifications from other apps.
- Android normalizes notification ID, package, app label, title, body, channel, category, flags, post time, and available action metadata.
- Android forwards notification events over the existing trusted encrypted LAN session; Bluetooth is not used.
- Desktop receives encrypted notification packets and logs normalized posted/removed events in the advertiser terminal.
- The current filter is minimal: the app excludes its own notifications, but user-managed per-app allow/deny settings are still pending.
- The current desktop UX is terminal logging only; native desktop notification display is still pending.

### Milestone 2: Notification Actions and Reply
- Supported notifications can be replied to from desktop
- Unsupported apps fail clearly without breaking sync
- Supported message reply still works while the phone is locked where Android permits it

Current implementation status:
- Android stores notification `PendingIntent` actions and `RemoteInput` metadata for active notifications.
- Desktop prompts in the advertiser terminal when a forwarded notification exposes reply-capable actions.
- Desktop sends encrypted `NotificationReplyRequest` packets over LAN; Android executes the selected notification reply action and returns `NotificationReplyResult`.
- Unsupported or expired actions fail with a visible desktop result instead of breaking the encrypted session.
- Reply behavior while locked depends on Android and the source app's notification action policy.
- Native desktop notification buttons and a persistent Android foreground service are still pending.

### Milestone 3: File and Media Transfer
- Trusted devices can send files in both directions over the encrypted session
- Transfer progress and failure handling are visible
- Transfers remain LAN-only without needing Bluetooth

Current implementation status:
- Desktop can send one file to the next trusted Android session with `./scripts/run_desktop.sh advertise --send-file PATH`.
- The PySide desktop GUI can queue explicit file sends with `Pick File` and `Send File`.
- Android can send a selected file back to the desktop with `Send File To PC`.
- Transfers use encrypted LAN packets: `FileOffer`, ordered `FileChunk`, `FileComplete`, and `FileTransferResult`.
- Android writes received files to a user-selected SAF folder, public Downloads, or app-specific fallback and verifies size plus SHA-256 before finalizing.
- Desktop writes received phone files to `~/Downloads/Linkable` and verifies size plus SHA-256 before finalizing.
- Bluetooth is not used.
- Current limitations: no detailed transfer progress UI, no cancel/resume, and file sends are queued against the current long-lived session heartbeat.

### Milestone 4: Utility Controls and Capability Negotiation
- Ring-phone command works
- Bluetooth capability state is exposed in protocol and UI
- If needed, first-pass Bluetooth pairing flow is operational
- If Bluetooth is not needed, the feature set remains complete for this phase without it

Current implementation status:
- Desktop exposes `Ring Phone` and `Stop Ring` controls in the PySide GUI.
- Ring commands are sent as trusted encrypted LAN packets and are delivered on the active or next phone heartbeat.
- Android executes ring commands by playing the local alarm/ringtone and vibrating for a bounded duration, then returns `RingPhoneResult`.
- Bluetooth is not used for this utility flow.
- Current limitations: delivery latency depends on the existing phone heartbeat, and richer capability-state UI is still pending.

## Deliverables
- Android notification forwarding module
- Linux desktop notification center integration or in-app notification panel
- App-selection settings on Android
- Secure file transfer implementation
- Ring-phone control
- Bluetooth research result and implementation only if required
- Lock-screen messaging behavior note covering supported and unsupported app cases

## Risks and Mitigations
- Some apps do not expose reply actions
  - Mitigation: support best-effort reply only where Android provides remote input
- Notification volume may overload desktop UX
  - Mitigation: support app filters, quiet hours, and batching rules
- File transfer may fail on unstable Wi-Fi
  - Mitigation: chunking, retry, integrity checks, and resumable transfers
- Locked-phone reply behavior may vary by app and Android version
  - Mitigation: build around Android-supported remote input flows and document unsupported cases clearly
- Linux desktop integrations may behave differently across desktop environments
  - Mitigation: keep the desktop feature core in-app and treat native desktop integrations as optional layers
- Automatic Bluetooth enablement may be restricted by platform permissions
  - Mitigation: keep user-assisted fallback and document exact platform limits, but do not depend on Bluetooth for core Phase 2 features

## Exit Criteria
- Selected phone notifications appear on the laptop reliably
- Supported notification replies work end to end
- Supported message reading and reply remain usable even while the phone is locked where Android allows it
- File and media transfer works securely between trusted devices
- Ring-phone action works from laptop
- Phase 2 core features work over LAN
- Bluetooth requirement is either implemented for a justified need or formally ruled unnecessary for Phase 3

## Phase 2 Decision Gate for Next Phase
Before Phase 3 starts, confirm:
- Whether incoming call accept and hangup can be controlled via Android APIs alone
- Whether incoming-call control can remain usable while the phone is locked
- Whether call audio remains on phone or must be bridged to laptop
- Whether dialing from laptop needs SIM selection support on phone UI or direct programmatic routing
- Whether Bluetooth can stay fully optional in Phase 3
