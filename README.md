# BlueBoard + BOSS Katana Pedalboard

> **Notice:** This independent, community-developed project is not affiliated
> with, sponsored by, or endorsed by IK Multimedia, iRig, BOSS, Roland, or any
> manufacturer of referenced hardware or software. Product names and trademarks
> belong to their respective owners.

A safe, configurable Python bridge that turns an iRig BlueBoard into a wireless
four-button controller for BOSS KATANA amplifiers. It receives BLE-MIDI from the
BlueBoard and sends documented Program Change and Control Change messages to the
amplifier over USB-MIDI. On the physically qualified original KATANA-100 MkI
firmware 4.00 profile, bounded read-only SysEx queries keep relative effect
toggles synchronized with the live temporary patch.

The v1.0.0 package revision includes the full Windows and Linux Mint 22.2 x86-64
runtime. The implementation was completed across the v0.8.0 development series;
the remaining acceptance records document device-specific evidence still to be
closed before publishing a stable tag.

The project builds on the BLE-MIDI connection, decoding, routing, reconnection,
dry-run, logging, and optional momentary LED foundation from
[`iRigBlueBoard-Macro-Handler` v1.0.0](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/tree/v1.0.0),
then narrows the action boundary to BOSS Katana control.

## Author

- Abraham Jhared Flores Azcona _(NotsoJharedtrollOx17)_
  `abrahamjhared.flores@gmail.com`

## At a glance

- BlueBoard A-D input as channel-1 CC20-CC23 press/release events.
- Original KATANA-100 MkI grouped effect controls and KATANA-100 MkII standard
  MIDI profile.
- Program Change preset selection and model-correct Control Change switching.
- Exact or unique-substring input/output selection; input and output are resolved
  independently.
- Read-only MkI firmware-4.00 startup, recovery, post-preset, and pre/post-toggle
  state queries.
- Safe unknown-state behavior: relative toggles are rejected instead of assuming
  an unknown effect is off.
- Dry-run by default; real amplifier actions require `--execute-actions`.
- Independent opt-in momentary BlueBoard lights through `--led-feedback`.
- Guided Windows and Linux onboarding, read-only doctor, bounded session logs,
  deterministic probes, structured metrics, tests, and package smoke checks.
- Macro-free configuration: only Katana, harmless log, or unmapped actions.

Not included: keyboard macros, UDP/process launch, persistent amp-state LEDs,
expression control, arbitrary SysEx addresses, deep parameter editing, patch
storage, or general SysEx writes.

## Support status

| Target | Source status | Physical qualification |
|---|---|---|
| Original KATANA-100 MkI v4.00 on Windows | Full bridge and state-aware runtime | Primary target; substantial dated evidence, with final stable-release gates still open |
| Original KATANA-100 MkI v4.00 on Linux Mint 22.2 x86-64 | Full v1.0.0 port | Setup/doctor/short startup reads are preliminary passes; full live acceptance is pending |
| KATANA-100 MkII | Standard-MIDI profile | Experimental and hardware-unvalidated; no SysEx state synchronization |

The original MkI and MkII are different targets. Use the matching Tone Studio
family and model-specific MIDI map. The MkII application reports `WRONG DEVICE`
for the original amplifier used by this project.

## How it works

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
                           KATANA USB-MIDI input + output
```

BlueBoard BLE and Katana USB-MIDI reconnect independently. One Katana worker
serializes read requests and standard-MIDI actions so BLE callbacks remain
responsive and SysEx replies cannot be consumed by competing requests. A
transport failure invalidates observed state; recovery opens input before output,
starts a new connection epoch, and resynchronizes before another relative toggle.

## Requirements

- Python 3.10, 3.11, or 3.12.
- iRig BlueBoard powered in validated mode 2 by holding C while switching it on.
- Original KATANA-100 MkI or KATANA-100 MkII with a USB data cable.
- The matching BOSS Tone Studio, compatible firmware, and model-correct BOSS USB
  driver on Windows.
- Bluetooth hardware supported by Bleak.
- For the qualified Linux target: Linux Mint 22.2 x86-64, BlueZ (including
  `bluetoothctl` and `gatttool`), ALSA sequencer support, and `aconnect`.

Python 3.13+ is not supported by this release path. Check the official support
page for your exact amplifier model instead of treating driver, firmware, or
Tone Studio versions as permanent constants.

Before active control, back up important Tone Settings, set a safe amplifier
volume, close Tone Studio/DAWs/MIDI monitors that may own the ports, and verify
the exact amplifier generation.

## Windows quick start

From PowerShell in the repository:

```powershell
.\onboardPedalboard.ps1
.\runPedalboard.ps1 --debug
```

Onboarding is the normal first-run path. It reuses or creates a compatible local
environment, discovers the BlueBoard and Katana input/output independently,
guides the model/layout/firmware decisions, shows the complete A-D map, and
writes the ignored `python/config/katana-pedalboard.local.json` only after
confirmation.

Onboarding and doctor are read-only toward the amplifier: they enumerate but do
not open a MIDI port or send MIDI. Running onboarding again verifies the saved
profile. Use `-Force` only to replace it intentionally; a timestamped backup is
created first.

For repeatable MkI setup, use the exact names enumerated on that computer:

```powershell
.\onboardPedalboard.ps1 -NonInteractive -Model katana100 `
  -Layout panel-first -Input "KATANA 0" -Output "KATANA 1" `
  -Firmware "4.00" -AcceptProfileStateDefaults -Force
