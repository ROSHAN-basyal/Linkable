# Linkable Session Memory

This file is intended to give another LLM enough context to continue the project from the same working state.

## User Vision

The user is building `Linkable`, originally called PC-mobile/pcmobile. It is a two-part platform:

- Android phone app.
- Linux desktop app, Arch/EndeavourOS-first but cross-distro where possible.

The phone should become a seamless Linux peripheral over trusted LAN and USB:

- Notification mirror.
- Reply to chats/messages.
- Call controls.
- Call dialing.
- Ring phone.
- File/media sharing.
- Lazy phone storage browsing.
- Screen mirroring.
- Shared app shortcuts.
- Keyboard/trackpad/volume/mic PC controls from phone.

Core constraints and preferences:

- LAN first.
- Bluetooth least possible.
- Bluetooth only for call audio if Android requires it.
- No packet-based SIM call audio injection; normal Android cannot integrate that without root/system/OEM privilege.
- Android only for now.
- Android app should stay lightweight.
- Linux desktop should work across Arch, Debian/Ubuntu, Fedora where possible.
- EndeavourOS/Arch must not use global system pip modification; use `.venv-desktop`.
- Clean UI, no junk, progressive disclosure, hidden logs unless requested.
- Desktop and Android should clearly show LAN/Bluetooth connection status.
- Devices should auto-reconnect when back on safe-listed Wi-Fi if user did not intentionally disconnect.
- If user intentionally disconnects, reconnect should not be automatic until explicitly allowed.
- Safe-listed Wi-Fi networks should be approved by user.
- Received files on phone go under `/Linkable` category folders or fallback Downloads.
- Use scrcpy for mirroring via USB and LAN.

## Major Decisions Made

### Project Rename

The project was renamed to `Linkable`.

Changed identity:

- Android package: `com.linkable`.
- Desktop Python package: `linkable_desktop`.
- Config directory: `~/.config/linkable`.
- mDNS service type: `_linkable._tcp.local.`
- App label: `Linkable`.

The old Android package `com.pcmobile` was uninstalled from the connected phone, and `com.linkable` was installed.

### Desktop UI Stack

Decision: use PyQt6 for the redesigned Linux desktop app.

Reasoning:

- Existing codebase is Python.
- PyQt6 is cross-distro and packageable.
- Avoids Electron/Tauri churn for now.
- Allows separation between logic and UI.
- Another agent can later redesign visual layer using `constants.py` and `theme.py`.

### Bluetooth And Call Audio

Important research conclusion:

- LAN-only packet audio injection into Android SIM calls is not feasible for a normal third-party Android app.
- Android does not expose APIs for arbitrary apps to inject/receive SIM call audio over LAN.
- Only viable normal-user path for SIM call audio on laptop is Bluetooth headset/HFP behavior.
- Therefore Linkable uses LAN for control/metadata and Bluetooth only for call audio routing.

Current policy:

- User manually pairs laptop and phone over Bluetooth.
- Linkable identifies whether LAN-connected phone and Bluetooth phone are the same device.
- Laptop is normal by default.
- Laptop mic/speaker should only be used when call is accepted from laptop or dialed from laptop.
- After call ends, audio should return to normal phone behavior.

### Mirroring

Decision: use `scrcpy` for both USB and LAN mirroring.

Behavior:

- Prefer USB ADB.
- LAN fallback uses `adb tcpip 5555`, known phone IP, `adb connect`, then `scrcpy`.
- User still needs to authorize ADB/wireless debugging.

### Desktop Privileges

Do not modify system Python or global pip.

Use:

```bash
source ./scripts/desktop_env.sh
python -m pip install -r desktop/requirements.txt -r desktop/requirements-ui.txt
```

For sudo firewall/system package commands:

- Show exact commands.
- Let user copy and run in terminal.
- Do not hide sudo execution behind GUI.

This is relevant because the user reported not being able to enter a password. The current redesigned compatibility UI intentionally copies sudo commands instead of executing them.

## Phase History

### Initial Roadmap

The user asked for phase roadmaps saved under `./phases_documention/phase_no_?_roadmap.md`.

