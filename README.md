# goosebrain rev 2: brain + smart pack, manual routing

This repo holds two boards that ship as one system:

- **The brain** (`kicad/thegoose.kicad_pro`): an RP2354A robot controller for six DC motors and six IO ports, with a USB-A host for a 2.4 GHz controller dongle. Its USB-C port is for programming only.
- **The smart pack** (`kicad-pack/goosepack.kicad_pro`): a small board that sits on the Ovonic 3S 450 mAh cells. It carries the charger, the protector, the 15 A fuse and its own USB-C charging port, and it plugs into the brain over an XT30 lead. Packs can be swapped, and spares can be sold.
- **The 2S smart pack** (`kicad-pack-2s/goosepack2s.kicad_pro`, started 2026-10-19): the same pack for 2-cell batteries. The charger is set for 2S by resistors, the protector is a HYCON HY2120-LB, and two HYCON HY2213 balancers replace the BQ7791501's balancing. See "The 2S pack board" below and PARTS.md. The brain runs from either pack.

The schematics are done. **The brain is placed on both sides and fully routed on 6 layers** (branch `double-sided`, 2026-10-20): 0 DRC errors, 0 unconnected items, ERC clean. See "The brain board" below and [ROUTING_LOG.md](ROUTING_LOG.md). The two pack boards are still unplaced and unrouted.

