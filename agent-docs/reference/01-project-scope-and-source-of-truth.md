# Project scope and source of truth

## Purpose of this reference set

This file is the entry point for future maintainers and coding agents. The five
files in this directory are the complete maintained documentation set: they
consolidate the implementation decisions, protocol boundary, operations, and
dated acceptance status formerly spread across milestone plans and records.

Read the five files in this directory in order:

1. this project scope and source-of-truth guide;
2. `02-architecture-and-runtime.md`;
3. `03-setup-configuration-and-operations.md`;
4. `04-protocol-evidence-and-hardware-validation.md`;
5. `05-release-history-and-v1.0.0-checklist.md`.

When a summary conflicts with current code or a new physical observation,
investigate the conflict and update the applicable reference instead of silently
choosing the more convenient claim.

## Product in one paragraph

BlueBoard + BOSS Katana Pedalboard is a Python 3.10-3.12 bridge that receives
BLE-MIDI button events from an iRig BlueBoard and routes them to documented
Program Change and Control Change operations on a BOSS KATANA amplifier over
USB-MIDI. For the physically qualified original KATANA-100 MkI firmware 4.00
profile, it also performs bounded, read-only SysEx queries to establish and
verify the six live effect flags needed for safe relative toggles. It supports
Windows and a Linux Mint 22.2 x86-64 port, defaults to dry-run, and keeps
momentary BlueBoard LED feedback separately opt-in.

## Authority order

Use this order when deciding what the project may claim or do:

1. Direct observation on the identified physical amplifier and BlueBoard,
   including the matching original BOSS Tone Studio application.
2. Sanitized dated acceptance records and captured fixtures in this repository.
3. Current executable source, tests, package metadata, and committed profiles.
4. Official BOSS/Roland and IK Multimedia documentation for the exact model.
5. Community protocol research, explicitly labeled with its provenance.

Never infer physical support merely because a byte-level unit test passes. Never
apply a MkII map or application to the original KATANA-100 MkI.

## Supported and implemented targets

| Target | Implementation | Physical evidence | Release meaning |
|---|---|---|---|
| Original KATANA-100 MkI, firmware 4.00, Windows | Full PC/CC and read-only runtime state-sync path | Standard MIDI A-D, six SysEx reads, reconnect recovery, endurance/demo evidence, and automated checks accepted | Validated v1.0.0 target |
| Original KATANA-100 MkI, firmware 4.00, Linux Mint 22.2 x86-64 | Full v1.0.0 port | Setup, ALSA selection, doctor, BLE compatibility, A-D/runtime behavior, reconnect, endurance, reboot, and regression checks accepted | Validated v1.0.0 target |
| KATANA-100 MkII | Standard MIDI model exists in source | No project hardware qualification | Source-supported and experimental; no MkII SysEx state synchronization |
| Other Katana models or firmware | Not approved | None | Out of scope until model-specific evidence and profiles are added |

“Implemented” and “released” are intentionally different. The current checkout
is v1.0.0 on the development worktree and the Windows/Linux readiness gates are
accepted; publication still requires the normal main-branch/tag/artifact steps.

## Product boundary

The retained `blueboard_macro_handler` Python namespace is a compatibility name,
not the current product scope. Configuration accepts only:

- `katana` actions;
- harmless `log` actions; and
- `null` for an unmapped binding.

Keyboard injection, UDP, process launch, `evdev`, `uinput`, daemonization,
automatic startup, arbitrary SysEx access, deep parameter editing, patch storage,
and generic macro handling are not part of this product. Legacy macro action
types must fail with migration guidance rather than execute.

The project also does not pair or trust the BlueBoard, edit persistent BlueZ
device state, scan arbitrary Katana CCs, or expose a general SysEx DT1 write
surface.

## Core user contract

- Dry-run is the default.
- `--execute-actions` is required before configured Katana actions can send.
- `--led-feedback` controls momentary A-D BlueBoard lights independently.
- Configuration and doctor workflows enumerate hardware but do not open Katana
  MIDI ports or send MIDI.
- MIDI input and output names are selected independently and must resolve exactly
  or as unique substrings.
- Unknown synchronized state is never treated as “off.” A relative toggle is
  rejected until the required group state is known.
- A transport failure invalidates observed state. Recovery opens input before
  output and obtains a new state snapshot before relative control resumes.
- SysEx state awareness is read-only and restricted to approved definitions for
  the exact configured model and firmware.

## BlueBoard and default pedal map

The validated BlueBoard mode emits channel-1 CC20-CC23. Press is value 127 and
release is value 0. The router normally binds press edges only.

The recommended original-KATANA Panel-first layout is:

| Button | BlueBoard event | Katana action |
|---|---|---|
| A | CC20 press | Panel, wire Program Change 4 |
| B | CC21 press | Bank A CH2, wire Program Change 1 |
| C | CC22 press | Toggle grouped Booster/Mod, normally CC16 |
| D | CC23 press | Toggle grouped Delay/FX, normally CC17 |

Program numbers are zero-based on the wire: Bank A CH1-4 are 0-3, Panel is 4,
and Bank B CH1-4 are 5-8.

## Repository map

| Path | Role |
|---|---|
| `python/src/blueboard_macro_handler/` | Maintained application source |
| `python/src/blueboard_macro_handler/katana/` | MIDI protocol, transport, session, registry, and runtime state logic |
| `python/tests/` | Unit and platform-contract tests |
| `python/config/` | Qualified MkI default, examples, and ignored generated local profile |
| root `*.ps1` and `*.sh` | Windows and Linux setup, onboarding, diagnostics, run, probe, and recording entry points |
| `.github/workflows/ci.yml` | Windows/Ubuntu Python and package-smoke definitions |
| `agent-docs/reference/` | Five canonical maintainer references |

## Change rules

Before changing behavior:

1. identify the amplifier model, generation, firmware, operating system, and
   current evidence class;
2. preserve the dry-run and explicit-action boundary;
3. keep BlueBoard BLE and Katana MIDI lifecycles independently recoverable;
4. add source tests before broadening a parser, registry, or side-effect path;
5. update the applicable canonical reference with dated acceptance data;
6. use a bounded hardware procedure with backup, safe volume, explicit consent,
   stop conditions, and restoration when physical verification is required.

## Current v1.0.0 decision

The stable target is a Windows and Linux bridge for the original KATANA-100 MkI
firmware 4.00, with documented PC/CC control and read-only state-aware toggles.
The source and cross-platform validation are complete for the stated v1.0.0
target. Publication now requires only the procedural steps in
`05-release-history-and-v1.0.0-checklist.md`; a tag must identify the accepted
`main` commit.
