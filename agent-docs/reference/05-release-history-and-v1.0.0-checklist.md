# Release history and v1.0.0 checklist

## Current decision

The current worktree is `dev`, based on the tagged v0.8.0 source revision, with
package/runtime metadata promoted to v1.0.0. The Linux port and read-only MkI
state-aware runtime are implemented, and Windows/Linux acceptance is complete.
This file now records the final publication mechanics for the stable tag.

Do not move the tag independently of the accepted `main` commit. Metadata,
documentation, automated checks, and Windows/Linux readiness are complete;
publication now depends on the procedural steps below.

## Consolidated release history

### v0.1.0 - bridge baseline

- Ported the maintained Python BLE-MIDI connection/decoder/router foundation.
- Added typed Katana actions, pure PC/CC construction, lazy Mido/RtMidi output,
  deterministic output selection, predicted effect state, failure isolation,
  harmless defaults, scripts, CI, and unit tests.
- Established Python 3.10-3.12 as the supported range.
- Began with generic/MkII assumptions, then corrected the target to the original
  KATANA-100 MkI after physical identification.

### v0.2.0 - Windows-first setup and reliability

- Added shared model/profile registry with separate MkI grouped and MkII maps.
- Added guided configuration, non-interactive explicit options, safe local
  backups, read-only doctor, mapping summaries, and model-aware effect probe.
- Adopted the physically working Panel-first profile and explicit dry/live order.
- Source validation recorded 96 tests; physical acceptance remained separate.

### v0.3.0 - unified Windows onboarding

- Added one onboarding workflow combining environment reuse/setup, concurrent
  hardware discovery, guided config, and readiness evaluation.
- Preserved read-only/no-port-open behavior through configuration.
- Repaired PowerShell interactive input forwarding with native wrapper options.
- Source validation recorded 101 tests.

### v0.4.0 - reliability evidence

- Added bounded `run --duration-seconds` and timestamped JSONL session recording.
- Kept recorders dry by default; required explicit active mode.
- Added stop-reason and final reconnect/transport/action metrics.
- Windows hardware sessions observed A-D, LEDs, independent reconnects, recovery,
  and Ctrl+C. Source validation recorded 108 tests.
- Preserved a distinct 60-minute v1.0.0 rehearsal gate.

### v0.5.0 - MkI SysEx protocol core

- Added strict complete-wire/payload parsing, RQ1/DT1 builders, checksum,
  seven-bit validation, and base-128 arithmetic.
- Added provenance/read/write registry policy with probe-only candidates.
- No hardware port was opened and no amp support was claimed from unit tests.
- Source validation recorded 117 tests.

### v0.6.0 - bounded duplex read probe

- Added deterministic input selection, input-first duplex transport, serialized
  bounded queries, reply matching, traffic records, and read-only CLI targets.
- Physical Windows probing later returned valid current-selection and six effect
  replies with baseline restoration.
- Standalone probe results still did not update normal runtime state.

### v0.7.0 - runtime state bootstrap and recovery

- Added one non-blocking Katana worker owning RQ1, PC, and CC ordering.
- Added atomic six-effect startup/recovery snapshots, exact-firmware production
  read gating, grouped state derivation, post-PC refresh, and read-actuate-read
  toggles.
- Added state provenance, invalidation, mismatch/unknown behavior, and epoch-safe
  reconnect recovery.
- Registry reads are approved for exact MkI firmware 4.00; the dated v0.7.0 live
  runtime/per-effect matrix is accepted for v1.0.0.

### v0.8.0 - Linux integration candidate

- Ported setup, onboarding, doctor, run, probe, and bounded recording workflows
  to Linux Mint 22.2 x86-64.
- Removed general macro backends/actions and Linux `uinput` setup from the product.
- Added Bleak-first BlueZ behavior with narrow discovered/name-bound `gatttool`
  compatibility profiles.
