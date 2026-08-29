# Release history and roadmap

## 0.1.0 development baseline

The initial bridge ports the maintained Python runtime from iRig BlueBoard Macro
Handler v1.0.0 and removes its duplicate milestone modules. It adds:

- a Katana configuration and typed actions;
- pure Program Change and Control Change constructors;
- lazy Mido/RtMidi transport with deterministic port selection;
- preset selection and predicted effect on/off state;
- failure isolation, reopen-on-next-command, close behavior, logs, and metrics;
- `midi-outputs` and explicit `katana-test` commands;
- a bounded interactive CC16-CC21 effect-switch probe with interruption cleanup;
- harmless defaults and an A/B preset, C/D effect example;
- Windows/Linux setup, run, scan, port-listing, and branch-aware update scripts;
- Windows/Linux CI configuration and an expanded unit suite.

The runtime is capped at Python 3.10-3.12 because the current python-rtmidi 1.5.8
release publishes prebuilt Windows/Linux wheels only through CPython 3.12. A clean
install on Python 3.14 correctly exposed the unsupported source-build fallback;
setup now rejects that interpreter before invoking pip.

The initial baseline was source-level implementation evidence. The subsequent
2026-08-23 Windows work corrected the target model to the original 100 W
KATANA-100, added its grouped MIDI profile, and physically validated the
integrated A/C/D path through `KATANA 1`. Reconnect, endurance, Linux, expression,
and SysEx claims remain explicitly unvalidated.

## 0.2.0 Windows-first setup and reliability release

Version 0.2.0 makes the validated original KATANA-100 profile the recommended
first-run path without changing the JSON schema or adding new MIDI capabilities.
It adds one shared model/profile registry, a hybrid guided configuration wizard,
safe timestamped local-profile backups, a read-only `doctor` command, concise
runtime mapping summaries, and a model-aware bounded switch probe.

The release target is Windows with the original KATANA-100. Linux scripts and
Python 3.10/3.12 CI remain as an experimental compatibility path, not a hardware
qualification claim. Expression control, SysEx, authoritative state readback,
and persistent state LEDs remain deferred.

Local source validation on 2026-08-24 passed 96 unit tests, Ruff, PowerShell and
shell syntax checks, Markdown link/fence checks, `git diff --check`, isolated
sdist/wheel builds, and installed-wheel `--version`, `validate`, and fixture
replay smoke tests. CI and the physical Windows acceptance record remain release
gates.

## 0.3.0 unified Windows onboarding prerelease

Version 0.3.0 replaces the normal Windows setup/configure/doctor sequence with
one `onboardPedalboard.ps1` entry point while retaining every specialist command.
The launcher reuses a compatible local environment or runs setup first. The new
Python `onboard` command then enumerates MIDI outputs and scans the BlueBoard
concurrently, stores the results in a typed snapshot, and reuses that snapshot for
profile generation and readiness evaluation.

Onboarding remains read-only toward the Katana and operating system: it does not
open the MIDI output, send a message, or execute an action. Configuration and the
last-address state are written only after readiness passes and the user confirms
the model-correct mapping. Standalone doctor continues to perform fresh discovery.

The release remains Windows-first and alpha. Linux retains its existing
experimental scripts and CI coverage but receives no unified onboarding launcher.
Expression control, SysEx, authoritative state readback, and persistent
amplifier-state LEDs remain deferred. See `v0.3.0-feature-plan.md` for the release
checklist and physical Windows onboarding gate.

Local source validation on 2026-08-25 passed 101 unit tests, Ruff, PowerShell
syntax, Markdown link/fence checks, `git diff --check`, isolated sdist/wheel
builds, and installed-wheel `--version`, `onboard --help`, `validate`, and replay
smoke tests. Physical Windows onboarding and dry-run observations remain pending.

## 0.4.0 reliability evidence prerelease

Version 0.4.0 adds an explicitly bounded `run --duration-seconds` session and a
Windows `recordPedalboardSession.ps1` helper. The helper writes timestamped,
ignored JSON logs, remains dry-run by default, and requires `-Active` to enable
configured actions. Final metrics now record whether a session reached its
duration limit or was interrupted.

This is the final prerelease scope before v1.0.0: stable support is limited to
the original KATANA-100 (MkI) on Windows once the acceptance record is complete.
Linux and MkII remain experimental; SysEx, expression control, authoritative
state synchronization, and persistent state LEDs remain separate future work.

