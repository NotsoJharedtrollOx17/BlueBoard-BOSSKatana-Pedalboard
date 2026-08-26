# Original KATANA-100 breakthrough record

**Date:** 2026-08-23 through 2026-08-24  
**Status:** Windows A/C/D hardware path working; profile-specific follow-up work remains.

## Why this note exists

The bridge began with an incorrect assumption that the target amplifier was a
KATANA-100 MkII. Hardware testing, the successful Tone Studio connection, and
the Tone Studio MIDI settings screen established that the physical amplifier is
the original 100 W KATANA-100 (MkI). This note preserves the correction and the
working configuration so later work does not repeat the MkI/MkII confusion.

The fuller evidence record remains in
[`protocol-evidence-and-hardware-validation.md`](protocol-evidence-and-hardware-validation.md).

## Confirmed hardware facts

| Area | Confirmed result |
|---|---|
| Amplifier | Original BOSS KATANA-100, 100 W (MkI) |
| Host platform | Windows with Python 3.10 bridge runtime |
| Main bridge output | `KATANA 1` |
| BlueBoard | BLE discovery and four-button routing work |
| Receive channel | MIDI channel 1 |
| Firmware | Updated during this work; exact installed version was not recorded |
| Tone Studio | Original **BOSS TONE STUDIO for KATANA**, not the MkII application |

Windows also exposes `KATANA DAW CTRL 2` and `KATANA CTRL 3`. Their presence does
not identify the amplifier generation and does not replace `KATANA 1` as the
validated bridge output.

## The Tone Studio edge case

Opening **BOSS TONE STUDIO for KATANA MkII** against this original amplifier
produces `WRONG DEVICE`, even if both MIDI fields read `KATANA`. That symptom is
an application/model mismatch, not proof of a bad USB cable, bad driver, or bad
MIDI-port choice.

The original Tone Studio application is older and Adobe AIR based. It is the
correct editor for this amplifier and exposes the authoritative MIDI settings.

## Captured MIDI map

Tone Studio displayed the following assignments:

| Tone Studio setting | MIDI message used by the bridge |
|---|---|
| A:CH1 | Program Change 0 |
| A:CH2 | Program Change 1 |
| A:CH3-A:CH4 | Program Change 2-3 |
| Panel | Program Change 4 |
| B:CH1-B:CH4 | Program Change 5-8 |
| Booster/Mod switch | CC16, `0` off / `127` on |
| Delay/FX switch | CC17, `0` off / `127` on |
| Reverb switch | CC18, `0` off / `127` on |
| Send/Return switch | CC19, `0` off / `127` on |
| Expression pedal | CC82, continuous value |
| GA-FC EXP1 / EXP2 | CC80 / CC81, continuous values |

Tone Studio presents its Program Change values as one-based numbers. The bridge
and standard MIDI messages use zero-based values, hence A:CH1 is wire Program
Change 0 and Panel is wire Program Change 4.

## What the earlier tests meant

The earlier symptoms were valid observations but were interpreted against the
wrong model map:

| Test result | Actual MkI meaning |
|---|---|
| CC16 controlled Booster | Expected: Booster/Mod is CC16 |
| CC18 affected Reverb | Expected: Reverb is CC18 |
| CC19 made no audible Delay change | Expected: it addresses Send/Return, which was not active |

Therefore, a successful command log only proves transport delivery. The Tone
Studio system page is required to identify which physical function a CC controls.

## Working bridge profiles

The runtime now supports two model names:

| Model value | Purpose |
|---|---|
| `katana100` | Original KATANA-100 grouped-switch profile |
| `katana100MkII` | MkII independent-switch profile; not hardware-validated on this amp |

The local, ignored profile for this workstation uses `katana100` and maps:

```text
A / BlueBoard CC20 -> Panel / Program Change 4
B / BlueBoard CC21 -> A:CH2 / Program Change 1
C / BlueBoard CC22 -> Booster/Mod toggle / CC16
D / BlueBoard CC23 -> Delay/FX toggle / CC17
```

The tracked reference copy is
[`python/config/katana-pedalboard-panel.example.json`](../python/config/katana-pedalboard-panel.example.json).
Use the normal local launcher for routine testing:

```powershell
.\runPedalboard.ps1 --debug --execute-actions
```

The bridge is dry-run by default. `--execute-actions` is deliberately required
before it opens the Katana output and changes the amp.

## Important effect limitation

On the original KATANA-100, Delay and FX share a single `DELAY/FX` slot and
CC17. D toggles whichever effect is assigned to that slot; it cannot independently
toggle Delay and FX, nor can both be active in that same slot at once.

The practical solution is separate Tone Studio presets: one with Delay assigned,
another with FX assigned, then use Program Change to recall the desired sound.

Likewise, Booster and Mod share CC16. Reverb is independently available through
CC18. The Version 4 `DELAY2` feature uses the Reverb-side slot, so it is an
alternative to Reverb rather than another independent reverb-side switch.

## Confirmed versus pending

Confirmed on the physical amplifier:

- Windows USB-MIDI transport through `KATANA 1`.
- Program Change 0 selecting A:CH1.
- CC16 switching Booster/Mod.
- CC17 switching the Delay/FX slot.
- BlueBoard A/C/D routing when actions are explicitly enabled.
- Panel-first configuration using Program Change 4 validates as configuration;
  its live physical behavior should be recorded in the next smoke test.

Still pending:

- Program Change 1/B physical confirmation after the Panel-first remap.
- Reverb, Send/Return, and expression-pedal routing through BlueBoard.
- Katana and BlueBoard reconnect tests, a rehearsal-duration run, and Linux.
- Physical validation of the v0.2.0 model-aware effect probe. Its source now
  derives grouped labels and CCs from the original `katana100` profile.
- SysEx parameter readback, authoritative effect-state synchronization, and
  persistent amplifier-state LED feedback.

## Relevant commits

| Commit | Purpose |
|---|---|
| `3bfbef1` | Adds `katana100` original-Katana MIDI profile support |
| `c9d16ae` | Records original-Katana validation and the Tone Studio edge case |
| `84be17f` | Adds the tracked Panel-first original-Katana profile |

## Operating rule for future changes

Treat the Tone Studio MIDI settings visible on the connected amplifier as the
source of truth. Do not copy MkII CC labels, SysEx addresses, or application
instructions into an original-Katana configuration without model-specific
evidence.

For current vendor downloads and original-model manuals, use the
[BOSS KATANA-100 support page](https://www.boss.info/us/support/by_product/katana-100/).
