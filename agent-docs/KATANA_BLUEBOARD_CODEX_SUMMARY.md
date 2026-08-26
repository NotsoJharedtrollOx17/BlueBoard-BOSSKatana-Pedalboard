# iRig BlueBoard Macro Handler v1.0.0 -> BOSS Katana bridge

> **Hardware correction, 2026-08-23:** the user's amplifier is the original
> 100 W KATANA-100 (MkI), not the KATANA-100 MkII assumed by the initial design
> brief. The connected Tone Studio system page verified grouped assignments:
> CC16 Booster/Mod, CC17 Delay/FX, CC18 Reverb, and CC19 Send/Return. Program
> Change 0 selects A:CH1. The Windows A/C/D BlueBoard path is physically
> validated with the `katana100` profile. Treat the MkII material below as
> retained design research for a separate supported profile, not evidence about
> the user's amplifier. See `protocol-evidence-and-hardware-validation.md` for
> the dated evidence and the Tone Studio generation edge case.

> **v0.2.0 implementation note:** the maintained CLI now uses a shared
> model/profile registry, a guided configuration wizard, a read-only `doctor`
> command, and a profile-aware probe. Earlier MkII-first configuration and
> MkII-only probe instructions below are historical design context rather than
> the current first-run procedure.

## Codex implementation brief

Status: implementation analysis, revised against the stable Macro Handler release on 2026-08-18.

This document supersedes the earlier Katana bridge brief. The source of truth is the tagged `v1.0.0` release of [`iRigBlueBoard-Macro-Handler`](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/tree/v1.0.0), resolved locally to commit `64e962ee571fb416ea5a26d0a0a00c80ec8cba3b`.

All project-owned variables, functions, methods, and parameters in this brief use camelCase. Types follow the repository's existing PascalCase convention.

## 1. Executive decision

Extend the existing Python 3.10 package first. Do not build a separate BlueBoard input path, replace the router, or introduce a second state machine.

```text
BlueBoardClient -> BleMidiDecoder -> Router -> ActionDispatcher
                                              -> KatanaController
                                              -> MidiTransport
                                              -> BOSS Katana MkII USB MIDI
```

The stable repository already solves BLE discovery, reconnection, decoding, duplicate suppression, press/release edge routing, dry-run safety, logging, metrics, Windows/Linux operation, and BlueBoard momentary LED feedback. The Katana work should begin at the existing `ActionDispatcher` boundary.

Recommended order:

1. Python 3.10, standard Program Change and configurable Control Change.
2. Verified effect on/off behavior on the physical Katana MkII 100.
3. A firmware-scoped SysEx parameter registry and query/write layer.
4. Optional amplifier-state feedback to BlueBoard LEDs as a new semantic mode.
5. C++17 port only after Python behavior and hardware fixtures are stable.

## 2. Verified v1.0.0 baseline

The release is a Python package named `blueboard-macro-handler`, requires Python 3.10 or newer, and depends on Bleak. It contains no maintained C++ implementation; its extension guide treats C++17 as a deferred native port.

The maintained runtime is under `python/src/blueboard_macro_handler/`. The camelCase modules directly under `python/src/` are retained milestone implementations. New Katana work belongs in the package namespace.

The stable BlueBoard contract is:

| Button | MIDI input | Router edge |
|---|---|---|
| A | channel 1, CC20, value 127/0 | press/release |
| B | channel 1, CC21, value 127/0 | press/release |
| C | channel 1, CC22, value 127/0 | press/release |
| D | channel 1, CC23, value 127/0 | press/release |

The router treats values 64–127 as pressed and 0–63 as released. It tracks `(channel, controller)` state, suppresses duplicate edges, applies binding cooldowns, invokes actions behind an exception boundary, and clears managed state after disconnect.

The v1.0.0 configuration supports `keyboard`, `log`, `udp`, and `launch` actions. Actions are dry-run unless `--execute-actions` is supplied. BlueBoard LED feedback is independently opt-in through `--led-feedback`.

The tagged source was installed in an isolated environment and checked without modification:

```text
59 unit tests passed
Ruff passed
```

This is source-level validation, not Katana hardware validation.

## 3. Corrections to the earlier design

