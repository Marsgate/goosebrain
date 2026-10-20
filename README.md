# goosebrain rev 2: brain + smart pack, manual routing

This repo holds two boards that ship as one system:

- **The brain** (`kicad/thegoose.kicad_pro`): an RP2354A robot controller for six DC motors and six IO ports, with a USB-A host for a 2.4 GHz controller dongle. Its USB-C port is for programming only.
- **The smart pack** (`kicad-pack/goosepack.kicad_pro`): a small board that sits on the Ovonic 3S 450 mAh cells. It carries the charger, the protector, the 15 A fuse and its own USB-C charging port, and it plugs into the brain over an XT30 lead. Packs can be swapped, and spares can be sold.
- **The 2S smart pack** (`kicad-pack-2s/goosepack2s.kicad_pro`, started 2026-10-19): the same pack for 2-cell batteries. The charger is set for 2S by resistors, the protector is a HYCON HY2120-LB, and two HYCON HY2213 balancers replace the BQ7791501's balancing. See "The 2S pack board" below and PARTS.md. The brain runs from either pack.

The schematics are done. The brain's placement is done except for rough spots for the new parts. All routing is left for you: tracks, vias, planes and pours.

It was copied on 2026-10-19 from [Marsgate/goosebrain](https://github.com/Marsgate/goosebrain), branch `rev2-rp2350` (commit `0ed7122` plus the uncommitted changes at the time), and then split into brain + pack the same day. Nothing here syncs back to that repo.

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

- **GPIO map (double-sided board, 2026-10-20):** the pins were reshuffled so each signal leaves U10 on the side facing where it goes. The MCU sheet's GPIO MAP note has the full list:
  - Motors (IN1/IN2, one PWM slice each): M1 GPIO10/11 (slice 5), M2 GPIO0/1 (slice 0), M3 GPIO22/23 (slice 3), M4 GPIO20/21 (slice 2), M5 GPIO12/13 (slice 6), M6 GPIO14/15 (slice 7). Before: M1 4/5, M2 7/6, M3 0/1, M4 14/15, M5 10/11, M6 13/12.
  - LED stick data: GPIO7 (was GPIO18).
  - USB-A host: GPIO27 = D+, GPIO26 = D− (was GPIO2/3). D− is the lower pin, so configure Pico-PIO-USB with `pin_dp = 27` and `pinout = PIO_USB_PINOUT_DMDP`. GPIO26/27 aren't 5 V tolerant, but USB full-speed signals at 3.3 V.
- **Spare GPIOs:** GPIO2–6, GPIO8, GPIO9 and GPIO29 are no-connects.
- **IO ports:** IO1–IO6 are GPIO16, 17, 18, 19, 24 and 25 (2026-10-20; before that GPIO16, 21, 22, 24, 25 and 19). All six are 5 V tolerant, because none is on an ADC pin. IO4–IO6 can run servos from hardware PWM (slices 1B, 4A and 4B; IO5 and IO6 share slice 4, so they share a frequency), and no motor uses slice 1 or 4. IO1–IO3 share slices with M2 (0A, 0B) or IO4 (1A), so drive their servos from PIO.
- **No I2C charger:** drop the charger driver. The battery voltage now comes only from the GPIO28 divider (VSYS / 4.7, so 12.6 V reads 2.68 V). It reads 0 with the switch off.
- **The pack cuts off in hardware:** the 3S pack at 2.8 V per cell (8.4 V), the 2S pack at 2.8 V per cell (5.6 V; the HY2120 turns back on at 3.0 V per cell). Warn the user well above that, at about 3.3 V per cell.
- **Work out the cell count at power-on** from the GPIO28 reading: above about 8.6 V it's a 3S pack, otherwise 2S. The only pack this reads wrong is a nearly flat 3S one, and the cutoff is in hardware, so the cost is only a wrong warning level.
- **Motor speed:** the motors run about 40 % slower on a 2S pack. To make the robot behave the same on either pack, cap the 3S PWM to match.
- **Motors:** six DRV8251As, one per motor, on the GPIO pairs above (IN1 = GPIOn_MxA, IN2 = GPIOn_MxB). M2, M4 and M6 stay wired reversed. There is no DRV_SLEEP or DRV_FAULT: a driver sleeps when both inputs stay low for about 1 ms. Each driver limits itself at about 1.36 A (shared VREF 2.53 V, 1.2 kΩ on IPROPI, so 1.34 A). They run from 4.5 V, so a 2S pack works.
- **USB-A:** the port is always powered through a 0.5 A PTC. There is no USBA_VBUS_EN. R109/R114 (15 kΩ) are the host pull-downs on D+/D−, so Pico-PIO-USB doesn't need the GPIO pull-downs on GPIO26/27.

## Bring-up tests

1. **Pack charge current:** with a USB-C charger, measure the cell current at about 3.5 V/cell (expect about 0.42–0.44 A) and at 4.1 V/cell (about 0.36–0.38 A). Also try a C-to-C cable from a PD-only charger: the datasheet doesn't say what the BQ25798's D+/D− detection reports for a source with open D+/D−. If it reports SDP, charging is limited to 0.5 A in.
2. **Trip recovery:** short the pack output through a 10 A-rated load to trip OCD, then check that unplugging the pack clears it. Trip it again with the brain connected and check that the brain's power switch clears it.
3. **NTC:** warm TH2 past 45 °C and check the charge voltage drops 0.4 V (JEITA warm), and past 60 °C that charging stops.
4. **Motors:** stall one motor and check the current chops at about 1.36 A.
5. **2S pack:** check that the charge stops at 8.4 V, measure the charge current (about 0.42 A at 3.5 V/cell), and check that each HY2213 bleeds about 89 mA once its cell passes 4.20 V. Trip the HY2120 with a load: over-current near 18–20 A, depending on how hot Q2/Q3 are. Then check that unplugging clears it.
6. **Brain on 2S:** at 5.6 V in (the 2S cutoff), check that Q1 is fully on (about −5 V gate drive), that VCC holds 4.96 V with the servos loaded, and that the soft start still takes about 70 µs with C71 at 10 nF.

## Opening it

Open `kicad/thegoose.kicad_pro` or `kicad-pack/goosepack.kicad_pro` in KiCad 10. Both projects share the libraries in `kicad/`:

- `hexy.pretty`: the custom footprints.
- `hexyhustle.kicad_sym`: the custom symbols.
- `3dmodels`: the custom 3D models.

The pack's library tables point at `${KIPRJMOD}/../kicad/`.

## The brain board

- **Board:** 73.4 × 43 mm with 2 mm corner radii, **4 layers**, 1.6 mm thick, and no mounting holes. It was 88.5 × 47 mm until 2026-10-19: 1,003 mm² (24 %) smaller, 15.1 mm shorter and 4 mm narrower.
- **Parts:** the part numbers and the reasons behind them are in [PARTS.md](PARTS.md). It mentions `circuit/goosebrain.py`, which is goosebrain's circuit-as-code source and isn't in this repo.

### Stackup: JLC04161H-7628

| Layer | Use | Thickness |
|---|---|---|
| F.Cu | signals, parts | 35 µm (1 oz) |
| prepreg 7628 | εr 4.4 | 0.2104 mm |
| In1.Cu | **solid GND** | 15 µm |
| core | εr 4.6 | 1.065 mm |
| In2.Cu | power (VSYS, VCC, PACK+, +3V3 areas) and some signals, over a GND background | 15 µm |
| prepreg 7628 | εr 4.4 | 0.2104 mm |
| B.Cu | signals | 35 µm (1 oz) |

It was 6 layers (JLC06161H-3313). In3 and In4 and their GND pours are gone.

### What's on the board now

- **Placement (compacted 2026-10-19):** the blocks were pulled together once the charger and protector were gone. Each block moved as a unit, so the parts inside it keep their relative spots.
  - **Top edge, left to right:** J12 (LED stick) in the top-left corner above M5, then SW1, SW2 (BOOT), J1 (USB-C) and J4 (USB-A).
  - **Left end:** M5 with U3 beside it, M6 with U17 beside it, then the J5 IO header. R55–R60 sit in a column just right of J5, and U14/C69 (LED buffer) under J12.
  - **Right end:** M1–M4 with U1/U15/U2/U16. Each driver's IPROPI resistor and two VM caps sit in a row just below it, next to its VM pin (pin 5).
  - **Bottom edge:** J3, the horizontal XT30, at the left, with its mouth out through the bottom wall. Q1 and its gate parts sit just above it. Between J3 and the buck, a narrow column holds D4 (VSYS TVS), C15 (VSYS bulk), R107/R108/C81 (the shared VREF divider) and FID2.
  - **Middle:** J4, then the RP2354A block directly under it, then the buck block (U4, L1, C73/C74 at its input pins, C5/C8/C12 and the rest, unchanged as a unit). U6, R99/R100 and U8 stay under J1.
  - **Bottom-right corner:** two rows. On top, U11, R48, R49, F2 and C59 (the USB-A ESD, series resistors, PTC and VBUS cap). Below them, U9, C39, D2 and D3 (the 3.3 V rail). U11 is about 25 mm from J4, so the port's ESD clamp is further away than ideal.
  - **No mounting holes:** the case holds the board (see the mechanical notes). FID1 sits under J5, FID2 beside J3 and FID3 under SW2. The goose logo is on the back, under the buck.
- **Removed:** the charger, PD sink, protector, fuse, VBUS TVS, balance connector, the SY6280 and its resistors, the DRV8848s and their sense and VREF networks, R54, R80, C58, C60, C70, and the "BAL", "CHG" and charge-LED silk and fab notes.
- **Airwires:** DRC reports 294 unconnected items.
- **GND pours:** F.Cu, In1, In2 and B.Cu each have a board-wide GND pour, redrawn to the new outline. They're unfilled, so press **B** to fill them.
- **"USB fan-out" rule areas:** five sit around the USB pads (J1, U6, R44/R45, J4, U11, R48/R49), moved with their parts. They don't block anything. They only exempt the short fan-out segments where a pair has to split from the diff-pair gap check. Move or delete them to suit your own fan-out.
- **DRC:** no clearance or courtyard errors, and no parts outside the outline. Warnings: 29 silkscreen-to-edge, 42 silk over copper and 35 silk overlaps (mostly reference text crowded by the compaction; tidy them while routing). The schematic-parity check is clean.
- **The schematics pass ERC with no violations,** both brain and pack.

**Routing is left for you.** Nothing is routed on either board.

## Routing rules

The net classes are set in the project file, and the custom DRC rules are in `kicad/thegoose.kicad_dru`.

| Class | Nets | Track | Clearance | Via (dia / drill) |
|---|---|---|---|---|
| Default | signals | 0.15 mm | 0.15 mm | 0.45 / 0.25 mm |
| Pack | PACK+, VSYS | 1.0 mm min | 0.2 mm | 0.8 / 0.4 mm |
| 5V | VCC, USB-A VBUS | 0.5 mm min | 0.2 mm | 0.6 / 0.3 mm |
| GND | GND | 0.4 mm min | 0.2 mm | 0.6 / 0.3 mm |
| Motor | U*_OUT1/2 | 0.4 mm min | 0.2 mm | 0.6 / 0.3 mm |
| Rail | +3V3, +1V1, VBUS | 0.2 mm | 0.2 mm | 0.45 / 0.25 mm |
| USB | USB pairs | 0.22 mm | 0.15 mm (0.2 mm to other nets) | 0.45 / 0.25 mm |

- **USB pairs:**
  - Route them as differential pairs: **0.22 mm tracks with a 0.15 mm gap**.
  - That gives about 90 Ω on F.Cu over In1 GND on JLC04161H-7628. The numbers come from the coupled-microstrip equations KiCad's calculator uses (105 Ω raw), scaled by the 13 % those equations read high against JLC's calculator on the old stackup (about 91 Ω). **Check them in JLC's impedance calculator before you order.**
  - Route the pairs on F.Cu, with In1 solid GND under them. If a pair has to go to B.Cu, its reference is In2, so keep In2 solid GND under it there.
- **Power widths:** the minimums in the table are DRC rules. Pours on those nets don't have to meet them.
- **Pack path:** PACK+ from J3 through Q1 to VSYS carries all the motor current, with stall peaks of several amps.
- **Switch nodes:** signals keep 0.2 mm from the buck switch node (U4 SW) and the RP2354 core regulator node (U10 VREG_LX).
- **Around the RP2354A:** J4, the MCU block and the buck are stacked with about 0.07 mm between courtyards, so there's no room above or below the MCU on F.Cu. Fan it out sideways and drop to the inner layers early.
- **Motor drivers:** each DRV8251A's exposed pad is GND and carries its heat. Give it a via array into In1.
- **Board edge:** copper keeps 0.3 mm from the edge, JLC's limit for routed edges.

## The pack board

`kicad-pack/goosepack.kicad_pcb` has all 72 footprints from the pack schematic, clustered by block (charger, protector, connectors) and **not placed**. It uses the same 4-layer JLC04161H-7628 stackup. **There is no board outline yet:** it will be drawn with the pack housing, so DRC reports one "invalid outline" error and 160 unconnected items.

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
- **Box size = outline + 5 mm:** about 78.4 × 48 mm (it was 93.5 × 52).
- **Box height:** about 16 mm, against about 30 mm before. The vertical XT30 with its plug in was about 17 mm tall and set the old height. Without it, the tallest parts are the right-angle connectors and J12 with its plug in. Check their heights against the case before you commit to 16 mm.
- **Holding the board:** there are no mounting holes, so the case needs ribs, slots or clips to hold it. Put a rib behind J3: the XT30 takes 1.2–3.5 kg to plug and unplug, and that force goes straight into the board's bottom edge.
- **Wall openings:** J3's mouth on the bottom wall, about 14 mm wide, centred 2.5 mm right of J3's pin 1 at x 125. The rest are unchanged: top wall for J1, J4, SW1 (lever slot), SW2 (pinhole); left wall for J5, M5 and M6; right wall for M1–M4.
- **J12 and the LED stick:** the strip lives in the lid, so J12 (vertical PH) needs no wall opening. Its cable goes straight up. Leave room above J12 for the plug and the bend of its wire, or put a hole in the lid right above it, and leave enough slack to open the lid without pulling on the plug.
- The F.Fab notes about the old pack envelope and the vertical XT30 are gone. J3's note now describes the horizontal part.

## Ordering boards

`tools/fab.py` builds a board's fab package: the brain by default, the 3S pack with `--board pack`, or the 2S pack with `--board pack2s` (into `build/fab-pack2s/`). It prints a CHECK line for every SMD part without an LCSC number; on the brain there are none now that the six DRV8251As have one (C5218844). The motor drivers' `Texas_HTSOP-8` rotation in `JLC_ROTATION` (-90, like the other SOIC-family packages) is a guess; check U1-U3 and U15-U17 in JLC's placement preview.

```bash
python3 tools/fab.py
```

```bash
python3 tools/fab.py --board pack
```

```bash
python3 tools/fab.py --board pack2s
```

It needs KiCad 10 in `/Applications` and writes these files to `build/fab/` (the pack's go to `build/fab-pack/`):

- `thegoose-gerbers.zip` (`goosepack-gerbers.zip` for the pack): the Gerbers and drill files.
- `jlc_bom.csv` and `jlc_cpl.csv`: JLC's assembly BOM and placement files.
- `bom.csv`: the full BOM.

**JLCPCB board options (both boards):**

| Option | Setting |
|---|---|
| Layers | 4 |
| Thickness | 1.6 mm |
| Surface finish | Lead-free HASL is fine (no ENIG requirement) |
| Impedance control | Yes, stackup JLC04161H-7628 |
| Via covering | Tented, or epoxy-filled and capped if you put vias in pads |

**Assembly:**

- **The JLC + hand split:** JLC places the basic and preferred parts and the hard chips. You hand-solder the easy extended parts, the through-hole parts and L3. SMD parts marked DNP in the schematic are hand-placed: `fab.py` leaves them out of the JLC BOM and CPL, and their pads stay on the board.
  - Brain, hand-placed: L1, L3, D4, U14, F2, SW2. Hand-soldered: J3, J4, J5, J12, M1–M6, SW1.
  - Pack, hand-placed: L2, Q2, Q3, R66, TH1, TH2, F1. Hand-soldered: J2 (lead), J3, J11.
  - 2S pack, hand-placed: L2, Q2, Q3, TH2, F1. Hand-soldered: J2 (lead), J3, J11.
- Order Economic PCBA, top side only, and upload `jlc_bom.csv` and `jlc_cpl.csv`.
- In JLC's placement preview, check the orientation of every IC, diode, LED, crystal and the USB-C receptacle before you pay.
- **D4 (SMF14A TVS):** its cathode band must face east, toward M4. Reversed, it shorts VSYS.
- **J1 (USB-C):** its footprint origin is 1.1 mm off its pad centre.
- **L3:** it isn't stocked at JLC, so buy it from Digi-Key and fit it before first power. Pin 1 (the dot) goes to the +1V1 side.
- **Through-hole parts:** clip their leads flush, because the case has 1 mm under the board.
