# Linkable

Linkable is a LAN-first Android-to-Linux companion project.

This repository currently implements:

- shared protocol schemas
- protocol and security documentation
- packet flow documentation
- lock-screen policy documentation
- protobuf stub-generation tooling
- Milestone 1 verification tooling that works without a globally configured Android SDK
- Linux desktop discovery utilities
- Android discovery, pairing, and trusted reconnect
- encrypted LAN transport with heartbeat
- Phase 2 notification forwarding from Android to Linux desktop terminal
- Phase 2 notification reply for apps that expose Android remote-input actions
- Phase 2 bidirectional encrypted file transfer slice
- Phase 2 ring-phone utility command over LAN
- Phase 3 incoming call-state mirroring over LAN
- Phase 3 desktop call accept/reject/hangup command slice
- Phase 3 desktop outgoing dialing with SIM-1 preference
- Phase 3 telephony diagnostics and desktop diagnostic export
- Phase 3 LAN-only call intelligence for caller/source/SIM/route/capability metadata
- Bluetooth HFP desktop audio controls for SIM call audio routing
- Android foreground service runtime for background and screen-off operation

## Current Status

Phase 1 is implemented through secure LAN discovery, short-code pairing, trusted reconnect, encrypted transport, and heartbeat.

Phase 2 Milestone 1 is implemented as a working vertical slice: Android captures notifications through notification-listener access and forwards posted/removed notification events over the trusted encrypted LAN session. The Linux desktop currently logs those events in the advertiser terminal.

Phase 2 Milestone 2 now has a working terminal-driven reply slice: when a notification exposes an Android remote-input action, the desktop prompts for reply text and Android sends it through the original notification action. Per-app filtering and native desktop notification UI remain later Phase 2 work.

Phase 2 Milestone 3 has a bidirectional file-transfer slice: the desktop GUI can send files to Android, and Android can send selected files back to the desktop. Android saves verified incoming desktop files under `/Linkable` when all-files access is granted, sorted into `images`, `videos`, `pdfs`, `apks`, and `files`; otherwise Android falls back to `Downloads/Linkable/...`. Desktop saves verified phone files under `~/Downloads/Linkable`. Progress UI, cancel, and resume are later work.

Phase 2 Milestone 4 has a first utility-control slice: the desktop GUI can queue `Ring Phone` and `Stop Ring` commands over the active encrypted LAN session. Android plays the local alarm/ringtone and vibrates for the requested duration without Bluetooth.

Phase 3 Milestone 1 has a first call-event slice: Android monitors local call state with `READ_PHONE_STATE` and forwards `IDLE`, `RINGING`, and `OFFHOOK` events over the trusted encrypted LAN session. The desktop GUI logs call events and shows the latest call state.

Phase 3 Milestone 2 has a first call-control slice: the desktop GUI can send accept, reject, and hangup commands over the encrypted LAN session. Android executes them through `TelecomManager` when `ANSWER_PHONE_CALLS` permission and device/OEM policy allow it. Bluetooth is still not used.

Phase 3 Milestone 3 has a first outgoing-dial slice: the desktop GUI has a phone-number field and SIM slot field defaulted to `1`. Android attempts to resolve SIM 1 to the active subscription and starts a direct call with `CALL_PHONE` permission. The result reports whether SIM 1 was resolved or the system default may have been used.

Phase 3 Milestone 4 has the first hardening slice: the desktop GUI can request telephony diagnostics from Android, show permission/SIM/capability status, and export a diagnostic text report. The Android app also shows a compact local telephony summary. Live lock-screen call workflow results should be recorded in [phase_3_telephony_validation_matrix.md](/home/rsnb/Documents/My_projects/PC-mobile/phases_documention/phase_3_telephony_validation_matrix.md).

The current LAN-only call-intelligence slice sends richer SIM-call metadata to the desktop: call direction, source classification, caller ID when Android exposes it, masked fallback, SIM slot, subscription ID, carrier, active phone-side audio route, ringer mode, volume state, and call capability flags. Caller ID may still be unavailable on newer Android builds unless `READ_CALL_LOG` is granted or the app is later promoted to a default-dialer/calling integration.

SIM call audio is intentionally handled through Bluetooth HFP instead of LAN packet injection. Bluetooth pairing/connection is now manual through the normal Linux and Android Bluetooth settings. The apps verify whether the active LAN phone is also connected over Bluetooth and whether that connection is A2DP media audio or HFP call audio. The desktop can install a reversible WirePlumber phone-safe mode that removes only the laptop's A2DP sink role, so phones stop routing YouTube/media audio to the laptop while HFP call audio remains available. LAN remains the control and metadata transport.

