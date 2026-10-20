# Routing log: double-sided brain board

Working notes for the double-sided rebuild of `kicad/thegoose.kicad_pcb` (branch `double-sided`), following
`HANDOFF-double-sided.md`. Newest pass last. Coordinates are board-local mm (origin at the top-left corner, x right,
y down).

## Tools

- `tools/place_double.py`: idempotent placement. Strips tracks, zones and drawings, swaps M1–M6 to JST PH, places
  every part from one table and draws the outline.
- `tools/route_recipe.py`: idempotent scripted routing in the locked PCB group `route_recipe`. It covers the U10
  fan-out and its decoupling, USB-C, USB-A, the crystal, the core regulator loop, the buck hot loop, the drivers'
  outputs/VM/IPROPI, the battery entry (PACK+, Q1 drain, gate network), the VCC feeds, the IO header's back side and
  all planes.
- Freerouting 2.1.0 fills in the rest. The DSN is post-processed: full-board planes stripped, the small scripted pours
  turned into keepouts, rule areas removed, power nets dropped from the network, signal clearance 0.2 mm. The session
  is imported item by item into the PCB group `autoroute`, so the recipe's copper is never replaced.
- `tools/in2_channels.py`: after routing, lays an In2 GND strip under every B.Cu signal track, so B.Cu signals never
  run over an In2 power area or cross a split.

## Placement passes

### Pass 1: concept layout, 66.3 → 73.4 × 34 mm (commit 9eaf6b9)

Built from `ph.py build_double_sw()`, with U10 at −90° and the USB pair on its east side. Unrouted.

### Pass 2: dongle spacing, 72.8 × 32 mm (not committed)

The user asked for more space between USB-A and USB-C: an 8BitDo dongle is 24 mm wide and must fit next to a USB-C
plug. J4 moved east so the plug centres sit 19.4 mm apart, with J12 between the two ports. That gave 72.8 × 32 mm.

### Pass 3: U10 at 0°, J5 at the top-left, 66.6 × 32 mm (commit 90ccb20)

The user suggested rotating U10. At 0° its USB pins face north, straight under J1. IO (west column) faces J5, which
moves to the top of the left wall with M5/M6 below it (the user approved the swap). SW1 now sits under U16 with its
lever through the bottom wall, and SW2 sits in the bottom-right corner under M4. Q1 is east of J3. The GPIO map was
redone for the new orientation; the schematic and README carry it:

| Function | GPIO | U10 pins |
| --- | --- | --- |
| IO1–IO4 | 0–3 | 2–5 (west) |
| IO5/IO6 | 8/9 | 12/13 (west) |
| M5, M6 | 12/13, 14/15 | 16–19 (south-west) |
| M4 | 16/17 | 27/28 (south) |
| M3, M2 | 20/21, 22/23 | 32–35 (east) |
| USB-A D−/D+ | 24/25 | 36/37 (east) |
| M1 | 26/27 | 40/41 (east) |
| battery sense | 28 (ADC2) | 42 |
| LED stick | 29 | 43 |

IO4–IO6 stay on PWM channels no motor uses (slice 1B, 4A, 4B), and no IO sits on GPIO26–29. GPIO3 replaces GPIO19 for
IO4: the same channel (1B).

### Pass 4: USB-C entry and crystal (not committed)

- With USB on U10's north side, J1 → ESD → 27 Ω → U10 stacked vertically left no room for the crystal and buck below
  U10.
- U6 (ESD) moved to the back. The main pair runs from J1's A6/B7 contacts straight down to R44/R45 and U10 pins 52/51
  on F.Cu, with no vias.
- The flipped contacts B6/A7 drop through two vias, join the pair on the back at vias in R44/R45's J1-side pads, and U6
  taps them there.
- Y1 turned to 180°, which saves 0.77 mm of height; U10 sits at y 15.7.

### Pass 5: first Freerouting runs, 66.6 × 32 mm

- F.Cu/B.Cu only: 41 unrouted, stuck for 60+ passes over 20 min. Letting it use In2 brought it to about 27.
- Bottleneck: all four right-hand drivers face J4 with their IN pins, and U15's IN pins are level with J4's right shell
  pin, 0.65 mm away. No via fits between them.
- J4 moved 0.4 mm west (plug centres now 19.5 mm apart, still above the 19.4 mm the dongle needs).
- The board widened by 1.6 mm to 68.2 mm, opening a riser channel between J4/Q1 and the drivers.

### Pass 6: corridor clean-up, 68.2 × 32 mm

- Moved off the corridor south of J4's pins: the gate network (R40, C72, C71), D4, C15 and R52.
- The motor VREF divider moved to the foot of the riser channel.
- FID3 moved below Q1.
- The PACK+ pour lost its lower lobe.

## Plane strategy (4 layers)

- F.Cu signals reference In1, which is solid GND. B.Cu signals reference In2.
- In2 is GND everywhere except power areas placed where no B.Cu signal has to run:
  - +3V3 under U10 and L3's +1V1 corner
  - VCC over J5 and a band under J1/J12/U14
  - VSYS over the right column, Q1's drain, the bottom strip, the buck input and the left drivers
- `tools/in2_channels.py` then puts GND under any B.Cu signal track that does cross a power area.
- VCC to J5 runs on a 1 mm B.Cu trunk from the buck's output caps up the west side. D3 and the buck's feedback (taken
  at the output caps) hang off it.

## Vias in pads

These need filled and capped vias (JLC POFV):
- the exposed pads of U10 and U4, and the drivers' footprint thermal vias
- the caps under U10, each sitting on its supply via
- R44/R45's J1-side pads
- Y1's XIN pad
- the IO resistors' U10-side pads
- several power pads

POFV is paid on JLC 4-layer and free on 6 layers or more.
