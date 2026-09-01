# Architecture and runtime

## System shape

```text
iRig BlueBoard
  BLE-MIDI notifications
          |
          v
BlueBoardClient -> BleMidiDecoder -> Router -> ActionDispatcher
       |                                      |
       | optional momentary LED writes        | queued Katana action
       v                                      v
  LedFeedbackController                 KatanaRuntime worker
                                               |
                                     KatanaSysExSession
                                               |
                                      MidoMidiTransport
                                      input + output
                                               |
                                  Original KATANA-100 MkI
```

The BLE and USB-MIDI lifecycles are independent. A BlueBoard disconnect must not
tear down the Katana worker. A Katana transport failure must not stop BLE event
processing. This separation is a central reliability requirement.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `client.py` | BlueBoard discovery, Bleak connection, Linux compatibility profile, notification delivery, LED packet writes, reconnect loop |
| `ble_midi.py` | Stateful BLE-MIDI packet decoding and encoding |
| `router.py` | Button labeling, channel/CC/edge matching, cooldown, momentary LED projection, dispatch |
| `actions/dispatcher.py` | Harmless log dispatch and opt-in Katana action boundary |
| `config.py` | Typed product configuration, model registry, validation, serialization, starter profiles |
| `katana/commands.py` | Pure Program Change, Control Change, RQ1, and DT1 byte construction |
| `katana/protocol.py` | Strict MkI SysEx parsing, checksum, seven-bit validation, base-128 address arithmetic |
| `katana/parameters.py` | Firmware-scoped evidence/read/write registry for known parameters |
| `katana/transport.py` | Deterministic independent input/output resolution and Mido/RtMidi ownership |
| `katana/session.py` | Bounded serialized requests, reply matching, traffic records, probe targets |
| `katana/runtime.py` | Worker queue, state snapshots, startup/recovery/post-action reads, toggle policy |
| `onboarding.py` | Read-only concurrent discovery, guided config, backups, readiness reports |
| `linuxDiagnostics.py` | Read-only Linux OS, BlueZ, D-Bus, adapter, ALSA, and backend inspection |
| `led_feedback.py` | Coalesced, paced, retry-aware momentary LED writes |
| `cli.py` | Command surface, logging, lifecycle, signals, bounded sessions, metrics |

## BLE input path

`BlueBoardClient` discovers a matching device, establishes a Bleak connection,
subscribes to the BLE-MIDI characteristic, and gives immutable packet copies to
the decoder. `BleMidiDecoder` preserves running status across packets and emits
typed MIDI events. `Router` maps channel-1 CC20-CC23 events to A-D, applies edge
and cooldown rules, logs the physical event, requests momentary LED state when
enabled, and invokes the configured action.

Event-handler failures are logged without terminating notification consumption.
The decoder is reset after disconnect so running status cannot cross connection
epochs.

## Linux BLE compatibility path

Bleak over BlueZ/D-Bus is primary. If BlueZ connects but omits the advertised
BLE-MIDI service, Linux may use the scoped `gatttool` path:

1. discover exactly one BLE-MIDI characteristic;
2. bound its descriptor span;
3. require exactly one `0x2902` CCCD;
4. construct an immutable `BlueBoardGattProfile` for notifications and writes;
5. use the tested `0x0022` value and `0x0023` CCCD fallback only for an exact,
   case-insensitive `iRig BlueBoard` name if valid discovery is unavailable;
6. fail closed for unknown devices or malformed, absent, or duplicate results.

Interactive `gatttool` is used only when LED writes are needed. A health read
detects silent process/connection loss. No persistent pairing or trust mutation
is performed.

## Action boundary

The dispatcher receives a typed `ActionSpec`. In dry-run it reports the action
without sending it. In active mode it submits Katana work and returns promptly;
the action does not block the BLE callback. Only `katana`, harmless `log`, and
`null` bindings are legal.

The worker owns all Katana operations. This provides one ordering domain for
RQ1 queries, Program Change, and Control Change, preventing competing requests
from consuming each other's replies.

## Katana transport and session

