# Linkable Desktop Icon Inventory

This folder is the pre-implementation icon contract for the redesigned desktop UI. No UI code has been changed for these icons yet.

Style target:
- Format: standalone SVG files.
- Canvas: `24x24` viewBox.
- Color: `currentColor` only, so PyQt can recolor icons for green/black/grey/danger states.
- Stroke: rounded line icons with consistent weight.
- Source: generated original SVGs for this project, not copied from an external icon pack.

Availability:
- `available`: an SVG file exists in this folder and can be used immediately.
- `runtime`: not a static asset; the phone or OS supplies it dynamically.

| SVG file | Status | UI use | Visual requirement |
|---|---:|---|---|
| `icon-refresh.svg` | available | Top bar refresh; file browser refresh | Even circular refresh arrows, square visual balance. |
| `icon-lan-service.svg` | available | LAN Service toggle | Broadcast/listener symbol showing the desktop service. |
| `icon-endpoint.svg` | available | Endpoint display | Network node/route marker. |
| `icon-device-id.svg` | available | Device ID display | ID card/chip identity symbol. |
| `icon-add-device.svg` | available | Add Devices button | Plus inside a device frame. |
| `icon-wifi-access.svg` | available | Wi-Fi Access All/Safelisted toggle | Wi-Fi arcs with access gate feel. |
| `icon-safe-wifi-list.svg` | available | Safelisted Wi-Fi popup menu | Wi-Fi with shield/list indication. |
| `icon-settings.svg` | available | Per-device settings entry | Gear. |
| `icon-notifications.svg` | available | Per-device notification tab entry | Bell. |
| `icon-wifi-online.svg` | available | LAN connected status | Green Wi-Fi icon when styled. |
| `icon-wifi-offline.svg` | available | Offline/no LAN status | Crossed Wi-Fi icon when styled grey. |
| `icon-wifi-bluetooth.svg` | available | LAN + Bluetooth connected status | Wi-Fi with Bluetooth subscript. |
| `icon-bluetooth.svg` | available | Bluetooth-only indication/details | Standard Bluetooth rune. |
| `icon-usb.svg` | available | USB mirroring/camera route | USB trident/plug. |
| `icon-reconnect.svg` | available | Device reconnect button | Circular reconnect arrow. |
| `icon-unpair.svg` | available | Device unpair button | Broken link/disconnect symbol. |
| `icon-ring.svg` | available | Ring phone action | Ringer bell icon. |
| `icon-ring-stop.svg` | available | Stop ringing action | Same footprint as ringer with stop mark. |
| `icon-phone-call.svg` | available | Open dialer popup | Phone handset. |
| `icon-phone-outgoing.svg` | available | Dial action inside dialer | Handset with outgoing arrow. |
| `icon-dialpad.svg` | available | Dialer keypad header | 3x3 keypad dots. |
| `icon-sim-card.svg` | available | SIM-specific dial button | SIM card shape. |
| `icon-contacts.svg` | available | Contacts popup | Person/contact card. |
| `icon-browse-files.svg` | available | Browse phone files popup | Folder with phone/device cue. |
| `icon-send-file.svg` | available | Send laptop file/folder to phone | File with upload arrow. |
| `icon-mirror.svg` | available | Screen mirror action | Phone/desktop screen reflection. |
| `icon-shared-apps.svg` | available | Shared apps popup | App grid. |
| `icon-back.svg` | available | Back/up navigation | Left arrow. |
| `icon-home.svg` | available | Phone file browser root | Home outline. |
| `icon-search.svg` | available | Contact/file search fields | Magnifying glass. |
| `icon-copy.svg` | available | Copy text/file action | Overlapping sheets. |
| `icon-send-to-laptop.svg` | available | Phone file context action | File arrow toward laptop. |
| `icon-folder.svg` | available | File browser folder rows | Folder outline. |
| `icon-file.svg` | available | File browser file rows | File outline. |
| `icon-more-menu.svg` | available | Overflow/menu button | Three vertical dots. |
| `icon-reply.svg` | available | Notification reply | Reply arrow. |
| `icon-copy-otp.svg` | available | Copy OTP action | Digits/check copy mark. |
| `icon-clear-one.svg` | available | Clear one notification | Single trash/close mark. |
| `icon-clear-all.svg` | available | Clear all notifications | Stacked trash/clear mark. |
| `icon-clipboard-to-phone.svg` | available | Laptop clipboard to mobile toggle | Clipboard arrow to phone. |
| `icon-clipboard-to-laptop.svg` | available | Mobile clipboard to laptop toggle | Phone arrow to clipboard/laptop. |
| `icon-camera-usb.svg` | available | Camera over USB toggle/test | Camera plus USB mark. |
| `icon-camera-lan.svg` | available | Camera over LAN toggle/test | Camera plus Wi-Fi mark. |
| `icon-camera-test.svg` | available | Camera test button | Camera with check mark. |
| `icon-camera-switch.svg` | available | Front/back camera switch | Camera with rotate arrows. |
| `icon-camera-on.svg` | available | Camera alive popup/service | Camera with live dot. |
| `icon-input-control.svg` | available | Control Input toggle | Cursor/controls symbol. |
| `icon-keyboard.svg` | available | Keyboard input acceptance | Keyboard outline. |
| `icon-mouse.svg` | available | Mouse/trackpad input acceptance | Mouse outline. |
| `icon-command.svg` | available | Command input acceptance | Terminal prompt. |
| App icons from phone | runtime | Shared Apps popup and notification rows | Supplied dynamically by Android app metadata, not a static desktop asset. |