Windows/MkI smoke validation on 2026-08-29 accepted v0.4.0 as a prerelease:
dry-run, active A-D routing, momentary LEDs, Ctrl+C metrics, and independent
BlueBoard/Katana reconnect behavior were observed. A duration-limited
60-minute rehearsal remains a v1.0.0 gate.

## Capability status

| Capability | Status | Evidence boundary |
|---|---|---|
| BlueBoard scan/connect/reconnect | Ported | Stable source plus mocked lifecycle tests |
| CC20-CC23 edge routing | Ported | Fixtures and router tests |
| Momentary BlueBoard LEDs | Ported, opt-in | Prior hardware evidence; current regression tests |
| Katana PC/CC byte construction | Implemented | Pure unit tests and official receive map |
| MIDI output resolution/transport | Implemented | Fake Mido transport tests |
| Preset/effect controller state | Implemented, predicted | A/C/D physically validated; external changes can make state stale |
| Original KATANA-100 USB-MIDI control | A/C/D validated on Windows | PC0, grouped CC16, and grouped CC17 physically observed 2026-08-23 |
| KATANA-100 MkII USB-MIDI control | Source-supported, hardware unvalidated | Official profile and unit tests only; it is not the user's amplifier |
| Interactive effect probe | Model-aware in source | Profile-derived labels/CCs; physical MkI probe record pending |
| Unified onboarding, guided configuration, and doctor | Implemented | Snapshot reuse is automated; Windows hardware smoke remains pending |
| Katana reconnect | Retry-on-next-command implemented | Simulated failure/reopen test |
| Bidirectional state synchronization | Not implemented | Requires verified SysEx input/query path |
| Deep parameter editing | Not implemented | Empty SysEx registry by design |
| Persistent Katana-state LEDs | Not implemented | Requires authoritative state source |
| C++17 port | Deferred | Python fixtures should become specification |

## Release plan

### Phase 1: standard MIDI proof

- Install the official driver and current firmware.
- Record the actual Katana output name.
- Confirm Program Change 0/1 and the model-specific effect CCs shown by Tone Studio.
- Save a dated hardware result in `agent-docs`.

Exit: the computer controls one preset and one effect without the BlueBoard.

### Phase 2: integrated pedalboard

- Confirm A/B preset and C/D effect actions.
- Exercise unknown-state behavior and external knob changes.
- Test either-device reconnect and Ctrl+C cleanup.
- Run a rehearsal-duration Windows session.

Exit: repeatable live use with disclosed predicted-state semantics.

### Phase 3: Linux qualification

- Run the automated suite in a clean Linux environment.
- Validate ALSA output naming and the normal or compatibility BlueBoard backend.
- Repeat physical smoke/reconnect tests.

Exit: recorded Windows and Linux behavior for a release candidate.

### Phase 4: model-scoped SysEx research

- Capture target-firmware traffic.
- Implement a firmware-scoped parameter registry and guarded framing.
- Add a MIDI input, bounded query worker, response matcher, pacing, and timeouts.
- Query, change, verify, and restore one parameter.

Exit: one parameter has reproduced target-hardware evidence.

### Phase 5: authoritative state and LEDs

- Add startup/readback synchronization.
- Define external-change and unknown-state policies.
- Add a separate `katana-state` LED mode without changing momentary feedback.

Exit: BlueBoard LEDs reflect verified amplifier state.

## Stable-release checklist

- [ ] Unit tests and Ruff pass on supported Windows and Linux Python versions.
- [ ] Wheel and sdist build from a clean `main` commit.
- [ ] Installed wheel passes `--version`, `validate`, and fixture replay.
- [ ] Fresh unified onboarding selects `katana100`, Panel-first, `KATANA 1`, and the intended BlueBoard.
- [ ] Onboarding and a subsequent fresh `doctor` pass without opening the MIDI output or sending a message.
- [x] Amplifier generation, Tone Studio family, and port names are recorded.
- [ ] Exact firmware and BOSS driver versions are recorded in the hardware note.
- [ ] PC0/PC1 and the profile-specific CC assignments are physically confirmed and restored.
- [ ] A-D, dry-run, opt-in actions, and momentary LEDs are smoke-tested; A/C/D actions are confirmed.
- [ ] Katana and BlueBoard reconnect independently.
- [ ] A timestamped v0.4 session log records the 60-minute rehearsal metrics.
- [ ] `dev` is intentionally merged to `main`.
- [ ] A release tag is created only from the validated `main` commit.

## Branch policy

`dev` receives reviewed feature branches. `main` contains release-ready snapshots.
The production updater defaults to `main` and accepts an explicit `dev` selection.
Never put unvalidated SysEx work directly on `main`.