```

The observed Windows machine used `KATANA 0` as input and `KATANA 1` as output,
but port numbering is host-specific. Never copy these names without enumerating.

Confirm button events without amplifier actions:

```powershell
.\runPedalboard.ps1 --debug
```

After confirming the expected A-D events and mapping, enable configured Katana
actions intentionally:

```powershell
.\runPedalboard.ps1 --debug --execute-actions
```

Momentary BlueBoard lights are separately opt-in:

```powershell
.\runPedalboard.ps1 --debug --execute-actions --led-feedback
```

Specialist setup, port-listing, configuration, scan, and diagnostic scripts remain
available for troubleshooting:

```powershell
.\setupPedalboard.ps1
.\listKatanaMidiInputs.ps1
.\listKatanaMidiOutputs.ps1
.\configurePedalboard.ps1
.\diagnosePedalboard.ps1
```

If local policy blocks scripts, use a process-scoped bypass:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\onboardPedalboard.ps1
```

## Install the CLI for use anywhere

The package installs the `blueboard-katana` command. The repository launchers
remain convenient because they automatically select the local virtual environment
and generated profile, but a global installation lets you call the CLI from any
directory.

### Windows

From PowerShell in this repository, install for the current user without an
administrator prompt:

```powershell
.\setupPedalboard.ps1 -Scope global -User
```

The setup script installs the Katana runtime, locates `blueboard-katana.exe`,
prints its containing Scripts directory, and verifies `--version`. If a new
PowerShell window still cannot find the command, add that printed Scripts
directory to your user `PATH`, then open another terminal.

The installed command defaults to the qualified original KATANA-100 MkI,
firmware 4.00, Panel-first profile (`KATANA 0` input and `KATANA 1` output).
For that exact setup, it works without a configuration argument:

```powershell
$config = "C:\path\to\katana-pedalboard.local.json"
blueboard-katana --version
blueboard-katana doctor
blueboard-katana run --debug
blueboard-katana run --debug --execute-actions
```

Use `--config $config` to override those selectors, map, or firmware for any
other amplifier, MIDI-port naming, or custom layout. Real amplifier actions
remain opt-in through `--execute-actions`. Rerun the same setup command after
pulling a newer revision to update the installation. When the package version
has not changed, add `-Reinstall` to replace only this package's files without
upgrading its shared Python dependencies.

### Linux

The supplied `setupPedalboard.sh` deliberately creates a repository-local virtual
environment. To expose the CLI globally for one user, install the project with
`pipx` after Linux Bluetooth/ALSA prerequisites are available:

```bash
sudo apt install pipx
pipx ensurepath
pipx install --editable '.[katana]'
```

Open a new terminal after `pipx ensurepath`, then use the same profile-explicit
commands:

```bash
config="/absolute/path/to/katana-pedalboard.local.json"
blueboard-katana --version
blueboard-katana doctor
blueboard-katana run --debug
blueboard-katana run --debug --execute-actions
```

