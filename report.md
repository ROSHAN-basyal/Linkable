# Linkable Architecture And Current State Report

Date: 2026-05-29  
Workspace: `/home/rsnb/Documents/My_projects/PC-mobile`  
Project name: `Linkable`

## Purpose

Linkable is a two-part system:

- Android app: runs on the phone and exposes trusted phone capabilities over LAN.
- Linux desktop app: runs on the laptop/PC and presents the phone as a trusted peripheral.

The project goal is to make the phone and Linux desktop behave like one connected platform over LAN first, with USB and Bluetooth only where they are technically required. Bluetooth is no longer treated as the main transport. It is only used for call audio routing when Android requires standard Bluetooth headset/HFP behavior.

## Current High-Level Status

Implemented and working from previous validation:

- Secure LAN discovery and pairing.
- mDNS/NSD discovery with manual direct-connect fallback.
- Trusted reconnect over encrypted LAN sessions.
- Android foreground/background service work so features keep running better outside the foreground UI.
- Phone notifications forwarded to Linux.
- Reply-capable notifications can be replied to from desktop.
- Silent/low-value notifications were filtered down to phone notification-bar notifications only.
- Two-way file transfer.
- Received Android-side files saved under `/Linkable` categories where broad storage access is available, with fallback under `Downloads/Linkable`.
- Phone ringing from desktop.
- SIM call state, call metadata, caller ID where Android exposes it, SIM count, carrier, ringer state, route/capability status.
- Call accept/reject/hangup from desktop for supported call surfaces.
- Dial from desktop, including SIM selection/default SIM handling.
- App-call answering through notification actions where the target app exposes usable notification actions.
- Manual Bluetooth pairing/status awareness.
- Call-audio routing policy: laptop audio is only intended for calls accepted from laptop or dialed from laptop, then should return to normal behavior after call end.
- scrcpy-based USB and LAN mirroring support.
- Linkable rename from old PC-mobile/pcmobile identity in Android and desktop package names.

Currently being rebuilt:

- The desktop UI is being redesigned as a clean PyQt6 application.
- The new PyQt6 desktop shell currently includes startup compatibility checks, first-run setup wizard, hidden event-log shell, always-on runtime startup, and a clean Devices panel.
- Remaining panels still need migration/implementation in the new PyQt6 shell: Notifications, Shared Apps, File Explorer, Mirror controls, Settings/Call Audio.

## Technology Decisions

### Desktop UI Stack

Chosen stack: Python 3.11+ with PyQt6.

Reasoning:

- The existing desktop logic is Python.
- Keeping UI and LAN/control logic in one Python process avoids Tauri/Electron packaging churn right now.
- PyQt6 is cross-distro friendly and available on Arch, Debian/Ubuntu, and Fedora.
- It supports a clean component model with themeable stylesheets.
- The UI can later be restyled by another agent because UI strings, theme tokens, and widgets are separated.

### Transport

Current production transport is the existing encrypted protobuf-over-TCP session used by the Android app.

The latest desktop specification requested WebSocket server/client on default port `37891`. The new desktop dependency set includes `websockets`, and the new default Linkable service port was moved to `37891`, but the actual mobile protocol is still the existing framed encrypted TCP protobuf transport. Any WebSocket migration must be coordinated on both Android and desktop.

### Mirroring

Backend: `scrcpy`.

Modes:

- USB: use active USB ADB device.
- LAN: run `adb tcpip 5555`, connect to known phone IP, then launch `scrcpy`.

Known constraint:

- Android still requires user approval for USB debugging/wireless debugging authorization.
- A locked phone can be mirrored once ADB is already authorized, but user unlock behavior depends on Android security policy and device state.

### Bluetooth

Current policy:

- User pairs phone and laptop manually.
- Linkable checks whether the LAN-trusted phone and Bluetooth-connected phone appear to be the same device.
- Laptop should behave as a normal paired PC device by default.
- Laptop audio should be used only when a call is accepted from desktop or dialed from desktop, then return to normal afterward.

Reason:

