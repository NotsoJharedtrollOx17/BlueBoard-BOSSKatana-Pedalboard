# Architecture and extension guide

## Scope

The maintained runtime is the Python package under
`python/src/blueboard_macro_handler`. The namespace is retained for import
compatibility, but the product is a Katana pedalboard rather than a general macro
handler. Keyboard injection, UDP, process launch, and their operating-system
backends are intentionally absent.

## Runtime flow

```text
BLE discovery and reconnect
  -> BlueBoardClient
  -> notification queue
  -> BleMidiDecoder
  -> Router
  -> ActionDispatcher
       -> KatanaRuntime single-worker queue
       -> KatanaSysExSession
       -> MidoMidiTransport
       -> BOSS USB-MIDI port

bounded diagnostic path:
CLI -> KatanaSysExProbe -> input-first MidoMidiTransport -> RQ1/DT1
```

### BlueBoard boundary

`client.py` owns BLE discovery, notification subscription, last-address
persistence, reconnect backoff, the narrow Linux compatibility path, and outbound
momentary LED packets. It does not import Katana code.

Bleak is the primary Linux transport over BlueZ/D-Bus. If BlueZ omits the
advertised BLE-MIDI service after connecting, an immutable
`BlueBoardGattProfile` scopes every notification and write. The compatibility
path asks `gatttool` for exactly one BLE-MIDI characteristic and exactly one
`0x2902` CCCD inside its descriptor span. Failed validation may fall back to the
tested `0x0022`/`0x0023` profile only for a device advertised exactly as
`iRig BlueBoard` ignoring case. Unknown names, missing tools, malformed output,
duplicate characteristics/descriptors, and missing descriptors fail closed.
Neither path pairs, trusts, or edits persistent BlueZ device state.

`ble_midi.py` decodes the channel-voice subset needed by the BlueBoard.

`router.py` owns press/release normalization, duplicate suppression, cooldowns,
logging, and action-failure isolation. It knows the semantic action description
but not Program Change, Control Change, port names, or effect state.

### Katana boundary

`katana/commands.py` is a pure byte-construction module. JSON uses MIDI channels
1-16; commands use wire channels 0-15. Standard Program Change/Control Change and
Mk I SysEx RQ1/DT1 builders all return complete wire bytes. Standard PC/CC remains
the runtime actuation plane; v0.7.0 adds production-approved RQ1 reads as a state
sensor. The two fixed editor-handshake DT1 messages remain diagnostic-only.

`katana/protocol.py` owns the Mk I frame constants, typed parser, seven-bit
validation, base-128 address arithmetic, and Roland checksum logic. The parser
requires callers to distinguish full-wire messages from Mido payloads, preventing
`F0`/`F7` indexes from leaking into normalized frames.

`katana/transport.py` owns Mido/RtMidi and port resolution. Selection order is:

1. case-sensitive exact name;
2. case-insensitive exact name;
3. one unique case-insensitive substring;
4. otherwise fail with the available or ambiguous names.

Inputs and outputs resolve independently. The duplex diagnostic opens the input
first so its callback is installed before a request can trigger an immediate
reply. The callback only copies the message and monotonic timestamp into a queue.
On Linux, onboarding independently derives a stable selector for each direction:
it considers removal of a trailing ALSA `client:port` coordinate and a redundant
client prefix, then saves the shortest candidate that still uniquely resolves to
the chosen full name. Ambiguity preserves the longer selector.

`katana/session.py` owns the shared serialized request matcher. It matches DT1
replies by device ID, address, length, and checksum; retains invalid/unexpected
traffic; applies bounded timeout/retry policy; and attempts editor-mode exit in
`finally` for the diagnostic current-selection operation. The diagnostic wrapper
records traffic; the runtime consumes only production-approved effect observations.

