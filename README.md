# BlueBoard + BOSS Katana Pedalboard

> **Notice:** This independent, community-developed project is not affiliated
> with, sponsored by, or endorsed by IK Multimedia, iRig, BOSS, Roland, or any
> manufacturer of referenced hardware or software. Product names and trademarks
> belong to their respective owners.

A Python bridge that turns an iRig BlueBoard into a configurable four-button
pedalboard for original and MkII BOSS KATANA-100 amplifiers. Version 0.8.0 ports
the proven original KATANA-100 Mk I workflow from Windows to Linux Mint 22.2
x86-64. Linux release completion remains gated on the checked-in physical
acceptance record.

The project carries forward the proven BLE-MIDI connection, decoding, routing,
reconnection, dry-run, logging, and optional momentary LED feedback from
[`iRigBlueBoard-Macro-Handler` v1.0.0](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/tree/v1.0.0).
It adds a separate USB-MIDI path for documented Katana Program Change and
Control Change messages plus bounded, read-only original-Katana SysEx probes.

Status: `0.8.0` alpha Linux-integration candidate. Automated source gates cover
the Windows regression baseline and Linux transport behavior. Do not treat the
release as complete, merge it to `main`, or tag it until every live Linux item in
`agent-docs/v0.8.0-linux-hardware-acceptance.md` has sanitized evidence.

## Author

- Abraham Jhared Flores Azcona _(NotsoJharedtrollOx17)_
  `abrahamjhared.flores@gmail.com`

## What v0.8.0 supports

- BlueBoard A-D input as channel 1 CC20-CC23 with press/release edge routing.
- BOSS preset selection through standard MIDI Program Change.
- Model-correct effect switches: grouped CC16-CC19 on the original KATANA-100
  and independent CC16-CC21 on MkII.
- Independent exact or unique-substring MIDI input/output selection; no arbitrary first-port choice.
- Predicted per-preset effect state with an explicit unknown-state failure.
- Dry-run by default. `--execute-actions` enables configured Katana actions only.
- A deliberately macro-free action boundary: JSON accepts `katana`, harmless
  `log`, or `null`; keyboard, UDP, and process-launch actions are rejected with
  migration guidance.
- Independent, opt-in momentary BlueBoard LEDs through `--led-feedback`.
- Unified Windows and Linux onboarding plus specialist helpers, replay
  fixtures, structured logging, metrics, and a Windows/Linux CI definition.
- Pure original-KATANA-100 SysEx RQ1/DT1 builders, a strict frame parser,
  base-128 address helpers, checksum verification, and evidence-aware definitions
  for six read-only effect-state probe candidates.
- Independent deterministic MIDI input/output resolution and input-first duplex
  opening so immediate replies cannot be missed.
- Explicit `sysex-probe` targets for current selection, six temporary-patch effect
  flags, and a bounded raw front-panel snapshot; no arbitrary address or DT1 write.
- Full sent/received bytes, decoded fields, checksum failures, timing, retries,
  connection epoch, structured metrics, and opt-in sanitized JSON fixtures.
- A single non-blocking Katana worker that serializes live RQ1, Program Change,
  and Control Change operations while BlueBoard BLE notifications continue.
- Atomic six-effect startup/recovery/post-PC snapshots, compound Booster/Mod and Delay/FX
  derivation, per-value queried/predicted/unknown/stale sources, and safe degraded
  behavior when a required read is unavailable.

Runtime state synchronization is enabled only for an active original KATANA-100
Mk I profile at the captured v4.00 firmware with an independent input/output pair.
Otherwise the run degrades safely: preset selection remains available and unknown
toggles are rejected. The synchronized runtime reads at startup, after Program Change, before every
relative toggle, after its Control Change, and after detected transport recovery.
Read-before-toggle observes intervening panel/GA-FC/Tone Studio changes without polling.
No generic SysEx write is exposed.

On Linux, Bleak over BlueZ/D-Bus is primary. If BlueZ connects but omits the
advertised BLE-MIDI service, the runtime discovers one MIDI value handle and one
validated `0x2902` descriptor with `gatttool`. Only an exact case-insensitive
`iRig BlueBoard` name may use the tested `0x0022`/`0x0023` fallback if discovery
fails. Unknown devices and malformed or duplicate discovery fail closed. The
runtime never pairs, trusts, or modifies persistent BlueZ device state.
Configurations requesting `device.pair: true` are rejected.