`pipx` changes only the current user's application environment. `sudo apt install
pipx` is the explicit system-level prerequisite installation; use your existing
package-management policy if you do not want that change. The normal Linux
onboarding/diagnostics prerequisites, including BlueZ and ALSA, still apply.

## Linux quick start

On Linux Mint 22.2 x86-64:

```bash
./setupPedalboard.sh --dev
./onboardPedalboard.sh
./diagnosePedalboard.sh
./runPedalboard.sh --debug
./runPedalboard.sh --debug --execute-actions
```

Use `--skip-system` only after installing BlueZ, Python venv support, and ALSA
prerequisites yourself. Setup does not configure `uinput`, change group
membership, pair the BlueBoard, or alter persistent BlueZ trust state.

Linux onboarding stores the shortest ALSA input/output selectors that still
resolve uniquely to the chosen full ports. This normally removes unstable
`client:port` coordinates. Verify the saved selectors after reconnect or reboot:

```bash
./onboardPedalboard.sh --verify-existing
```

`diagnosePedalboard.sh` checks the distribution, kernel, architecture, BlueZ,
D-Bus, adapter, `gatttool`, ALSA sequencer, Mido/RtMidi backend, saved selectors,
profile, approved SysEx definitions, and BlueBoard discovery without opening the
Katana ports or sending MIDI.

Bleak over BlueZ/D-Bus is primary. If BlueZ connects but omits the BLE-MIDI
service, the runtime uses a fail-closed `gatttool` compatibility path: it
discovers exactly one MIDI characteristic and one `0x2902` descriptor. The
tested `0x0022`/`0x0023` fallback is accepted only for a device advertised
exactly as `iRig BlueBoard` ignoring case.

## Default pedal layout

The recommended original-MkI Panel-first mapping is:

| Button | BlueBoard input | Katana action |
|---|---:|---|
| A | CC20 press | Panel / Program Change 4 |
| B | CC21 press | Bank A CH2 / Program Change 1 |
| C | CC22 press | Toggle Booster/Mod / CC16 |
| D | CC23 press | Toggle Delay/FX / CC17 |

Program Change is zero-based on the wire: Bank A CH1-4 are 0-3, Panel is 4, and
Bank B CH1-4 are 5-8.

The original KATANA-100 grouped standard-MIDI switches are:

| Function | Default CC |
|---|---:|
| Booster/Mod | 16 |
| Delay/FX | 17 |
| Reverb | 18 |
| Send/Return | 19 |

Delay and FX cannot be switched independently through the MkI standard-MIDI
assignment. CC19 is Send/Return and may have no audible result when the effects
loop is inactive.

The MkII source profile uses independent Booster/Mod/FX/Delay/Reverb/Effect Loop
CC16-CC21. It is not the map for the original amplifier.

## State-aware MkI toggles

State synchronization is eligible only when the generated profile specifies:

- model `katana100`;
- exact firmware `4.00`;
- independent input and output selectors; and
- `stateSync.enabled: true`.

At active startup the runtime reads six individual temporary-patch flags. After
Program Change it replaces the settling prediction with a fresh six-effect
snapshot. Before a grouped toggle it reads the live members, sends the opposite
documented CC, then reads back and verifies the result. Panel, GA-FC, or Tone
Studio changes are therefore observed on the next toggle without continuous
polling.

If a required read is unavailable, the state is unknown—not off. Preset selection
can remain available, but relative toggles are rejected until state is known. No
generic SysEx write is exposed.

The installed default profile is the qualified original-MkI v4.00 Panel-first
map. Use onboarding to create a machine-specific profile whenever the amplifier,
firmware, or MIDI selectors differ.

## Configuration

The packaged default at
[`python/config/blueboard.json`](python/config/blueboard.json) is the qualified
original KATANA-100 MkI firmware-4.00 Panel-first profile. It uses `KATANA 0`
for input and `KATANA 1` for output. The examples are starting points; generate
an ignored local profile with onboarding if those facts do not exactly match
your hardware.

Bindings may contain only a `katana` action, harmless `log`, or `null`. Legacy
keyboard, UDP, launch, and general macro actions are rejected.

Validate an edited profile offline:

```powershell
.\python\.venv\Scripts\python.exe -m blueboard_macro_handler validate `
  --config .\python\config\katana-pedalboard.example.json
```

JSON MIDI channels are 1-16; wire channels are 0-15. Input and output selectors
are independent. Non-interactive onboarding refuses to guess a model, firmware,
or ambiguous device.

## Commands and side effects