- Android does not provide a normal third-party app API for injecting SIM-call audio over arbitrary LAN packets.
- Packet-based SIM call audio injection is not viable without root, system privileges, OEM privileges, or writing a separate VoIP stack.
- Bluetooth HFP/headset routing is the normal Android-supported route for SIM call audio to a laptop-like device.

## Repository Layout

Important root-level paths:

- `android/`: Android app.
- `desktop/`: Linux desktop app.
- `protocol/`: protobuf schemas and protocol docs.
- `scripts/`: build/run/check scripts.
- `phases_documention/`: phase roadmaps, prerequisites, UI pivot plan, validation notes.
- `.venv-desktop/`: project-local desktop Python venv.
- `.gradle-session/`: project-local Gradle cache/session data.

## Protocol Layer

Protocol schemas are under `protocol/schemas/`.

Important schemas:

- `common.proto`: packet type IDs and common envelope concepts.
- `pairing.proto`: pairing request/challenge/confirm/complete/reject.
- `session.proto`: encrypted session init/ack/close.
- `transport.proto`: heartbeat, ping/pong, device info, capabilities.
- `notifications.proto`: notification posted/removed, actions, replies.
- `files.proto`: file transfer requests/chunks/results.
- `utilities.proto`: ring-phone commands.
- `calls.proto`: call metadata, call control, dialing, telephony diagnostics.
- `bluetooth.proto`: Bluetooth assist/status metadata.
- `input.proto`: PC control input events from mobile to desktop.

Generated Python protobuf bindings are loaded through:

- `desktop/src/linkable_desktop/proto.py`

Android generated protobuf sources are handled by the Gradle/protobuf setup.

## Security Architecture

Pairing and trust:

- Desktop identity key stored under `~/.config/linkable/identity_key.pem`.
- Desktop trust store stored under `~/.config/linkable/trusted_devices.json`.
- Android trust store is handled by `android/app/src/main/java/com/linkable/trust/TrustStore.kt`.
- Pairing uses public-key identities and a short verification code.
- After pairing, reconnects require the trusted public key and encrypted session proof.

Session:

- Encrypted session setup uses ephemeral keys and directional encryption keys.
- Runtime messages are protobuf frames over the encrypted channel.
- Heartbeat keeps desktop aware of active connection.

Safe network:

- Android safe-listing is implemented by `android/app/src/main/java/com/linkable/network/SafeNetworkStore.kt`.
- During pairing, trusted Wi-Fi networks can be recorded.
- Auto-reconnect should only activate on safe-listed networks.

Firewall:

- Previous implementation used port `7734`.
- The new desktop specification has moved the default control port to `37891`.
- mDNS discovery requires UDP `5353`.
- The new compatibility checker provides exact commands for `firewalld`, `ufw`, and iptables-style setups.

## Android Architecture

Android package root:

- `android/app/src/main/java/com/linkable`

Core files:

- `LinkableApp.kt`: application entry.
- `LinkableRuntime.kt`: runtime service coordination.
- `MainActivity.kt`: Compose activity.
- `ProtocolMilestone.kt`: protocol milestone marker.

Discovery:

- `discovery/NsdDiscoveryManager.kt`: Android NSD/mDNS discovery.
- `discovery/DirectConnectHelper.kt`: manual endpoint parsing. Default direct-connect port now follows `37891`.
- `discovery/DiscoveredDevice.kt`: discovered desktop model.

Pairing and trust:

- `pairing/PairingManager.kt`: pairing, trusted reconnect, encrypted session management.
- `pairing/PairingState.kt`: UI/runtime pairing state.
- `trust/TrustStore.kt`: trusted desktop persistence.
- `trust/TrustedDevice.kt`: trusted device model.

Crypto and transport:

- `crypto/DeviceIdentity.kt`: Android device identity.
- `crypto/CryptoUtils.kt`: crypto helpers.
- `crypto/SessionCipher.kt`: session encryption.
- `transport/Framing.kt`: protobuf frame I/O.
- `transport/EncryptedConnection.kt`: encrypted session connection wrapper.

Services and background operation:

- `service/LinkableForegroundService.kt`: foreground service to keep Linkable active.
- `service/BootReceiver.kt`: boot receiver for resuming service after device boot where allowed.
- These were added because Android would otherwise pause many features when app UI went background or phone locked.

