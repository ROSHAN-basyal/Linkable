# UI Pivot Plan: Desktop Control Center and Android Diagnostics

## Reason For Pivot

The current desktop terminal flow was useful for proving protocol behavior, but it is now too hard to operate:

- discovery, pairing, notification logs, reply prompts, and file sending all compete for one terminal
- file transfer needs progress, destination status, and errors
- notification reply needs clear action buttons instead of typed action IDs
- future call and media features need persistent state, not terminal prompts

The next implementation work should pause feature expansion and build UI foundations first.

## Desktop UI Decision

### Chosen Stack

- Backend: existing Python desktop codebase
- UI toolkit: PySide6 / Qt for Python
- Styling format: Qt Style Sheets (`.qss`)
- Runtime environment: project-local `.venv-desktop`
- Packaging target: Linux-first, distro-neutral Python virtualenv now; AppImage or Flatpak later

### Why This Choice

PySide6 is the most pragmatic path for this codebase because the desktop backend is already Python. It avoids rewriting pairing, discovery, trust store, encrypted transport, notification handling, and file transfer into a different language.

Qt is broadly Linux-friendly across Arch, Fedora, Debian, Ubuntu, and derivatives. PySide6 can be installed in the project venv without modifying system Python or system pip. This fits EndeavourOS/Arch constraints.

QSS gives us CSS-like styling without adding a web runtime. We should keep style tokens in one file, for example:

```text
desktop/assets/styles/linkable.qss
```

### Why Not Tauri/Electron Right Now

Tauri and Electron would give standard web CSS, but they introduce a second frontend stack and more packaging complexity. Tauri also depends on system WebKitGTK packages that vary by distro. Electron is heavier than needed for a LAN companion app.

The recommended path is:

1. Build PySide6 UI over the existing Python backend.
2. Keep business logic UI-agnostic.
3. Revisit Tauri or another web frontend only if the Qt UI becomes limiting.

## Desktop Architecture Target

Split desktop into three layers:

- `core`: discovery, pairing, trust store, encrypted session, notifications, replies, file transfer
- `service`: long-running session coordinator exposing state/events/commands
- `ui`: PySide6 views bound to service state

The UI must not directly own protocol logic. It should call service commands:

- start/stop advertise
- browse LAN devices
- approve pairing
- send file
- reply to notification
- forget trusted device
- open settings

The service should emit UI events:

- desktop advertised with IP/port/device ID
- phone connected/disconnected
- pairing code requested
- trusted reconnect accepted
- notification received/removed
- reply sent/failed
- file transfer accepted/progress/completed/failed
- heartbeat/state changes

## Desktop UI Screens

### 1. Dashboard

- Current desktop identity
- Advertise status
- LAN IP and port
- Connected phone
- Encrypted session state
- Last heartbeat

### 2. Devices

- Discovered phones/desktops
- Trusted devices
- Pair/forget actions
- Direct-connect field

### 3. Notifications

- Notification list
- App name, title, body, time
- Reply button when remote input is supported
- Removed/expired state

### 4. File Transfer

- Send file button
- Destination phone selector
- Transfer progress
- Result path shown after completion
- Failed transfer diagnostics

### 5. Logs / Diagnostics

- Timeline of protocol events
- Discovery events
- Pairing/session events
- Encrypted packet category counts
- Copy diagnostic report button

### 6. Settings

- Desktop display name
- Service port
- Default file-send behavior
- Notification display behavior
- Trust store management

## Desktop Styling Direction

Use QSS with explicit design tokens:

- background: warm off-black or deep slate, not default gray
- accent: green/cyan LAN status color, not purple
- cards: rounded, low-contrast panels
- status chips: connected, reconnecting, failed, idle
- typography: Qt default initially, later bundle a readable font if packaging allows

Suggested files:

```text
desktop/assets/styles/linkable.qss
desktop/assets/styles/tokens.qss
desktop/src/linkable_desktop/ui_qt/
```

## Python / Pip Policy

Do not modify system Python or system pip.

All GUI dependencies must go into `.venv-desktop`:

```bash
./scripts/setup_desktop_venv.sh
source ./scripts/desktop_env.sh
python -m pip install -r desktop/requirements-ui.txt
```

If pip itself needs changes, update only inside `.venv-desktop`, never through the OS Python:

```bash
source ./scripts/desktop_env.sh
python -m pip install --upgrade pip
```

This is safe because it affects only the project virtual environment. On Arch/EndeavourOS, do not use `sudo pip` and do not update distro-managed Python packages through pip.

## Android UI Decision

Keep Android on Jetpack Compose Material 3.

The current Android screen should be split into tabs or sections:

- Connect
- Notifications
- Transfers
- Diagnostics
- Settings

## Android Transfer Destination Decision

The current app-specific path is:

```text
/sdcard/Android/data/com.linkable/files/Download/
```

This is technically safe but bad UX because normal file managers may hide or restrict it.

### Default Target

Use Android `MediaStore.Downloads` for public Downloads:

```text
/sdcard/Download/
```

This should be the default for completed incoming files.

### Editable Target

Add a user-selected destination using Storage Access Framework:

- launch `ACTION_OPEN_DOCUMENT_TREE`
- persist URI permission with `takePersistableUriPermission`
- store selected URI in app preferences
- write received files through `DocumentFile`

This allows users to choose a custom folder without broad storage permission.

### Fallback

If public Downloads or selected folder write fails, save to app-specific external Downloads and show the fallback path in the UI.

## Android UI Requirements

### Connect Screen

- Discovery start/stop
- Direct connect
- Trusted devices
- Pairing state
- Encrypted session state

### Notifications Screen

- Notification listener enabled/disabled state
- Last forwarded notifications
- Reply result history
- Per-app allow/deny controls later

### Transfers Screen

- Incoming transfer list
- File name, size, progress, result
- Save destination selector
- Open destination settings
- Last saved path

### Diagnostics Screen

- LAN IP if available
- Desktop endpoint
- Device ID
- Last heartbeat
- Last protocol error
- Recent event timeline

## Implementation Order

1. Refactor desktop terminal callbacks into a UI-agnostic event bus.
2. Add `desktop/requirements-ui.txt` with PySide6 only after the event bus is ready.
3. Build a minimal PySide6 dashboard that starts/stops advertise and shows connection/log events.
4. Move notification reply prompts into the desktop UI.
5. Move file-send into the desktop UI with progress.
6. Add Android Transfers and Diagnostics screens.
7. Change Android received-file saving to public Downloads with SAF custom folder support.
8. Keep CLI commands as debug tools, but stop using them as the primary workflow.

## Current Pause Boundary

Do not add more protocol features until:

- desktop UI can show connection/session state
- desktop UI can show notifications and reply without terminal prompts
- desktop UI can send a file and show completion/error
- Android UI can show transfer result and destination path
- Android can save received files to public Downloads or a user-selected folder

## Implemented First UI Slice

- Desktop PySide6 control center launcher: `./scripts/run_desktop_gui.sh`
- Desktop QSS stylesheet: `desktop/assets/styles/linkable.qss`
- Desktop GUI can start/stop advertisement, show device identity/endpoint, display trusted devices, show event logs, select and explicitly queue one file for transfer with `Send File`, handle pairing prompts, and show notification reply dialogs.
- Android main screen now includes a Transfers & Diagnostics card.
- Android records connection, pairing, session, notification, reply, and transfer events.
- Android received files now save to a user-selected SAF folder when configured, otherwise public Downloads through MediaStore on Android 10+, with app-specific fallback.