| Command | Behavior |
|---|---|
| `scan` | Scan for a BlueBoard |
| `onboard` | Discover, configure, and verify without sending MIDI |
| `configure` | Specialist profile generation without sending MIDI |
| `doctor` | Fresh read-only readiness checks; exit 0 ready, 2 actionable failure |
| `validate` | Validate/normalize configuration offline |
| `replay` | Replay BLE-MIDI fixtures offline |
| `midi-inputs` / `midi-outputs` | Enumerate without opening ports |
| `run` | Connect and route; dry-run unless `--execute-actions` |
| `katana-test` | Send one explicit standard-MIDI PC or CC diagnostic |
| `probe-effects` | Bounded model-aware standard-MIDI probe after `PROBE` consent |
| `sysex-probe` | Bounded predefined read-only SysEx probe after `READ` consent |
| `init-config` | Write an editable copy of the qualified MkI v4.00 default |

Run `blueboard-katana COMMAND --help` for current options.

## CLI reference

`blueboard-katana` is the standalone applet version of the project: it discovers
the wireless BlueBoard, decodes its four BLE-MIDI controls, and routes configured
button presses to a Katana over USB-MIDI. The normal live path is:

```text
onboard -> doctor -> run --dry-run -> run --execute-actions
```

Without `--config`, the applet uses the qualified original KATANA-100 MkI
firmware-4.00 Panel-first profile. Use a generated local profile whenever your
hardware, MIDI selectors, or layout differs.

### Common options

Most runtime and diagnostic commands accept these options:

| Option | Meaning |
|---|---|
| `--config PATH` | Profile to load. Runtime commands otherwise use the packaged qualified MkI v4.00 Panel-first default; onboarding/configuration commands otherwise write `blueboard-katana.json` in the current directory. |
| `--debug` | Emit detailed human-readable diagnostics. |
| `--json-logs` | Emit structured JSON log records. |
| `--log-file PATH` | Write logs to a file as well as the console. |
| `--name TEXT` | BlueBoard name substring used during discovery. |
| `--address ADDRESS` | Exact BlueBoard address when more than one matching device is present. |
| `--scan-timeout SECONDS` | Bound BLE discovery for that invocation. |
| `--state-file PATH` | Persist/reuse the last successful BlueBoard address where the command supports it. |

### Everyday commands

| Command | Options | What it does |
|---|---|---|
| `scan` | `--config`, `--name`, `--scan-timeout`, logging options | Scan for a BlueBoard. No Katana MIDI port is opened. |
| `onboard` | Common configuration options below plus `--verify-existing` | Recommended first-run workflow: discover, generate/replace a profile after confirmation, or read-only verify an existing one. |
| `doctor` | `--config PATH`, `--scan-timeout`, `--state-file`, logging options | Read-only installation/device readiness report; without `--config`, checks the packaged qualified MkI default. Exit 0 means ready; exit 2 means an actionable failure. |
| `run` | `--config`, device-selection options, `--duration-seconds`, mode/LED options, logging options | Connect BlueBoard and route configured bindings. Dry-run is the default. |
| `validate` | `--config`, logging options | Validate and print the normalized profile without hardware access. |
| `init-config [PATH] --force` | Optional output path; `--force` replaces an existing file | Write an editable copy of the qualified MkI v4.00 Panel-first profile. |
| `replay FILE` | `--config`, `--execute-actions`, logging options | Replay recorded BLE-MIDI fixture packets. Keep actions disabled unless deliberately testing dispatch. |

The configuration/orchestration options for `onboard` and `configure` are:

| Option | Meaning |
|---|---|
| `--input NAME` / `--output NAME` | Exact or uniquely matching Katana MIDI selectors. They are independent; non-interactive mode never guesses. |
| `--model katana100|katana100MkII` | Amplifier profile. Use `katana100` for the original MkI. |
| `--layout panel-first|channels-1-2` | Generated A-D starter map. `panel-first` is the recommended original-MkI layout. |
| `--midi-channel 1..16` | JSON-facing MIDI channel; the wire channel is zero-based internally. |
| `--firmware VALUE` | Firmware evidence recorded in the profile; use exact `4.00` for eligible MkI state synchronization. |
| `--accept-profile-state-defaults` | Explicitly accept generated initial effect-state predictions. |
| `--non-interactive` | Require every ambiguous decision to be supplied as an option. |
| `--force` | Replace an existing generated profile after creating a timestamped backup. |
| `--verify-existing` | `onboard` only: inspect the saved profile again without prompting or writing. |

`configure` generates a profile through its specialist workflow. `onboard` is
usually preferable because it combines discovery, configuration, and a fresh
read-only readiness check.

### Running the pedalboard

`run` accepts the following operation-specific options:

| Option | Meaning and side effect |
|---|---|
| `--dry-run` | Default. Decode, route, and log A-D events without sending configured Katana actions. |
| `--execute-actions` | Enable configured Program Change, Control Change, and eligible read-only state synchronization. This can change amplifier state. |
| `--duration-seconds N` | Stop cleanly after a positive bounded duration; useful for recorded sessions. |
| `--led-feedback` | Mirror physical A-D press/release on BlueBoard lights. Independent from amplifier actions. |
| `--reset-leds` | Send one paced A-D-off sequence and disconnect; requires `--led-feedback`. |
| `--name`, `--address`, `--scan-timeout` | Override BlueBoard discovery for this run. |
| `--state-file PATH` | Override the saved-address file. |

Examples:

```powershell
$config = "C:\path\to\katana-pedalboard.local.json"
blueboard-katana doctor --config $config
blueboard-katana run --config $config --debug
blueboard-katana run --config $config --debug --execute-actions --led-feedback
blueboard-katana run --config $config --debug --duration-seconds 300
```

### MIDI and protocol diagnostics

These commands are for deliberate troubleshooting and hardware evidence, not
the normal daily pedalboard path.

| Command | Required/options | Side-effect boundary |
|---|---|---|
| `midi-inputs` / `midi-outputs` | Logging options only | List ports without opening them or sending MIDI. |
| `katana-test` | `--output NAME`; one of `--program N` or `--control N --value N`; optional `--channel 1..16` | Sends exactly one standard-MIDI diagnostic message. Program values are wire values; original-MkI Panel is 4. |
| `probe-effects` | Exactly one of `--config PATH` or `--output NAME`; `--model` required with raw output; optional `--channel`, `--program`, `--effects` | Requires `PROBE` confirmation, tests only documented model-correct switches, requests physical observation, and attempts switch-off cleanup after interruption. |
| `sysex-probe` | `--model katana100 --input NAME --output NAME --read TARGET`; optional `--device-id`, `--timeout-ms`, `--retries`, `--editor-settle-ms`, `--save-fixture` | Requires `READ` before opening ports. Sends bounded RQ1 reads only; fixture saving requires a second `SAVE` confirmation. |

`sysex-probe --read` accepts only `current-selection`, `effect-states`, or
`panel-snapshot`. It does not accept arbitrary addresses and exposes no generic
SysEx write. `--timeout-ms` defaults to 750, `--retries` defaults to 1, and
`--editor-settle-ms` defaults to 75 for the predefined current-selection
handshake.

For example, a bounded original-MkI effect-state read is:

```powershell
blueboard-katana sysex-probe --model katana100 `
  --input "KATANA 0" --output "KATANA 1" --read effect-states --debug
```

## Read-only SysEx probe

Close competing MIDI clients, back up important settings, use safe volume, and
list both directions first. Example for the observed Windows host:

```powershell
.\probeKatanaSysEx.ps1 --model katana100 `
  --input "KATANA 0" --output "KATANA 1" --read effect-states --debug
```

Available targets are `effect-states`, `current-selection`, and
`panel-snapshot`. The probe requires `READ` before opening ports. Saving a
fixture requires a separate `SAVE`. It opens input first, uses bounded
timeouts/retries, records complete-wire traffic, and fails unless every required
reply is checksum-valid, address-matched, correctly sized, and decodable.

`current-selection` uses a fixed editor-mode handshake and attempts exit in
cleanup. `panel-snapshot` preserves separate returned chunks. Probes do not
synchronize a separately running bridge or expose arbitrary addresses/writes.

## Recorded sessions

Recorders are dry-run unless active mode is explicit.

Windows:

```powershell
.\recordPedalboardSession.ps1 -DurationMinutes 5
.\recordPedalboardSession.ps1 -Active -LedFeedback -DurationMinutes 60
```

Linux:

```bash
./recordPedalboardSession.sh --debug --led-feedback --duration-minutes 5
./recordPedalboardSession.sh --active --debug --led-feedback --duration-minutes 60
```

The active commands can change amplifier state. Logs are ignored timestamped
JSONL with final packet/action/reconnect/Katana/state metrics and stop reason.
Sanitize addresses, usernames, host paths, serial numbers, and unrelated device
details before attaching evidence.

## Troubleshooting