Notifications:

- `notifications/PhoneNotificationListener.kt`: Android notification listener.
- `notifications/NotificationBridge.kt`: converts Android notifications to Linkable notification events.
- `notifications/NotificationActionStore.kt`: stores actionable notification intents for reply/call actions.
- Silent/irrelevant notifications are filtered before forwarding.
- Reply works for apps exposing Android remote-input actions.

Calls:

- `calls/CallStateMonitor.kt`: observes call state.
- `calls/CallStateBridge.kt`: sends call metadata events to desktop.
- `calls/CallSessionContext.kt`: tracks desktop-originated or desktop-accepted calls.
- `calls/CallControlHandler.kt`: accept/reject/hangup commands.
- `calls/DialHandler.kt`: desktop-originated dialing, SIM selection.
- `calls/TelephonyDiagnosticsProvider.kt`: permissions, SIM count, carrier, ringer state, route/capability snapshot.

Bluetooth:

- `bluetooth/BluetoothAssistHandler.kt`: receives desktop Bluetooth status/assist messages.
- `bluetooth/BluetoothConnectedDevicesReader.kt`: reads bonded/connected Bluetooth devices.
- `bluetooth/BluetoothConnectionStatusProvider.kt`: reports desktop Bluetooth status.

File transfer:

- `transfer/FileTransferReceiver.kt`: receives files from desktop and stores them under `/Linkable` category folders or fallback Downloads path.
- `transfer/PhoneFileSender.kt`: sends selected phone files to desktop.
- `transfer/TransferDestinationStore.kt`: configurable received-file destination logic.

UI:

- `ui/DiscoveryViewModel.kt`: Compose state and actions.
- `ui/screens/DiscoveryScreen.kt`: current Android UI.
- `ui/theme/Theme.kt`: Linkable Android theme.

Current Android UI accomplishments:

- Device discovery and direct connect.
- Pair/connect flows.
- Connection status/logging.
- Notification permission flow.
- File-transfer debugging.
- Ring phone controls.
- Bluetooth status display.
- Cleaner landing layout with quick action components started.

## Desktop Architecture

Desktop package root:

- `desktop/src/linkable_desktop`

Configuration:

- `config.py`
- Config path: `~/.config/linkable/config.json`
- Identity path: `~/.config/linkable/identity_key.pem`
- Trust store path: `~/.config/linkable/trusted_devices.json`
- Default service type: `_linkable._tcp.local.`
- Current default service port: `37891`

Discovery:

- `discovery/mdns_advertiser.py`: desktop mDNS/Avahi advertisement.
- `discovery/mdns_browser.py`: mDNS browser/debug support.
- `discovery/fallback.py`: manual endpoint parsing.
- `discovery/models.py`: discovered device models.

Pairing/session:

- `pairing/pairing_server.py`: TCP server, pairing, session init, encrypted message serving, outbound command queues.
- `pairing/code_generator.py`: verification code generation.
- `pairing/ui_prompts.py`: CLI prompt adapter.

Important recent pairing-server additions:

- Trusted-session allow provider.
- Disconnect-request provider.
- Session-close notification on session end.
- Network interface reporting now uses the configured service port instead of hardcoded `7734`.

Crypto/session/transport:

- `crypto/identity.py`: desktop device identity and signature verification.
- `crypto/session_cipher.py`: encrypted envelope channel.
- `session/auth.py`: session proof helpers.
- `transport/framing.py`: protobuf frame I/O.

Notifications:

- Legacy native notification support remains in `ui_qt/native_notifications.py`.
- New PyQt notification panel is not migrated yet.

File transfer:

- `transfer/file_sender.py`: desktop-to-phone file sender.
- `transfer/file_receiver.py`: phone-to-desktop file receiver.

Mirroring:

- `mirroring/scrcpy.py`: scrcpy and ADB helper logic.

Bluetooth:

- `bluetooth/hfp.py`: Linux Bluetooth/HFP related helpers from the earlier implementation.

Input:

- `input/control.py`: ydotool/wpctl/pactl-backed PC control surface for keyboard, pointer, volume, mic.

Legacy UI:

- `ui_qt/app.py`: older PySide6 all-in-one control center.
- This is now legacy code and should not be the default app path.

New PyQt6 UI:

- `ui_pyqt/app.py`: new desktop entrypoint.
- `ui_pyqt/constants.py`: i18n-ready UI strings.
- `ui_pyqt/theme.py`: theme tokens and stylesheet generator.
- `ui_pyqt/compatibility_gate.py`: startup compatibility checklist UI.
- `ui_pyqt/first_run_wizard.py`: first-run setup wizard.
- `ui_pyqt/main_window.py`: clean app shell.
- `ui_pyqt/devices_panel.py`: clean Devices panel.
- `ui_pyqt/runtime_bridge.py`: thread-safe Qt signal bridge.
- `ui_pyqt/qt_helpers.py`: dynamic style helper.

New app/business layer:

- `app/compatibility.py`: production startup checks and fix commands.
- `app/setup_state.py`: first-run state, safe Wi-Fi SSID persistence, systemd user service unit generation.
- `app/runtime.py`: owns mDNS advertisement, pairing server, trust store, live device state.
- `app/devices.py`: device view-model construction.

Desktop packaging/dependencies:

- `desktop/pyproject.toml`: pip-installable package metadata and `linkable-desktop` entrypoint.
- `desktop/requirements.txt`: core runtime dependencies.
- `desktop/requirements-ui.txt`: PyQt6 dependency.
- `desktop/packaging/PKGBUILD`: Arch package recipe.
- `scripts/run_desktop_gui.sh`: now launches `linkable_desktop.ui_pyqt.app`.
- `scripts/setup_desktop_venv.sh`: installs both core and UI requirements into `.venv-desktop`.

## New Desktop Startup Compatibility Check

Implemented in:

- `desktop/src/linkable_desktop/app/compatibility.py`
- `desktop/src/linkable_desktop/ui_pyqt/compatibility_gate.py`

Checks:

- Python import `PyQt6`.
- Python import `websockets`.
- Python import `zeroconf`.
- Binary `adb`.
- Binary `scrcpy`.
- Desktop notification capability through `notify-send` and session DBus.
- Audio control capability through `pactl` or `wpctl`.
- Listener port availability for configured port, default `37891`.
- Firewall status through `firewall-cmd`, `ufw`, or iptables/nft detection.

Behavior:

- Critical failures block the main UI.
- Non-critical failures can be skipped by explicit user action.
- Each failed check shows plain-language detail and fix commands.
- Commands are grouped by sudo vs non-sudo.
- Each command has a Copy button.

Important note:

- The app intentionally does not run sudo commands directly in the GUI at this stage. If a sudo firewall command is needed, the user should copy it into a terminal. This avoids hidden privilege escalation and avoids password-entry problems inside the GUI.

## New First-Run Setup Wizard

Implemented in:

- `desktop/src/linkable_desktop/app/setup_state.py`
- `desktop/src/linkable_desktop/ui_pyqt/first_run_wizard.py`

Features:

- Shows current Wi-Fi SSID when detectable.
- Persists first-run completion under `~/.config/linkable/desktop_setup.json`.
- Writes safe Wi-Fi data under `~/.config/linkable/safe_networks.json`.
- Shows exact systemd user unit file.
- Shows exact install command.
- Can install the systemd user service without sudo:
  - Unit path: `~/.config/systemd/user/linkable-desktop.service`
  - Command path: `systemctl --user enable --now linkable-desktop.service`

## New Devices Panel

Implemented in:

- `desktop/src/linkable_desktop/app/devices.py`
- `desktop/src/linkable_desktop/app/runtime.py`
- `desktop/src/linkable_desktop/ui_pyqt/devices_panel.py`

Features:

- Lists trusted devices from `~/.config/linkable/trusted_devices.json`.
- Shows green status dot for connected devices.
- Shows brown status dot for unavailable or manually disconnected devices.
- Shows LAN chip and Bluetooth chip.
- Shows disconnect, allow reconnect, and unpair actions as applicable.
- Manual disconnect pauses auto-reconnect for that device.
- Unpair removes the device from the desktop trust store.

Limitations:

