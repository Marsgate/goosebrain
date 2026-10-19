# thegoose

goosebrain rev 2 is a robot controller for six DC motors and six IO ports. It runs from an internal 3S LiPo that charges over USB-C. There's no radio on the board: a 2.4 GHz 8BitDo controller dongle plugs into its USB-A port.

## The board

- **Board:** 88.5 × 47 mm, 6 layers, in a box of about 93.5 × 52 × 30 mm.
- **MCU:** RP2354A (an RP2350A with 2 MB of flash in the package), 12 MHz crystal.
- **USB-C** (native USB) is for programming, serial, and charging. A CH224A asks a USB-PD charger for 9 V; plain 5 V USB also works.
- **USB-A host** for the controller dongle, driven by Pico-PIO-USB on GPIO2/3. Its 5 V supply is current-limited to about 0.68 A (0.51–0.85 A) and stays off until firmware turns it on.
- **Motors:** three DRV8848 drivers for six motors (M1–M6, JST-XH 2-pin). They run straight from the pack through a 15 A fuse and the power switch. Each bridge limits its current to about 1.3 A.
- **Battery:** an Ovonic 80C 3S 450 mAh pack sits on top of the board and plugs into the vertical XT30 (J3), with its balance lead in J11.
  - Charger: BQ25798 buck-boost.
  - Protection: a BQ7791501 protector on the board (over- and under-voltage, over-current, short circuit, temperature, cell balancing).
- **Rails:** a 5 V buck (AP64500, up to 5 A) feeds the IO ports, the LED stick and the dongle. 3.3 V comes from an XC6206 LDO.
- **Status:** an 8 × WS2812B LED stick on J12, plus the charger's CHG LED, which you see through a hole in the top wall.

Parts, part numbers and the reasons behind them are in [circuit/PARTS.md](circuit/PARTS.md).

## Power and charging

- **Charging works with the power switch off.** The switch only connects the motors, the 5 V rail and the dongle to the pack.
- **Charge rate with no firmware:** the input-current limit defaults to about 0.3 A. That gives about 200 mA into the pack from a 9 V USB-PD charger (roughly 2.5 hours from empty), or about 120 mA from plain 5 V USB. Firmware can raise the limit over I2C.
- **The CHG LED** is lit while the pack charges. The charger drives it directly, so it works with no firmware.
- **You can drive while plugged in.** The charger tops up the pack while the motors draw from it.
- **The MCU runs from USB alone,** so you can program the board with the switch off or the pack flat.
- **Battery voltage:** GPIO28 (ADC2) reads VSYS / 4.7, so 12.6 V reads about 2.68 V. VSYS is only live with the switch on. With the switch off, read the pack voltage from the charger's ADC.

## Programming it

The RP2354A runs the RP2350's standard UF2 bootloader.

- **Drag and drop:**
  1. Unplug USB-C and turn the power switch off.
  2. Press BOOT with a 2.5 mm hex key through the pinhole in the top wall.
  3. Keep holding BOOT, plug USB-C in, then let go.
  4. A drive named `RP2350` appears. Copy a `.uf2` file onto it.
- **Arduino:**
  - Use the Raspberry Pi Pico/RP2040/RP2350 core (earlephilhower) with an RP2350 board and 2 MB of flash.
  - Uploads and the Serial Monitor go over USB-C, while the dongle on USB-A runs through Pico-PIO-USB.
  - A board support library for the motors, the IO ports, the charger and the LED stick is planned. Firmware is a separate piece of work.
- **There's no RESET button.** To restart, turn the switch off and unplug USB-C. A RUN test pad (TP3) and SWD pads (TP1 SWCLK, TP2 SWDIO, TP4 GND) are on the back.

### GPIO map

| GPIO | Use | GPIO | Use |
|---|---|---|---|
| 0–1 | M3 IN1/IN2 | 16 | IO1 (S1) |
| 2–3 | USB-A D+/D− (PIO-USB) | 17 | I2C SCL (charger) |
| 4–5 | M1 IN1/IN2 | 18 | LED stick data |
| 6–7 | M2 IN2/IN1 | 19 | Motor driver nFAULT (shared) |
| 8 | I2C SDA (charger) | 20 | Spare |
| 9 | Charger /INT | 21 | IO2 (S2) |
| 10–11 | M5 IN1/IN2 | 22 | IO3 (S3) |
| 12–13 | M6 IN2/IN1 | 23 | Motor driver nSLEEP (all three) |
| 14–15 | M4 IN1/IN2 | 24 | IO4 (S4) |
| 25 | USB-A 5 V enable | 26–27 | IO5, IO6 (S5, S6; ADC0–1) |
| 28 | Battery sense (ADC2) | 29 | Spare (ADC3) |

- Each motor's two inputs are one PWM slice.
- M2 and M6 have IN1 on the odd GPIO, so firmware maps their direction per motor.

### IO ports

- **S1–S6** come out of the left end on one right-angle 3 × 6 header (J5).
- **Pins in each column:**
  - GND is on the row nearest the board.
  - 5 V is in the middle.
  - The signal is on the top row.

  A plug put in upside down only swaps signal and GND.