## Architecture

```text
iRig BlueBoard (BLE-MIDI)
        |
BlueBoardClient -> BleMidiDecoder -> Router -> ActionDispatcher
                                              |
                                      Katana worker queue
                                              |
                               KatanaRuntime / SysExSession
                                              |
                                       Mido / RtMidi
                                              |
                           KATANA USB-MIDI input/output
```

The BlueBoard BLE lifecycle and Katana MIDI lifecycle are independent. The Katana
worker owns both MIDI directions and one request at a time. A transport failure
invalidates the current epoch; the next Katana operation reopens input before
output and attempts bounded resynchronization without stopping BlueBoard input.

## Requirements

- Python 3.10, 3.11, or 3.12. The current python-rtmidi 1.5.8 release publishes
  wheels only through CPython 3.12; Python 3.13+ otherwise needs a local C++ build
  toolchain and is not a supported installation path for this release.
- iRig BlueBoard configured in its validated mode 2 profile.
- Original KATANA-100 or KATANA-100 MkII with a USB data cable. The original
  KATANA-100 remains the hardware-qualified runtime target; v0.8.0 Linux release
  completion still depends on its checked-in live acceptance gate.
- Model-correct BOSS Tone Studio, compatible firmware, and the official BOSS USB
  driver on Windows.
- Bluetooth support compatible with Bleak.
- Linux Mint 22.2 x86-64 for the v0.8.0 Linux target, with BlueZ (including
  `bluetoothctl` and `gatttool`), ALSA sequencer support, and `aconnect`.

The official BOSS support page currently lists Katana MkII System Program 2.00,
BOSS Tone Studio 2.1.0, and the Windows 10/11 driver. Check the support page for
your OS and model rather than treating those versions as permanent constants.

## Windows quick start

From PowerShell in this repository:

```powershell
.\onboardPedalboard.ps1
.\runPedalboard.ps1 --debug
```

`onboardPedalboard.ps1` is the normal first-run path. It reuses a compatible local
v0.8.0 environment or runs setup first, then enumerates Katana MIDI inputs/outputs and
scans for the BlueBoard concurrently. One typed discovery snapshot feeds both the
guided configuration and readiness evaluation, so the same devices are not
scanned twice. The wizard asks for the amplifier generation and starter layout,
records the MIDI channel and firmware evidence, explains synchronization/prediction
assumption, shows the complete A-D map, and confirms before writing the ignored
local profile at `python/config/katana-pedalboard.local.json`.

Onboarding never opens a MIDI port, sends MIDI, or executes an operating-system
action. Unique devices are selected automatically; ambiguous Katana ports or
BlueBoards are presented as numbered choices. If one discovery source fails,
interactive onboarding can retry that source without discarding the successful
result from the other device.

The default diagnostic scan is 20 seconds. `scanBlueBoard.ps1` and
`diagnosePedalboard.ps1` also apply that timeout to older local profiles; pass
`--scan-timeout SECONDS` after the script name to override it for one run.

After it has written a profile, running the same command again performs a fresh,
read-only readiness check of that saved profile—there are no numbered setup
questions to answer. To deliberately replace the profile, add `-Force` and use
the native PowerShell options below. This avoids relying on PowerShell's raw
argument forwarding, which can prevent the interactive wizard from receiving
numbered selections in some terminals.

The recommended original-KATANA profile is Panel-first:

| Button | Action |
|---|---|
| A | Panel / Program Change 4 |
| B | A:CH2 / Program Change 1 |
| C | Toggle Booster/Mod / CC16 |
| D | Toggle Delay/FX / CC17 |

For repeatable or headless setup, specify every hardware decision explicitly:

```powershell
.\onboardPedalboard.ps1 -NonInteractive -Model katana100 `
  -Layout panel-first -Input "KATANA 0" -Output "KATANA 1" -Firmware "4.00" `
  -AcceptProfileStateDefaults -Force
```

Non-interactive setup fails instead of guessing a model or choosing among
ambiguous devices. `-Output`, `-Model`, `-Layout`, `-MidiChannel`, `-Firmware`,
`-Name`, `-Address`, and `-ScanTimeout` map directly to the onboarding CLI.
Use `-VerifyExisting` to request the saved-profile check explicitly. Explicit
replacement creates a timestamped ignored `.local.json` backup first.

The former three-step tools remain available for troubleshooting:

```powershell
.\setupPedalboard.ps1
.\configurePedalboard.ps1
.\diagnosePedalboard.ps1
```

`diagnosePedalboard.ps1` always performs fresh read-only checks of Python, the
configuration, MIDI backend/output resolution, and BlueBoard discovery. It
returns exit code 0 when ready or 2 when a required check fails.

If local PowerShell policy blocks scripts, use a process-scoped bypass:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\onboardPedalboard.ps1
```

If a compatible Python is installed but not registered with the Windows `py`
launcher, pass its executable explicitly:

```powershell
.\onboardPedalboard.ps1 -Dev -PythonExe "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
```

Connect the amplifier with a USB data cable and use the exact output selected by
onboarding. Close BOSS Tone Studio for the first transport tests so port
ownership is unambiguous.

Test one documented preset message without involving the BlueBoard:

```powershell
.\python\.venv\Scripts\python.exe -m blueboard_macro_handler katana-test `
  --output "KATANA" --channel 1 --program 0
```

For the documented MkII receive map, wire program `0` is Bank A CH1 and values
`0` through `8` cover Bank A CH1-4, Panel, and Bank B CH1-4. The CLI accepts the
full MIDI range for diagnostics, but `0-8` is the supported Katana profile.

Test Booster on and off explicitly:

```powershell
.\python\.venv\Scripts\python.exe -m blueboard_macro_handler katana-test `
  --output "KATANA" --channel 1 --control 16 --value 127

.\python\.venv\Scripts\python.exe -m blueboard_macro_handler katana-test `
  --output "KATANA" --channel 1 --control 16 --value 0
```

When Tone Studio is unavailable or a preset's switch assignments are unclear,
run the constrained, model-aware interactive probe:

```powershell
.\probeKatanaEffects.ps1
```

The probe derives its model, channel, first preset, labels, and configured CCs
from the local profile. On the original amplifier this means grouped Booster/Mod,
Delay/FX, Reverb, and Send/Return switches; it no longer applies the MkII map to
a MkI device. It waits for observations after every ON and OFF message and
prints a result table. Type `PROBE` at its confirmation prompt. Moving an
EFFECTS knob invalidates the observation. Ctrl+C attempts to turn the active
switch off before closing. The probe does not scan unknown CCs, write presets,
or send SysEx.

Run the complete bridge in dry-run mode first. The launcher uses the generated
local profile and tells the user to configure first if it is missing:

```powershell
.\runPedalboard.ps1 --debug
```

After confirming A-D button events in the logs, enable amplifier actions
intentionally:

```powershell
.\runPedalboard.ps1 --debug --execute-actions
```

Momentary BlueBoard button lights are a separate opt-in feature:

```powershell
.\runPedalboard.ps1 --debug --execute-actions --led-feedback
```

## Recorded Windows sessions

Use the session recorder for rehearsal evidence. It creates an ignored JSON log
with final packet, action, reconnect, Katana-transport, and stop-reason metrics.
It is dry-run unless `-Active` is supplied.

```powershell
.\recordPedalboardSession.ps1 -DurationMinutes 5
.\recordPedalboardSession.ps1 -Active -LedFeedback -DurationMinutes 60
```

The second command can change the amplifier because `-Active` enables configured
actions. Press Ctrl+C for an interrupted session, or use `-DurationMinutes` for
a clean bounded session. Logs default to `logs\pedalboard-sessions`; an explicit
`-LogDirectory` or `-ScanTimeout` overrides that invocation only.

## Read-only SysEx hardware probe

Close BOSS Tone Studio first: MIDI ports are commonly single-client on Windows.
Back up important Tone Settings and set a safe amplifier output volume even though
the predefined targets are reads. Then list both directions independently:

```powershell
.\listKatanaMidiInputs.ps1
.\listKatanaMidiOutputs.ps1
```

Use the exact main KATANA input and output names reported on this machine. The
following example reads the six individual live temporary-patch flags:

```powershell
.\probeKatanaSysEx.ps1 --model katana100 `
  --input "KATANA 1" --output "KATANA 1" --read effect-states `
  --save-fixture ".\logs\sysex-effect-states.json" --debug
```

The command requires `READ` before opening either port and separately requires
`SAVE` before writing a fixture. It opens the input before the output, permits one
request at a time, defaults to a 750 ms timeout and one retry, and returns exit code
2 unless every requested value has a checksum-valid, address-matched, decodable
reply. The console prints complete-wire bytes even though Mido callbacks supply
payload-only SysEx data.