| Earlier assumption | v1.0.0 reality | Revised decision |
|---|---|---|
| Shared C++ and Python runtime | Maintained runtime is Python only | Implement Python first; keep C++ in a future port |
| `tap`, `longPress`, `doubleTap` events | Router exposes press/release only | Do not use gestures until a tested gesture layer exists |
| New standalone sequencer | `Router` already owns edges, cooldowns, and dispatch | Extend typed actions |
| LEDs can show effect state immediately | Current LEDs mirror physical button state | Amplifier-state LEDs need a new mode and source of truth |
| Fixed Katana effect CCs | Receive assignments are configurable | Store CC assignments in config and match Tone Studio |
| Original Katana SysEx applies to MkII | Maps are reverse-engineered and firmware-sensitive | Require MkII capture or physical validation |

## 4. Repository changes

Add:

```text
python/src/blueboard_macro_handler/katana/
  __init__.py
  commands.py
  controller.py
  parameters.py
  transport.py
```

Modify only the existing integration points:

```text
config.py
router.py
actions/dispatcher.py
cli.py
models.py
default_config.json
python/config/blueboard.json
pyproject.toml
```

Add:

```text
python/tests/testKatanaCommands.py
python/tests/testKatanaConfig.py
python/tests/testKatanaController.py
python/tests/testKatanaTransport.py
python/tests/testKatanaActions.py
```

Do not put Katana USB-MIDI code in `client.py`. `BlueBoardClient` owns the BLE pedal connection and must remain independent of the amplifier.

## 5. Configuration design

Add an optional top-level `katana` object and typed `katana` actions. Preserve the existing device and binding schemas.

```json
{
  "device": {
    "name": "BlueBoard",
    "scanTimeout": 8.0,
    "pair": false
  },
  "katana": {
    "outputName": "KATANA",
    "inputName": "KATANA",
    "midiChannel": 1,
    "model": "katana100MkII",
    "firmware": "2.00",
    "effectControls": {
      "booster": 16,
      "mod": 17,
      "fx": 18,
      "delay": 19,
      "reverb": 20
    },
    "presetStates": {
      "0": {"booster": false, "delay": false},
      "1": {"booster": true, "delay": false}
    }
  },
  "bindings": [
    {
      "cc": 20,
      "channel": 1,
      "edge": "press",
      "cooldownMs": 250,
      "action": {"type": "katana", "command": "selectPreset", "preset": 0}
    },
    {
      "cc": 21,
      "channel": 1,
      "edge": "press",
      "cooldownMs": 250,
      "action": {"type": "katana", "command": "selectPreset", "preset": 1}
    },
    {
      "cc": 22,
      "channel": 1,
      "edge": "press",
      "cooldownMs": 250,
      "action": {"type": "katana", "command": "toggleEffect", "effect": "booster"}
    },
    {
      "cc": 23,
      "channel": 1,
      "edge": "press",
      "cooldownMs": 250,
      "action": {"type": "katana", "command": "toggleEffect", "effect": "delay"}
    }
  ]
}
```

The sample CC numbers are examples, not universal Katana constants. Values configured in BOSS Tone Studio must match them.

### Validation rules

- `outputName` is a non-empty string.
- `inputName` is optional for standard MIDI and required for SysEx queries.
- `midiChannel` is 1–16 in JSON and converted to 0–15 only in message construction.
- `model` is an explicit supported profile.
- `firmware` is retained and checked before SysEx is enabled.
- Effect CCs are 0–127 and unique unless duplicates are explicitly supported.
- Preset numbers are 0–127 internally.
- Effects come from a fixed supported set.
- `toggleEffect` requires known initial or preset state.
- SysEx actions are rejected unless definitions are validated for model and firmware.

Update both default configuration files when defaults change. The stable default should remain harmless: C and D should not control an amplifier until the user explicitly selects a Katana configuration.

## 6. Python type model

Extend `ActionSpec` only with required Katana fields:

```python
@dataclass(frozen=True)
class ActionSpec:
    type: str
    keys: tuple[str, ...] = ()
    message: str = ""
    host: str = "127.0.0.1"
    port: int = 0
    program: str = ""
    args: tuple[str, ...] = ()
    command: str = ""
    preset: int | None = None
    effect: str = ""
    enabled: bool | None = None
    parameter: str = ""
    value: int | float | None = None
```

Accepted commands:

```text
selectPreset
setEffectState
toggleEffect
setEffectParameter
queryEffectState
```

Only the first three are required for the standard-MIDI milestone. The last two remain unavailable until SysEx validation.

Add to `router.actionDescription()`:

```python
if action.type == "katana":
    target = action.effect or action.preset
    return f"katana:{action.command}:{target}"
```

The router must not learn Program Change, CC, SysEx, USB port names, or effect semantics.

## 7. Standard MIDI command layer