Android now runs the connection stack from a foreground service instead of only the UI `ViewModel`. Discovery, trusted reconnect, encrypted heartbeats, notification reply, file transfer, ring phone, call control, dialing, call metadata, and Bluetooth status checks remain active when the app is backgrounded or the screen is off. The app also exposes an `Allow Unrestricted Battery` button because some OEM battery managers can still kill foreground services unless the user exempts the app.

The Linkable rename is now applied to the Android package (`com.linkable`), Linux package (`linkable_desktop`), app label, launcher/autostart entries, config directory (`~/.config/linkable`), and mDNS service (`_linkable._tcp.local.`). Existing old app trust records should be considered obsolete and re-pairing is expected.

The current feature slice also adds safe-listed Wi-Fi enforcement for trusted reconnect. The first pairing records the current Wi-Fi network; future automatic reconnect only runs on networks already safe-listed for that desktop. If the phone sees the trusted desktop on a new Wi-Fi, the user must explicitly press Connect from the app to approve that current network.

The PyQt6 desktop control center is available. Install its dependency into the project venv only:

```bash
./scripts/setup_desktop_venv.sh
source ./scripts/desktop_env.sh
python -m pip install -r desktop/requirements-ui.txt
```

Run it with:

```bash
./scripts/run_desktop_gui.sh
```

## Repository Layout

```text
PC-mobile/
├── android/               # Android-specific notes and future app landing zone
├── desktop/               # Desktop-specific notes and future app landing zone
├── phases_documention/    # Roadmaps, blueprint, and prerequisite notes
├── protocol/              # Milestone 1 deliverables
├── scripts/               # Code generation and verification scripts
└── shared/                # Cross-platform shared assets
```

## Current Quick Start

1. Set up the desktop virtual environment if you need Python dependencies such as `zeroconf`:

```bash
./scripts/setup_desktop_venv.sh
```

2. Run the desktop checks:

```bash
./scripts/check_milestone_4.sh
```

3. Run the Linux desktop advertiser:

```bash
./scripts/run_desktop.sh advertise
```

Or run the GUI:

```bash
./scripts/run_desktop_gui.sh
```

In the GUI, use `Pick File`, then `Send File`. The queued file sends on the active or next trusted phone heartbeat. Use `Ring Phone` to trigger the phone finder command. Incoming call states and call metadata appear in the desktop log and phone-utilities status area after the Android app has phone-state permission. Use `Accept Call`, `Reject Call`, or `Hang Up` to test call controls on supported devices. For outgoing calls, enter a number, leave SIM as `1`, and press `Dial`. Use `Refresh Telephony` after the phone is connected to verify permissions, SIM mapping, ringer mode, route, and call capabilities; use `Export Diagnostics` to save the current status and event log.

The desktop GUI now uses a pairing gate. If no phone is trusted yet, new pairing is open so the first phone can be added. After at least one trusted phone exists, new pairing requests are blocked by default and trusted reconnect still works through signed session proof. Use `Allow New Pairing 2m` only when intentionally adding another phone.

Phone display mirroring is handled by `scrcpy` from the desktop GUI. `Mirror USB` uses the authorized USB-debugging device. For LAN mirroring, connect once by USB, press `Prepare LAN ADB`, then `Mirror LAN`; or manually pair Android Wireless debugging and enter that ADB endpoint. Mirroring uses `--no-audio` so it does not interfere with the separate Bluetooth call-audio route. If the phone is locked, the lock screen is mirrored and can be unlocked from the scrcpy window after ADB authorization.

PC Controls are available from the Android app behind the `PC Controls` button. Text entry, pointer movement/click/scroll, speaker volume, and mic mute travel over the encrypted LAN session. The desktop executes keyboard/pointer actions through `ydotool`/uinput and audio controls through `wpctl` or `pactl`.

For SIM call audio, use the GUI `Bluetooth HFP Call Audio` section:

```text
Pair phone and laptop manually in OS Bluetooth settings -> Refresh Bluetooth -> Check Phone Bluetooth
```

Both apps show whether the current connection is `LAN only` or `LAN + Bluetooth`. Android also reports whether the matched laptop is connected as `Media audio`/A2DP; if so, install `Phone-safe BT` from the desktop GUI and reconnect Bluetooth. When you press `Accept Call` or `Dial` in the desktop UI, the desktop switches only the matched phone Bluetooth card to HFP/HSP for SIM call audio, then returns that phone card to `off` after the call reports idle. It does not start pairing, trust/connect devices, or switch unrelated Bluetooth headsets.