Additional bounded targets are `current-selection` and `panel-snapshot`.
`current-selection` temporarily enters editor mode, waits 75 ms, performs the
read, and attempts editor-mode exit in `finally`. `panel-snapshot` captures one or
more returned chunks inside the predefined `00 00 04 00` range without pretending
that gaps form one contiguous response. None of these diagnostic commands updates
the live controller or promotes candidate addresses to production evidence. Active
runtime uses the same matcher only after the registry's production-read gate passes.

## Linux quick start

The v0.8.0 Linux target is Linux Mint 22.2 x86-64. Power the BlueBoard in mode 2
by holding C while switching it on, connect the original KATANA-100 Mk I over a
USB data cable, and close Tone Studio, DAWs, MIDI monitors, and stale pedalboard
processes before claiming the ports.

```bash
./setupPedalboard.sh
./onboardPedalboard.sh
./diagnosePedalboard.sh
./recordPedalboardSession.sh --debug --led-feedback --duration-minutes 5
./recordPedalboardSession.sh --active --debug --led-feedback --duration-minutes 60
```

Setup installs only the Katana runtime by default. Use `--dev` for validation
tools, `--python-exe PATH` to select Python 3.10-3.12, or `--skip-system` after
installing BlueZ, Python venv support, and ALSA yourself. It never configures
`uinput` or changes group membership.

Onboarding lists input and output ports independently, then saves the shortest
Linux ALSA selector that still resolves uniquely to the chosen enumerated port.
This normally removes changing `client:port` coordinates and a redundant client
prefix, while preserving the full name whenever shortening would be ambiguous.
Run `./onboardPedalboard.sh --verify-existing` after reconnects or reboot.

`diagnosePedalboard.sh` performs fresh read-only OS, BlueZ/D-Bus, adapter, ALSA,
Mido/RtMidi, selector, profile, approved-definition, and BlueBoard checks. It
does not open MIDI ports or send commands. The session recorder writes a
timestamped JSONL log and is dry-run unless `--active` is explicit. Momentary
`--led-feedback` remains independent of both dry-run and Katana actions.

## Pedal configuration

The packaged default at
[`python/config/blueboard.json`](python/config/blueboard.json) leaves all four
buttons unmapped. It is safe for scanning, validation, and installation.

The configure command generates `python/config/katana-pedalboard.local.json`
from a model-correct starter layout. The committed
[`python/config/katana-pedalboard.example.json`](python/config/katana-pedalboard.example.json)
remains a reference for manual customization. The layout is:

| Button | BlueBoard input | Example Katana action |
|---|---:|---|
| A | CC20 press | Program 4 / Panel for the recommended MkI profile |
| B | CC21 press | Program 1 / Bank A CH2 |
| C | CC22 press | Toggle Booster/Mod / CC16 |
| D | CC23 press | Toggle Delay/FX / CC17 |

The Mk I example enables `stateSync`, records independent input/output names, and
requests a six-effect snapshot at active startup. After A or B sends Program
Change, the worker lets the new temporary patch settle and replaces the short-lived
`presetStates` prediction with six queried values. C/D refresh the live group before
choosing the opposite CC value and read it back afterward. Panel, GA-FC, or Tone
Studio changes are therefore observed on the next toggle without continuous polling.

Bindings may contain only a `katana` action, a harmless `log` action, or `null`.
The retained `blueboard_macro_handler` import namespace is compatibility-only;
the old keyboard, UDP, launch, and operating-system backend modules are not part
of this product.

For the original KATANA-100, a Panel-first profile is included at
[`python/config/katana-pedalboard-panel.example.json`](python/config/katana-pedalboard-panel.example.json).
It maps A to Panel (wire Program Change 4), B to A:CH2, C to Booster/Mod, and D
to Delay/FX. Test it with:

```powershell
.\python\.venv\Scripts\python.exe -m blueboard_macro_handler run `
  --config .\python\config\katana-pedalboard-panel.example.json --debug --execute-actions
```

The Panel profile queries all six effect flags at active startup and after selecting
Panel for the captured Mk I v4.00 firmware. `presetStates["4"]` is only a labeled
prediction during the bounded Program Change settling window.

Validate any edited configuration without connecting hardware:

```powershell
.\python\.venv\Scripts\python.exe -m blueboard_macro_handler validate `
  --config .\python\config\katana-pedalboard.example.json
```

