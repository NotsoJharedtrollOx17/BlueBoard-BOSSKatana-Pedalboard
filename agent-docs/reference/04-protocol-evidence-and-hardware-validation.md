# Protocol evidence and hardware validation

## Evidence vocabulary

The parameter registry uses explicit provenance and access levels:

| Evidence | Meaning | Production read | Write |
|---|---|---:|---:|
| `official` | Exact behavior documented by the vendor for the target model | Eligible after scope review | Only with separate validation |
| `capturedMkI` | Reproduced on the target MkI with firmware/restoration evidence | Eligible for the exact captured scope | Not automatic |
| `communityMkI` | Credible MkI community source, not reproduced here | No | No |
| `legacyKatana` | Older related implementation with incomplete model scope | No | No |
| `inferred` | Derived from adjacent addresses/behavior | No | No |
| `unverifiedPlaceholder` | Design-only value | No | No |

`readAccess` is `none`, `probe`, or `production`. `writeAccess` is `none` unless a
separate physically validated write procedure exists. Current production effect
definitions are exact-firmware read-only entries; runtime SysEx writes remain off.

## Physically identified amplifier

The owner's amplifier is the original 100 W BOSS KATANA-100 MkI, not the MkII.
The original-generation BOSS Tone Studio application communicates with it; the
MkII application displayed `WRONG DEVICE`. This model correction overrides older
generic or MkII-oriented assumptions.

`WRONG DEVICE` in that situation identifies an editor/model mismatch, not a USB
cable, driver, or chosen-port failure. Treat the MIDI settings displayed by the
matching original-generation Tone Studio application as the model-specific
standard-MIDI source of truth.

Observed Windows USB-MIDI names were:

- input from amplifier: `KATANA 0`;
- output to amplifier: `KATANA 1`.

Names may differ on another host. Linux preliminary enumeration selected the main
ALSA `KATANA MIDI 1` port independently in both directions with a coordinate-free
unique selector.

## Standard MIDI maps

Program Change is zero-based on the wire:

| Destination | Program |
|---|---:|
| Bank A CH1-4 | 0-3 |
| Panel | 4 |
| Bank B CH1-4 | 5-8 |

The original MkI grouped map captured from the matching Tone Studio settings is:

| Function | Default CC | Semantics |
|---|---:|---|
| Booster/Mod switch | 16 | Shared group |
| Delay/FX switch | 17 | Shared group |
| Reverb switch | 18 | Reverb |
| Send/Return switch | 19 | Effects loop; may be inaudible when inactive |

Tone Studio labels its Program Change values one-based; the bridge uses the
zero-based wire values shown above. Historical observations of expression values
CC80, CC81, and CC82 are not a supported bridge feature and must not be exposed
without a separate model-specific evidence and safety review.

The official MkII map represented in source is independent:

| Function | CC |
|---|---:|
| Booster | 16 |
| Mod | 17 |
| FX | 18 |
| Delay | 19 |
| Reverb | 20 |
| Effect Loop | 21 |

For switch CCs, values 0-63 are off and 64-127 are on. Moving an EFFECTS-section
knob can make the physical knob setting effective and invalidate the earlier MIDI
switch setting. Do not promise independent Delay and FX switching through the
MkI standard-MIDI assignment.

## Standard-MIDI evidence to date

On the original MkI Windows path, Program Change 0 selected A:CH1, CC16 switched
the Booster/Mod group, and CC17 switched the Delay/FX group. The integrated
BlueBoard A/C/D route was physically observed as working after the model/profile
correction. Later v0.4.0 sessions observed A-D routing, momentary LEDs, independent
BlueBoard/Katana reconnect, and clean Ctrl+C metrics. A recovery after a WinMM
send error proves that recovery occurred; it does not establish the cause.

PC1/B, Reverb, Send/Return, every reconnect/endurance scenario, and each platform
retain their own evidence requirements. Do not expand one successful message into
a blanket hardware-support claim.

## MkI SysEx wire format

The supported protocol core builds and parses complete Roland MkI frames:

```text
F0 41 <device-id> 00 00 00 33 12 <address:4> <data...> <checksum> F7  (DT1)
F0 41 <device-id> 00 00 00 33 11 <address:4> <size:4> <checksum> F7     (RQ1)
```

All payload bytes are seven-bit values. The Roland checksum is computed across
address plus data/size so that the low seven bits of the sum including checksum
are zero. Addresses and sizes use four-byte base-128 arithmetic.

`MidiCommand.data` contains complete wire bytes including `F0`/`F7`. Mido sends
and callbacks use payload-only SysEx representations internally, so the transport
removes/adds framing at the boundary. The parser requires callers to declare
whether framing is present and validates manufacturer, model, command, shape,
seven-bit values, and checksum.

## Production read definitions

The registry currently permits six strict-boolean reads only for
`model=katana100`, exact firmware `4.00`:

| State | Address | Length | Access |
|---|---|---:|---|
| Boost enabled | `60 00 00 30` | 1 | production read |
| Mod enabled | `60 00 01 40` | 1 | production read |
| FX enabled | `60 00 03 4C` | 1 | production read |
| Delay enabled | `60 00 05 60` | 1 | production read |
| Reverb enabled | `60 00 06 10` | 1 | production read |
| Effect Loop enabled | `60 00 06 55` | 1 | production read |

Only `00` and `01` decode as booleans. Other values are unknown/error, never
implicitly true or false. All six entries have `writeAccess=none`.

## SysEx observations to date

The 2026-08-30 Windows session used input `KATANA 0` and output `KATANA 1`.
Current-selection reads distinguished PC0/CH1 and PC4/Panel. Six effect queries
returned checksum-valid, address-matched responses without retries/timeouts. The
recorded baseline and restoration snapshots matched: Boost on; Mod and FX off;
Delay, Reverb, and Effect Loop on.

This supports the bounded read path and the exact v4.00 registry promotion. The
Windows runtime gate still requires controlled per-effect fixture sets and the
full live runtime matrix. A standalone `sysex-probe` does not synchronize another
running process; only the integrated `KatanaRuntime` path owns live state.

The preliminary Linux active startup opened ALSA input before output, received
six valid replies in roughly 113 ms, and reported six requests/replies with zero
retries, timeouts, or checksum failures. A human comparison against the physical
amplifier remains unchecked in the Linux release gate.

## Bounded probe behavior

The public probe exposes predefined targets only:

- `effect-states`: the six known temporary-patch flags;
- `current-selection`: editor-mode enter, one bounded read, editor-mode exit in
  cleanup; and
- `panel-snapshot`: a bounded predefined range whose returned chunks remain
  separate rather than being fabricated into a contiguous response.

The probe opens input before output, permits one request at a time, records full
sent/received bytes and decoded fields, and fails unless all required replies are
valid. It exposes neither arbitrary addresses nor a general DT1 write. Saving a
sanitized fixture requires a second confirmation.

## Safe standard-MIDI validation sequence

Before sending, record model, firmware, OS, driver/backend, application family,
USB path, exact input/output names, receive channel, baseline state, backup, and
restoration location.

1. Back up Tone Settings and set a safe volume.
2. Enumerate ports; do not open or send during this step.
3. Close competing MIDI applications.
4. Send Program Change 0; observe A:CH1.
5. Send Program Change 1; observe A:CH2.
6. Send CC16 on/off on the MkI; observe Booster/Mod.
7. Send CC17 on/off; observe Delay/FX.
8. Restore the original state.
9. Run the bridge dry, then active A, A/B, and C/D in stages.
10. Test each device reconnect independently and confirm cleanup.

Typed consent is required immediately before a sending probe. A send log is not
a physical observation.

## Safe SysEx evidence sequence

For each candidate read:

1. record exact physical model and firmware using the BOSS-prescribed check;
2. capture a baseline read;
3. change exactly one flag through a validated standard control or physical/Tone
   Studio operation;
4. close any competing MIDI client;
5. capture the changed value and confirm intended/coupled physical behavior;
6. restore the original state and capture restoration;
7. sanitize identifiers and attach bytes, timing, address, firmware, observation,
   and restoration metadata;
8. promote access only after review.

No SysEx write is required for the v1.0.0 state-awareness scope.

## Windows acceptance still relevant to v1.0.0

- Re-run the 167-test/Ruff/package/script gates from the candidate revision.
- Confirm generated exact-firmware profile and read-only doctor.
- Confirm six queried startup values against the amplifier.
- Confirm A/B post-PC snapshots and first-press C/D pre-read/verification.
- Confirm failed reads produce unknown state and reject relative toggles.
- Confirm Katana and BlueBoard reconnect independently and Ctrl+C closes cleanly.
- Retain a duration-limited 60-minute active rehearsal with final metrics.

## Linux acceptance still relevant to v1.0.0

The checked-in Linux record currently has preliminary setup, ALSA, doctor, BLE
profile, short dry-run, and short startup-read passes. It still requires sanitized
evidence for:

- physical mode/firmware confirmation and backup preparation;
- A-D decoding/actions and amplifier-matched six-state startup;
- post-PC and pre/post-toggle synchronization;
- momentary LEDs in dry and active modes;
- BlueBoard and Katana reconnect;
- failed-read unknown behavior;
- Ctrl+C cleanup;
- 60-minute active endurance; and
- selector survival across an operator-authorized reboot.

The same candidate must preserve Windows behavior. Automated Linux tests do not
stand in for these human observations.

## Evidence handling rules

- Sanitize Bluetooth addresses, usernames, host paths, serial numbers, and
  unrelated devices.
- Preserve exact MIDI/SysEx bytes, timestamps, exit status, metrics, model,
  firmware, expected behavior, observed behavior, and restoration result.
- Keep ignored raw logs local; attach only reviewed excerpts or fixtures.
- Record failure and recovery separately from root-cause hypotheses.
- Never check a box based only on source inspection or automated mocks when it
  requests a physical observation.