Created phase documentation:

- `phases_documention/phase_no_1_roadmap.md`
- `phases_documention/phase_no_2_roadmap.md`
- `phases_documention/phase_no_3_roadmap.md`

Later updated docs:

- Locked phone behavior.
- LAN-first behavior.
- Linux-friendly desktop codebase.
- Android lightweight only.
- PDFs removed by user; no more PDFs needed.

### Phase 1 Secure LAN Foundation

Implemented:

- Desktop mDNS advertisement.
- Android NSD scanning.
- Direct connect fallback.
- Secure pairing using code verification.
- Trust store.
- Encrypted reconnect/session.
- Heartbeat.

Important issue fixed:

- Android discovered wrong `172.17.0.1` Docker/bridge IP.
- Desktop advertisement was adjusted to prefer actual LAN IP.
- Firewall port was opened earlier for old port `7734`.

Original port:

- `7734`.

New spec port:

- `37891`.

Latest code changed default port to `37891`.

### Notification Phase

Implemented:

- Android notification listener.
- Forward notifications to desktop.
- Reply-capable notifications.
- Messenger reply was verified by user.
- App notification filtering was added.
- Later user complained about spam such as APK uninstall.
- Filtering was adjusted to forward only notification-bar relevant notifications and avoid silent notifications.

Important Android listener command after reinstall:

```bash
adb shell cmd notification allow_listener com.linkable/.notifications.PhoneNotificationListener 0
```

### File Transfer Phase

Implemented:

- Desktop to phone file send.
- Phone to desktop file send.
- Dedicated send button.
- File receive debug UI.
- Android storage destination work.
- Received image file was verified by user.

Android storage policy:

- Preferred: `/sdcard/Linkable/images`, `/videos`, `/pdfs`, `/apks`, `/files`.
- Fallback: `Downloads/Linkable/<category>`.

### Ring Phone Phase

Implemented:

- Ring phone from desktop.
- User confirmed ring phase completed.

### Telephony Phase

Implemented:

- Call metadata events.
- Phone capability snapshot.
- Ringer/silent/vibrate state.
- SIM count.
- Carrier.
- Caller ID where available.
- Call direction/route/capability status.
- Accept/reject/hangup buttons.
- Dial from desktop.
- Default SIM discussion; SIM selection supported.
- Dialing verified by user.

Known Android limitations:

- Caller ID may be withheld unless `READ_CALL_LOG`, default dialer role, or Android-specific permission surface allows it.
- Third-party app calls like WhatsApp/Messenger require notification action handling, not SIM telephony APIs.

### App Calls

User could not receive WhatsApp calls initially.

Work was done to use notification actions for third-party app calls:

- Notification call detection.
- Call-like notification action extraction.
- Desktop can trigger actions exposed by apps.

User later confirmed answering WhatsApp call worked.

### Bluetooth Phase

Several iterations happened:

- Attempted Bluetooth/HFP assist from desktop.
- User found Bluetooth setup too complicated.
- User wanted LAN to exchange Bluetooth IDs and then user approves pairing.
- Problems occurred:
  - Phone saw laptop as audio device all the time.
  - YouTube/audio routed to laptop when not wanted.
  - Pairing code mismatch dialogs.
  - Broken headset connection due to desktop Bluetooth role changes.

Final direction:

- Remove aggressive automatic Bluetooth configuration from app.
- User manually pairs laptop and phone.
- Linkable only checks LAN/Bluetooth same-device status.
- Linkable should activate laptop audio only during desktop-accepted or desktop-dialed calls.

### Mirroring Phase

User requested phone display mirroring on PC.

Research conclusion:

- Best method is `scrcpy`.

Implemented:

- Desktop scrcpy manager.
- USB mirroring.
- LAN mirroring preparation with ADB TCP mode.
- GUI integration was started in legacy UI.

Known old issue:

- ADB connect attempted `192:5555`, which was wrong parsing from IP; this was fixed in mirroring helper work.

### UX Pivot

User paused feature expansion because desktop side was too hard to handle.

Requested:

