# Android

This directory now contains the Android discovery, pairing, encrypted transport, notification-forwarding/reply, and first file-transfer receiver app.

## Current Scope

- Gradle-based Android app module
- NSD service discovery manager
- direct-connect endpoint parsing helper
- Compose discovery and pairing screen
- short-code pairing flow against the desktop service
- trusted-device persistence for reconnect without re-pairing
- encrypted test exchange after trusted reconnect
- UI summary for encrypted `ping`, `device_info`, `capabilities`, and heartbeat probe
- app-scoped live encrypted session with heartbeat updates while the screen is open
- reconnect retry loop after encrypted session failure
- foreground-service automatic trusted reconnect when exactly one paired desktop is visible on LAN
- notification listener entry point
- notification access settings shortcut in the app UI
- encrypted forwarding of posted/removed notification events over LAN
- storage and execution of reply-capable notification actions via Android `RemoteInput`
- storage and execution of non-reply notification actions, used for third-party call answer/decline/hangup when apps expose those actions
- encrypted file receive support with size and SHA-256 verification
- fixed Linkable receive folders under `/Linkable` when all-files access is granted
- safe-listed Wi-Fi enforcement for automatic trusted reconnect
- PC Controls tab for encrypted keyboard, pointer, volume, and mic-mute requests to desktop
- transfer and diagnostics card in the main Compose UI
- unit tests for direct-connect parsing and pairing helpers

## Phase 2 Notification Notes

Notification forwarding requires Android notification-listener access. Open the app, tap `Notification Access`, and enable Linkable in Android settings.

The current implementation forwards notifications while the app has an active encrypted session to a trusted desktop. It does not use Bluetooth.

Forwarding is intentionally limited to user-visible, alerting notifications. The Android listener drops silent/low-importance notifications, foreground-service/ongoing notifications, group summaries, and system/status/progress categories such as package install or uninstall status updates. Call-like notifications are exempt from those noise filters so incoming and active app calls can still be controlled from the desktop.

Reply works only for notifications whose source app exposes a remote-input action. Android keeps those actions valid only while the notification is active, so dismissed or updated notifications may no longer be replyable. Per-app filtering and a foreground service are planned for later Phase 2 work.

Third-party app calls such as WhatsApp, Messenger, Telegram, Signal, Meet, Zoom, and similar apps are handled through their call notifications, not through the SIM `TelecomManager` path. Linkable detects call-like notifications and forwards action metadata to the desktop. Answer/decline/hangup works only when the source app exposes those notification action `PendingIntent`s to Android notification listeners.

Notification payloads include the source package/app label and a small PNG app icon so the Linux desktop can display native notifications with the originating app identity.

## Automatic Reconnect Notes

The foreground service starts discovery and attempts trusted reconnect without opening the Android UI. It auto-connects only when exactly one trusted desktop is visible, no active/pending session exists, and the current Wi-Fi network is safe-listed for that desktop. If multiple trusted desktops are visible, the app pauses automatic reconnect so the user can choose manually.

The first successful pairing safe-lists the current Wi-Fi network for that desktop. A new Wi-Fi network is not added automatically; the user must press Connect for that trusted desktop while on the new network.

## Phase 2 File Transfer Notes

The current Android slice receives desktop-sent files over the encrypted LAN session. With all-files access, completed files are saved under:

```text
/sdcard/Linkable/images
/sdcard/Linkable/videos
/sdcard/Linkable/pdfs
/sdcard/Linkable/apks
/sdcard/Linkable/files
```

Without all-files access on scoped-storage Android versions, Linkable falls back to MediaStore Downloads:

```text
/sdcard/Download/Linkable/<type>/
```

If public storage writes fail, the last fallback remains app-specific external Downloads:

```text
/sdcard/Android/data/com.linkable/files/Download/
```

Phone-to-desktop sends still use Android's document picker so the user can choose any file Android exposes without root.

## Local Build Notes

The repo scripts do not assume your Android SDK is exported globally.
Use:

```bash
source ./scripts/android_env.sh
```

If the helper finds your local SDK and a cached Gradle distribution, it will export the variables needed for local Android checks.

## Milestone 1 Generated Protocol Outputs

Milestone 1 protocol generation still writes Android-consumable protobuf Java Lite classes to:

- `protocol/generated/android-java`
