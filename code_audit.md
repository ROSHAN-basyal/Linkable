# Linkable Codebase Audit

Audit date: 2026-07-30

## Scope

This audit covered the Android runtime, discovery, pairing, encrypted transport,
notification/call bridges, Compose state flow, Linux pairing server, desktop
runtime, PyQt UI bridge, compatibility checks, startup service, dependencies,
and existing tests.

The audited source tree contains 132 Kotlin/Python files and about 22,800 lines.
Generated protobuf files are included in that count.

## Connection Failure Root Cause

The supplied logs did not show an mDNS failure. Android repeatedly found and
resolved the correct desktop endpoint at `192.168.1.14:7734`. The connection
failed because discovery and connection ownership were fragmented:

1. `LinkableRuntime` repeatedly opened timed reconnect scan windows.
2. `NsdDiscoveryManager` independently restarted scans for ordinary
   `onCapabilitiesChanged` callbacks, even when the Wi-Fi `Network` had not
   changed.
3. Manual 30-second scanning and trusted reconnect shared one boolean. The UI
   timer could stop the reconnect coordinator's scan.
4. Manual connect, NSD reconnect, fallback reconnect, and dropped-session retry
   could launch overlapping socket attempts.
5. The desktop accepted a replacement session for the same device while the
   previous handler thread could remain blocked.
6. Python buffered socket streams were used after a socket read timeout. Once a
   buffered read times out, later reads can fail permanently.

## Implemented Corrections

### Android discovery and reconnect

- Added `ReconnectCoordinator` as the single owner of trusted reconnect policy.
- Removed periodic reconnect scan windows.
- Added explicit `USER_SCAN` and `TRUSTED_RECONNECT` discovery leases.
- Made NSD start idempotent and service resolution deduplicated.
- Restart NSD only when the actual Wi-Fi `Network` object changes.
- Stop NSD after connection and reopen it after a real session failure.
- Keep a low-frequency LAN fallback only after mDNS has had time to succeed.
- Enforce one socket/pairing/reconnect attempt at a time.
- Close pending, connecting, and active sockets during reset/unpair/shutdown.

### Encrypted transport and resource use

- Replaced Android's 100 ms session polling loop with a conflated event signal
  and a 15-second heartbeat deadline.
- Split the Android session into one blocking reader and one event-driven writer.
- Made encrypted writes thread-safe.
- Ensure an event burst larger than one drain batch is drained immediately
  instead of waiting for the next heartbeat.
- Replaced the desktop's 250 ms outgoing-command polling loop with a semaphore.
  Dial, call, notification, file, camera, and Bluetooth commands now wake the
  writer immediately.
- Moved desktop file sending to the same event-driven writer.
- Reject duplicate desktop sessions, including duplicates from the same phone.
- Track and close all accepted desktop sockets when the service stops.

### State and UI efficiency

- Debug logs no longer participate in the Android main-screen state. Logs are
  collected only while the log or transfer screen is visible.
- Clipboard monitoring starts only for an active, permitted desktop and stops
  on disconnect or permission removal.
- Trust and per-device permission stores now cache parsed state, synchronize
  updates, and tolerate malformed persisted JSON.
- Removed a duplicate installed-app enumeration from every device-state update.
- Device cards are not destructively rebuilt when their models did not change.
- Replaced log-parsed desktop connection lifecycle updates with typed callbacks.

### Pairing UX and cleanup

- New pairing remains gated by desktop policy and the six-digit challenge.
- When the user has opened a pairing window, the desktop goes directly to the
  code prompt instead of showing a redundant second allow/deny dialog.
- A desktop with no trusted devices accepts a code-authenticated first pairing
  without requiring the `Add Devices` window first.
- Removed the obsolete 86 KB PySide all-in-one GUI.
- Removed unused `websockets` and `pulsectl` dependencies.
- Removed dead firewall probes, an obsolete native-call implementation, stale
  metadata parsing, unused direct-connect UI state, and roughly 600 lines of
  unreachable Compose UI.
- ADB and scrcpy are optional compatibility checks because core LAN operation
  does not require screen mirroring.

## Verification

- Android `compileDebugKotlin`: passed.
- Android `testDebugUnitTest`: passed.
- Android `assembleDebug`: passed.
- Desktop `compileall`: passed.
- Desktop unit tests: 38 passed with exit code 0.
- Desktop listener: active on `0.0.0.0:7734`.
- mDNS: `_linkable._tcp.` advertises `192.168.1.14:7734` with the correct TXT
  host override.

The updated APK exists at:

`android/app/build/outputs/apk/debug/app-debug.apk`

It was not installed during this audit because `adb devices -l` showed no
attached or authorized device and the old wireless ADB endpoint refused port
5555.

## Remaining Structural Debt

These are not fixed by cosmetic renaming and should be addressed as controlled
follow-up refactors:

1. `PairingManager.kt` is 1,872 lines. Extract protocol request handlers,
   outbound event queues, session lifecycle, and pairing handshake into separate
   classes with integration tests.
2. `DesktopRuntime` is 1,581 lines. Extract notification/call state, camera
   orchestration, mirror orchestration, and outbound command storage.
3. `pairing_server.py` is 1,425 lines. Replace the packet-type `elif` chain with
   a typed handler registry after adding protocol-level integration tests.
4. `devices_panel.py` is 1,615 lines. Split device cards, dialogs, camera UI,
   notification UI, and file browser into separate modules.
5. Android has only two local unit-test files. Discovery leases, reconnect
   cancellation, persisted-store corruption, notification deduplication, and
   session drop/recovery need dedicated tests.
6. The desktop GUI currently stops the background service and owns the LAN port,
   then restarts the service on exit. A production design should keep one
   background daemon and let the GUI communicate with it through a local Unix
   socket or D-Bus.
7. Deprecated Android NSD resolution, clipboard, and permission-result APIs
   should be migrated with API-level compatibility wrappers.
8. The workspace is not a Git repository. This is a major change-control and
   rollback risk for a protocol-heavy project.

## Expected Connection Flow

For an existing trusted pair, no action is required: the Android foreground
service acquires the trusted-reconnect discovery lease, finds the desktop, and
opens one authenticated encrypted session.

For the current clean trust stores, open Linkable on the phone, press the
30-second scan button, select `rbsylasusTUF`, and type the phone's six-digit code
into the desktop prompt. There is no separate desktop approval dialog and no
mobile “I entered the code” protocol step. Later reconnects are automatic unless
the user explicitly unpairs/disconnects.