- UI-based desktop approach.
- Mobile UI changes to debug file transfer and key stages.
- Clean CSS/styling.
- Appropriate backend across Linux distros.
- No global pip updates on Arch/EndeavourOS.

Old UI:

- PySide6 control center at `desktop/src/linkable_desktop/ui_qt/app.py`.
- Became crowded and was considered "same as before".

New request:

- Complete redesign, clean icon-led panels.
- PyQt6 accepted.
- Start with startup compatibility check and Devices panel.

## Current New PyQt6 Desktop Work

Recently added files:

- `desktop/src/linkable_desktop/app/__init__.py`
- `desktop/src/linkable_desktop/app/compatibility.py`
- `desktop/src/linkable_desktop/app/setup_state.py`
- `desktop/src/linkable_desktop/app/devices.py`
- `desktop/src/linkable_desktop/app/runtime.py`
- `desktop/src/linkable_desktop/ui_pyqt/__init__.py`
- `desktop/src/linkable_desktop/ui_pyqt/constants.py`
- `desktop/src/linkable_desktop/ui_pyqt/theme.py`
- `desktop/src/linkable_desktop/ui_pyqt/qt_helpers.py`
- `desktop/src/linkable_desktop/ui_pyqt/compatibility_gate.py`
- `desktop/src/linkable_desktop/ui_pyqt/first_run_wizard.py`
- `desktop/src/linkable_desktop/ui_pyqt/runtime_bridge.py`
- `desktop/src/linkable_desktop/ui_pyqt/devices_panel.py`
- `desktop/src/linkable_desktop/ui_pyqt/main_window.py`
- `desktop/src/linkable_desktop/ui_pyqt/app.py`

Modified:

- `desktop/src/linkable_desktop/pairing/pairing_server.py`
- `desktop/src/linkable_desktop/config.py`
- `desktop/src/linkable_desktop/discovery/fallback.py`
- `desktop/src/linkable_desktop/setup/capabilities.py`
- `android/app/src/main/java/com/linkable/discovery/DirectConnectHelper.kt`
- `desktop/requirements.txt`
- `desktop/requirements-ui.txt`
- `desktop/pyproject.toml`
- `scripts/run_desktop_gui.sh`
- `scripts/setup_desktop_venv.sh`

Added packaging:

- `desktop/packaging/PKGBUILD`

Added test:

- `desktop/tests/test_desktop_app_models.py`

### New Compatibility Layer

File:

- `desktop/src/linkable_desktop/app/compatibility.py`

Checks:

- `PyQt6`
- `websockets`
- `zeroconf`
- `adb`
- `scrcpy`
- `notify-send`
- `DBUS_SESSION_BUS_ADDRESS`
- `pactl` or `wpctl`
- port `37891`
- firewalld/ufw/iptables/nft status

UI:

- `desktop/src/linkable_desktop/ui_pyqt/compatibility_gate.py`

Behavior:

- Critical failures block.
- Non-critical failures can be skipped.
- Commands grouped into sudo/non-sudo sections.
- Each command has Copy button.

### New First-Run Wizard

Files:

- `desktop/src/linkable_desktop/app/setup_state.py`
- `desktop/src/linkable_desktop/ui_pyqt/first_run_wizard.py`

Features:

- Detect current Wi-Fi SSID through `iwgetid` or `nmcli`.
- Save setup state in `~/.config/linkable/desktop_setup.json`.
- Save safe network in `~/.config/linkable/safe_networks.json`.
- Show systemd user service unit.
- Install systemd user service with non-sudo `systemctl --user`.

### New Runtime

File:

- `desktop/src/linkable_desktop/app/runtime.py`

Responsibilities:

- Load desktop config.
- Load/create identity.
- Load trust store.
- Start mDNS advertisement.
- Start PairingServer.
- Track live active devices.
- Handle manual disconnect state.
- Allow temporary new pairing window.
- Unpair trusted devices.

Current limitation:

- It listens to PairingServer prompt/log callbacks and parses reconnect/heartbeat messages.
- Future work should add structured PairingServer events.

### New Devices Panel

Files:

- `desktop/src/linkable_desktop/app/devices.py`
- `desktop/src/linkable_desktop/ui_pyqt/devices_panel.py`

Features:

- Clean card layout.
- Green dot for connected.
- Brown dot for unavailable/manual disconnect.
- LAN chip.
- Bluetooth chip.
- Disconnect action.
- Allow reconnect action.
- Unpair action.
- Empty state with Pair new phone action.

### New Main Window

File:

- `desktop/src/linkable_desktop/ui_pyqt/main_window.py`

Features:

- Clean sidebar.
- Disabled placeholders for future panels.
- Device-first main content.
- Hidden event log.
- Service status chips.
- Endpoint and Device ID chips.

### New Entrypoint

File:

- `desktop/src/linkable_desktop/ui_pyqt/app.py`

Behavior:

- Runs compatibility gate.
- Runs first-run wizard if needed.
- Starts runtime.
- Shows main window.
- Supports `--background-service` for systemd user service mode.

Launcher:

- `scripts/run_desktop_gui.sh` now imports PyQt6 and launches `linkable_desktop.ui_pyqt.app`.

## Dependencies

Desktop core requirements now include:

- `protobuf`
- `zeroconf`
- `cryptography`
- `websockets`
- `pulsectl`

Desktop UI requirements:

- `PyQt6`

Installed into `.venv-desktop` during current work:

- `PyQt6-6.11.0`
- `PyQt6-Qt6-6.11.1`
- `PyQt6-sip-13.11.1`
- `websockets-16.0`
- `pulsectl-24.12.0`

Do not update system pip. Use the project venv.

## Important Commands

Run new desktop GUI:

```bash
cd /home/rsnb/Documents/My_projects/PC-mobile
source ./scripts/desktop_env.sh
./scripts/run_desktop_gui.sh
```

Run background service:

```bash
cd /home/rsnb/Documents/My_projects/PC-mobile
source ./scripts/desktop_env.sh
./scripts/run_desktop_gui.sh --background-service
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

Install Android app:

```bash
cd /home/rsnb/Documents/My_projects/PC-mobile
source ./scripts/android_env.sh
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Enable Android notification listener after reinstall:

```bash
adb shell cmd notification allow_listener com.linkable/.notifications.PhoneNotificationListener 0
```

## Current User Issue Context

The user said: "bro I am not being able to enter the password".

Likely cause:

- New compatibility/startup flow shows sudo commands but does not execute them.
- If the user expects to type sudo password inside GUI, that is not implemented and is intentionally avoided.

Recommended response:

- Explain that sudo commands should be copied and run in a terminal.
- If desired later, implement a `pkexec`/Polkit helper flow, but it should be explicit and auditable.

## Current Work Remaining From Latest Request

The latest instruction asked to scaffold and implement startup compatibility check and Devices panel first, then confirm before moving to remaining panels.

Completed for that slice:

- Project structure for new desktop app.
- PyQt6 entrypoint.
- Theme/i18n constants.
- Startup compatibility gate.
- First-run wizard.
- Devices panel.
- Runtime wrapper.
- Launcher switch.
- PyPI/PKGBUILD packaging metadata.

Still to verify after the latest files:

- Launch GUI manually in a real desktop session.
- Confirm phone can see desktop on new default port `37891`.
- If Android was previously built with old default direct-connect port, rebuild/reinstall Android before testing port `37891`.

Latest desktop test result:

- `PYTHONPATH="$PWD/desktop/src" python -m unittest discover -s desktop/tests`
- Result: `Ran 30 tests in 0.013s`, `OK`.

## Next Best Step

Run:

```bash
cd /home/rsnb/Documents/My_projects/PC-mobile
source ./scripts/desktop_env.sh
PYTHONPATH="$PWD/desktop/src" python -m unittest discover -s desktop/tests
```

Then run:

```bash
./scripts/run_desktop_gui.sh
```

Confirm:

- Startup gate opens only if a requirement is missing.
- First-run wizard shows Wi-Fi SSID.
- Main window is the new clean Linkable UI, not the old PySide control center.
- Devices panel shows trusted phone state.