## Official standard-MIDI map

The current English MkII owner's manual documents:

| Message | Function | Values |
|---|---|---|
| Program Change | Bank A CH1-4, Panel, Bank B CH1-4 | 0-8 on the wire |
| CC16 | Booster switch | 0-63 off, 64-127 on |
| CC17 | Mod switch | 0-63 off, 64-127 on |
| CC18 | FX switch | 0-63 off, 64-127 on |
| CC19 | Delay switch | 0-63 off, 64-127 on |
| CC20 | Reverb switch | 0-63 off, 64-127 on |
| CC21 | Effect Loop switch | 0-63 off, 64-127 on |

The manual also warns that operating an EFFECTS-section knob makes the knob's
setting effective and discards the earlier MIDI on/off setting.

### Original KATANA-100 profile

The original KATANA-100 uses grouped standard-MIDI switches. Its Tone Studio
MIDI-setting screen is the authority for the values saved in the local profile:

| Function | Default CC |
|---|---:|
| Booster/Mod switch | 16 |
| Delay/FX switch | 17 |
| Reverb switch | 18 |
| Send/Return switch | 19 |

Use `"model": "katana100"` and configure the project with the values shown by
the connected amplifier. The BlueBoard's D action remains named `delay`, but on
this profile it sends the shared Delay/FX switch (CC17 by default); Delay and FX
cannot be independently switched through this standard-MIDI assignment.

Primary references:

