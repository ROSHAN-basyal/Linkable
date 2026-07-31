# Phase 3 Telephony Validation Matrix

Use this matrix to record live behavior per Android device and OS build. A workflow is supported only if it succeeds through the app over the encrypted LAN session and reports a clear desktop result.

## Device Under Test

- Device model:
- Android version:
- Build/OEM skin:
- App version/build:
- Desktop distro:
- LAN type:
- SIM 1 carrier/subscription ID:
- SIM 2 carrier/subscription ID:

Current target notes from this session:

- SIM 1 has previously resolved as logical slot 0, `subId=3`, carrier `Namaste`.
- SIM 2 has previously resolved as logical slot 1, `subId=4`, carrier `Ncell`.
- Android default voice subscription has previously resolved to `subId=3`, so desktop SIM field `1` should target Namaste unless the device subscription state changes.

## Permission And Capability Snapshot

Record from the desktop `Refresh Telephony` button and exported diagnostics:

- `READ_PHONE_STATE` granted:
- `READ_CALL_LOG` granted:
- `ANSWER_PHONE_CALLS` granted:
- `CALL_PHONE` granted:
- SIM 1 resolved:
- SIM 2 resolved:
- Call-state mirroring supported:
- Caller ID supported:
- Call control supported:
- Direct dial supported:
- LAN call audio supported: expected `false`
- Bluetooth call audio recommended: expected `true` until HFP/audio routing is implemented
- BlueZ adapter powered:
- Laptop pairable/discoverable:
- PipeWire/WirePlumber active:
- HFP/HSP profile visible after Bluetooth pairing:

## Workflow Results

| Workflow | Unlocked Result | Locked Result | Notes |
| --- | --- | --- | --- |
| `Refresh Telephony` returns permission/SIM snapshot | Not tested | Not tested | |
| Capability snapshot shows ringer mode and active route | Not tested | Not tested | |
| Incoming call mirrors `RINGING` | Not tested | Not tested | |
| Incoming call metadata shows source/direction/caller/SIM/carrier | Not tested | Not tested | Caller ID may require `READ_CALL_LOG` or default-dialer integration |
| Answer incoming call from desktop | Not tested | Not tested | |
| Reject incoming call from desktop | Not tested | Not tested | |
| Hang up active call from desktop | Not tested | Not tested | |
| Dial from desktop using SIM 1 | Not tested | Not tested | |
| Dial from desktop using SIM 2 | Not tested | Not tested | |
| Desktop receives `IDLE` after call ends | Not tested | Not tested | |
| Laptop pairs as Bluetooth audio device from Android settings | Not tested | Not tested | HFP audio only; LAN remains control path |
| Desktop sends Bluetooth ID over LAN and Android starts bond prompt | Not tested | Not tested | Use `Enable HFP Pairing` or `Send BT ID To Phone` |
| SIM call audio routes to laptop speaker/mic or laptop default headset | Not tested | Not tested | Requires BlueZ/PipeWire HFP profile |
| LAN metadata/control still works while Bluetooth audio is connected | Not tested | Not tested | |

## Pass Criteria

- Desktop log shows the expected request and result packet for each tested action.
- `Refresh Telephony` shows all required permissions as granted before call-control and direct-dial tests.
- Android does not crash or drop the encrypted session.
- Failure cases return explicit result details instead of hanging silently.
- SIM-specific dialing is marked supported only when the result says the requested SIM resolved and the real outgoing call uses that SIM.
- Caller ID is marked supported only when Android exposes the caller number to this app; masked/unavailable metadata is acceptable as a privacy/platform fallback.
- Bluetooth HFP audio is marked supported only when the phone routes a real SIM call to the laptop and laptop microphone/speaker are used for the call.

## Known Platform Caveats

- Android/OEM dialers can ignore SIM-selection extras even when the subscription resolves.
- `TelecomManager.acceptRingingCall()` and `TelecomManager.endCall()` are deprecated but remain the compatibility path used for the current minSdk.
- Lock-screen behavior can differ by vendor, permission state, default dialer policy, battery restrictions, and carrier configuration.
- This project still does not route call audio to the laptop.