It was developed in a separate repo (goosebrain-manual), copied on 2026-10-19 from branch `rev2-rp2350` (commit `0ed7122` plus the uncommitted changes at the time) and split into brain + pack the same day. On 2026-10-20 that work, with its full history, was merged back into [Marsgate/goosebrain](https://github.com/Marsgate/goosebrain) `main`. The old SKiDL circuit generator (`circuit/`) was retired then: the KiCad schematics are the source of truth.

## The system

- **Charging:** plug the pack's USB-C into any 5 V USB charger. The pack is a plain 5 V sink (5.1 kΩ Rd on CC1/CC2, no PD), so VBUS stays at 5 V.
  - The BQ25798 runs standalone, from its power-on defaults: 3S (12.6 V), termination on, 12 h safety timer, JEITA temperature window, ADC off. No firmware can change it.
  - The ILIM_HIZ divider (39k / 24k from REGN) caps the input at about **1.04 A** (0.94–1.13 A over REGN tolerance). That gives about 0.44 A into the cells at 3.5 V/cell (1C) and 0.38 A at 4.1 V/cell, so a full charge takes about **1.2–1.3 h**.
  - A PC's USB-A port (BC1.2 SDP) is limited to 0.5 A, so charging from one takes about twice as long.
  - **The green LED on the pack** is lit while charging, off when full, and blinks on a fault.
  - TH2, a 10 kΩ NTC pressed against the cells, stops charging below 0 °C and above 60 °C.
- **Protection:** BQ7791501 with low-side FETs and a 2 mΩ shunt. OV 4.25 V, UV 2.8 V per cell, OCD1 17.5 A (14 A worst case), OCD2 30 A, SCD 60 A, OCC 10 A, plus the 15 A fast fuse.
- **Clearing a trip:** an over-current trip clears when the load goes away. **Unplug the pack, or switch the brain off and on.** R94 (100 kΩ, PACK− to cell −) lets the protector see the load removed even with the charger's 17 µA standby draw on the pack.
- **The brain** takes the pack's XT30U-F lead on J3, a horizontal XT30PW-M whose mouth faces out through the bottom wall (pin 1 GND = PACK−, pin 2 PACK+). The power switch drives Q1. With the switch off, nothing on the brain loads the pack.
- **Programming:** the brain's USB-C powers the MCU through U8 alone, so you can flash it with no pack or with the switch off.

## Firmware changes

- **`code/` is the old firmware.** It's the ESP32 program (Bluepad32, ESP32Servo, DRV8848 pins) from before rev 2 and doesn't run on the RP2354A. Rev 2 needs a new firmware built around the pin map below and a USB host stack for the dongle (Pico-PIO-USB).
- **Core supply:** DVDD comes from an external 1.1 V LDO (U12), not the RP2354's own regulator (RP2350 datasheet §6.3.7). Early in boot, set the VREG register's HIZ bit to shut the on-chip regulator down (it starts anyway and draws about 400 µA until then). Never put it in low-power mode, which connects it straight to DVDD. The core voltage is fixed at 1.1 V, so don't raise it in software (`vreg_set_voltage`) or overclock past the default 150 MHz.
- **GPIO map (double-sided board, 2026-10-20):** the pins were reshuffled so each signal leaves U10 on the side facing where it goes. The MCU sheet's GPIO MAP note has the full list:
  - Motors (IN1/IN2, one PWM slice each): M1 GPIO26/27 (slice 5), M2 GPIO22/23 (slice 3), M3 GPIO20/21 (slice 2), M4 GPIO16/17 (slice 0), M5 GPIO12/13 (slice 6), M6 GPIO14/15 (slice 7).
  - LED stick data: GPIO29.
  - USB-A host: GPIO25 = D+, GPIO24 = D−. D− is the lower pin, so configure Pico-PIO-USB with `pin_dp = 25` and `pinout = PIO_USB_PINOUT_DMDP`.
  - Battery sense: GPIO28 (ADC2), unchanged.
- **Spare GPIOs:** GPIO4–7, GPIO10, GPIO11, GPIO18 and GPIO19 are no-connects.
- **IO ports:** IO1–IO6 are GPIO0, 1, 2, 3, 8 and 9. All six are 5 V tolerant, because none is on an ADC pin (GPIO26–29). IO4–IO6 can run servos from hardware PWM (slices 1B, 4A and 4B; IO5 and IO6 share slice 4, so they share a frequency), and no motor uses slice 1 or 4. IO1 and IO2 share slice 0 with M4, and IO3 shares slice 1 with IO4, so drive their servos from PIO.
- **No I2C charger:** drop the charger driver. The battery voltage now comes only from the GPIO28 divider (VSYS / 4.7, so 12.6 V reads 2.68 V). It reads 0 with the switch off.
- **The pack cuts off in hardware:** the 3S pack at 2.8 V per cell (8.4 V), the 2S pack at 2.8 V per cell (5.6 V; the HY2120 turns back on at 3.0 V per cell). Warn the user well above that, at about 3.3 V per cell.
- **Work out the cell count at power-on** from the GPIO28 reading: above about 8.6 V it's a 3S pack, otherwise 2S. The only pack this reads wrong is a nearly flat 3S one, and the cutoff is in hardware, so the cost is only a wrong warning level.
- **Motor speed:** the motors run about 40 % slower on a 2S pack. To make the robot behave the same on either pack, cap the 3S PWM to match.
- **Motors:** six DRV8251As, one per motor, on the GPIO pairs above (IN1 = GPIOn_MxA, IN2 = GPIOn_MxB). M2, M4 and M6 stay wired reversed. There is no DRV_SLEEP or DRV_FAULT: a driver sleeps when both inputs stay low for about 1 ms. Each driver limits itself at about 1.36 A (shared VREF 2.53 V, 1.2 kΩ on IPROPI, so 1.34 A). They run from 4.5 V, so a 2S pack works.
- **USB-A:** the port is always powered through a 0.5 A PTC. There is no USBA_VBUS_EN. R109/R114 (15 kΩ) are the host pull-downs on D+/D−, so Pico-PIO-USB doesn't need the GPIO pull-downs on GPIO24/25.
- **Start the USB host only when VSYS is present** (GPIO28 reads a pack). U11's VP is on VCC, which is 0 V on USB-C power alone; driving GPIO24/25 high then back-powers VCC (the dongle, J5's servos, the LED stick) at about 2.5 V through R48/R49 and U11's diodes.
- **Motor PWM:** a DRV8251A sleeps after 0.8–1.5 ms with both inputs low and takes 250 µs to wake, so use drive/brake (slow-decay) PWM, or coast PWM above a few kHz, so the off time never reaches that.
- **Entering BOOTSEL:** there's no RUN button, and with the pack on, +3V3 stays up through D3, so unplugging USB-C doesn't reset the chip. Switch off, hold BOOT (SW2) and plug in USB-C; or hold BOOT and short TP3 (RUN) to TP4 (GND); or reboot into BOOTSEL from firmware with picotool.
- **RP2350 erratum E9:** it affects only the A2 stepping, and R109/R114 (15 kΩ) are above its 8.2 kΩ limit. Read the stepping of the first boards (`picotool info`); on A2, a USB-A unplug may not be detected.

## Bring-up tests