The equivalent terminal status command is:

```bash
./scripts/run_desktop.sh hfp-status
./scripts/run_desktop.sh hfp-install-phone-safe
./scripts/run_desktop.sh hfp-remove-phone-safe
```

Manual Bluetooth pairing is required. Open Android Bluetooth settings and Linux Bluetooth settings yourself, pair the devices, then use `Refresh Bluetooth` and `Check Phone Bluetooth` in the GUI.

If Android sends normal media/video audio to the laptop, disable `Media audio` for this laptop in Android Bluetooth device settings. Do not disable A2DP globally on Linux if this laptop also uses Bluetooth headsets.

To send one file to the next trusted phone session:

```bash
./scripts/run_desktop.sh advertise --send-file ./README.md
```

4. Build and install the Android app:

```bash
source ./scripts/android_env.sh
export GRADLE_USER_HOME="$PWD/.gradle-session"
"${LINKABLE_GRADLE_BIN}" -p android assembleDebug
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

5. Enable Android notification listener access from the app by tapping `Notification Access`, then connect to the trusted desktop and trigger a notification from another app. The desktop advertiser terminal should print `[notification] ...`. If the notification has a reply action, the terminal will prompt for an action id and reply text.

Generated protocol outputs still land here:

- `protocol/generated/python`
- `protocol/generated/android-java`
- `protocol/generated/descriptor`

## Design Notes

- The protocol is **LAN-first** and **Bluetooth-free** for Milestone 1.
- Android output generation intentionally targets **Java Lite protobuf classes** instead of Kotlin-specific protobuf classes.
  This is a deliberate deviation from the blueprint because it removes the need for a Kotlin protobuf codegen plugin during Milestone 1, while remaining fully consumable from Kotlin later.
- The top-level wire `Envelope` uses a typed header plus raw `bytes payload` instead of a `oneof` body.
  This keeps the transport framing simple and avoids cross-file import cycles between packet families.
- Milestone 2 uses `zeroconf` on the Linux side for mDNS advertisement and browsing, but wraps it so the codebase can still be imported and unit-tested even if that dependency is not installed.
- Android local-network tooling is detected by scripts instead of assuming globally exported SDK variables.

## Local Tooling Assumptions

Milestone 1 only requires:

- `bash`
- `python3`
- `protoc`
- `javac` for later Android-side work, though not for the Milestone 1 verifier

Desktop-side Python dependencies should be installed in the project-local virtual environment, not into the system Python:

```bash
./scripts/setup_desktop_venv.sh
source ./scripts/desktop_env.sh
```

For broader environment notes, see:

- [phase_1_prerequisites.md](/home/rsnb/Documents/My_projects/PC-mobile/phases_documention/phase_1_prerequisites.md)

## Current Files

- desktop entrypoint: [main.py](/home/rsnb/Documents/My_projects/PC-mobile/desktop/src/main.py)
- desktop advertiser: [mdns_advertiser.py](/home/rsnb/Documents/My_projects/PC-mobile/desktop/src/linkable_desktop/discovery/mdns_advertiser.py)
- desktop browser: [mdns_browser.py](/home/rsnb/Documents/My_projects/PC-mobile/desktop/src/linkable_desktop/discovery/mdns_browser.py)
- desktop pairing/session server: [pairing_server.py](/home/rsnb/Documents/My_projects/PC-mobile/desktop/src/linkable_desktop/pairing/pairing_server.py)
- Android discovery manager: [NsdDiscoveryManager.kt](/home/rsnb/Documents/My_projects/PC-mobile/android/app/src/main/java/com/linkable/discovery/NsdDiscoveryManager.kt)
- Android discovery UI: [DiscoveryScreen.kt](/home/rsnb/Documents/My_projects/PC-mobile/android/app/src/main/java/com/linkable/ui/screens/DiscoveryScreen.kt)
- Android pairing/session manager: [PairingManager.kt](/home/rsnb/Documents/My_projects/PC-mobile/android/app/src/main/java/com/linkable/pairing/PairingManager.kt)
- Android notification listener: [PhoneNotificationListener.kt](/home/rsnb/Documents/My_projects/PC-mobile/android/app/src/main/java/com/linkable/notifications/PhoneNotificationListener.kt)
- environment helper: [android_env.sh](/home/rsnb/Documents/My_projects/PC-mobile/scripts/android_env.sh)