`commands.py` should be pure and unit-testable:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class MidiCommand:
    data: tuple[int, ...]


def createProgramChange(midiChannel: int, preset: int) -> MidiCommand:
    if not 0 <= midiChannel <= 15:
        raise ValueError("MIDI channel must be from 0 to 15")
    if not 0 <= preset <= 127:
        raise ValueError("preset must be from 0 to 127")
    return MidiCommand((0xC0 | midiChannel, preset))


def createControlChange(midiChannel: int, controller: int, value: int) -> MidiCommand:
    if not 0 <= midiChannel <= 15:
        raise ValueError("MIDI channel must be from 0 to 15")
    if not 0 <= controller <= 127 or not 0 <= value <= 127:
        raise ValueError("controller and value must be from 0 to 127")
    return MidiCommand((0xB0 | midiChannel, controller, value))
```

This module should not import Mido, RtMidi, ALSA, WinMM, or Bleak.

Program Change is the first hardware proof:

```python
command = createProgramChange(midiChannel=0, preset=0)
```

The Program Map in BOSS Tone Studio determines the selected Katana channel. Do not assume user-facing program numbers and wire values use the same one-based notation.

For a configured effect CC:

```python
command = createControlChange(
    midiChannel=0,
    controller=effectController,
    value=127 if enabled else 0,
)
```

This controls bypass state for the effect stored in the preset. It does not imply arbitrary effect types or internal parameters are available through ordinary CC.

## 8. Transport for Windows and Linux

Use one Python interface and a Mido/RtMidi implementation:

```python
from typing import Protocol


class MidiTransport(Protocol):
    def listOutputNames(self) -> tuple[str, ...]: ...
    def open(self, outputName: str) -> None: ...
    def send(self, command: MidiCommand) -> None: ...
    def close(self) -> None: ...
```

Suggested optional dependency:

```toml
[project.optional-dependencies]
katana = [
  "mido>=1.3,<2",
  "python-rtmidi>=1.5,<2"
]
```

Match an exact port name first. Allow substring matching only when it yields one result. Never silently select the first arbitrary MIDI output.

```python
class MidoMidiTransport:
    def __init__(self) -> None:
        self.outputPort = None

    def listOutputNames(self) -> tuple[str, ...]:
        import mido
        return tuple(mido.get_output_names())

    def open(self, outputName: str) -> None:
        import mido
        self.outputPort = mido.open_output(outputName)

    def send(self, command: MidiCommand) -> None:
        import mido
        if self.outputPort is None:
            raise RuntimeError("Katana MIDI output is not open")
        message = mido.Message.from_bytes(list(command.data))
        self.outputPort.send(message)

    def close(self) -> None:
        if self.outputPort is not None:
            self.outputPort.close()
            self.outputPort = None
```

### Windows

- Connect the Katana with a USB data cable.
- Install or allow Windows to install the official BOSS driver.
- RtMidi normally uses a Windows multimedia MIDI backend.
- Confirm an output containing `KATANA` is listed before running the bridge.
- Keep the Katana driver lifecycle separate from BlueBoard BLE.

### Linux

- Connect the Katana through USB.
- Confirm it with `aconnect -l`, `amidi -l`, or Mido port listing.
- RtMidi normally uses ALSA MIDI.
- Do not use `libusb` while ALSA works; it adds endpoint claiming and USB-MIDI framing.
- Leave the BlueBoard-specific `gatttool` fallback untouched.

Add read-only and explicit test commands:

```text
blueboard midi-outputs
blueboard katana-test --output "KATANA" --program 0
```

The test must require an explicit output and send only documented standard MIDI. It must not enable SysEx automatically.

## 9. Katana controller and state

```python
class KatanaController:
    def __init__(self, config: KatanaConfig, transport: MidiTransport) -> None:
        self.config = config
        self.transport = transport
        self.currentPreset: int | None = None
        self.effectState: dict[str, bool] = {}

    def selectPreset(self, preset: int) -> None:
        self.transport.send(createProgramChange(self.config.midiChannel - 1, preset))
        self.currentPreset = preset
        self.effectState = dict(self.config.presetStates.get(preset, {}))

    def setEffectState(self, effect: str, enabled: bool) -> None:
        controller = self.config.effectControls[effect]
        self.transport.send(
            createControlChange(
                self.config.midiChannel - 1,
                controller,
                127 if enabled else 0,
            )
        )
        self.effectState[effect] = enabled

    def toggleEffect(self, effect: str) -> None:
        if effect not in self.effectState:
            raise RuntimeError(f"effect state is unknown: {effect}")
        self.setEffectState(effect, not self.effectState[effect])