The `configure` command adds a hybrid guided discovery layer above that
transport. It selects unique devices automatically, presents numbered choices
for ambiguous outputs or BlueBoards, requires an explicit model in
non-interactive mode, shows the complete mapping, and confirms predicted-state
assumptions before writing. Replacements create timestamped ignored backups. It
lists outputs but never opens one, so configuration cannot change the amplifier.

`katana/runtime.py` owns one worker queue for all runtime RQ1, Program Change, and
Control Change operations. It opens input before output, publishes atomic six-flag
snapshots, preserves individual members of grouped controls, invalidates connection
epochs on failure, and attempts bootstrap again on reopen. BLE event handling never
waits for a SysEx timeout. `katana/controller.py` retains the compatibility name.

`katana/parameters.py` contains the firmware-scoped SysEx observation registry.
Six original-KATANA v4.00 temporary-patch effect flags are captured-Mk-I,
production-readable definitions. None is writable. Evidence provenance and
read/write authorization remain separate so an address cannot become safe merely
by being listed.

### Onboarding boundary

`onboarding.py` owns first-run discovery, profile drafting, and readiness
evaluation. `DiscoverySnapshot` gathers MIDI input/output enumeration, BlueBoard BLE
discovery, Python compatibility, and existing-configuration inspection without
opening an output. MIDI enumeration runs in a worker thread while BLE discovery
runs in the asyncio loop. The resulting snapshot is passed directly to both
configuration generation and `ReadinessReport`; onboarding does not parse its own
console output or repeat successful discovery.

Interactive onboarding can refresh only a failed discovery source. Standalone
`doctor` deliberately gathers a new snapshot so it describes current hardware
rather than onboarding-time state. Configuration and state files are written only
after readiness passes and the user confirms the proposed mapping.

On Linux, doctor also reports distribution support, kernel, architecture, BlueZ
version/service/D-Bus/adapter readiness, `gatttool`, ALSA sequencer state,
Mido/RtMidi versions and APIs, saved and resolved selectors, the configured
model/firmware, six production-approved effect definitions, and scan results.
It continues to enumerate only: it never opens either MIDI direction.

### Side-effect boundary

`ActionDispatcher.invoke()` always logs the requested action. Unless the process
was started with `--execute-actions`, Katana actions remain dry-run. Harmless
`log` actions never actuate hardware, and momentary LED feedback is independently
controlled by `--led-feedback`. `midi-inputs` and `midi-outputs` only enumerate
ports. `sysex-probe` is a confirmed, predefined read diagnostic; its only DT1
output is the fixed current-selection editor handshake. `katana-test` is a
separate, explicit hardware command that requires both the output and MIDI data.
The guided `configure` command is also MIDI-read-only; its side effects are
limited to local configuration and last-address files.

`probe-effects` is a bounded, model-aware exception for physical effect
discovery. It derives its model, channel, first Program Change, switch labels,
and controllers from the selected configuration. Raw-output use requires an
explicit model. It waits for a human observation between state changes, records
no claim automatically, and attempts an OFF cleanup if interrupted. Arbitrary CC
scanning and runtime SysEx remain outside this path.

`doctor` is a repeatable read-only readiness check. It validates Python,
configuration loading, MIDI backend/output resolution, and BlueBoard discovery.
It never opens a MIDI port, sends a command, or changes saved state.

`onboard` composes the read-only discovery, configuration, and doctor boundaries
into one workflow. Its only possible side effects are confirmed local
configuration, backup, and last-address writes.

## Configuration model

One internal profile registry is the source for model names, default controls,
grouped/independent labels, layouts, wizard summaries, validation defaults, and
effect probing. The optional top-level `katana` object remains backward-compatible
and has:

- `outputName`: exact or unique substring for the MIDI output;
- `midiChannel`: JSON channel 1-16;
- `model`: `katana100` for the original grouped-switch profile, or
  `katana100MkII` for the independent-switch MkII profile;
