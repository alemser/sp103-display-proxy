# Brief: passively spying on the SP103 front-board controller (T9311DP)

Written 2026-11-05 for Alessandro's local Claude Code. The owner is an amateur: explain step by step, in Portuguese, and wait for his measurements before claiming anything. Earlier context is in `BRIEF-claude-code.md` and `captura-lcd-resumo.md` (LCD bus already mapped and working; the Pico 2 W inside the amp runs the firmware in the repo `alemser/sp103-display-proxy`).

## Goal
Find out, without modifying the amp, what each leg of the front-board controller does: IR receiver input, volume encoder, buttons, I2C (EEPROM and the two PT2314 on the input board), and any outputs that change between standby and on (e.g. a standby/mute line). Reasons:
1. Phone control: the existing Pico could inject IR codes into the IR receiver output line, and needs to know the amp state.
2. Wake from standby by turning the knob (encoder A/B).
3. Only if ever considered: judge with data whether a Pico could replace the controller. A full 40-leg map is mandatory before that discussion.

Out of scope (owner's decision): no digital audio processing of any kind. The sound path stays analog. Tone-control capacitors stay as they are.

## Tools the owner has
- A **spare** Raspberry Pi Pico 2 W, to be flashed with gusmanb LogicAnalyzer (Pico 2 W build). The Pico already inside the amp stays untouched.
- DAOKAI test hook clips with male Dupont ends.
- A multimeter with continuity beep.
- **No** USB logic analyzer. **No** resistors yet (a kit may arrive about 11 Nov). Only 47 kΩ resistors, which are too large for RP2350 inputs (erratum E9).

## Safety rules (obligatory)
- Clips go on and off only with the amp **unplugged**. GND clip first (LCD pin 1 or IC801 pin 4).
- Front board only. Never the mains board, transformer or power amp board.
- One clip per leg. Check with a torch that it touches nothing else. Prefer component legs (capacitors, IR receiver legs, EEPROM) over the chip's 2.54 mm legs.
- **Never** touch the 12 MHz crystal or chip legs 18/19 (oscillator may stop).
- Board signals are 5 V; the Pico is 3.3 V. RP2350 inputs tolerate 5 V only while powered. So: Pico on USB **before** the amp is plugged in; at the end, unplug the amp **before** the Pico. Laptop must not sleep. Never use GP26–GP28.
- Optional (recommended when resistors arrive): 2.2 kΩ in series per channel. Do not use 47 kΩ.

## What is known about the front board ("SP103 AMPLIFIER CONTROL BOARD 3", DSP-ISS2, 2007/06/08)
- Controller: DIP-40 `T9311DP`, no datasheet. **12 MHz crystal** and resistor networks R907/R908 (9P4K7), so very likely 8051-family (still unconfirmed).
- Leg numbering (top view): leg 1 bottom-left, 1–20 along the bottom row, 21–40 back along the top row (40 top-left).
- Seen from the underside photo (board vertical, LCD end at top): the right inner column holds legs 1→20 top to bottom (leg 1 = square pad); the left inner column holds legs 21→40 bottom to top. The outer columns are the resistor networks. **Verify:** leg 20 beeps to LCD pin 1 (GND), leg 40 to LCD pin 2 (+5 V).
- Measured earlier: LCD RS = leg 10, RW = leg 11, E = leg 28, D0–D7 = legs 39–32. The controller reads the LCD busy flag.
- IR receiver: metal-can module with 3 legs, between the LCD and the chip. R903 + C903 (100 nF) + C904 (470 µF) filter its supply, so the leg on that side is +5 V. C902 (33 pF) is likely on the output. The can is GND. Leg order is not assumed; find it by continuity. Guess (unverified): output goes to leg 12 (P3.2/INT0).
- Volume encoder: 3 signal pins + 2 mounting lugs. C907 and C908 ("104") next to it are probably the A/B filter caps. Their legs are good, safe clip points.
- Q902 = 2N4401 NPN with a 4.7 kΩ base resistor, right next to J2. It is a controller-driven output, maybe standby or mute (unverified).
- J2: 9-wire cable to the input board, no labels on the front-board side. The input board's CON51 is labelled SDA0, SDA1, SCL, GND (two PT2314, probably on separate SDA lines).
- IC801 = 24C01 EEPROM (pin 4 GND, pin 5 SDA, pin 6 SCL).
- Speaker relay (CYF2-2A-12VDC) and TR1–TR4 sit on the power amp board. Probably a standalone analog delay/DC-protection circuit (inferred from photos). Whether the controller commands it through J2 is unknown.
- The Function button already offers bass, treble and balance.

## Suggested order
1. **Multimeter map** (amp unplugged): IR receiver legs, encoder A/B, each button K1–K7 + Power (two legs beeping = matrix), IC801 pins 5/6, every J2 wire, the front LED, and the bases of Q901/Q902. Record "component → chip leg N".
2. **I2C capture** at IC801 pins 5/6 (4–8 MHz): power-on, volume, input change, bass/treble. Decode I2C. Expect PT2314 at 0x44 (7-bit) and EEPROM at 0x50. If the PT2314 are missing here, capture at CON51.
3. **IR output** (1 MHz): idle level, pulses while pressing remote keys; compare with the owner's known codes.
4. **Encoder A/B**: quadrature, direction.
5. **Buttons**: scanned matrix or direct lines.
6. **Standby ↔ on**: many channels on the unknown legs (never 9, 18, 19); note which legs change state (Q902 base included).

## Files (same folder)
- `foto-baixo-placa-frontal.jpg`: underside of the owner's front board
- `placa-frontal-baixo-mapa.jpg`: the same, annotated
- `placa-frontal-mapa.jpg`: top side (reference photo, low resolution), annotated
- `foto-chip-encoder-J2.jpg`: top side, chip, crystal, encoder, J2, Q902
- `foto-receptor-IR.jpg`: top side, IR receiver area
- Owner's step-by-step guide (Portuguese, Claude Doc): https://claude.ai/artifact/Vyfwrp8jadVUj19V5BtWtr
