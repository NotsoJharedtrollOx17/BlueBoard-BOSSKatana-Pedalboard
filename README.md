# BlueBoard + BOSS Katana Pedalboard

A cross-platform Python bridge that turns an iRig BlueBoard into a configurable
four-button pedalboard for a BOSS KATANA-100 MkII amplifier.

The project carries forward the proven BLE-MIDI connection, decoding, routing,
reconnection, dry-run, logging, Linux compatibility, and optional momentary LED
feedback from
[`iRigBlueBoard-Macro-Handler` v1.0.0](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/tree/v1.0.0).
It adds a separate USB-MIDI output path for documented Katana Program Change and
Control Change messages.

Status: `0.1.0` alpha. The software and simulated transport are tested; the Katana
path still requires validation on the target KATANA-100 MkII hardware before a
stable release.

## What the first milestone supports

- BlueBoard A-D input as channel 1 CC20-CC23 with press/release edge routing.
- BOSS preset selection through standard MIDI Program Change.
- Booster, Mod, FX, Delay, Reverb, and Effect Loop on/off through the documented
  CC16-CC21 receive map.
- Exact or unique-substring MIDI output selection; no arbitrary first-port choice.
- Predicted per-preset effect state with an explicit unknown-state failure.
- Dry-run by default. Amplifier and operating-system actions require
  `--execute-actions`.
- Independent, opt-in momentary BlueBoard LEDs through `--led-feedback`.
- Windows and Linux launch/setup helpers, replay fixtures, structured logging,
  metrics, and a Windows/Linux CI definition.

This milestone does not write Katana SysEx. Detailed effect type and parameter
editing remains in BOSS Tone Studio until addresses are captured and reproduced on
the exact MkII model and firmware.

## Architecture

```text
iRig BlueBoard (BLE-MIDI)
        |
BlueBoardClient -> BleMidiDecoder -> Router -> ActionDispatcher
                                              |
                                      KatanaController
                                              |
                                       Mido / RtMidi
                                              |
                               KATANA USB-MIDI output
```

The BlueBoard BLE lifecycle and Katana MIDI lifecycle are independent. A Katana
transport failure is contained at the existing action boundary; the next command
attempts to reopen the configured MIDI output without stopping BlueBoard input.

## Requirements

- Python 3.10, 3.11, or 3.12. The current python-rtmidi 1.5.8 release publishes
  wheels only through CPython 3.12; Python 3.13+ otherwise needs a local C++ build
  toolchain and is not a supported installation path for this release.
- iRig BlueBoard configured in its validated mode 2 profile.
- BOSS KATANA-100 MkII with a USB data cable.
- Current Katana MkII firmware and the official BOSS USB driver on Windows.
- Bluetooth support compatible with Bleak.

The official BOSS support page currently lists Katana MkII System Program 2.00,
BOSS Tone Studio 2.1.0, and the Windows 10/11 driver. Check the support page for
your OS and model rather than treating those versions as permanent constants.

## Windows quick start

From PowerShell in this repository:

```powershell
.\setupPedalboard.ps1
.\configurePedalboard.ps1
.\runPedalboard.ps1 --debug
```

`configurePedalboard.ps1` is the normal user path. With the Katana connected by
USB and the BlueBoard powered on, it performs read-only discovery, chooses the
single non-control Katana output, writes the ignored local profile at
`python/config/katana-pedalboard.local.json`, remembers the BlueBoard address,
and prints the next commands. It never sends MIDI to the amplifier. If more than
one possible main output exists, it stops and requests an explicit selection:

```powershell
.\configurePedalboard.ps1 --output "KATANA 1"
```