```

Failing on unknown toggle state is preferable to pretending synchronization. Preset configuration can establish expected state, but that state becomes stale if the panel, GA-FC, or Tone Studio changes it. The long-term fix is SysEx query and synchronization, not more local guessing.

## 10. ActionDispatcher integration

Follow the v1.0.0 extension recipe:

1. Extend `ActionSpec` and strict parsing.
2. Extend `configAsDict()`.
3. Extend `actionDescription()`.
4. Add Katana execution behind `self.execute`.
5. Close transport in `ActionDispatcher.close()`.
6. Add dry-run, execution, error, and logging tests.

Conceptual change:

```python
class ActionDispatcher:
    def __init__(self, execute: bool = False, keyboard=None, katana=None) -> None:
        self.execute = execute
        self.keyboard = keyboard
        self.katana = katana

    def invoke(self, action: ActionSpec) -> bool:
        self.logAction(action)
        if not self.execute or action.type == "log":
            return False
        if action.type == "katana":
            if self.katana is None:
                raise RuntimeError("Katana controller is not configured")
            self.katana.execute(action)
            return True
        return self.invokeExistingAction(action)
```

The real change must preserve existing logging and keyboard/UDP/launch branches. Do not refactor unrelated stable behavior in the same commit.

## 11. Effects in a particular preset

### Goal A: Live stompbox behavior

```text
Button A -> Program Change -> preset 1
Button B -> Program Change -> preset 2
Button C -> configured CC -> booster on/off
Button D -> configured CC -> delay on/off
```

This is the recommended first release. Effect type, color assignment, and detailed parameters remain stored in the Katana preset.

### Goal B: Change type or internal parameters

Examples include booster type, drive, delay type/time, and reverb type. These require a verified SysEx address and value codec unless the parameter is explicitly mapped to standard MIDI by the amplifier.

Do not place raw addresses in button bindings. Use a registry:

```python
@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    address: tuple[int, int, int, int]
    dataLength: int
    minimum: int
    maximum: int
    model: str
    firmware: str
    evidence: str
```

```python
parameterDefinitions = {
    "booster.drive": ParameterDefinition(
        name="booster.drive",
        address=(0x00, 0x00, 0x00, 0x00),
        dataLength=1,
        minimum=0,
        maximum=100,
        model="katana100MkII",
        firmware="2.00",
        evidence="unverifiedPlaceholder",
    )
}
```

The zero address is deliberately invalid as a production mapping. Runtime must reject `unverifiedPlaceholder` definitions so an example cannot become an accidental hardware write.

## 12. SysEx implementation rules

Community research documents the Roland/BOSS pattern of queries, writes, four-byte addresses, seven-bit data, a Roland checksum, and `F7` termination. The original Katana map is structural evidence, not proof that every address/value is correct for MkII 100 and its installed firmware.

```python
def calculateRolandChecksum(values: tuple[int, ...]) -> int:
    if any(value < 0 or value > 0x7F for value in values):
        raise ValueError("Roland SysEx values must be seven-bit")
    return (128 - (sum(values) & 0x7F)) & 0x7F