- **Series resistors:** each signal has a 330 Ω series resistor.
- **Logic levels:** S1–S4 tolerate 5 V logic. **S5 and S6 are ADC pins and must stay at 3.3 V.**
- **Current:** the 5 V pins share the 5 V buck with the LED stick and the dongle. Check the total current of the servos and sensors you attach.

**LED stick (J12, JST-PH):** pin 1 is 5 V, pin 2 is DIN (5 V logic through a 74AHCT1G125), pin 3 is GND. At full white the stick draws up to about 0.5 A, so cap the brightness in firmware.

## Ordering boards

Build the fab package:

```bash
.venv/bin/python tools/fab.py
```

It writes these files to `build/fab/`:

- `thegoose-gerbers.zip`: the Gerbers for all six copper layers, plus drill files (PTH and NPTH).
- `jlc_bom.csv` and `jlc_cpl.csv`: JLCPCB's assembly BOM and placement files. They list only the SMD parts JLC places.
- `bom.csv`: the full BOM, with MPN, manufacturer and LCSC number. Its Assembly column says how each part goes on:
  - **JLC SMT:** machine-placed by JLC.
  - **Hand-place:** L3, from Digi-Key.
  - **Hand-solder:** the through-hole connectors and the power switch.

**JLCPCB board options:**

| Option | Setting |
|---|---|
| Layers | 6 |
| Thickness | 1.6 mm |
| Surface finish | ENIG |
| Impedance control | Yes, stackup JLC06161H-3313 (the USB pairs are 0.15 mm tracks with a 0.20 mm gap, about 90 Ω) |
| Via covering | Epoxy-filled and capped (the board has vias in pads) |

**Assembly:**

- Order Economic PCBA, top side only.
- Upload `jlc_bom.csv` and `jlc_cpl.csv`.
- In JLC's placement preview, check the orientation of every IC, diode, LED, crystal and the USB-C receptacle before you pay. The rotations are KiCad's plus the per-package offsets in `JLC_ROTATION` in `tools/fab.py`, read off JLC's preview.
- Check D4 (SMF14A TVS, below U2) closely: its cathode band must face east, toward R86. Reversed, it shorts VSYS.
- Check J1 (USB-C) closely: its footprint origin is 1.1 mm off its pad centre.
- **Stock to check when ordering:**
  - L3 (Abracon AOTA-B201610S3R3-101-T) isn't stocked at JLC or LCSC (1 and 0 on 2026-10-19), so buy it from Digi-Key.
  - The lowest-stocked parts on 2026-10-19: J5 (144), U13 BQ7791501 (309), L1 (1,266). `circuit/PARTS.md` lists every part's stock and alternatives.

**After the boards arrive:**

1. **Fit L3 before first power.** The RP2354A's core regulator needs it. The dot (pin 1) goes to the +1V1 side, as marked.
2. Hand-solder the connectors (J3, J4, J5, J11, J12, M1–M6) and the power switch (SW1). Clip their leads flush, because the case has 1 mm under the board.
3. Check the XT30's "−" mark against the footprint: pad 1, the keyed end, is the pack's −.

The pack has no UN38.3 test summary published. Get one from Ovonic before shipping boards with packs installed.

## Circuit as code

[circuit/goosebrain.py](circuit/goosebrain.py) describes the circuit in [SKiDL](https://github.com/devbisme/skidl) and is the source of truth for parts and connections. The schematic (`kicad/thegoose.kicad_sch` with the `power`, `mcu_usb`, `motors` and `io` sheets) and the PCB layout (`kicad/thegoose.kicad_pcb`) live in KiCad.

One-time setup (needs KiCad 10 in `/Applications`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

To change the circuit:

1. Edit `circuit/goosebrain.py`.
2. Run `.venv/bin/python circuit/goosebrain.py`. It runs SKiDL's ERC and writes `build/goosebrain.net`.
3. Make the same change in the KiCad schematic (the schematic loop below does this through the KiCad MCP server). Then update the PCB from the schematic.

The schematic review checks that the KiCad schematic and SKiDL still match, net by net. To compare any two netlists yourself (net names don't need to match):

```bash
python3 circuit/compare_netlists.py REFERENCE.net build/goosebrain.net
```

## Design review loop

Claude improves the schematic and the PCB in a "screenshot, analyse, improve" loop. It edits through the KiCad MCP server, renders the result, has a fresh critic agent score it against a rubric, fixes the top findings, and repeats.

- `.venv/bin/python tools/review.py sch` / `pcb` renders zoomable images and runs the hard checks into `build/review/<sch|pcb>/NN/summary.md`.
  - Schematic gates: no ERC errors, and the netlist matches SKiDL.
  - PCB gates: no DRC errors or new warnings, nothing unrouted, schematic parity, and minimum power-track widths.
- `.claude/agents/schematic-critic.md` and `pcb-critic.md` hold the scoring rubrics.
- `.claude/skills/schematic-loop` and `pcb-loop` define the procedure, phases and stopping rules. Ask Claude to "run the schematic loop", then "run the PCB loop" once the schematic is final.

The loop never commits. Review the result in KiCad before ordering.