| Symptom | Resolution |
|---|---|
| Tone Studio says `WRONG DEVICE` | Confirm MkI versus MkII and install the matching Tone Studio family |
| Katana ports are missing or busy | Close Tone Studio, DAWs, monitors, and stale bridge processes; enumerate again |
| Input/output selector is ambiguous | Use exact or independently unique names; never accept arbitrary first-port selection |
| MkI D controls the wrong group | Use grouped Delay/FX CC17, not the MkII independent map |
| CC19 seems ineffective | It is Send/Return on MkI; verify that the effects loop is active |
| Toggle is rejected as unknown | Verify MkI firmware 4.00, both ports, state-sync settings, and six successful reads |
| Linux BLE service disappears after connect | Install full BlueZ/`gatttool`; inspect backend/profile logs; do not broaden the named fallback |
| ALSA selector fails after reboot | Run `./onboardPedalboard.sh --verify-existing`; use a longer unique selector if needed |
| A MIDI send error is followed by reopen | This proves recovery, not the root cause; inspect ownership, cable, driver, and competing clients separately |

Stop a live test on a wrong model, ambiguous port, unexpected state change,
checksum-invalid frame, failed restoration, leaked port, or unbounded recovery.

## Development and validation

The maintained source is under `python/src/blueboard_macro_handler`; the project
is Python-only. The intended branch flow is `feature/<name> -> dev -> main`, with
tags created from accepted `main` commits.

Local Windows validation after the documentation/code review:

```text
Ran 166 tests in 7.178s
OK (skipped=5)
```

The review also fixed a platform-isolation defect in the Linux fallback test
that previously made the Windows suite enter the reconnect loop. The CI-style
suite now completes. Expected simulated failure logs are not test failures; use
the final summary and exit status.

The five canonical references for future agents are:

1. [Project scope and source of truth](agent-docs/reference/01-project-scope-and-source-of-truth.md)
2. [Architecture and runtime](agent-docs/reference/02-architecture-and-runtime.md)
3. [Setup, configuration, and operations](agent-docs/reference/03-setup-configuration-and-operations.md)
4. [Protocol evidence and hardware validation](agent-docs/reference/04-protocol-evidence-and-hardware-validation.md)
5. [Release history and v1.0.0 checklist](agent-docs/reference/05-release-history-and-v1.0.0-checklist.md)

Historical plans and acceptance records remain in `agent-docs/` for provenance.

## v1.0.0 release boundary

The package and documentation now identify v1.0.0. Before publishing the stable
tag, the same accepted revision must:

- pass Ruff, scripts, Markdown/diff, Windows/Ubuntu CI, build, and clean-install
  smoke gates;
- reconcile the remaining Windows v0.7.0 runtime/per-effect acceptance items;
- complete the final Windows 60-minute rehearsal;
- complete every physical Linux A-D, state, LED, reconnect, cleanup, 60-minute,
  reboot, and Windows-regression item; and
- close or explicitly approve the remaining physical evidence, rerun validation,
  merge to `main`, then tag that accepted `main` commit.

See the [canonical release checklist](agent-docs/reference/05-release-history-and-v1.0.0-checklist.md)
and the underlying [Linux hardware acceptance record](agent-docs/v0.8.0-linux-hardware-acceptance.md).

## Primary references

- [BOSS KATANA-100 support](https://www.boss.info/us/support/by_product/katana-100/)
- [BOSS KATANA-100 MkII support](https://www.boss.info/us/support/by_product/katana-100_mk2/)
- [KATANA MkII owner's manual](https://static.roland.com/assets/media/pdf/KATANA-Mk2_eng02_W.pdf)
- [Mido documentation](https://mido.readthedocs.io/)
- [Bleak documentation](https://bleak.readthedocs.io/)
- [python-rtmidi documentation](https://spotlightkid.github.io/python-rtmidi/)

Community SysEx research is useful but remains provenance-labeled and cannot by
itself authorize target-hardware production access. Exact source links and the
full rationale are preserved in the historical v1.0.0 SysEx specification.

## Third-party notices

This project uses Python packages including Bleak, Mido, and python-rtmidi under
their respective licenses. BOSS, Roland, KATANA, IK Multimedia, iRig, and
BlueBoard are trademarks or product names of their respective owners.

## License

Licensed under the [MIT License](LICENSE).

## Citation

If this project contributes to research, documentation, or a derived tool,
please cite it as:

```bibtex
@software{flores_azcona_blueboard_katana_2026,
  author  = {Flores Azcona, Abraham Jhared},
  title   = {BlueBoard + BOSS Katana Pedalboard},
  year    = {2026},
  url     = {https://github.com/NotsoJharedtrollOx17/BlueBoard-BOSSKatana-Pedalboard}
}
```