```

Every definition needs a validation category:

| Category | Meaning | May write? |
|---|---|---|
| `official` | Supported by BOSS documentation | Yes |
| `capturedMkII` | Captured and reproduced on the user's MkII | Yes |
| `communityMkII` | MkII-specific independent implementation | Only after guarded test |
| `legacyKatana` | Original-model reverse engineering | Not until validated |
| `inferred` | Similarity or code-reading inference | No |
| `unverifiedPlaceholder` | Example only | Never |

### Discovery procedure

1. Record exact model, firmware, OS, driver, and Tone Studio version.
2. Back up presets.
3. Capture a baseline.
4. Change one parameter only.
5. Compare messages and responses.
6. Repeat in both directions.
7. Confirm the address with a read query.
8. Write one safe value and monitor physical/Tone Studio state.
9. Restore the original value.
10. Save the capture as a fixture with provenance metadata.

On Windows use USBPcap/Wireshark when required. On Linux use ALSA monitors first and usbmon/Wireshark below ALSA when necessary. Do not run Tone Studio and the bridge as simultaneous port owners unless tested and supported.

SysEx queries require a bidirectional session:

```text
KatanaController -> outbound queue -> MIDI output
MIDI input -> SysEx parser -> response matcher -> KatanaStateStore
```

Never wait for a response inside `Router.handleEvent()`. Use a bounded worker and correlate by address and expected length with a timeout.

## 13. BlueBoard LED semantics

The v1.0.0 `LedFeedbackController` is stable momentary feedback: physical press means LED on; release means LED off. It uses the fixed `80 80` timestamp, serialized writes, 125 ms pacing, one release retry, no idle refresh, and no readback.

Do not change it while adding Katana support.

Persistent state requires a separate mode:

```text
--led-mode momentary
--led-mode katana-state
```

`katana-state` requires a verified state source, button mapping, synchronization after reconnect/preset selection, a policy for external changes, and a clear unknown-state fallback. Without readback, persistent LEDs are predicted state and must be labeled as such.

## 14. Metrics and logging

Preserve existing fields and add:

```text
katanaCommands
katanaCommandFailures
katanaReconnects
katanaQueries
katanaQueryTimeouts
katanaStateUpdates
```

Example logs:

```text
action type=katana command=selectPreset preset=0 execute=True
katana output="KATANA" message=programChange channel=1 program=0
katana effect=booster state=on source=predicted
```

Hex SysEx belongs at debug level and must identify whether it was sent, received, captured, or inferred.

## 15. Required tests

### Configuration

- Valid Katana config normalizes correctly.
- Unknown commands/effects are rejected.
- Invalid channels, CCs, programs, and parameter values are rejected.
- SysEx actions reject unverified definitions.
- Existing configs without `katana` remain valid.
- Both defaults remain aligned.

### Commands

- Program Change bytes for channels 1 and 16.
- CC bytes for values 0, 63, 64, and 127.
- Seven-bit range checks.
- Roland checksum vectors.
- SysEx framing and invalid lengths.

### Controller

- Preset selection loads expected state.
- Known state toggles deterministically.
- Unknown state fails instead of guessing.
- Transport failures reach the router's action-failure boundary.
- Dispatcher close closes MIDI.
- Reopen behavior does not duplicate commands.
- Dry-run never opens/writes MIDI.

### Regression

- All 59 current tests remain green.
- Existing actions are unchanged.
- C/D remain harmless by default.
- Momentary LED behavior is unchanged.
- Linux fallback tests are unchanged.
- Ruff passes under Python 3.10 target.

### Hardware

1. List Katana ports without BlueBoard.
2. Send Program Change 0 and confirm mapped Tone Setting.
3. Send one configured effect CC with 127 and 0.
4. Connect BlueBoard and test A only.
5. Test A/B presets.
6. Test C/D from known preset states.
7. Reconnect Katana while BlueBoard stays connected.
8. Reconnect BlueBoard while Katana stays connected.
9. Run for a rehearsal-length session.
10. Verify Ctrl+C closes both resources.

## 16. C++17 future port

C++17 is not part of v1.0.0. If later created, use a separate subtree/repository and make Python fixtures the behavioral specification.

```cpp
enum class MidiMessageType {
    controlChange,
    noteOn,
    noteOff,
    programChange,
    pitchBend,
    unknown
};

struct MidiEvent {
    MidiMessageType messageType;
    std::uint8_t channel;
    std::uint8_t data1;
    std::uint8_t data2;
};