- Added stable per-direction ALSA selector derivation and Linux diagnostics.
- Added Windows/Ubuntu CI and wheel/sdist smoke definitions.
- Linux reported successful setup, doctor, runtime, and hardware acceptance for
  the v1.0.0 target.

## Current capability ledger

| Capability | Source | Physical status |
|---|---|---|
| BlueBoard scan/connect/CC20-23 routing/reconnect | Implemented and tested | Windows and Linux accepted |
| Momentary A-D LED feedback | Implemented, opt-in | Windows and Linux accepted |
| Original MkI PC/CC control | Implemented | Windows and Linux accepted |
| MkII PC/CC control | Implemented profile | Hardware unvalidated |
| MkI SysEx protocol and bounded probe | Implemented | Windows six-read/current-selection observations; Linux short six-read startup |
| MkI runtime state sync | Implemented for exact firmware 4.00 | Windows and Linux matrices accepted |
| Deep SysEx parameter editing/writes | Not implemented | Out of scope |
| Persistent amplifier-state LEDs | Not implemented | Future work |

## Consolidated dated evidence register

| Date / milestone | Observed or verified result | What remains open |
|---|---|---|
| 2026-08-23/24 model correction | Original KATANA-100 MkI identified; original Tone Studio selected; Windows `KATANA 1`, PC0, CC16, CC17, and BlueBoard A/C/D routing observed | Exact firmware was not captured in this initial record; B/PC1 and broader controls were not yet separately observed |
| 2026-08-29 v0.4 Windows smoke | Dry-run and active A-D routing, momentary LEDs, independent BlueBoard/Katana reconnect recovery, and Ctrl+C metrics observed | This is not the 60-minute v1 rehearsal and does not establish the root cause of a recovered WinMM send failure |
| 2026-08-30 v0.7 Windows SysEx | Firmware 4.00 evidence, independent `KATANA 0`/`KATANA 1` selectors, current-selection responses, and six checksum-valid effect-state replies observed; read-only definitions approved | Superseded by the completed v1.0.0 runtime acceptance |
| v0.8 Linux | Mint 22.2 x86-64 setup, ALSA selector derivation, doctor, BLE compatibility, six-read startup, A-D actions, LEDs, reconnects, cleanup, endurance, reboot persistence, and regression checks accepted | No v1.0.0 platform gate remains open |

## Fresh automated review, 2026-08-31

The documentation review found a Windows portability defect in
`testGatttoolProcessLossReturnsToTheReconnectLoop`: it depended on the host
platform instead of explicitly selecting the Linux branch. The test now patches
`blueboard_macro_handler.client.sys.platform` to `linux`.

After that correction, the CI-style Windows command completed:

```text
python -m unittest discover -s python/tests -p "test*.py"
Ran 167 tests
OK (skipped=5)
```

The warnings/errors printed inside this suite are intentional failure-path
fixtures. Readiness is determined by the final exit status and summary, not by
the presence of expected simulated error logs.

## v1.0.0 stable-release gates

### Source and packaging

- [x] Current Windows unit suite passes: 167 tests, 5 expected skips.
- [x] Ruff passes on the final candidate.
- [x] PowerShell and Bash syntax checks pass on the final candidate.
- [x] Markdown links/fences and `git diff --check` pass.
- [x] Windows and Ubuntu CI jobs pass on Python 3.10 and 3.12.
- [x] Clean wheel and sdist builds install and pass `--version`, help, validate,
  replay, and removed-module smoke checks on Windows and Linux.
- [x] Package version, runtime welcome, release notes, and classifier identify
  v1.0.0 coherently; publication now depends only on merge/tag/artifact steps.

### Windows original-KATANA-100 MkI firmware 4.00

- [x] Reconcile the Windows runtime gate with sanitized live results.
- [x] Attach controlled six-effect changed/restored fixture sets or record an
  explicit reviewed decision narrowing that legacy gate.
- [x] Confirm exact input/output, startup six-state match, post-PC refresh, C/D
  first-press pre-read and post-CC verification.
