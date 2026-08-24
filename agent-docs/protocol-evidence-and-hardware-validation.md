# Protocol evidence and hardware validation

## Evidence classes

This project separates:

1. official vendor documentation;
2. source behavior and automated tests;
3. captured interoperability evidence;
4. physical observations on the user's equipment;
5. community reverse engineering and inference.

Passing unit tests proves byte construction and software boundaries. It does not
prove a particular Katana generation accepts those bytes over its USB driver.

## Official standard-MIDI evidence

The current English KATANA MkII owner's manual lists receive channel 1-4, OMNI
off, Program Change values 0-8, and CC16-CC21 for Booster, Mod, FX, Delay, Reverb,
and Effect Loop. Off is 0-63 and on is 64-127. It also warns that using an Effects
knob discards the prior MIDI on/off setting.

The same manual describes the USB port, the required driver, and effect editing
through dedicated software. The physical MIDI IN connector is model-limited in
the manual. Therefore USB-MIDI behavior on the KATANA-100 MkII combo remains an
explicit hardware-validation item even though the driver exposes MIDI ports.

Primary sources:

- <https://www.boss.info/us/support/by_product/katana-100/>
- <https://www.boss.info/us/support/by_product/katana-100_mk2/>
- <https://static.roland.com/assets/media/pdf/KATANA-Mk2_eng02_W.pdf>
- <https://static.roland.com/assets/media/pdf/BTS_KTN-Mk2_eng01_W.pdf>

## Current source evidence

The software constructs ordinary channel-voice messages only:

```text
Program Change: 0xC0 | channel, program
Control Change: 0xB0 | channel, controller, value
```

The transport resolves a requested output deterministically, opens it through
Mido/RtMidi, sends one parsed message, and closes on shutdown. Tests use a fake
transport and never require the amplifier.

The SysEx parameter registry is empty. Community original-Katana maps are not
treated as MkII proof.

## Windows observation, 2026-08-23

### Model correction and application trap

The target amplifier is the original 100 W KATANA-100 (MkI), not a KATANA-100
MkII. The initial MkII assumption made the documented CC16-CC21 map look
applicable when it was not. Windows exposed `KATANA 1`, `KATANA DAW CTRL 2`, and
`KATANA CTRL 3` alongside the Windows wavetable output; those port names alone do
not distinguish the amplifier generation.

Two different Tone Studio applications can coexist on Windows. Opening BOSS TONE
STUDIO for KATANA MkII against the original KATANA produces `WRONG DEVICE` even
when MIDI IN and MIDI OUT are both `KATANA`. The application that successfully
edited this amplifier was the original BOSS TONE STUDIO for KATANA, an older
Adobe AIR application. Always identify both the chassis generation and the Tone
Studio product before diagnosing cable, driver, or port selection.

The user updated the amplifier firmware before the final validation. The exact
firmware number was not captured, so the local configuration records it as
`unknown` rather than inferring a version from the update procedure.

### Captured system assignments

Tone Studio exposed the following receive settings on the connected amplifier:

| Setting | Tone Studio value | Wire/API interpretation |
|---|---:|---|
| RX channel | Ch.1 | MIDI channel 1 |
| Panel | 5 | Program Change 4 on the wire |
| A:CH1-A:CH4 | 1-4 | Program Change 0-3 on the wire |
| B:CH1-B:CH4 | 6-9 | Program Change 5-8 on the wire |
| Booster/Mod switch | CC16 | Shared switch |
| Delay/FX switch | CC17 | Shared switch |
| Reverb switch | CC18 | Reverb on/off |
| Send/Return switch | CC19 | Effects-loop on/off |
| Expression pedal | CC82 | Continuous controller |
| GA-FC EXP1 | CC80 | Continuous controller |
| GA-FC EXP2 | CC81 | Continuous controller |

This resolves the earlier observations exactly: CC16 controlled Booster/Mod,
CC18 affected Reverb, and CC19 did nothing audible because it addressed
Send/Return with no active loop. CC19 was never the Delay switch on this
amplifier. A broad CC scan was unnecessary.

### End-to-end result

The main `KATANA 1` port accepted Program Change 0 and changed Panel mode to
A:CH1. CC16 values 127 and 0 switched Booster/Mod. After the local profile was
changed to `model: katana100` and its `delay` action was mapped to CC17, the user
confirmed the BlueBoard bridge worked end to end: A selected A:CH1, C controlled
Booster/Mod, and D controlled the shared Delay/FX switch. The BlueBoard address
is intentionally omitted from committed documentation.

This proves the Windows USB-MIDI path and the A/C/D performance path on the
tested original KATANA-100. PC1/B, Reverb, Send/Return, expression input,
independent reconnects, rehearsal-duration reliability, Linux, and SysEx remain
separate validation items.

## Windows hardware checklist

Record the following in a dated test note:

- exact amplifier model and serial-safe identifier;
- system firmware version;
- Windows version;
- BOSS driver version;
- BOSS Tone Studio version;
- USB cable/port;
- `midi-outputs` result;
- whether Tone Studio was closed;
- amplifier receive channel;
- original preset/effect state and restoration result.

Run in this order:

1. Back up the current Tone Settings.
2. Put the amplifier at a safe output volume.
3. List ports without connecting the BlueBoard.
4. Send Program Change 0 and confirm Bank A CH1.
5. Send Program Change 1 and confirm Bank A CH2.
6. Send CC16 value 127 and 0; confirm Booster on and off.
7. Repeat another effect using the CC shown by that model's Tone Studio MIDI
   settings; on the tested original KATANA-100, Delay/FX is CC17.
8. Start the bridge in dry-run and confirm A-D decoding.
9. Enable actions and test A only, then A/B, then C/D from known preset state.
10. Reconnect the Katana while the BlueBoard remains connected.
11. Reconnect the BlueBoard while the Katana remains connected.
12. Confirm Ctrl+C closes both connections.
13. Run a rehearsal-duration session and record failures/reconnect metrics.

Do not generalize a successful Program Change into proof of SysEx parameter
support.

### Bounded switch probe

The current `probeKatanaEffects.ps1` implementation is MkII-only: it hard-codes
the independent CC16-CC21 meanings. Do not run it against the original
KATANA-100, even when the supplied local configuration selects `katana100`.
Inspect the original model's Tone Studio MIDI page or use explicit, individually
confirmed `katana-test` messages instead. A future profile-aware probe must take
both its labels and controllers from the selected model profile. A successful
send log alone proves transport delivery, not a physical effect change.

## Linux hardware checklist

In addition to the Windows message order:

- record the distribution, kernel, BlueZ, ALSA, Mido, and python-rtmidi versions;
- compare `aconnect -l`, `amidi -l`, and `midi-outputs`;
- record whether the normal Bleak path or fixed-handle compatibility path ran;
- verify the RtMidi ALSA port name can change without making substring selection
  ambiguous;
- repeat disconnect and rehearsal-duration checks.

## SysEx discovery gate

Before adding one address:

1. Capture a baseline with exact model/firmware metadata.
2. Change one parameter only in Tone Studio.
3. Compare both directions and repeat.
4. Issue a read query and correlate the response by address and length.
5. Write one safe value, observe the amp and Tone Studio, then restore the original.
6. Save sanitized capture bytes and provenance beside the test fixture.
7. Add a guarded registry definition and negative tests.

Until this sequence succeeds, the address category is `inferred`,
`legacyKatana`, `communityMkII`, or `unverifiedPlaceholder` and is not writable by
the production bridge.