- [BOSS KATANA-100 MkII support, manuals, firmware, and drivers](https://www.boss.info/us/support/by_product/katana-100_mk2/)
- [KATANA MkII owner's manual](https://static.roland.com/assets/media/pdf/KATANA-Mk2_eng02_W.pdf)
- [Using BOSS Tone Studio for KATANA MkII](https://static.roland.com/assets/media/pdf/BTS_KTN-Mk2_eng01_W.pdf)
- [Mido RtMidi backend](https://mido.readthedocs.io/en/stable/backends/rtmidi.html)

## Commands

```text
blueboard-katana scan
blueboard-katana run
blueboard-katana replay <fixture.json>
blueboard-katana validate
blueboard-katana init-config [path]
blueboard-katana midi-inputs
blueboard-katana midi-outputs
blueboard-katana sysex-probe --model katana100 --input NAME --output NAME --read TARGET
blueboard-katana katana-test --output NAME (--program N | --control N --value N)
blueboard-katana probe-effects (--output NAME | --config PATH) [--effects EFFECT ...]
blueboard-katana configure [--input NAME] [--output NAME] [--config PATH]
blueboard-katana onboard [--input NAME] [--output NAME] [--config PATH]
blueboard-katana doctor --config PATH [--scan-timeout SECONDS]
```

`replay`, `validate`, and the test suite do not need hardware. `midi-inputs` and
`midi-outputs` enumerate without opening ports. `sysex-probe` is a bounded,
confirmed hardware diagnostic limited to predefined original-Katana read targets;
the current-selection target includes only its required editor-mode handshake.
`katana-test` is intentionally a direct side-effect command and requires an
explicit output plus message. `configure` discovers both devices and writes
local state, but never opens a MIDI port or sends a command.
`onboard` performs concurrent discovery, guided configuration, and readiness
evaluation from one snapshot. It writes only after all required checks pass and
the user confirms the proposed profile.
`probe-effects` is an explicit, interactive hardware command constrained to the
selected model profile. Raw-output use requires `--model`; configuration-based
use derives the model and first preset. `doctor` is read-only and never opens a
MIDI port or sends a command.

## Development and branches

The repository uses:

```text
feature/<name> -> dev -> main -> version tag
```

- `dev` is the integration branch.
- `main` is the release-ready branch.
- Runtime SysEx bootstrap is production-readable only for the captured original
  KATANA-100 Mk I v4.00 effect-flag definitions; other firmware values degrade
  safely without sending a runtime SysEx request.
- `updatePedalboard.ps1 -Branch dev` and `updatePedalboard.sh --branch dev` support
  explicit development updates; production updates default to `main`.

Run the source checks:

```powershell
.\setupPedalboard.ps1 -Dev
.\python\.venv\Scripts\python.exe -m unittest discover -s python\tests -p "test*.py"
.\python\.venv\Scripts\ruff.exe check python\src\blueboard_macro_handler python\tests
```

On Linux, use `./setupPedalboard.sh --dev --skip-system`, then run the same
`unittest` and `ruff` modules from `python/.venv/bin/python`, followed by
`bash -n ./*.sh` and `git diff --check`.

## Evidence boundary and roadmap

Source-level automated validation does not prove the target amplifier accepted a
message. Before `v1.0.0`, record the amp model, firmware, Windows driver, Tone
Studio version, discovered port names, preset/CC results, reconnect behavior, and
a rehearsal-duration test.

See:

- [`agent-docs/architecture-and-extension-guide.md`](agent-docs/architecture-and-extension-guide.md)
- [`agent-docs/protocol-evidence-and-hardware-validation.md`](agent-docs/protocol-evidence-and-hardware-validation.md)
- [`agent-docs/release-history-and-roadmap.md`](agent-docs/release-history-and-roadmap.md)
- [`agent-docs/v0.3.0-feature-plan.md`](agent-docs/v0.3.0-feature-plan.md), the unified onboarding implementation and release checklist
- [`agent-docs/v0.3.0-onboarding-input-repair.md`](agent-docs/v0.3.0-onboarding-input-repair.md), the diagnosis and acceptance plan for the PowerShell input repair
- [`agent-docs/v0.4.0-feature-plan.md`](agent-docs/v0.4.0-feature-plan.md), the final reliability-evidence prerelease plan
- [`agent-docs/v0.4.0-windows-mki-acceptance.md`](agent-docs/v0.4.0-windows-mki-acceptance.md), the v1.0.0 Windows MkI physical release record
- [`agent-docs/v0.5.0-feature-plan.md`](agent-docs/v0.5.0-feature-plan.md), the pure MkI SysEx protocol-core implementation and release gates
- [`agent-docs/v0.6.0-feature-plan.md`](agent-docs/v0.6.0-feature-plan.md), the duplex read-only SysEx probe implementation and source gates
- [`agent-docs/v0.6.0-sysex-hardware-acceptance.md`](agent-docs/v0.6.0-sysex-hardware-acceptance.md), the ordered target-amplifier capture checklist
- [`agent-docs/v0.7.0-feature-plan.md`](agent-docs/v0.7.0-feature-plan.md), the runtime bootstrap implementation and source gates
- [`agent-docs/v0.7.0-sysex-runtime-acceptance.md`](agent-docs/v0.7.0-sysex-runtime-acceptance.md), the exact-firmware production-read and reconnect checklist
- [`agent-docs/v0.8.0-linux-integration-plan.md`](agent-docs/v0.8.0-linux-integration-plan.md), the canonical Linux implementation plan and release gates
- [`agent-docs/v0.8.0-linux-hardware-acceptance.md`](agent-docs/v0.8.0-linux-hardware-acceptance.md), the required live Linux evidence record
- [`agent-docs/v1.0.0-mki-sysex-state-awareness-spec.md`](agent-docs/v1.0.0-mki-sysex-state-awareness-spec.md), the complete staged state-awareness specification
- [`agent-docs/KATANA_BLUEBOARD_CODEX_SUMMARY.md`](agent-docs/KATANA_BLUEBOARD_CODEX_SUMMARY.md), the original implementation brief
- [`agent-docs/2026-08-23-original-katana100-breakthroughs.md`](agent-docs/2026-08-23-original-katana100-breakthroughs.md), the dated original-Katana hardware breakthrough record
- [`agent-docs/v0.2.0-windows-hardware-acceptance.md`](agent-docs/v0.2.0-windows-hardware-acceptance.md), the historical v0.2.0 Windows acceptance record

## Third-party notices

Mido is MIT-licensed. python-rtmidi is MIT-licensed and wraps RtMidi, which uses a
permissive license. See each dependency's distribution for its complete notices.

## License

[MIT](LICENSE) © 2026 Abraham Jhared Flores Azcona.

## Citation

If you use this software in a project, publication, or technical report, please
cite it as:

```bibtex
@misc{
    floresazcona2026blueboardbosskatana,
    title = {BlueBoard + BOSS Katana Pedalboard},
    author = {Flores-Azcona, Abraham Jhared},
    year = {2026},
    month = {Aug},
    url = {https://github.com/NotsoJharedtrollOx17/BlueBoard-BOSSKatana-Pedalboard}
}
```
