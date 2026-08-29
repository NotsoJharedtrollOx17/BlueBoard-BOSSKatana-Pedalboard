# BlueBoard + BOSS Katana Pedalboard

> **Notice:** This independent, community-developed project is not affiliated
> with, sponsored by, or endorsed by IK Multimedia, iRig, BOSS, Roland, or any
> manufacturer of referenced hardware or software. Product names and trademarks
> belong to their respective owners.

A Python bridge that turns an iRig BlueBoard into a configurable four-button
pedalboard for original and MkII BOSS KATANA-100 amplifiers. The original
KATANA-100 on Windows is the release target; Linux remains an experimental,
source-tested compatibility path until physical qualification.

The project carries forward the proven BLE-MIDI connection, decoding, routing,
reconnection, dry-run, logging, Linux compatibility, and optional momentary LED
feedback from
[`iRigBlueBoard-Macro-Handler` v1.0.0](https://github.com/NotsoJharedtrollOx17/iRigBlueBoard-Macro-Handler/tree/v1.0.0).
It adds a separate USB-MIDI output path for documented Katana Program Change and
Control Change messages.

Status: `0.4.0` alpha reliability-evidence snapshot. The original KATANA-100
A/C/D path has been physically validated on Windows. B, independent reconnects,
the full release smoke test, and a one-hour rehearsal run remain v1.0.0 gates.

## Author

- Abraham Jhared Flores Azcona _(NotsoJharedtrollOx17)_
  `abrahamjhared.flores@gmail.com`

## What the first milestone supports

- BlueBoard A-D input as channel 1 CC20-CC23 with press/release edge routing.
- BOSS preset selection through standard MIDI Program Change.
- Model-correct effect switches: grouped CC16-CC19 on the original KATANA-100
  and independent CC16-CC21 on MkII.
- Exact or unique-substring MIDI output selection; no arbitrary first-port choice.
- Predicted per-preset effect state with an explicit unknown-state failure.
- Dry-run by default. Amplifier and operating-system actions require
  `--execute-actions`.
- Independent, opt-in momentary BlueBoard LEDs through `--led-feedback`.
- Unified Windows onboarding plus specialist Windows/Linux helpers, replay
  fixtures, structured logging, metrics, and a Windows/Linux CI definition.

This milestone does not write Katana SysEx. Detailed effect type and parameter
editing remains in BOSS Tone Studio until addresses are captured and reproduced on
the exact target model and firmware.

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
- Original KATANA-100 or KATANA-100 MkII with a USB data cable. The original
  KATANA-100 is the hardware-qualified target for v0.4.0.
- Model-correct BOSS Tone Studio, compatible firmware, and the official BOSS USB
  driver on Windows.
- Bluetooth support compatible with Bleak.

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
v0.4.0 environment or runs setup first, then enumerates Katana MIDI outputs and
scans for the BlueBoard concurrently. One typed discovery snapshot feeds both the
guided configuration and readiness evaluation, so the same devices are not
scanned twice. The wizard asks for the amplifier generation and starter layout,
records the MIDI channel and optional firmware, explains the predicted-state
assumption, shows the complete A-D map, and confirms before writing the ignored
local profile at `python/config/katana-pedalboard.local.json`.

Onboarding never opens a MIDI output, sends MIDI, or executes an operating-system
action. Unique devices are selected automatically; ambiguous Katana outputs or
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
  -Layout panel-first -Output "KATANA 1" -Address "BLUEBOARD-ADDRESS" `
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

## Linux quick start

Linux remains experimental in v0.4.0: automated regressions run on Linux, but
the full BlueBoard-to-amplifier path has not been physically qualified.

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
from a model-correct starter layout. The committed
[`python/config/katana-pedalboard.example.json`](python/config/katana-pedalboard.example.json)
remains a reference for manual customization. The layout is:

| Button | BlueBoard input | Example Katana action |
|---|---:|---|
| A | CC20 press | Program 4 / Panel for the recommended MkI profile |
| B | CC21 press | Program 1 / Bank A CH2 |
| C | CC22 press | Toggle Booster/Mod / CC16 |
| D | CC23 press | Toggle Delay/FX / CC17 |

The example `presetStates` table seeds the controller's predicted effect state
after A or B selects a preset. Pressing a toggle before a known preset is selected
fails clearly instead of guessing. Panel changes, GA-FC actions, or Tone Studio
changes can make predicted state stale; bidirectional SysEx readback is the future
solution.

For the original KATANA-100, a Panel-first profile is included at
[`python/config/katana-pedalboard-panel.example.json`](python/config/katana-pedalboard-panel.example.json).
It maps A to Panel (wire Program Change 4), B to A:CH2, C to Booster/Mod, and D
to Delay/FX. Test it with:

```powershell
.\python\.venv\Scripts\python.exe -m blueboard_macro_handler run `
  --config .\python\config\katana-pedalboard-panel.example.json --debug --execute-actions
```

The Panel profile assumes Booster/Mod and Delay/FX are initially off. If the
physical Panel state differs, update `presetStates["4"]` before using C or D.

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
blueboard-katana onboard [--output NAME] [--config PATH]
blueboard-katana doctor --config PATH [--scan-timeout SECONDS]
```

`replay`, `validate`, and the test suite do not need hardware. `midi-outputs` is
read-only. `katana-test` is intentionally a direct side-effect command and requires
an explicit output plus message. `configure` discovers both devices and writes
local state, but never opens a MIDI port or sends a command.
`onboard` performs concurrent discovery, guided configuration, and readiness
evaluation from one snapshot. It writes only after all required checks pass and
the user confirms the proposed profile.
`probe-effects` is an explicit, interactive hardware command constrained to the
selected model profile. Raw-output use requires `--model`; configuration-based
use derives the model and first preset. `doctor` is read-only and never opens the
MIDI output or sends a command.

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
- [`agent-docs/v0.3.0-feature-plan.md`](agent-docs/v0.3.0-feature-plan.md), the unified onboarding implementation and release checklist
- [`agent-docs/v0.3.0-onboarding-input-repair.md`](agent-docs/v0.3.0-onboarding-input-repair.md), the diagnosis and acceptance plan for the PowerShell input repair
- [`agent-docs/v0.4.0-feature-plan.md`](agent-docs/v0.4.0-feature-plan.md), the final reliability-evidence prerelease plan
- [`agent-docs/v0.4.0-windows-mki-acceptance.md`](agent-docs/v0.4.0-windows-mki-acceptance.md), the v1.0.0 Windows MkI physical release record
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
