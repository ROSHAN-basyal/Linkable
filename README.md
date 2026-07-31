# Linkable

<p align="center">
  <img src="Icons/linkable-app-icon.png" alt="Linkable app icon" width="128">
</p>

Linkable connects an Android phone to a Linux desktop over a local network. It
provides encrypted pairing and reconnect, notification mirroring and replies,
call controls, file transfer and browsing, phone ringing, contacts and dialing,
screen mirroring through scrcpy, PC input controls, clipboard forwarding, shared
app launching, and an optional phone-to-PC camera.

> **Status:** Linkable is an alpha project. The downloadable Android APK supports
> Android 8.0 (API 26) and newer. Hardware, OEM battery policies, third-party call
> actions, Bluetooth HFP, and broad storage access vary by device. The APK is
> tested before release, but no project can guarantee every Android/OEM variant.

## Download Android APK

Download the current signed APK and checksum:

- [Linkable-v0.3.0.apk](https://github.com/ROSHAN-basyal/Linkable/releases/latest/download/Linkable-v0.3.0.apk)
- [Linkable-v0.3.0.apk.sha256](https://github.com/ROSHAN-basyal/Linkable/releases/latest/download/Linkable-v0.3.0.apk.sha256)

Release signing-certificate SHA-256:
`5f471e51a682e6e0aaa4902e18c9e50dd6f053abbdfb89ab8cc36d663868555d`.

Verify and install over USB:

```bash
sha256sum -c Linkable-v0.3.0.apk.sha256
adb install -r Linkable-v0.3.0.apk
```

For installation directly on the phone, allow your browser or file manager to
install unknown apps, open the APK, and approve the Android installer prompt.
Only install APKs downloaded from this repository's Releases page and verify the
SHA-256 checksum when possible.

If a locally built debug version is already installed, Android will reject the
release APK because it has a different signing certificate. Uninstall the debug
app first, then install the release APK. Uninstalling clears Linkable's local
trust/settings, so pair the devices again afterward.

## Linux Prerequisites

The desktop application targets Arch Linux, EndeavourOS, Manjaro, and other
Arch-based distributions. Python dependencies are installed in a project-local
virtual environment; Linkable never modifies Arch's system Python with pip.

Install the base runtime:

```bash
sudo pacman -S --needed git python python-pip avahi nss-mdns libnotify \
  pipewire pipewire-pulse wireplumber
sudo systemctl enable --now avahi-daemon.service
```

Install feature-specific packages as needed:

```bash
# ADB and screen mirroring
sudo pacman -S --needed android-tools scrcpy

# Bluetooth status and SIM-call HFP audio
sudo pacman -S --needed bluez bluez-utils
sudo systemctl enable --now bluetooth.service

# Phone keyboard/trackpad control
sudo pacman -S --needed ydotool

# Phone camera exposed as "Linkable Camera"
sudo pacman -S --needed v4l2loopback-dkms v4l-utils ffmpeg linux-headers
```

Use the header package matching the running kernel (`linux-lts-headers`,
`linux-zen-headers`, and so on) instead of `linux-headers` when applicable.
ADB, scrcpy, ydotool, Bluetooth, and virtual-camera packages are optional; the
encrypted LAN connection, notifications, and basic transfers do not require all
of them.

## Install and Run the Desktop

### Recommended source installation

```bash
git clone https://github.com/ROSHAN-basyal/Linkable.git
cd Linkable
./scripts/setup_desktop_venv.sh
./scripts/install_desktop_app.sh
./scripts/run_desktop_gui.sh
```

To keep only the low-power LAN/notification service running after login:

```bash
./scripts/install_desktop_app.sh --autostart
```

The GUI does not autostart. The systemd user service runs with
`--background-service`; opening the GUI temporarily hands the LAN port to the
GUI and restores the background service when the window closes.

Useful commands:

```bash
./scripts/run_desktop_gui.sh
./scripts/run_desktop.sh advertise
./scripts/run_tests.sh
systemctl --user status linkable-desktop.service
```

### Native Arch package

After cloning, build a package from the checked-out source:

```bash
cd desktop/packaging
makepkg -si
linkable-desktop
```

Enable its background service only if wanted:

```bash
systemctl --user enable --now linkable-desktop.service
```

## Firewall

Linkable advertises `_linkable._tcp.local.` over mDNS (UDP 5353) and listens on
TCP `37891` by default. The GUI never runs sudo or changes the firewall
automatically.

For firewalld:

```bash
sudo firewall-cmd --add-port=37891/tcp --permanent
sudo firewall-cmd --add-service=mdns --permanent
sudo firewall-cmd --reload
```

For UFW:

```bash
sudo ufw allow 37891/tcp
sudo ufw allow 5353/udp
```

If `~/.config/linkable/config.json` overrides `service_port`, open that port
instead. Prefer a firewall zone scoped to the trusted home LAN. An open Linkable
port does not establish trust by itself: unknown peers must pass the pairing
gate and cryptographic verification.

## Connect Phone and Desktop

1. Connect both devices to the same private Wi-Fi network.
2. Start `./scripts/run_desktop_gui.sh`, enable **LAN Service**, and press
   **Add Devices**. This opens a short pairing window.
3. Install/open Linkable on Android, grant nearby-device/location access needed
   by Android network discovery, and press **Scan**.
4. Select the desktop. The phone displays a large six-digit code.
5. Enter that code in the desktop prompt and press Enter. The phone validates
   the authenticated transcript and completes pairing automatically.
6. Tap **OK** on the phone after reading the code. This only dismisses the code;
   it does not authorize the pairing.
7. Enable requested feature permissions individually. Notification access is a
   special Android Settings permission and must be enabled there.

Trusted devices reconnect automatically when they return to an approved Wi-Fi.
If Safe Wi-Fi mode is enabled, moving to a new network requires explicit
approval before that SSID is added. **Disconnect** is temporary, **Unpair**
disables automatic reconnect until reconnect is requested, and **Forget**
removes trust and device settings so the next contact is a new pairing.

If discovery fails:

```bash
systemctl status avahi-daemon.service
ss -ltn | grep 37891
avahi-browse -rt _linkable._tcp
```

Confirm AP/client isolation is disabled on the router. As a fallback, enter the
desktop's LAN IP and configured port in Android Direct Connect.

## Android Permissions

Linkable requests permissions only for enabled features:

| Permission/access | Feature |
| --- | --- |
| Nearby devices/location and Wi-Fi multicast | mDNS discovery |
| Notification listener | notification forwarding, replies, app-call actions |
| Phone state, call log, answer calls, call phone | SIM metadata/control/dialing |
| Contacts | desktop contact lookup |
| Camera | user-approved camera sessions |
| Files/all-files access | broad storage browsing and transfer; document picker and Downloads fallback remain available |
| Foreground service and battery exemption | trusted reconnect while backgrounded |
| Bluetooth nearby devices | verify that LAN and Bluetooth refer to the same paired phone/PC |

Android and third-party apps remain the authority. WhatsApp, Messenger, and
similar calls can only be answered or rejected when their notification exposes
the corresponding Android `PendingIntent` action. Linkable does not bypass the
lock screen or Android permission model.

## Mirroring, Camera, and Bluetooth

- **Mirror USB:** authorize USB debugging, connect USB, then press Mirror USB.
- **Mirror LAN:** authorize once over USB, prepare ADB TCP mode, then use Mirror
  LAN. Wireless Debugging can also be paired manually.
- **Camera LAN:** MJPEG frames travel inside the existing encrypted Linkable
  session.
- **Camera USB:** `adb reverse` carries the short-lived authenticated camera
  socket over USB. The desktop publishes frames through V4L2 loopback.
- **Call audio:** pair phone and PC manually in normal Bluetooth settings.
  Linkable uses LAN for control/metadata and HFP only during a desktop-answered
  or desktop-dialed SIM call.

Install the virtual camera once:

```bash
./scripts/setup_linkable_camera.sh --persist
```

## Build the Android App

### Prerequisites

- JDK 17
- Android SDK command-line tools or Android Studio
- Android SDK Platform 36
- Android SDK Build Tools 36.0.0

On Arch, Android Studio from the AUR is the simplest supported SDK installer.
The SDK normally lands at `~/Android/Sdk`. With `sdkmanager` available:

```bash
sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"
```

The repository includes the checksum-pinned Gradle 8.9 wrapper required by
Android Gradle Plugin 8.7. Protobuf Java Lite sources are generated
automatically from `protocol/schemas`; no global Gradle or protoc is required.

Build and install a debug APK:

```bash
source ./scripts/android_env.sh
./android/gradlew -p android testDebugUnitTest assembleDebug
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Build a locally signed release:

```bash
./scripts/generate_android_signing_key.sh
source "${XDG_CONFIG_HOME:-$HOME/.config}/linkable/signing/release.env"
./scripts/build_android_release.sh
```

Back up the generated keystore and environment file securely. Android requires
all future updates to use the same signing key. Signing material is ignored by
Git and must never be committed.

## Security Design

- Pairing is user-initiated and time-limited. A six-digit code is derived from
  fresh nonces and both identity public keys; the code itself is not advertised.
- Each device has a persistent P-256 ECDSA identity. Android stores its private
  key in Android Keystore. Linux stores its identity and trust records under
  `~/.config/linkable` with directory mode `0700` and file mode `0600`.
- Trusted reconnect verifies signed session-init transcripts against the pinned
  public key. A device name, IP address, mDNS record, or Bluetooth name alone is
  never sufficient.
- Every LAN session uses ephemeral P-256 ECDH, HKDF-SHA-256 directional keys,
  and AES-256-GCM framed encryption with monotonic counters and replay
  rejection.
- File transfers include declared sizes and SHA-256 verification. Camera LAN
  frames use the same encrypted session; USB camera transport stays inside ADB
  reverse forwarding and uses a random per-session token.
- Android backup/device transfer excludes Linkable trust and configuration.
  Linux private-state writes are atomic and permission-restricted.
- Safe Wi-Fi is an additional policy boundary, not a replacement for
  cryptographic authentication.

Threat model and packet details:

- [Threat model](protocol/docs/threat_model.md)
- [Protocol specification](protocol/docs/protocol_spec.md)
- [Packet flow](protocol/docs/packet_flow.md)

## Verification

Run the same primary checks used by CI:

```bash
./scripts/setup_desktop_venv.sh
PYTHONPATH=desktop/src .venv-desktop/bin/python -m unittest discover -s desktop/tests
./android/gradlew -p android testDebugUnitTest assembleDebug
bash -n scripts/*.sh
```

The release APK is additionally verified with Android SDK `apksigner` before it
is uploaded. See [GitHub Actions](.github/workflows/ci.yml) for the clean-run
build definition.

## License

Linkable is distributed under the [MIT License](LICENSE).