1. **Pack charge current:** with a USB-C charger, measure the cell current at about 3.5 V/cell (expect about 0.42–0.44 A) and at 4.1 V/cell (about 0.36–0.38 A). Also try a C-to-C cable from a PD-only charger: the datasheet doesn't say what the BQ25798's D+/D− detection reports for a source with open D+/D−. If it reports SDP, charging is limited to 0.5 A in.
2. **Trip recovery:** short the pack output through a 10 A-rated load to trip OCD, then check that unplugging the pack clears it. Trip it again with the brain connected and check that the brain's power switch clears it.
3. **NTC:** warm TH2 past 45 °C and check the charge voltage drops 0.4 V (JEITA warm), and past 60 °C that charging stops.
4. **Motors:** stall one motor and check the current chops at about 1.36 A.
5. **2S pack:** check that the charge stops at 8.4 V, measure the charge current (about 0.42 A at 3.5 V/cell), and check that each HY2213 bleeds about 89 mA once its cell passes 4.20 V. Trip the HY2120 with a load: over-current near 18–20 A, depending on how hot Q2/Q3 are. Then check that unplugging clears it.
6. **Brain on 2S:** at 5.6 V in (the 2S cutoff), check that Q1 is fully on (about −5 V gate drive), that VCC holds 4.96 V with the servos loaded, and that the soft start still takes about 70 µs with C71 at 10 nF.
7. **Core supply (+1V1):** measure +1V1 at C86 at idle, then with the CPU at its highest clock and the USB host running. It should stay at 1.1 V (U12's tolerance is ±1.4 %). Check that the firmware sets the VREG register's HIZ bit after boot: +3V3 current drops by about 0.4 mA when it does.
8. **Buck load step:** step the VCC load (servos) and watch VCC. If it rings, change C16 to 2.7 nF and add 39 pF from COMP (U4 pin 6) to GND, as DS41979 Table 1 does (there's no pad for it, so tack it onto C16's GND end). With L1 at 2.2 µH the ripple at 12.6 V in is about 2.7 A p-p, so expect about 4.5 A of usable output, not 5 A.
9. **Q1 turn-off:** switch off with a motor stalled and scope Q1's gate and VSYS. R40 (47k) with C71 + C72 takes about 5 ms to turn it off, so it passes through its linear region while the motors draw current.
10. **Shared motor VREF:** during test 4, also stall several motors at once and check that MOT_VREF stays at 2.53 V.

## Opening it

Open `kicad/thegoose.kicad_pro` or `kicad-pack/goosepack.kicad_pro` in KiCad 10. Both projects share the libraries in `kicad/`:

- `hexy.pretty`: the custom footprints.
- `hexyhustle.kicad_sym`: the custom symbols.
- `3dmodels`: the custom 3D models.

The pack's library tables point at `${KIPRJMOD}/../kicad/`.

## The brain board

- **Board:** 68.2 × 32 mm with 1 mm corner radii, **6 layers**, 1.6 mm thick, no mounting holes, **parts on both sides**.
  - It was 73.5 × 43.1 mm (3,169 mm²) before the double-sided build. Now it's 2,182 mm²: 31 % smaller, 5.3 mm shorter and 11.1 mm narrower.
  - It was 88.5 × 47 mm until 2026-10-19.
- **Parts:** the part numbers and the reasons behind them are in [PARTS.md](PARTS.md).
- **How it was built:** the placement, the routing passes, the 4-to-6-layer decision and the trade-offs are in [ROUTING_LOG.md](ROUTING_LOG.md). The copper is generated by scripts:
  - `tools/place_double.py` places every part.
  - `python3 tools/route_all.py` rebuilds all the copper from that placement in about 10 minutes: the scripted critical routing (`tools/route_recipe.py`), a small grid router for the rest (`tools/grid_router.py`), GND channels and stitching, and the silkscreen.
  - Hand edits to tracks are lost on the next rebuild, so change the scripts instead.

### Stackup: JLC06161H-3313

| Layer | Use | Thickness |
|---|---|---|
| F.Cu | parts, USB pairs, short signals, GND pour | 35 µm (1 oz) |
| prepreg 3313 | εr 4.1 | 0.0994 mm |
| In1.Cu | **solid GND** | 15 µm |
| core | | 0.55 mm |
| In2.Cu | signals, GND fill | 15 µm |
| prepreg 2116 | | 0.1088 mm |
| In3.Cu | GND with the VSYS, VCC and +3V3 areas; GND channels under every In2 signal | 15 µm |
| core | | 0.55 mm |
| In4.Cu | **solid GND** | 15 µm |
| prepreg 3313 | εr 4.1 | 0.0994 mm |
| B.Cu | back-side parts, signals, GND pour | 35 µm (1 oz) |

JLC quotes 1.54 mm finished.

The 4-layer stack (JLC04161H-7628) was tried first. It still left 27–60 connections unrouted after three placement passes, scripted critical routing and 30-minute Freerouting runs, and B.Cu signals would have crossed In2's power areas. Filled vias in pads are free on 6 layers. Impedance control was too when the move was made, but it cost $33.08 in the quote of 2026-10-20 (see "Ordering boards").

### What's on the board now

- **Top wall, left to right:** J1 (USB-C), J12 (LED stick, vertical PH) and J4 (USB-A). J1's and J4's plug centres are 19.5 mm apart, so an 8BitDo dongle (24 mm wide) fits next to a USB-C plug.
- **Left wall:** J5 (the 3 × 6 right-angle IO header) at the top, then M5 and M6.
- **Right wall:** M1–M4.
- **Bottom wall:** J3 (horizontal XT30) with its mouth out through the wall, SW1's lever, and SW2 (BOOT) in the bottom-right corner.
- **Front:**
  - U10 (RP2354A, at 0°) under J1, with Y1 next to it.
  - U10's core supply north-east of it: an external 1.1 V LDO (U12, TLV74311) as in the RP2350 datasheet's Fig. 24, with C86 (output) and C87 (input) beside it, so the on-chip switching regulator and its inductor aren't used. C85 (VREG_VIN) sits right off pins 47–49; VREG_FB goes to a GND via inside the pin ring and VREG_LX is open. C52, the second 4.7 µF, is on the back at DVDD pin 23.
  - The buck (U4, L1, C73/C74, C14) below U10.
  - U3/U17 beside M5/M6, and U1/U15/U2/U16 beside M1–M4.
  - Q1 east of J3.
- **Back** (all assembled by JLC except D4, U14 and F2), each part under or next to what it serves:
  - U10's decoupling, each cap on its supply via, and C52 (the second +1V1 4.7 µF) at DVDD pin 23
  - U6 (USB-C ESD) and R99/R100 under J1
  - U11, R109/R114, F2 and C59 under J4
  - U14 and C69 under J12
  - the 3.3 V LDO cluster (U8, U9, D2, C37–C40) under J3
  - the buck's output caps and feedback parts under L1
  - R55–R60 beside J5
  - the drivers' VM caps and IPROPI resistors
  - D4 and the Q1 gate network
  - TP1–TP4
  - The tallest back parts are the 1206 caps C5/C8/C12, at 1.6 mm.
- **Fiducials:** FID1–FID3 on the front and FID4–FID6 on the back. The goose logo is on the back silkscreen, wherever tools/silk.py finds room.
- **Routing:** complete.
  - `kicad-cli pcb drc --schematic-parity --severity-error` with zones refilled: 0 errors, 0 unconnected, 0 parity issues.
  - ERC: 0 violations.
  - The only DRC warnings are 9 footprints that differ from their library copies (M1–M6, J3, J4 and the logo). Their silk was trimmed at the outline, and the logo was scaled to fit.
  - 27 references are hidden: FID1–6, the caps under U10 (C52 among them), C85 by the core supply pins and a few others with no clear 0.8 mm spot. They're still on the fab layers.
- **Vias:** 0.45/0.3 mm for signals (168) and 0.6/0.3 mm for power (51), so the smallest hole on the board is 0.3 mm (the drivers' thermal vias are 0.33 mm). The signal vias were 0.45/0.25 mm until 2026-10-20; at 0.3 mm the order avoids JLC's small-via surcharge, and the annular ring is 0.075 mm. Several sit in pads, so order filled and capped vias (POFV), which are free on 6 layers.
- **"USB fan-out" rule areas:** they only exempt the short fan-out segments where a pair has to split from the diff-pair gap check.
- **"VREG corner" rule area:** over pins 47–50 and C85. The VREG_PGND, VREG_VIN and VREG_FB stubs are only as wide as the 0.2 mm pads, so inside it 0.15 mm spacing applies and the GND stubs are exempt from the 0.4 mm GND width.

## Routing rules

The net classes are set in the project file, and the custom DRC rules are in `kicad/thegoose.kicad_dru`.

| Class | Nets | Track | Clearance | Via (dia / drill) |
|---|---|---|---|---|
| Default | signals | 0.15 mm | 0.15 mm | 0.45 / 0.3 mm |
| Pack | PACK+, VSYS | 1.0 mm min | 0.2 mm | 0.8 / 0.4 mm |
| 5V | VCC, USB-A VBUS | 0.5 mm min | 0.2 mm | 0.6 / 0.3 mm |
| GND | GND | 0.4 mm min | 0.2 mm | 0.6 / 0.3 mm |
| Motor | U*_OUT1/2 | 0.4 mm min | 0.2 mm | 0.6 / 0.3 mm |
| Rail | +3V3, +1V1, VBUS | 0.2 mm | 0.2 mm | 0.45 / 0.3 mm |
| USB | USB pairs | 0.124 mm, 0.127 mm gap | 0.12 mm (0.2 mm to other nets) | 0.45 / 0.3 mm |

- **USB pairs:**
  - Route them as differential pairs: **0.124 mm tracks with a 0.127 mm gap**.
  - JLC's impedance calculator gives 90 Ω for that on F.Cu over In1 on JLC06161H-3313 (checked 2026-10-20). **Order with the stackup specified (JLC06161H-3313), not impedance control:** the stackup alone fixes the dielectric this geometry was sized for. Impedance control costs $33.08 on this order and needs an impedance spec sheet in the Gerber zip, and USB here runs at full speed (12 Mbit/s), where the pair's impedance barely matters.
  - The pairs run on F.Cu over solid In1, except J1's flipped contacts, which join on the back over solid In4.
- **Power widths:** the minimums in the table are DRC rules. Pours on those nets don't have to meet them.
- **Pack path:** PACK+ from J3 through Q1 to VSYS carries all the motor current, with stall peaks of several amps. It runs in pours on F.Cu and B.Cu and in the In3 VSYS area, with several vias at every layer change.
- **Switch node:** signals keep 0.2 mm from the buck switch node (U4 SW).
- **In2 signals** reference In3. `tools/plane_channels.py` cuts a GND channel (track + 0.5 mm each side) out of the In3 power areas under every In2 signal.
- **Board edge:** copper keeps 0.3 mm from the edge, JLC's limit for routed edges.

## The pack board

`kicad-pack/goosepack.kicad_pcb` has all 72 footprints from the pack schematic, clustered by block (charger, protector, connectors) and **not placed**. It uses the 4-layer JLC04161H-7628 stackup (the brain moved to 6 layers). **There is no board outline yet:** it will be drawn with the pack housing, so DRC reports one "invalid outline" error and 160 unconnected items.

Layout notes for later:

- The pack board sits on the cell pack, and TH2 goes on its underside, pressed against the cells.
- The housing shows LED1 and the USB-C opening.
- R66 is a TA-I RLP25 2 mΩ 2512 metal shunt. It uses KiCad's generic 2512 land pattern for now: check TA-I's recommended pads before laying it out.
- J2's pads take a 16 AWG lead with an XT30U-F. The footprint's silk now reads PACK− on the square pad 1 and PACK+ on pad 2.

## The 2S pack board

`kicad-pack-2s/goosepack2s.kicad_pcb` started as a copy of the 3S pack board. U13 (now an HY2120-LB, SOT-23-6) and J11 (now a B3B-XH-A) were swapped in place. The BQ7791501's parts are gone, and the ten new parts (U21, U22, Q4, Q5, R110–R113, C83, C84) are in a row at y 170. Like the 3S pack it has no outline yet, so DRC reports the "invalid outline" error and 143 unconnected items. The schematic passes ERC, and the board passes the schematic-parity check.

- **The cells aren't chosen yet.** The charge rate (about 0.42 A) assumes 450 mAh. For a different capacity, re-pick R33.
- **The protector measures current across Q2 + Q3,** so its trip point moves with their temperature. There's no shunt and no TH1.
- **R112/R113 are 1 W bleed resistors** carrying about 0.38 W each while balancing. Keep them off TH2 and away from the cells.

## Mechanical notes for later

- **The pack rides outside the brain's box** and plugs into J3 through the bottom wall, so the box has no pack bay.
- **Every port is flush with the case wall.** The ports overhang the board edge by the wall plus 0.25 mm clearance: J1 (USB-C), J4 (USB-A) and J3 (XT30) by 1.4 mm at the top and bottom, and M1–M6 and J5 by 1.9 mm at the sides. So the top and bottom walls are 1.15 mm thick and the side walls 1.65 mm. J1's shell pads sit at the 0.3 mm copper-to-edge limit, so it can't go further out.
- **Box size:** about 72.1 × 34.8 × 15.6 mm (it was 78.5 × 48.1 mm in plan before the double-sided build).
- **Under the board:** the case must leave a **2 mm gap** under the board. Back-side parts are at most 1.6 mm tall (the 1206 caps C5/C8/C12), and through-hole leads must be clipped to 1.5 mm or less.
- **Box height:** 1.5 mm floor, the 2 mm gap, the 1.6 mm board, 9 mm above it and a 1.5 mm lid. The tallest front part is J4 at 7.7 mm above the board, and the LED stick hangs under the lid over J3 (5 mm tall).
- **Holding the board:** there are no mounting holes, so the case needs ribs, slots or clips to hold it. Put a rib behind J3: the XT30 takes 1.2–3.5 kg to plug and unplug, and that force goes straight into the board's bottom edge.
- **Wall openings** (board-local mm, origin at the top-left corner of the outline, x right, y down):
  - **Top wall:** J1 (USB-C) centred at x 23.1, and J4 (USB-A) centred at x 42.6. Both faces at y −1.4.
  - **Left wall:** J5's pins span y 1.75–14.45 (open y 0.5–16). M5's mouth spans about y 16.5–23.4 and M6's about y 23.5–30.4.
  - **Right wall:** M1 y 0–7, M2 y 6.9–13.9, M3 y 13.9–20.9, M4 y 20.8–27.8.
  - **Bottom wall:**
    - J3's mouth, about 14 mm wide, centred at x 38.6, face at y 33.4.
    - SW1's lever slot at x 56.6. The lever reaches y 35.1, 1.7 mm past the wall.
    - SW2's (BOOT) plunger at x 64.8 in the bottom-right corner. It ends at the board edge, so the case has a pin hole there.
- **J12 and the LED stick:** the stick lives under a diffuser window in the lid, over the middle of the board, so J12 (vertical PH) needs no wall or lid opening. Its plug leaves about 2 mm under the lid for the wire's bend, so use a plug whose wire can turn right away, and leave enough slack to open the lid without pulling on the plug.
- **Motor leads** now need JST PH 2.0 mm plugs (PHR-2), rated 2 A, against the drivers' 1.34 A current limit.
- The F.Fab notes about the old pack envelope and the vertical XT30 are gone. J3's note describes the horizontal part.

## Ordering boards

`tools/fab.py` builds a board's fab package: the brain by default, the 3S pack with `--board pack`, or the 2S pack with `--board pack2s` (into `build/fab-pack2s/`).

```bash
python3 tools/fab.py
```

```bash
python3 tools/fab.py --panel
```

```bash
python3 tools/fab.py --board pack
```

```bash
python3 tools/fab.py --board pack2s
```

It needs KiCad 10 in `/Applications` and writes these files to `build/fab/` (the pack's go to `build/fab-pack/`):

- `thegoose-gerbers.zip` (`goosepack-gerbers.zip` for the pack): the Gerbers (all six copper layers for the brain) and drill files.
- `jlc_bom.csv` and `jlc_cpl.csv`: JLC's assembly BOM and placement files. Back-side parts have Layer = Bottom. The BOM has one line per LCSC number (JLC charges a loading fee per line), so parts with the same part on different footprints share a line.
- `bom.csv`: the full BOM.

**`--panel` (brain only):** builds the brain's JLC panel with KiKit into `build/fab-panel/` (`thegoose-panel-gerbers.zip`, `jlc_bom.csv`, `jlc_cpl.csv`, `bom.csv`, and front and back renders in `renders/`). Upload this one for the brain, not `build/fab/`. KiKit runs from a venv on KiCad's own Python, made once:

```bash
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -m venv --system-site-packages build/kikit-venv && build/kikit-venv/bin/pip install kikit
```

The panel is one board in a full frame, 88.3 × 74.1 mm ([tools/panel.json](tools/panel.json)), the same as the single-board package except:
- Coordinates are the panel's.
- The through-hole parts (J3, J4, J5, J12, M1–M6, SW1) are in `jlc_bom.csv` and `jlc_cpl.csv` too, at their pad centre, so JLC can fit them while the board is still in the panel.
- fab.py checks that the panel is at least 70 mm on each side, that every part clears every rail by at least 1 mm, and that no tab sits under an overhanging part. It prints the panel size and the clearance on each side.

**What fab.py prints for the brain:**
- the 79 bottom-side placements
- the parts that get a rotation offset

J1's USB-C footprint origin sits 1.15 mm toward the board edge from its pads, and JLC centres it on the pads, so the CPL gives J1's pad centre. U8's HT7550-1 (C16106) model sits 180° off the other SOT-89s, so it gets its own offset. The drivers' `Texas_HTSOP-8` needs no offset. J5's WingTAT 3×6 right-angle header (C51953246, panel only) gets −90°, so the CPL gives 270: at 0 the preview laid its body across the holes with the pins toward the bottom edge. All four were read off JLC's placement preview on 2026-10-20.

**Bottom-side rotation:** it follows kicad-jlcpcb-tools, JLC's KiCad plugin: the angle is mirrored (180° − KiCad's angle), then the package's offset is added, the same as on top.

**JLCPCB board options, brain:**

| Option | Setting |
|---|---|
| Layers | 6 |
| Thickness | 1.6 mm |
| Surface finish | **ENIG**: the front pads go through reflow twice (both sides assembled), and the hand-placed and through-hole parts are soldered after that. OSP degrades with each reflow and HASL is uneven on the QFNs. |
| Specify stackup | **Yes, JLC06161H-3313**. JLC warns that it finishes at 1.54 mm (±10 %), not 1.6 mm; accept it |
| Impedance control | **No requirement**. It costs $33.08 and needs an impedance spec sheet in the Gerber zip; the specified stackup is enough for full-speed USB (see "USB pairs" above) |
| Via covering | **Epoxy-filled and capped (POFV)**: the board has vias in pads. $0 on 6 layers. |
| Min via hole size / diameter | **0.3 mm / 0.45 mm** (the default): every via is 0.3 mm drill. A smaller setting adds the small-via surcharge (about $17 per order) |
| Confirm production file | Yes (JLC turns it on by itself for some options; $1.05) |
| Panel (delivery format) | **Panel by customer**, 1 column × 1 row: upload `build/fab-panel/thegoose-panel-gerbers.zip` (see below). JLC adds a $33 engineering fee for a customer panel |
| Quantity | **5 panels** (one board each); JLC counts each panel as one board |
| PCB remark | "Customer panel, 1 board per panel, mouse bites, do not add rails. Stackup JLC06161H-3313, all vias epoxy filled and capped (vias in pads)." |
| Assembly | **Standard PCBA, both sides**, quantity 5 |
| Edge Rails/Fiducials (PCBA form) | **Added by Customer**: the frame, fiducials and tooling holes are in the Gerbers |
| Confirm Parts Placement | **Yes**, and tick **Do not confirm automatically** in the pop-up, or JLC starts production by itself after 72 h |
| Assembly remark (Advanced Options → Yes) | "Customer panel with our own rails, please do not add rails. Please assemble the through-hole parts (J3, J4, J5, J12, M1-M6, SW1) while the board is still in the panel, and clip their leads to 1.5 mm or less on the bottom side (the enclosure leaves 2 mm under the board). Several connectors intentionally overhang the board edge into the routed gap." JLC prices a remark after review, so the final total can rise slightly |

**Quote on 2026-10-20** (web, 5 panels, these settings, after the CPL fixes for J3, J12, M1–M6, SW1 and U8): PCB $55.65 (engineering fee $33.00, ENIG $17.30, board $4.30, production file $1.05) + Standard PCBA $213.54 (setup $51.50, stencils $16.54, parts for 47 lines $52.31, loading fees $63.55 = 41 SMD lines × $1.55, through-hole lines aren't charged, SMT $4.52, hand-soldering $3.61, manual assembly $4.01, assembly fixture $16.54, placement confirmation $0.45, packaging $0.51) = **$269.19**, before shipping (DHL DDP estimated at about $32 for 0.23 kg; the order weighs 792 g, so expect more), duty and tax. The assembly remark is "Quote after review", so the total can rise a little. U12 (the core LDO, extended) added $2.57 over the earlier $266.62. The $33 engineering fee is for the panel; JLC charges it for "Panel by JLCPCB" too, and its own panel is V-cut with no gap between boards, which J3/SW1 and J1/J4 overhangs can't share. JLCONE Desktop quotes the same order $1–20 cheaper; set it up the same way there.

**Edge rails:**
- Standard PCBA needs each side of the board or panel to be at least 70 mm, with edge rails. JLC's quote page says it would otherwise resize this upload to 78.2 × 70 mm and add its own rails, which could land on the left and right edges, where M1–M6 and J5 overhang. The KiKit panel is over 70 mm both ways and brings its own rails. Choose **Panel by customer** and **Edge Rails/Fiducials: Added by Customer**.
- Parts overhang all four edges, so the ports sit flush with the case wall. By courtyard or fab outline: J1 and J4 by 1.9 mm at the top; J3 by 2.3 mm and SW1's lever by 4.5 mm at the bottom (3.4 mm by its 3D model); M1–M6 by 2.5 mm and J5 by 1.7 mm at the sides.
- The panel is 88.3 × 74.1 mm, a full frame:
  - **Rails:** 15 mm wide at the top and bottom, 5 mm at the sides. The side rails only join the top and bottom rails; nothing holds the board's left and right edges.
  - **Gaps:** 6 mm routed above and below the board, 5 mm beside it. Every part clears every rail by at least 1.5 mm (see the renders in `build/fab-panel/renders/`):
    - SW1's lever clears the bottom rail by 1.5 mm.
    - J1/J4 clear the top rail by 4.1 mm.
    - M1–M6 and J5 clear the side rails by 2.6 mm.
  - **Why a full frame:** a rails-only panel can't reach 70 mm across, because the board is only 68.2 mm wide. A closed frame is also stiffer on JLC's conveyor whichever pair of edges it clamps.
  - **Tabs:** 3 mm mouse-bite tabs, no V-cut. Three on the top edge, at 5.5, 31.3 and 57 mm from the west edge (west of J1, between J1 and J4, east of J4). Two on the bottom edge, at 4.5 and 48.5 mm (west of J3, between J3 and SW1).
    - No tab sits under an overhanging port, so the nubs can't stop a port sitting flush against the case wall.
    - The holes sit just outside the board edge, clear of the stitching vias and MLCCs 0.3–0.6 mm in from the bottom edge. Each nub can stand up to about 0.5 mm proud; sand it if it catches.
  - **Fiducials and tooling:** three 1 mm fiducials (2 mm mask opening) on the top and bottom rails, front and back, and three 1.152 mm NPTH tooling holes in the frame corners, JLC's size. `JLCJLCJLCJLC` on the bottom rail is where JLC prints its order number.
- With every part fitted in the panel, the board needs no work after it arrives except snapping it out.
- The through-hole parts are in the JLC files. To hand-solder some of them instead, untick them on JLC's BOM page.
- KiCad's DRC on `thegoose-panel.kicad_pcb` shows 16 errors around the VREG corner and the USB pair. They aren't real: KiKit renames every net to `Board_0-…`, so the board's custom rules no longer match. Run DRC on `kicad/thegoose.kicad_pcb` instead.
- JLC's engineers confirm the panel before production.

**JLCPCB board options, packs (4 layers):**

| Option | Setting |
|---|---|
| Layers | 4 |
| Thickness | 1.6 mm |
| Surface finish | Lead-free HASL is fine (no ENIG requirement) |
| Impedance control | Yes, stackup JLC04161H-7628 |
| Via covering | Tented, or epoxy-filled and capped if you put vias in pads |

**Assembly:**

- **The JLC + hand split:** JLC places the basic and preferred parts and the hard chips, on both sides of the brain. SMD parts marked DNP in the schematic are hand-placed: `fab.py` leaves them out of the JLC BOM and CPL, and their pads stay on the board.
  - Brain: JLC places every SMD part, D4, U14, F2 and SW2 included (they were hand-placed until 2026-10-20). Through-hole, in the panel's JLC files (or hand-soldered): J3, J4, J5, J12, M1–M6, SW1. L1 was hand-placed until 2026-10-20; JLC places it now (the Zeng Yi HMS0530-2R2M instead of the Coilcraft XAL5030). L3 is gone: the core runs from an LDO (U12).
  - Pack, hand-placed: L2, Q2, Q3, R66, TH1, TH2, F1. Hand-soldered: J2 (lead), J3, J11.
  - 2S pack, hand-placed: L2, Q2, Q3, TH2, F1. Hand-soldered: J2 (lead), J3, J11.
- **Brain:** order Standard PCBA, both sides, and upload `build/fab-panel/jlc_bom.csv` and `jlc_cpl.csv`. Check every through-hole part in the preview too: their footprint origins are at pin 1, so the CPL gives the pad centre. In the previews on 2026-10-20, J5 needed the −90° offset, J3, J12 and M1–M6 came out turned 180° (housings inboard, pins at the edge), and SW1's lever pointed into the board; fab.py now adds these offsets by LCSC number. J4 sat right with none. **Packs:** Economic PCBA, top side only.
- **In JLC's placement preview, before you pay:**
  - Check the orientation of every IC, diode, LED, crystal and the USB-C receptacle.
  - Check all 79 bottom-side parts. Their rotation is mirrored, so check pin 1 of U6, U8, U9 and U11 and the polarity of D2 and D3. A mistake on any of these kills the 3.3 V rail, so check each against this table (coordinates are KiCad's, seen from the top, y down; seen from the bottom in JLC's viewer, east and west swap):

    | Part | CPL rotation | Must see in the preview | If it's wrong |
    |---|---|---|---|
    | U6 (SRV05-4, USB-C ESD) | 90 | pin 1 (the dot) at the west column's south end, at (122.41, 111.90): under R44's side of the pair | rotated 180°, pin 2 (GND) lands on VP (+3V3) and the clamp diode shorts +3V3. Set U6 to 270 in `jlc_cpl.csv` |
    | U11 (SRV05-4, USB-A ESD) | 180 | pin 1 at the north row's west end, at (141.60, 106.51) | rotated 180°, it shorts VCC the same way. Set U11 to 0 |
    | U8 (HT7550-1) | 0 (with the C16106 offset) | pin 1 (GND) at the south end of the pin row | as it showed on 2026-10-20 |
    | U9 (XC6206) | 0 | pin 1 (GND) west/south; the single pin 3 (VIN) faces east | |
    | D2, D3 (B5819W) | 90 | the cathode band to the south, toward the bottom edge (y 132) | reversed, there's no +3V3 from that source |

  - **U12 (TLV74311, front, CPL rotation 90 = KiCad's 180 plus the SOT-23-5 offset):** pin 1 (IN) must be the south-east pad, at (131.69, 111.90), next to C87; OUT (pin 5) is the south-west pad, toward U10. JLC's footprint for C485147 has pin 1 at the bottom-left like U6's SOT-23-6, which matched at the same offset, but U12 hasn't been seen in a preview yet. Rotated 180°, IN and OUT swap and DVDD gets no supply.
  - Check that the drivers (U1–U3, U15–U17) have their pins on the long sides, over the pads, that U8's pin 1 is next to its ▲, and that J1's contacts sit over its pads.
  - **Preview of 2026-10-20 (88.3 × 74.1 mm panel):** every part sat on its pads. U6, U8, U9, U11, the drivers, Q1, U4 and U10 had pin 1 at their ▲ marks, and D2/D3 had their bands to the south. J5 needed 270°. Later previews the same day showed J3, J12 and M1–M6 turned 180°, SW1's lever pointing into the board onto U16, and U8 0.3 mm toward its tab, short of its pin pads; fab.py now turns those parts 180° and places U8 at its pad centre. J3's XT30 pins also sat 0.5 mm off-centre in their holes: JLC centres J3 and J4 on their pad centres, not on the pad copper, and fab.py now does the same for them. Recheck all of them after uploading the new CPL.
  - If every part looks shifted by several millimetres, JLC has added its own rails ("Edge Rails/Fiducials: Added by JLCPCB") and moved the board under the CPL. Set it back to Added by Customer.
- **D4 (SMF14A TVS, back):** its cathode band (pad 1, VSYS) must face J3, toward the board's west edge. Looking at the back, that's to your right. Reversed, it shorts VSYS.
- **J4 (USB-A):** ShouHan's drawing doesn't number the contacts, so the pin 1 position is inferred from KiCad's Molex footprint. JLC fits it in the panel, so check this before ordering, on a loose part (continuity, or LCSC's EasyEDA footprint for C456018): the contact next to the square pad (pin 1, VBUS) must be the one opposite GND. Mirrored, VBUS lands on the GND contact.
- **Through-hole parts:** clip their leads to 1.5 mm or less, because the case leaves 2 mm under the board. This is in the assembly remark above; if you hand-solder any yourself, clip those the same.
