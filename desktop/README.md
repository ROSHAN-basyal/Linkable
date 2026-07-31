# Desktop

This directory now contains the Linux desktop discovery, pairing, encrypted transport, notification receiver/reply, file transfer, phone utility, and telephony-control implementation.

## Available Commands

From the repository root:

```bash
./scripts/setup_desktop_venv.sh
./scripts/run_desktop.sh init-config
./scripts/run_desktop.sh advertise
./scripts/run_desktop.sh advertise --send-file ./README.md
./scripts/run_desktop.sh browse
./scripts/run_desktop.sh browse --status-window
./scripts/run_desktop.sh connect-by-ip 192.168.1.20:7734
./scripts/run_desktop.sh list-trusted
./scripts/run_desktop.sh forget-trusted DEVICE_ID
./scripts/run_desktop.sh hfp-status
./scripts/run_desktop.sh hfp-install-phone-safe
./scripts/run_desktop.sh hfp-remove-phone-safe
./scripts/run_desktop_gui.sh
./scripts/install_desktop_app.sh
./scripts/install_desktop_app.sh --autostart
```

The GUI treats Bluetooth audio as call-scoped and manual-pairing-only. Pair the phone and laptop through the normal Linux and Android Bluetooth settings, then use `Refresh Bluetooth` and `Check Phone Bluetooth` to verify whether the current transport is `LAN only` or `LAN + Bluetooth`. If Android reports that the laptop is connected as media audio/A2DP, use `Install Phone-safe BT`; it writes a reversible WirePlumber config that removes only the laptop A2DP sink role while preserving laptop-to-headset A2DP source and HFP roles. When `Accept Call` or `Dial` is pressed, the desktop switches only the matched phone card to HFP/HSP and switches that card back to `off` after the phone reports call idle.
If Android still routes media/video audio to the laptop, disable `Media audio` for this laptop in Android Bluetooth device settings. Do not disable A2DP globally on Linux if this laptop also uses Bluetooth headsets.

`install_desktop_app.sh` installs a freedesktop launcher under `~/.local/share/applications`. The `--autostart` option installs/enables the `linkable-desktop.service` systemd user service only, so the LAN listener starts after login without opening the GUI. Any old `~/.config/autostart/linkable.desktop` GUI startup entry is removed.

## Current Scope

- mDNS advertisement via `zeroconf`
- mDNS browsing via `zeroconf`
- direct-connect endpoint parsing
- full short-code pairing flow over LAN
- trusted-device persistence in JSON under `~/.config/linkable`
- launch-time compatibility checks for mDNS, ADB, scrcpy, ydotool/uinput, desktop notifications, audio tools, and TCP port availability
- trusted reconnect handshake without repeating pairing
- one-active-phone session gate; another trusted phone is rejected until the current phone disconnects
- AES-GCM encrypted test exchange after trusted reconnect
- encrypted handlers for `ping`, `device_info`, `capabilities`, and heartbeat
- long-lived encrypted TCP sessions stay open while the Android client sends heartbeats
- encrypted handlers for posted/removed Android notification events
- terminal logging for received notification payloads
- terminal prompt for reply-capable Android notification actions
- encrypted notification reply request/result exchange
- encrypted generic notification action request/result exchange for third-party app calls that expose answer/decline/hangup notification actions
- native Linux notifications through freedesktop `notify-send`, including source app labels, app icons sent by Android, reply action callbacks, and app-call answer/decline/hangup actions
- one-file desktop-to-phone encrypted transfer with `advertise --send-file PATH`
- desktop receive path for phone-to-PC encrypted file transfers under `~/Downloads/Linkable`
- encrypted Android call-state event logging for idle, ringing, and off-hook states
- encrypted Android call-metadata events for SIM call source, direction, caller ID when available, SIM slot, subscription ID, carrier, and active phone-side route
- encrypted Android call-control commands for accept, reject, and hangup where Android allows them
- encrypted outgoing dial requests with SIM slot 1 as the desktop default
- encrypted telephony diagnostics request/result exchange for Android permission, SIM, and capability status
- Bluetooth HFP status, phone-safe A2DP-sink suppression, and call-scoped profile switching using BlueZ plus PipeWire/PulseAudio tooling for desktop-handled SIM calls and notification-controlled app calls
- LAN-assisted Bluetooth status checks that verify the current LAN phone is also manually connected over Bluetooth
- encrypted desktop input handler backed by ydotool/uinput for keyboard and pointer requests, with wpctl/pactl for speaker volume and mic mute
- PyQt6 control-center UI for advertise/stop, pairing prompts, notification reply dialogs, trusted-device view, event logs, file selection, an explicit `Send File` button, phone-finder controls, latest call-state display, call metadata display, call-control buttons, outgoing dial controls, telephony diagnostics refresh, Bluetooth HFP audio setup, and diagnostic export
- first-run setup command display for firewall, mDNS, autostart, and ydotool daemon setup; sudo commands are shown but not run automatically
- CLI output for discovered devices
- optional Tk status window

