# Architecture and extension guide

## Scope

The maintained runtime is the Python package under
`python/src/blueboard_macro_handler`. The project deliberately reuses the stable
BlueBoard Macro Handler lifecycle and adds Katana behavior at the action-dispatch
boundary. The older prototype modules from the source repository were not copied.

## Runtime flow

```text
BLE discovery and reconnect
  -> BlueBoardClient
  -> notification queue
  -> BleMidiDecoder
  -> Router
  -> ActionDispatcher
       -> KatanaController
       -> MidoMidiTransport
       -> BOSS USB-MIDI port

bounded diagnostic path:
CLI -> KatanaSysExProbe -> input-first MidoMidiTransport -> RQ1/DT1
```

### BlueBoard boundary

`client.py` owns BLE discovery, pairing, notification subscription, last-address
persistence, reconnect backoff, the narrow Linux compatibility path, and outbound
momentary LED packets. It does not import Katana code.

`ble_midi.py` decodes the channel-voice subset needed by the BlueBoard.

`router.py` owns press/release normalization, duplicate suppression, cooldowns,
logging, and action-failure isolation. It knows the semantic action description
but not Program Change, Control Change, port names, or effect state.

### Katana boundary

`katana/commands.py` is a pure byte-construction module. JSON uses MIDI channels
1-16; commands use wire channels 0-15. Standard Program Change/Control Change and
Mk I SysEx RQ1/DT1 builders all return complete wire bytes; only the standard
messages are connected to runtime actions. In v0.6.0, RQ1 and the two fixed
editor-handshake DT1 messages are connected only to the bounded diagnostic.

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

`katana/session.py` owns the serialized v0.6.0 diagnostic path. It matches DT1
replies by device ID, address, length, and checksum; retains invalid/unexpected
traffic; applies bounded timeout/retry policy; and attempts editor-mode exit in
`finally`. It never updates `KatanaController` state.

The `configure` command adds a hybrid guided discovery layer above that
transport. It selects unique devices automatically, presents numbered choices
for ambiguous outputs or BlueBoards, requires an explicit model in
non-interactive mode, shows the complete mapping, and confirms predicted-state
assumptions before writing. Replacements create timestamped ignored backups. It
lists outputs but never opens one, so configuration cannot change the amplifier.

`katana/controller.py` owns lazy output opening, Program Change, effect state,
predicted state updates, one-command failure accounting, and reopen-on-next-action.
It never guesses an unknown toggle state.

`katana/parameters.py` contains the firmware-scoped SysEx observation registry.
The six original-KATANA temporary-patch effect flags are recorded as community or
legacy Mk I probe candidates with `firmwareRange: unknown`. None is production
readable or writable. Evidence provenance and read/write authorization are
separate fields so a community address cannot become safe merely by being listed.

### Onboarding boundary

`onboarding.py` owns first-run discovery, profile drafting, and readiness
evaluation. `DiscoverySnapshot` gathers MIDI output enumeration, BlueBoard BLE
discovery, Python compatibility, and existing-configuration inspection without
opening an output. MIDI enumeration runs in a worker thread while BLE discovery
runs in the asyncio loop. The resulting snapshot is passed directly to both
configuration generation and `ReadinessReport`; onboarding does not parse its own
console output or repeat successful discovery.

Interactive onboarding can refresh only a failed discovery source. Standalone
`doctor` deliberately gathers a new snapshot so it describes current hardware
rather than onboarding-time state. Configuration and state files are written only
after readiness passes and the user confirms the proposed mapping.

### Side-effect boundary

`ActionDispatcher.invoke()` always logs the requested action. Unless the process
was started with `--execute-actions`, it returns before obtaining a keyboard
backend or Katana controller. `midi-inputs` and `midi-outputs` only enumerate
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
It never opens the MIDI output, sends a command, or changes saved state.

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

The MkII profile uses CC16-CC21 for independent effect switches. The original
KATANA-100 profile uses CC16 Booster/Mod, CC17 Delay/FX, CC18 Reverb, and CC19
Send/Return. Overrides are accepted for controlled experiments, but Tone Studio
settings for the connected model are authoritative.

## Lifecycle and failure behavior

- The Katana output is opened lazily on the first executed Katana action.
- Dry-run never imports Mido or opens a port.
- A send/open failure increments `katanaCommandFailures`, closes the transport,
  leaves BLE consumption running, and reaches the router's exception boundary.
- The next action retries opening and increments `katanaReconnects` after the
  first successful open.
- Ctrl+C and normal shutdown call `ActionDispatcher.close()`, which closes both
  initialized keyboard and Katana backends.
- Selecting a preset replaces predicted effect state with the configured state
  for that preset. Missing state remains unknown.

## Metrics

The inherited runtime metrics are preserved. Katana adds:

- `katanaCommands`;
- `katanaCommandFailures`;
- `katanaReconnects`.

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

## Extending SysEx after v0.6.0

Do not add raw addresses to button bindings. Add a `ParameterDefinition` with:

- logical name;
- four-byte seven-bit address;
- data length and decoder;
- exact model and firmware range;
- evidence category, read access, write access, safety notes, and fixture reference.

Community and legacy definitions may be used only by the bounded probe.
Production reads and validated writes require `official` or reproduced
`capturedMkI` evidence plus explicit access authorization. Production
synchronization still needs a dedicated worker, transaction guard, reconnect
epoch/invalidation, coherent snapshots, and post-action verification. The router
must never block waiting for a response.

## Branch and release process

Use `feature/<name> -> dev -> main`. Keep `main` release-ready. Do not tag a stable
version until automated checks pass on Windows and Linux and the hardware checklist
has been recorded for the target KATANA model.