- `firmware`: recorded provenance, not an automatic compatibility claim;
- `effectControls`: supported effect name to CC;
- `presetStates`: preset number to predicted on/off values.

Supported standard-MIDI actions are:

- `selectPreset` with `preset` 0-127;
- `setEffectState` with `effect` and `enabled`;
- `toggleEffect` with `effect`.

At the JSON binding boundary, only `{"type": "katana", ...}` and harmless
`{"type": "log", "message": ...}` actions are accepted; `null` leaves a button
unmapped. Removed keyboard, UDP, launch, and legacy macro aliases produce a
migration-oriented configuration error.

The MkII profile uses CC16-CC21 for independent effect switches. The original
KATANA-100 profile uses CC16 Booster/Mod, CC17 Delay/FX, CC18 Reverb, and CC19
Send/Return. Overrides are accepted for controlled experiments, but Tone Studio
settings for the connected model are authoritative.

## Lifecycle and failure behavior

- A state-sync-enabled active run starts its Katana worker and performs a bounded
  bootstrap before BlueBoard discovery. Legacy profiles retain lazy output opening.
- Dry-run never imports Mido or opens a port.
- A send/open failure closes both directions, increments the connection epoch,
  invalidates observed state, and leaves BLE consumption running.
- The next queued Katana operation reopens input before output and attempts a
  bounded resync. Unknown toggles are rejected; preset selection remains available.
- Ctrl+C and normal shutdown drain the Katana queue, close both ports, and join
  the worker before returning.
- Selecting a preset briefly loads its configured prediction, labels the earlier
  snapshot stale, waits on the Katana worker for the temporary patch to settle,
  and replaces the prediction with six queried values.
- A toggle refreshes the live temporary patch before deriving the opposite value,
  sends its standard-MIDI CC, and reads back afterward. A mismatch is counted and
  reported as a failed action rather than confirmed state.

## Metrics

The inherited runtime metrics are preserved. Katana adds:

- `katanaCommands`;
- `katanaCommandFailures`;
- `katanaReconnects`.
- `katanaStateSyncs`, `katanaStateSyncFailures`, and `katanaStateMismatches`;
- `katanaStateInvalidations` and `katanaInputReconnects`.

Bounded session runs also add `stopReason=duration-limit` to the final summary;
Ctrl+C records `stopReason=interrupted`.

The v0.6.0 diagnostic also records input messages, SysEx requests/replies,
timeouts, retries, checksum failures, and unexpected replies. These metrics do
not imply authoritative runtime state.

## Adding a standard Katana command

1. Verify the message in official documentation, the model-correct Tone Studio
   receive settings, or a captured fixture from the same model and firmware.
2. Add typed fields and strict validation in `config.py`.
3. Add a pure constructor in `katana/commands.py` if the message shape is new.
4. Implement the behavior in `KatanaController.execute()`.
5. Add an action description without teaching the router MIDI details.
6. Add config, command, controller, dispatcher, dry-run, failure, and close tests.
7. Update both config examples and all relevant documentation.
8. Record physical evidence separately from source/test evidence.

## Extending SysEx after v0.7.0

Do not add raw addresses to button bindings. Add a `ParameterDefinition` with:

- logical name;
- four-byte seven-bit address;
- data length and decoder;
- exact model and firmware range;
- evidence category, read access, write access, safety notes, and fixture reference.

Community and legacy definitions may be used only by the bounded probe.
Production reads and validated writes require `official` or reproduced
`capturedMkI` evidence plus explicit access authorization. v0.7.0 supplies the
worker, transaction guard, reconnect epoch/invalidation, coherent bootstrap,
post-PC synchronization, and read-actuate-verify toggles. The router never blocks
waiting for a response; the single Katana worker owns every transaction.

## Branch and release process

Use `feature/<name> -> dev -> main`. Keep `main` release-ready. Do not tag a stable
version until automated checks pass on Windows and Linux and the hardware checklist
has been recorded for the target KATANA model.