Per-app filtering UI, detailed transfer progress, cancel/resume, lazy storage browsing, shared apps, and packaging polish remain later work. SIM call audio routing is delegated to the Linux Bluetooth stack through HFP/HSP; LAN packet injection is intentionally not implemented.

## UI Direction

The terminal flow is now considered a debug fallback. PyQt6 remains the desktop GUI stack for this implementation because it is already integrated, works from the project venv without touching system Python, avoids Electron/Tauri packaging churn, and keeps the LAN/control logic in one Python process. A future UI redesign can restyle or replace the view layer because the capability, input, mirroring, transfer, and pairing logic is kept outside the widget code.

See [ui_pivot_plan.md](/home/rsnb/Documents/My_projects/PC-mobile/phases_documention/ui_pivot_plan.md).

Install GUI dependencies:

```bash
./scripts/setup_desktop_venv.sh
source ./scripts/desktop_env.sh
python -m pip install -r desktop/requirements-ui.txt
```

Run the GUI:

```bash
./scripts/run_desktop_gui.sh
```

File sending workflow:

```text
Start Advertise -> Pick File -> Send File -> connect or keep phone connected
```

The selected file is queued and sent on the active or next trusted phone heartbeat.

Screen mirroring workflow:

```text
USB: enable USB debugging -> authorize laptop -> Mirror USB
LAN: USB authorized once -> Prepare LAN ADB -> disconnect USB if desired -> Mirror LAN
Wireless debugging: pair/connect ADB manually -> enter host:port -> Mirror LAN
```

Mirroring uses `scrcpy` with audio disabled. It can show the lock screen and lets the user unlock from the desktop window after ADB authorization. `scrcpy` and Android platform-tools must be installed on the desktop.

Onboarding path shown in the GUI:

```text
Android Settings -> About phone -> Build number -> tap 7 times
Android Settings -> System -> Developer options -> USB debugging
Android Settings -> System -> Developer options -> Wireless debugging
Accept the ADB authorization prompt when it appears
```

Pairing gate workflow:

```text
First phone: Start Advertise -> pair normally
Additional phone: Start Advertise -> Allow New Pairing 2m -> pair within the temporary window
Normal use: Start Advertise -> trusted phone reconnects automatically
```

After at least one trusted phone exists, unsolicited new `PairingRequest` packets are rejected before the desktop prompts the user. Trusted reconnect still requires the phone to prove its stored identity key and then all command traffic stays inside the encrypted session.

Telephony diagnostics workflow:

```text
Start Advertise -> keep phone connected -> Refresh Telephony -> Export Diagnostics
```

`Refresh Telephony` asks Android for current permission, SIM, ringer, route, volume, and call capability status over the encrypted LAN session. `Export Diagnostics` writes the desktop identity, endpoint, latest call state, latest call metadata, latest telephony snapshot, and event log to a text file.

Bluetooth HFP workflow:

```text
Pair manually in OS Bluetooth settings -> Install Phone-safe BT if Android reports media audio -> reconnect Bluetooth -> Refresh Bluetooth -> Check Phone Bluetooth -> Accept Call or Dial
```

The desktop app does not start pairing, run a pairing agent, trust/connect Bluetooth devices, or select arbitrary Bluetooth cards. It only reports local Bluetooth/HFP readiness and asks Android for manual Bluetooth status over the encrypted LAN session.

When the current LAN phone is verified as the same Bluetooth-connected phone, the desktop can act like a Bluetooth headset/car kit for SIM call audio during desktop-handled calls. Phone-safe mode prevents the laptop from being offered as a phone media speaker, while this desktop app continues using LAN for call metadata and control. On PipeWire-based distros, the call audio stream should route through the system default speaker/microphone or the default headset already connected to the laptop.

## Python Environment

On EndeavourOS, do not update or install Python packages into the system environment for this project.
Use the project-local virtual environment instead:

```bash
./scripts/setup_desktop_venv.sh
source ./scripts/desktop_env.sh
```

All desktop scripts prefer `.venv-desktop` automatically when it exists.
