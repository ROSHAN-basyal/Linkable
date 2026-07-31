# Lock-Screen Policy

Linkable never treats a trusted peer as permission to bypass Android's lock
screen or platform security model.

## Rules

- Trusted reconnect and passive event delivery may continue while locked when
  Android background policy permits it.
- Every remote action requires an authenticated session and the corresponding
  Android permission or app-provided action.
- The UI exposes an action only when the phone reports the relevant capability.
- Unsupported lock-screen behavior returns an explicit result instead of
  silently attempting a weaker path.
- Pairing, camera approval, storage selection, and permission grants remain
  user-visible Android interactions.

## Capability Flags

- `message_reply_while_locked`
- `call_control_while_locked`
- `dial_while_locked`
- `screen_lock_state_reporting`

Availability varies by Android version, OEM policy, default-dialer status, and
the source application's notification actions. Bluetooth does not bypass these
requirements.
