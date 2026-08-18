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
- harmless defaults and an A/B preset, C/D effect example;
- Windows/Linux setup, run, scan, port-listing, and branch-aware update scripts;
- Windows/Linux CI configuration and an expanded unit suite.

The runtime is capped at Python 3.10-3.12 because the current python-rtmidi 1.5.8
release publishes prebuilt Windows/Linux wheels only through CPython 3.12. A clean
install on Python 3.14 correctly exposed the unsupported source-build fallback;
setup now rejects that interpreter before invoking pip.

This is source-level implementation evidence. No physical Katana validation is
claimed by this repository snapshot.

## Capability status

| Capability | Status | Evidence boundary |
|---|---|---|
| BlueBoard scan/connect/reconnect | Ported | Stable source plus mocked lifecycle tests |
| CC20-CC23 edge routing | Ported | Fixtures and router tests |
| Momentary BlueBoard LEDs | Ported, opt-in | Prior hardware evidence; current regression tests |
| Katana PC/CC byte construction | Implemented | Pure unit tests and official receive map |
| MIDI output resolution/transport | Implemented | Fake Mido transport tests |
| Preset/effect controller state | Implemented, predicted | Unit tests; hardware not yet validated |
| KATANA-100 MkII USB-MIDI control | Awaiting hardware | Must be observed on target amp |
| Katana reconnect | Retry-on-next-command implemented | Simulated failure/reopen test |
| Bidirectional state synchronization | Not implemented | Requires verified SysEx input/query path |
| Deep parameter editing | Not implemented | Empty SysEx registry by design |
| Persistent Katana-state LEDs | Not implemented | Requires authoritative state source |
| C++17 port | Deferred | Python fixtures should become specification |

## Release plan

### Phase 1: standard MIDI proof

- Install the official driver and current firmware.
- Record the actual Katana output name.
- Confirm Program Change 0/1 and CC16/CC19 on the target amp.
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

### Phase 4: MkII SysEx research

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
- [ ] BOSS driver, firmware, Tone Studio, and port names are recorded.
- [ ] PC0/PC1 and CC16/CC19 are physically confirmed and restored.
- [ ] A-D, dry-run, opt-in actions, and momentary LEDs are smoke-tested.
- [ ] Katana and BlueBoard reconnect independently.
- [ ] Rehearsal-duration metrics are recorded.
- [ ] `dev` is intentionally merged to `main`.
- [ ] A release tag is created only from the validated `main` commit.

## Branch policy

`dev` receives reviewed feature branches. `main` contains release-ready snapshots.
The production updater defaults to `main` and accepts an explicit `dev` selection.
Never put unvalidated SysEx work directly on `main`.
