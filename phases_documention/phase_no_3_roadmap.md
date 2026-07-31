# Phase 3 Roadmap: Call Control and Dialing from Laptop

## Phase Goal
Complete the telephony layer so the Linux laptop can help manage phone calls through the Android device, beginning with incoming call handling while the phone remains locked and then extending to laptop-initiated dialing with SIM selection where supported, keeping LAN as the preferred transport path.

## Suggested Duration
4 to 7 weeks

## Primary Outcome
By the end of this phase, the laptop can surface incoming calls, allow the user to accept or reject them within the supported platform limits even while the phone remains locked, and initiate outgoing calls through the phone with clear feedback and SIM-aware behavior where the device supports it, without making Bluetooth a default dependency unless a validated telephony limitation forces it.

## Scope

### In Scope
- Incoming call event propagation from phone to laptop
- Desktop controls for accept, reject, mute, and hang up where supported
- Outgoing dialing request from laptop to phone even when the phone is locked where Android permits it
- SIM selection support if the Android device and permissions allow it
- Call-state synchronization between devices
- Audit trail and failure messaging for unsupported telephony actions
- Validation of lock-screen-safe call behavior
- Linux-friendly desktop telephony UX and packaging assumptions

### Out of Scope
- Full VoIP replacement
- Cloud relay calling outside local connectivity
- Contact sync beyond what is necessary for dialing UX
- Bluetooth dependency for call control unless proven mandatory

## Recommended Technical Direction
- Use Android Telecom and call-state APIs where permitted
- Treat telephony control as capability-driven because OEM behavior differs
- Separate call signaling from audio routing
- Keep LAN as the default control path and introduce Bluetooth only if a proven platform restriction blocks required call control
- If laptop audio routing is later required, treat it as an additional sub-phase rather than forcing it into initial call control delivery
- Keep the Android side lightweight by using the smallest viable background footprint for telephony state propagation

## Core Workstreams

### 1. Incoming Call Signaling
- Detect ringing state on Android
- Push call metadata to laptop with minimal delay
- Keep missed, answered, rejected, and ended states synchronized
- Ensure signaling still works when the phone is locked

### 2. Desktop Call Control
- Provide accept, reject, mute, and hangup controls when supported
- Show clear disabled states when permissions or device behavior block an action
- Keep the control surface Linux-friendly and avoid relying on one desktop environment only

### 3. Outgoing Call Workflow
- Send dial request from laptop to phone
- Resolve target SIM where dual-SIM support exists
- Confirm call initiation, failure, or user cancellation
- Validate whether dial requests can be executed while the phone is locked and trusted

### 4. Permissions, Compliance, and OEM Validation
- Validate required Android permissions and background execution rules
- Test across at least one stock Android device and one OEM-customized device
- Document unsupported scenarios explicitly
- Validate whether any remaining telephony step truly requires Bluetooth

## Milestones

### Milestone 1: Call Event Mirroring
- Incoming call events appear on laptop in near real time
- Ended and missed call states sync correctly
- Incoming call mirroring still works while the phone is locked

Current implementation status:
- Added `CallStateEvent` protocol packets for `IDLE`, `RINGING`, and `OFFHOOK` phone states.
- Android registers a lightweight call-state listener while an encrypted trusted desktop session is active.
- Android requires `READ_PHONE_STATE`; caller number access is intentionally not part of this slice.
- Call-state events are sent over the existing encrypted LAN session without Bluetooth.
- Desktop receives call-state packets, logs them, and updates the call-state label in the PySide control center.
- Current limitations: no accept/reject/hangup controls, no caller ID display, and OEM lock-screen behavior still needs live validation.

### Milestone 2: Accept and Hangup Controls
- Desktop can accept or reject calls where APIs allow
- Desktop reflects real device state changes immediately
- Locked-phone call control behavior is validated and documented