Input and output selectors resolve independently. Exact matches win; otherwise a
case-insensitive substring must match exactly one port. Ambiguity is an error.
The session always opens input first so an immediate reply to the first output
request cannot be missed.

Each received message is copied into a queue. A pending SysEx request matches
only a checksum-valid DT1 reply with the configured device ID, expected address,
expected data length, and current connection epoch. Unrelated or late replies
are recorded but cannot satisfy the request. Timeouts and retries are bounded.

## State model

The atomic `AmpStateSnapshot` contains:

- a connection epoch;
- a timestamp;
- optional selected preset;
- six individual `EffectStateValue` entries; and
- source/error data for each value.

Sources distinguish `queried`, `predicted`, `unknown`, and `stale`. The six
individual effects are Boost, Mod, FX, Delay, Reverb, and Effect Loop.

MkI standard MIDI exposes two compound switches:

- Booster/Mod is on if either Boost or Mod is on;
- Delay/FX is on if either Delay or FX is on.

If a required member is unknown and no known member proves the group is on, the
derived group is unknown. Both-on state remains representable; it is not
collapsed into an invented single active member.

## Runtime lifecycle

### Startup

For an active `katana100` profile with `stateSync.enabled=true`, exact firmware
4.00, approved definitions, and both port selectors, the worker:

1. opens input before output;
2. increments the connection epoch;
3. reads all six production-approved flags;
4. publishes one atomic snapshot only after all required reads complete.

If the profile is not eligible, output-only prediction mode is used with an
explicit warning. If an eligible synchronization fails, preset selection can
remain available, but relative toggles are rejected while their group is unknown.

### Program Change

The runtime marks old observations stale, sends the documented Program Change,
loads any labeled preset prediction only for the settling interval, waits for the
temporary patch to settle, and replaces the prediction with a six-effect query.

### Relative toggle

Before toggling a MkI group, the runtime reads the current group members. It
rejects the operation if the group cannot be determined. Otherwise it sends the
opposite standard-MIDI CC value, marks the group stale, reads the group again,
and fails if the observed result does not match the requested state.

### Explicit effect state

An explicit set uses the configured standard-MIDI CC and, when synchronization
is active, verifies the corresponding group afterward. SysEx DT1 is not used for
runtime actuation.

### Recovery

Any input/output failure invalidates the snapshot and closes both directions.
The next Katana operation opens input first, creates a new epoch, and attempts a
full synchronization before continuing. Replies from an older epoch cannot make
new state authoritative.

### Shutdown

Ctrl+C or a duration limit sets the stop event, cancels BLE discovery/backoff,
releases momentary LEDs, joins the Katana worker, closes both MIDI directions,
and emits final metrics. Interrupted runs preserve the intended exit status;
duration-limited runs record `stopReason=duration-limit`.

## LED ownership

Current `--led-feedback` is momentary input feedback: a light mirrors a physical
press and release. It is not amplifier-state feedback and is not coupled to
whether a Katana action succeeds. Writes are serialized and coalesced, all LEDs
are cleared during initialization/cleanup, and release retries are conservative.

Persistent Katana-state LEDs remain out of scope. If added later, they need an
explicit mode and a single state-projection owner; do not overload momentary
feedback.

## Metrics and logs

Structured metrics cover BLE packets/events/actions, connection duration,
reconnects, Katana commands/failures/reconnects, input messages, SysEx
requests/replies/retries/timeouts/checksum/unexpected replies, state sync
attempts/completions/failures, state invalidations, and stop reason. Logs must
distinguish sent intent, predicted state, queried state, mismatch, recovery, and
cleanup.

## Extension rules

- Standard MIDI: add a pure constructor or registry entry, validate ranges,
  route through `KatanaRuntime`, and add command/controller/dispatcher tests.
- SysEx read: add a provenance-labeled `ParameterDefinition`, keep it probe-only
  until exact-firmware evidence exists, then promote only after captured
  reproduction and restoration.
- SysEx write: remains prohibited unless a separately reviewed safe scope,
  physical restoration procedure, and `writeAccess` evidence are approved.
- New platform: retain the shared decoder/router/runtime and add the narrowest
  transport compatibility layer possible.