- Bluetooth same-device validation is not fully reflected in the new PyQt Devices panel yet.
- The runtime observes active LAN sessions through PairingServer log callbacks; future improvement should emit structured session events directly from PairingServer instead of parsing messages.

## Commands

Run desktop GUI:

```bash
cd /home/rsnb/Documents/My_projects/PC-mobile
source ./scripts/desktop_env.sh
./scripts/run_desktop_gui.sh
```

Run desktop tests:

```bash
cd /home/rsnb/Documents/My_projects/PC-mobile
source ./scripts/desktop_env.sh
PYTHONPATH="$PWD/desktop/src" python -m unittest discover -s desktop/tests
```

Build Android:

```bash
cd /home/rsnb/Documents/My_projects/PC-mobile
source ./scripts/android_env.sh
export GRADLE_USER_HOME="$PWD/.gradle-session"
"${LINKABLE_GRADLE_BIN}" -p android testDebugUnitTest assembleDebug
```

Install Android debug APK:

```bash
cd /home/rsnb/Documents/My_projects/PC-mobile
source ./scripts/android_env.sh
export GRADLE_USER_HOME="$PWD/.gradle-session"
"${ANDROID_SDK_ROOT}/platform-tools/adb" install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Re-enable notification listener after reinstall if needed:

```bash
adb shell cmd notification allow_listener com.linkable/.notifications.PhoneNotificationListener 0
```

## Verification Already Performed

Known earlier validations:

- Desktop unit tests reached `28 tests OK` before the latest PyQt scaffold.
- Android `testDebugUnitTest assembleDebug` passed after earlier implementation rounds.
- Real phone testing confirmed:
  - mDNS/direct discovery after firewall/advertisement fixes.
  - Pairing and encrypted heartbeat.
  - Notification mirroring.
  - Messenger reply.
  - File transfer including image receive.
  - Ring phone.
  - Dial from desktop.
  - WhatsApp call answer via notification action after app-call handling work.
  - scrcpy USB/LAN workflow partially validated, with earlier LAN parsing issue fixed.

Latest PyQt scaffold checks run during implementation:

- PyQt/app compile/import checks passed.
- Compatibility report returned 9 checks with 0 failures in the current environment.
- PyQt widgets instantiated under `QT_QPA_PLATFORM=offscreen`.
- Desktop test suite now passes: `Ran 30 tests in 0.013s`, `OK`.

## Known Incomplete Work

The following are not fully complete in the new PyQt6 UI:

- Notifications panel with grouped app notifications and app icons.
- Shared Apps panel with launch + mirror behavior.
- Lazy phone file explorer.
- Mirror controls panel.
- Settings/Call Audio panel.
- Full WebSocket implementation matching Android.
- Full icon-led UI polish across all panels.
- Direct DBus notification action integration in the new UI.
- Structured runtime event bus replacing log parsing.
- Complete production package install validation from the PKGBUILD.

The following exist in legacy or lower layers and should be migrated into the new PyQt UI:

- Notification reply/action queueing.
- Native Linux notification display.
- File send/receive UI.
- Ring phone controls.
- Call metadata/control/dial UI.
- Bluetooth status UI.
- scrcpy mirror controls.

## Recommended Next Implementation Order

1. Finish the new PyQt6 Devices panel integration and confirm pairing/reconnect with the phone.
2. Add a structured runtime event bus so UI panels do not parse log strings.
3. Migrate Notifications panel:
   - Group by app.
   - Show app name/title/body/timestamp.
   - Use icon cache from Android payload when available.
   - Wire reply actions.
4. Migrate Mirror panel:
   - USB button.
   - LAN button.
   - Known phone IP from session.
   - scrcpy process lifecycle.
5. Migrate File Explorer:
   - Add protocol support for lazy browse if not already complete on both sides.
   - Implement open/copy semantics with temp cleanup.
6. Migrate Shared Apps:
   - Android installed-app sharing list.
   - Icons/categories.
   - Launch app + mirror.
7. Migrate Settings/Call Audio:
   - pulsectl/wpctl sliders.
   - show call-relay state.
8. Add package-level tests for PyQt business logic and compatibility logic.