Current implementation status:
- Added `CallControlRequest` and `CallControlResult` protocol packets for accept, reject, and hangup actions.
- Desktop PySide GUI exposes `Accept Call`, `Reject Call`, and `Hang Up` buttons.
- Desktop now has a low-latency outgoing command pump, so ring and call-control commands do not wait for the normal heartbeat cycle.
- Android executes accept/reject/hangup through `TelecomManager` when `ANSWER_PHONE_CALLS` permission and device/OEM policy allow it.
- Android returns explicit success/failure detail for unsupported API levels, missing permission, or calls that cannot be controlled.
- Bluetooth is not used.
- Current limitations: live call-control behavior still needs device/OEM validation, `TelecomManager` methods are deprecated but remain the available compatibility path for this minSdk, and no call audio routing is implemented.

### Milestone 3: Outgoing Dialing
- Laptop can request a dial action on phone
- SIM selection works on supported devices or falls back cleanly
- Dialing while the phone is locked is supported where Android permits it and clearly blocked where it does not

Current implementation status:
- Added `DialRequest` and `DialResult` protocol packets.
- Desktop PySide GUI exposes a phone-number field, SIM field, and `Dial` button.
- Desktop defaults the requested SIM slot to `1`.
- Android resolves SIM 1 as logical slot 0 through `SubscriptionManager` when `READ_PHONE_STATE` is granted.
- Android starts a direct `ACTION_CALL` intent when `CALL_PHONE` is granted and includes subscription/account hints where available.
- Dial results report requested SIM slot, whether that SIM resolved, and the resolved subscription ID.
- Live device subscription diagnostics showed SIM 1 maps to logical slot 0 with `subId=3` and carrier `Namaste`; SIM 2 maps to logical slot 1 with `subId=4`.
- Current limitations: OEM dialer/SIM routing may ignore some subscription extras, so the result explicitly reports fallback risk; lock-screen direct dialing still needs live validation.

### Milestone 4: Hardening and Device Matrix
- Test telephony workflows across multiple Android versions and vendor builds
- Document limitations and stable supported feature set
- Confirm whether Bluetooth stays optional or is required only for explicitly named edge cases

Current implementation status:
- Added encrypted `TelephonyDiagnosticsRequest` and `TelephonyDiagnosticsResult` packets.
- Added encrypted `CallMetadataEvent` packets for SIM-call source classification, direction, caller ID when Android exposes it, masked fallback, SIM slot, subscription ID, carrier, video flag, and active phone-side audio route.
- Added encrypted `PhoneCapabilitySnapshot` packets sent after trusted session establishment and included in diagnostics.
- Android reports `READ_PHONE_STATE`, `ANSWER_PHONE_CALLS`, and `CALL_PHONE` permission state.
- Android reports `READ_PHONE_STATE`, `READ_CALL_LOG`, `ANSWER_PHONE_CALLS`, and `CALL_PHONE` permission state.
- Android reports visible SIM slots, subscription IDs, carriers, default voice/data/SMS flags, ringer mode, ring/voice-call volume, wired/Bluetooth SCO availability, speakerphone flag, and route/capability status.
- Android app diagnostics show a compact telephony and phone-capability summary.
- Desktop GUI can refresh telephony diagnostics and displays the latest call metadata plus permission/SIM/ringer/route/capability snapshot.
- Desktop GUI can export a diagnostic text report with identity, endpoint, call state, call metadata, telephony snapshot, and event log.
- Added a validation matrix at [phase_3_telephony_validation_matrix.md](/home/rsnb/Documents/My_projects/PC-mobile/phases_documention/phase_3_telephony_validation_matrix.md).
- Current limitations: caller ID can still be withheld by Android unless `READ_CALL_LOG` is granted or a later default-dialer/calling integration is added; LAN call audio is explicitly reported unsupported, with Bluetooth/HFP still the recommended future audio route.

### Milestone 5: Bluetooth HFP Audio Bridge
- Laptop can be made discoverable/pairable as a Bluetooth audio endpoint.
- Android phone can route SIM call audio to the laptop through the standard Bluetooth HFP/HSP path.
- Linux desktop keeps LAN for metadata/control and uses BlueZ/PipeWire only for audio.

