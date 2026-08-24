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
1-16; commands use wire channels 0-15.

`katana/transport.py` owns Mido/RtMidi and port resolution. Selection order is:

1. case-sensitive exact name;
2. case-insensitive exact name;
3. one unique case-insensitive substring;
4. otherwise fail with the available or ambiguous names.

The `configure` command adds a user-facing discovery layer above that transport.
It selects a Katana-named port only when exactly one main, non-`CTRL`/`DAW`
candidate exists, discovers the strongest matching BlueBoard advertisement,
writes an ignored local starter profile, and persists the address. It lists
outputs but never opens one, so configuration cannot change the amplifier.

`katana/controller.py` owns lazy output opening, Program Change, effect state,
predicted state updates, one-command failure accounting, and reopen-on-next-action.
It never guesses an unknown toggle state.

`katana/parameters.py` reserves the firmware-scoped SysEx registry. It ships
empty. A checksum helper and evidence model exist, but no production SysEx address
or write path is enabled.

### Side-effect boundary

`ActionDispatcher.invoke()` always logs the requested action. Unless the process
was started with `--execute-actions`, it returns before obtaining a keyboard
backend or Katana controller. `midi-outputs` is read-only. `katana-test` is a
separate, explicit hardware command that requires both the output and MIDI data.
The guided `configure` command is also MIDI-read-only; its side effects are
limited to local configuration and last-address files.

`probe-effects` is the bounded exception for physical effect discovery. It sends
one documented Program Change and only CC16-CC21, waits for a human observation
between state changes, records no claim automatically, and attempts an OFF
cleanup if interrupted. Arbitrary CC scanning and SysEx remain outside this path.

## Configuration model

The optional top-level `katana` object has:

- `outputName`: exact or unique substring for the MIDI output;
- `midiChannel`: JSON channel 1-16;
- `model`: currently only `katana100MkII`;
- `firmware`: recorded provenance, not an automatic compatibility claim;
- `effectControls`: supported effect name to CC;
- `presetStates`: preset number to predicted on/off values.

Supported standard-MIDI actions are:

- `selectPreset` with `preset` 0-127;
- `setEffectState` with `effect` and `enabled`;
- `toggleEffect` with `effect`.

The documented profile uses CC16-CC21. Overrides are accepted for controlled
experiments but must not be represented as official without model/firmware evidence.

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

Future bidirectional work may add queries, timeouts, and authoritative state
updates only when there is a real input-session implementation.

## Adding a standard Katana command

1. Verify the message in official documentation or a captured MkII fixture.
2. Add typed fields and strict validation in `config.py`.
3. Add a pure constructor in `katana/commands.py` if the message shape is new.
4. Implement the behavior in `KatanaController.execute()`.
5. Add an action description without teaching the router MIDI details.
6. Add config, command, controller, dispatcher, dry-run, failure, and close tests.
7. Update both config examples and all relevant documentation.
8. Record physical evidence separately from source/test evidence.

## Adding SysEx later

Do not add raw addresses to button bindings. Add a `ParameterDefinition` with:

- logical name;
- four-byte seven-bit address;
- data length and range;
- exact model and firmware;
- evidence category and fixture reference.

Only `official` and reproduced `capturedMkII` entries should write by default.
Queries need a MIDI input, response matcher, bounded worker, timeout, and reconnect
cleanup. The router must never block waiting for a response.

## Branch and release process

Use `feature/<name> -> dev -> main`. Keep `main` release-ready. Do not tag a stable
version until automated checks pass on Windows and Linux and the hardware checklist
has been recorded for the KATANA-100 MkII.