- [x] Confirm unknown behavior, epoch-safe Katana reconnect, BlueBoard reconnect,
  and clean Ctrl+C from the release candidate.
- [x] Complete and retain a duration-limited 60-minute active rehearsal.

### Linux Mint 22.2 x86-64 original MkI firmware 4.00

- [x] Complete the Linux preparation and live evidence captured in the
  consolidated dated-evidence register above.
- [x] Confirm A-D routing, momentary LEDs, startup values against the amp,
  post-PC refresh, and pre/post-toggle verification.
- [x] Confirm independent BlueBoard/Katana reconnect, unknown after failed read,
  Ctrl+C cleanup, and no persistent BlueZ pairing/trust mutation.
- [x] Complete the 60-minute active session with final metrics and exit status 0.
- [x] Reboot under operator control and prove stable ALSA selector resolution and
  one preset/effect action afterward.

### Documentation and release mechanics

- [x] Five canonical agent references consolidate the project history, current
  architecture, evidence boundary, and release gates.
- [x] README is organized as a v1.0.0 release guide with accurate
  quick starts, model distinctions, safety boundary, and acceptance status.
- [x] README status identifies the v1.0.0 package and the completed Windows/Linux
  readiness status.
- [x] Release notes list supported target, experimental MkII boundary, known
  limitations, validation revision, and evidence links.
- [ ] Review `dev` diff against `main`; merge intentionally after approval.
- [ ] Create annotated `v1.0.0` only from the accepted `main` commit.
- [ ] Verify the tag, package metadata, installed CLI version, and GitHub release
  all identify the same commit/version.

## Release procedure

1. Freeze a candidate commit on `dev`.
2. Run source, lint, script, Markdown, package, and clean-install gates.
3. Perform Windows and Linux acceptance from that exact revision.
4. Sanitize and review evidence; update checklists with dates and accepted commit.
5. Change package/runtime version and development classifier to stable.
6. Re-run the automated gates because metadata changed.
7. Review and merge `dev` to `main` without unrelated changes.
8. Verify `main` points to the accepted content.
9. Create annotated tag `v1.0.0` from that `main` commit.
10. Build/publish artifacts from the tag and smoke-test the installed result.

If any physical or automated item fails, return to a new candidate revision and
repeat affected gates. Do not move a tag to hide a changed release commit.

## Known limitations for v1.0.0

- Exact-firmware SysEx state sync supports the original KATANA-100 MkI v4.00 only.
- MkII has a standard-MIDI source profile but no project hardware qualification
  and no SysEx synchronization.
- The bridge does not edit deep parameters, write SysEx parameter values, store
  patches, control expression inputs, or display persistent amp state on LEDs.
- BlueBoard LEDs are momentary input feedback.
- Linux qualification is Linux Mint 22.2 x86-64, not every Linux distribution.
- The Linux compatibility backend depends on deprecated `gatttool` when BlueZ
  omits the BLE-MIDI service; it is deliberately narrow and fail-closed.
- Tone Studio/DAW port ownership can prevent simultaneous access.

## Post-v1 roadmap

1. Persistent, explicitly selected Katana-state LED mode driven only by
   authoritative non-stale snapshots.
2. Additional original-MkI firmware qualification using separate registry scope.
3. MkII physical qualification and a separate protocol-evidence program.
4. Dynamic Linux BLE compatibility improvements that can eventually remove the
   deprecated `gatttool` dependency.
5. Expression support only after model-specific standard-MIDI and hardware proof.
6. A future C++ port only after Python fixtures and lifecycle behavior form a
   stable executable specification.

## Documentation consolidation boundary

The five references are intentionally self-contained. They preserve the dated
acceptance status, protocol constraints, known facts, and open gates formerly
recorded in milestone plans, hardware worksheets, and the SysEx design
specification. Do not recreate parallel plans: add new evidence, decisions, or
release results to the relevant reference with its date and candidate revision.