Current implementation status:
- Added a Linux HFP integration helper around `bluetoothctl`, `pactl`, and `wpctl`/PipeWire availability checks.
- Desktop CLI now exposes `hfp-status`, `hfp-pairing`, `hfp-connect`, and `hfp-select-profile`.
- Added encrypted `BluetoothAssistDesktopStatus` and `BluetoothAssistPhoneStatus` packets so the LAN session can exchange Bluetooth adapter identity and user-approved bonding status.
- Desktop GUI now has a `Bluetooth HFP Call Audio` section for readiness status, enabling pairing mode, sending the desktop Bluetooth ID to Android over LAN, trusting/connecting a phone Bluetooth address, and selecting the first available HFP/HSP profile.
- Android requests Nearby Devices permissions and starts a public `BluetoothDevice.createBond()` flow against the desktop Bluetooth address when it receives the assist packet; Android user approval is still required.
- Diagnostic export now includes Bluetooth HFP status.
- This does not implement custom audio packets; SIM call audio is delegated to BlueZ plus PipeWire/WirePlumber because Android does not expose normal-app SIM call audio capture/injection APIs.
- Current limitation: exact HFP profile names and routing behavior depend on distro versions, BlueZ, WirePlumber policy, and the phone's Bluetooth stack. Live validation is still required on the target laptop/phone pair.

### Milestone 6: Background and Sleep Resilience
- Android companion features remain active when the phone screen is off or the UI is backgrounded.
- Long-lived LAN sessions are not owned by an Activity/ViewModel lifecycle.
- User is guided to disable OEM battery restrictions when needed.

Current implementation status:
- Added `LinkableRuntime` at the application level to own `NsdDiscoveryManager` and `PairingManager`.
- Added `LinkableForegroundService` with an ongoing notification, partial wake lock, and high-performance Wi-Fi lock while active.
- `DiscoveryViewModel` now binds to the application runtime instead of creating/shutting down its own managers.
- The app starts the foreground service on launch and requests restart after normal boot.
- Android UI includes an `Allow Unrestricted Battery` action to open battery-optimization exemption settings.
- Current limitation: aggressive OEM battery managers can still require manual unrestricted-battery approval even with a foreground service.

## Deliverables
- Android telephony bridge module
- Linux desktop incoming call UI and action controls
- Outgoing dialing flow from laptop
- SIM selection handling or fallback logic
- Device compatibility matrix and telephony limitations note
- Lock-screen call control behavior note

## Risks and Mitigations
- Android telephony permissions and OEM restrictions vary widely
  - Mitigation: design by capability negotiation and maintain a tested support matrix
- Some devices may block full remote answer or hangup actions
  - Mitigation: show unsupported state instead of pretending support exists
- Locked-phone dialing or call control may differ by vendor and Android version
  - Mitigation: separate supported lock-screen-safe flows from unsupported ones and expose capability state clearly
- Audio handoff to laptop may add major complexity
  - Mitigation: keep call control separate from audio bridging unless required by the product goal
- Dual-SIM behavior may differ between vendors
  - Mitigation: implement fallback to default SIM and explicit user confirmation
- Bluetooth may be requested as a workaround too early
  - Mitigation: require evidence that LAN plus Android APIs cannot support the needed telephony action before introducing Bluetooth

## Exit Criteria
- Incoming call state is mirrored reliably to laptop
- Accept, reject, and hangup work on the supported device set
- Laptop-initiated dialing works with clear state feedback
- Lock-screen-safe call handling and dialing behavior are validated on the supported device set
- SIM handling is either supported or gracefully degraded
- Telephony limitations are documented and visible in UI

## Final Phase Output
At the end of Phase 3, the project should have:
- A secure device-pairing foundation
- Notification, messaging, file transfer, and utility workflows
- Supported telephony control from the Linux laptop to the Android phone
- A LAN-first architecture with Bluetooth minimized or removed unless a proven platform limitation requires it

## Recommended Post-Phase Backlog
- Contact sync and search
- Additional Linux packaging targets and distro validation
- Wi-Fi Direct or hotspot fallback
- Better observability and remote debug bundle export
- Optional call audio routing research as a separate initiative