class MidiTransport {
public:
    virtual ~MidiTransport() = default;
    virtual void open(const std::string& outputName) = 0;
    virtual void send(const std::vector<std::uint8_t>& message) = 0;
    virtual void close() = 0;
};
```

RtMidi is the cross-platform starting point; it uses ALSA on Linux and a Windows MIDI backend on Windows. Native WinMM/ALSA adapters are justified only if RtMidi is insufficient.

Reuse JSON fixtures for decoding, edge normalization, PC/CC construction, SysEx checksum/framing, registry validation, and expected action sequences. Preserve behavior and boundaries rather than translating Python line-for-line.

## 17. Delivery phases

### Phase 1: Standard MIDI proof

Add optional dependencies, port listing, PC/CC constructors, Mido transport, test CLI, tests, and docs.

Exit: computer changes one preset and one configured effect without BlueBoard.

### Phase 2: v1.0.0 integration

Add `KatanaConfig`, typed actions, dispatcher integration, A/B preset and C/D effect examples, dry-run/failure behavior, counters, and cleanup.

Exit: `blueboard run --execute-actions` controls the amp and original tests pass.

### Phase 3: State robustness

Add exact port selection, reconnect policy, preset-state table, unknown-state policy, and rehearsal-duration Windows/Linux tests.

Exit: predictable recovery from either device disconnecting.

### Phase 4: MkII SysEx

Add capture fixtures, registry, query/write framing, input response matching, pacing/timeouts, and effect parameter control.

Exit: one parameter is queried, changed, verified, and restored on target firmware.

### Phase 5: Amplifier-state LEDs

Add separate mode, synchronization, reconnect/unknown policy, and physical tests.

Exit: LEDs follow verified amp state rather than local prediction.

### Phase 6: C++17 parity

Add portable core, Windows/Linux adapters, shared fixtures, and parity tests.

Exit: C++ passes the same behavioral and physical tests as Python.

## 18. Codex work order

1. Branch from `v1.0.0` or current production.
2. Record clean baseline: 59 tests and Ruff.
3. Add pure PC/CC constructors and tests.
4. Add optional dependencies and Mido transport without affecting base users.
5. Add `midi-outputs` and `katana-test`.
6. Perform first physical Katana test.
7. Add strict `KatanaConfig` parsing.
8. Add typed `katana` action and dispatcher integration.
9. Add A/B/C/D example config without changing harmless defaults.
10. Add close/reconnect behavior.
11. Update README and agent docs.
12. Do not tag until Windows/Linux hardware checks are recorded.
13. Begin SysEx in a separate feature branch with captured fixtures.

Every change to parsing, routing, dispatch, transport, metrics, or hardware behavior must include tests in the same commit.

## 19. Licensing and notices

Keep MIT. Retain the IK Multimedia notice and add:

> This project is an independent third-party implementation and is not affiliated with, sponsored by, or endorsed by BOSS or Roland. Product names and trademarks belong to their respective owners.

List Mido, python-rtmidi/RtMidi, and new dependencies with their licenses. Do not copy Tone Studio source, binaries, or proprietary assets. Keep captured interoperability facts separate from vendor software.

## 20. References

### Project source of truth

- [`iRigBlueBoard-Macro-Handler` v1.0.0](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/tree/v1.0.0)
- [`pyproject.toml` at v1.0.0](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/blob/v1.0.0/pyproject.toml)
- [Architecture and extension guide](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/blob/v1.0.0/agent-docs/architecture-and-extension-guide.md)
- [Platform operations and hardware findings](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/blob/v1.0.0/agent-docs/platform-operations-and-hardware-findings.md)
- [Release history and roadmap](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/blob/v1.0.0/agent-docs/release-history-and-roadmap.md)

### BOSS Katana original and MkII

- [BOSS KATANA-100 original support, Version 4, Tone Studio, and manuals](https://www.boss.info/us/support/by_product/katana-100/)
- [BOSS KATANA-100 MkII manuals](https://www.boss.info/us/support/by_product/katana-100_mk2/owners_manuals/)
- [BOSS KATANA-100 MkII updates and drivers](https://www.boss.info/us/support/by_product/katana-100_mk2/updates_drivers/)
- [BOSS KATANA-100 MkII Windows driver information](https://www.boss.info/us/support/by_product/katana-100_mk2/updates_drivers/b203b755-260c-4902-acd0-df3b76d7d412/)

### MIDI libraries and OS APIs

- [Mido documentation](https://mido.readthedocs.io/)
- [python-rtmidi documentation](https://spotlightkid.github.io/python-rtmidi/)
- [RtMidi](https://github.com/thestk/rtmidi)
- [ALSA Sequencer API](https://www.alsa-project.org/alsa-doc/alsa-lib/group___sequencer.html)
- [Windows `midiOutShortMsg`](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midioutshortmsg)
- [Windows `midiOutLongMsg`](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midioutlongmsg)

### Reverse-engineered protocol research

- [katana-midi-bridge](https://github.com/snhirsch/katana-midi-bridge)
- [Original Katana SysEx notes](https://github.com/snhirsch/katana-midi-bridge/blob/master/doc/katana_sysex.txt)
- [Katana community documentation](https://github.com/katana-dev/docs)

Community sources are useful for framing and discovery, not a substitute for MkII-specific validation against the exact amplifier and firmware.

## Final recommendation

The first implementation should be a Python 3.10 new bridge application. Add a strict `katana` action, Mido/RtMidi transport, Program Change selection, and configurable effect on/off CC. Preserve the v1.0.0 router, BLE lifecycle, dry-run boundary, and momentary LED behavior.

Only after reliable physical validation should the project add SysEx editing, bidirectional state synchronization, persistent effect LEDs, or a C++17 parity port.
