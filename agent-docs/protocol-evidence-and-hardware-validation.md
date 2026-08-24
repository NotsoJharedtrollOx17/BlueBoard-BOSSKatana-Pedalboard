# Protocol evidence and hardware validation

## Evidence classes

This project separates:

1. official vendor documentation;
2. source behavior and automated tests;
3. captured interoperability evidence;
4. physical observations on the user's equipment;
5. community reverse engineering and inference.

Passing unit tests proves byte construction and software boundaries. It does not
prove the KATANA-100 MkII combo accepts those bytes over its USB driver.

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

The user's KATANA-100 MkII exposed `KATANA 1`, `KATANA DAW CTRL 2`, and
`KATANA CTRL 3` alongside the Windows wavetable output. With Tone Studio not
required for the test, the main `KATANA 1` port accepted Program Change 0 and
physically changed Panel mode to Bank A CH1. It also accepted CC16 values 127 and
0, with Booster observed on and off. The CLI recorded one Katana command and zero
failures for each operation. The BlueBoard was independently discovered by name;
its hardware address is intentionally omitted from committed documentation.

This proves the Windows USB-MIDI path, PC0, and CC16 on the tested amplifier. It
does not yet prove PC1, CC19, integrated A-D routing, reconnect behavior, Linux,
or SysEx.

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
7. Repeat one other effect such as Delay on CC19.
8. Start the bridge in dry-run and confirm A-D decoding.
9. Enable actions and test A only, then A/B, then C/D from known preset state.
10. Reconnect the Katana while the BlueBoard remains connected.
11. Reconnect the BlueBoard while the Katana remains connected.
12. Confirm Ctrl+C closes both connections.
13. Run a rehearsal-duration session and record failures/reconnect metrics.

Do not generalize a successful Program Change into proof of SysEx parameter
support.

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
