# Lock-Screen Policy

This document records the policy expectations for features that must interact with the phone while it is locked.

Milestone 1 does not implement any lock-screen-sensitive feature. It only defines the policy boundary so later phases do not guess.

## Policy Principles

- trust alone is not enough; platform support must also exist
- capabilities must declare whether an action is supported while locked
- unsupported lock-screen behavior must fail explicitly, not silently degrade into insecure behavior
- future UI must clearly explain when an action is unavailable because the device is locked

## Phase Mapping

| Feature | Phase | While Locked | Policy Status |
|---|---:|---|---|
| Discovery | 1 | Not required | Allowed when app background policy permits |
| Pairing initiation | 1 | Not expected | User-facing pairing should assume unlocked interaction |
| Trusted reconnect | 1 | Expected | Allowed after trust is established |
| Ping / DeviceInfo / Capabilities | 1 | Expected | Allowed if transport is already trusted |
| Notification mirroring | 2 | Expected | Must be capability-gated |
| Message read from notification payload | 2 | Expected where Android permits | Must be capability-gated |
| Message reply via notification action | 2 | Expected where Android permits | Must be capability-gated |
| Ring phone to find device | 2 | Expected | Must remain auditable and rate-limited |
| Incoming call state mirror | 3 | Expected | Must be capability-gated |
| Accept or reject call remotely | 3 | Desired, not assumed | Must require explicit support declaration |
| Outgoing dialing from laptop | 3 | Desired, not assumed | Must require explicit support declaration |

## Capability Flags Reserved For Later Phases

- `message_reply_while_locked`
- `call_control_while_locked`
- `dial_while_locked`
- `screen_lock_state_reporting`

## Enforcement Requirements

Later milestone implementations must:

- check trust before any remote action
- check the declared capability before exposing the action
- surface a specific error if the platform or policy blocks the action
- avoid introducing Bluetooth as a shortcut around missing lock-state policy decisions

## Android Considerations For Later Phases

This protocol note does not assume every Android version or OEM permits:

- remote notification replies while locked
- telephony control while locked
- background execution needed for persistent call control

Those must be treated as runtime capability questions, not compile-time assumptions.