If local PowerShell policy blocks scripts, use a process-scoped bypass:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setupPedalboard.ps1
```

If a compatible Python is installed but not registered with the Windows `py`
launcher, pass its executable explicitly:

```powershell
.\setupPedalboard.ps1 -Dev -PythonExe "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
```

Connect the amplifier with a USB data cable and use the exact output printed by
the second command. Close BOSS Tone Studio for the first transport tests so port
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

When Tone Studio is unavailable or a preset's effect assignments are unclear,
run the constrained interactive probe:

```powershell
.\probeKatanaEffects.ps1
```

The probe selects Bank A CH1 (wire program 0), then walks through only the six
officially documented switches: Booster/CC16, Mod/CC17, FX/CC18, Delay/CC19,
Reverb/CC20, and Effect Loop/CC21. It waits for an observation after every ON
and OFF message and prints a result table. Type `PROBE` at its confirmation
prompt. Moving an EFFECTS knob during the probe invalidates the observation.
Ctrl+C attempts to turn the currently active switch off before closing. The
probe does not scan unknown CCs, write presets, or send SysEx.

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

## Linux quick start

```bash
chmod +x ./*.sh
./setupPedalboard.sh
./configurePedalboard.sh
./runPedalboard.sh --debug
./runPedalboard.sh --debug --execute-actions
```

Use `./setupPedalboard.sh --skip-system` if BlueZ, Python venv support, and ALSA
runtime libraries are already installed. The inherited Linux `gatttool` fallback
is used only when BlueZ omits the BlueBoard BLE-MIDI service; its fixed ATT handles
remain specific to the previously tested BlueBoard profile.

## Pedal configuration

The packaged default at
[`python/config/blueboard.json`](python/config/blueboard.json) leaves all four
buttons unmapped. It is safe for scanning, validation, and installation.

The configure command generates `python/config/katana-pedalboard.local.json`
from the documented starter layout. The committed
[`python/config/katana-pedalboard.example.json`](python/config/katana-pedalboard.example.json)
remains a reference for manual customization. The layout is:

| Button | BlueBoard input | Example Katana action |
|---|---:|---|
| A | CC20 press | Program 0 / Bank A CH1 |
| B | CC21 press | Program 1 / Bank A CH2 |
| C | CC22 press | Toggle Booster / CC16 |
| D | CC23 press | Toggle Delay / profile-specific CC |

The example `presetStates` table seeds the controller's predicted effect state
after A or B selects a preset. Pressing a toggle before a known preset is selected
fails clearly instead of guessing. Panel changes, GA-FC actions, or Tone Studio
changes can make predicted state stale; bidirectional SysEx readback is the future
solution.

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
blueboard-katana midi-outputs
blueboard-katana katana-test --output NAME (--program N | --control N --value N)
blueboard-katana probe-effects (--output NAME | --config PATH) [--effects EFFECT ...]
blueboard-katana configure [--output NAME] [--config PATH]
```

`replay`, `validate`, and the test suite do not need hardware. `midi-outputs` is
read-only. `katana-test` is intentionally a direct side-effect command and requires
an explicit output plus message. `configure` discovers both devices and writes
local state, but never opens a MIDI port or sends a command.
`probe-effects` is an explicit, interactive hardware command constrained to the
vendor-documented standard effect switches.

## Development and branches

The repository uses:

```text
feature/<name> -> dev -> main -> version tag
```

- `dev` is the integration branch.
- `main` is the release-ready branch.
- SysEx work belongs in a separate feature branch with captured fixtures.
- `updatePedalboard.ps1 -Branch dev` and `updatePedalboard.sh --branch dev` support
  explicit development updates; production updates default to `main`.

Run the source checks:

```powershell
.\setupPedalboard.ps1 -Dev
.\python\.venv\Scripts\python.exe -m unittest discover -s python\tests -p "test*.py"
.\python\.venv\Scripts\ruff.exe check python\src\blueboard_macro_handler python\tests
```

## Evidence boundary and roadmap

Source-level automated validation does not prove the target amplifier accepted a
message. Before `v1.0.0`, record the amp model, firmware, Windows driver, Tone
Studio version, discovered port names, preset/CC results, reconnect behavior, and
a rehearsal-duration test.

See:

- [`agent-docs/architecture-and-extension-guide.md`](agent-docs/architecture-and-extension-guide.md)
- [`agent-docs/protocol-evidence-and-hardware-validation.md`](agent-docs/protocol-evidence-and-hardware-validation.md)
- [`agent-docs/release-history-and-roadmap.md`](agent-docs/release-history-and-roadmap.md)
- [`agent-docs/KATANA_BLUEBOARD_CODEX_SUMMARY.md`](agent-docs/KATANA_BLUEBOARD_CODEX_SUMMARY.md), the original implementation brief

## License and independence

MIT License. Copyright 2026 Abraham Jhared Flores Azcona.

This independent third-party project is not affiliated with, sponsored by, or
endorsed by IK Multimedia, iRig, BOSS, or Roland. Product names and trademarks
belong to their respective owners.

Mido is MIT-licensed. python-rtmidi is MIT-licensed and wraps RtMidi, which uses a
permissive license. See each dependency's distribution for its complete notices.
