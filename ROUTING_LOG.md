# Routing log: double-sided brain board

Working notes for the double-sided rebuild of `kicad/thegoose.kicad_pcb` (branch `double-sided`). Newest pass
last. Coordinates are board-local mm (origin at the top-left corner, x right,
y down).

## Result

- **68.2 × 32 mm, 2,182 mm²**, against 73.5 × 43.1 mm (3,169 mm²) before: 31 % less area, 5.3 mm shorter and 11.1 mm
  narrower. 1 mm corner radii.
- **6 layers**, JLC06161H-3313 (1.6 mm nominal; 1.54 mm finished per JLC).
- **Parts on both sides:** 79 SMD parts on the back, all assembled by JLC (Standard PCBA, both sides).
- **Checks:**
  - `kicad-cli pcb drc --schematic-parity --severity-error` with zones refilled: 0 errors, 0 unconnected items,
    0 parity issues.
  - ERC: 0 violations.
- **Warnings left:** 9, all `lib_footprint_mismatch`. M1–M6, J3 and J4 had their silk trimmed to the board outline, and
  the goose logo was shrunk to 80 %. Updating those footprints from the library would bring the trimmed silk back, which
  is harmless: JLC clips silk at the outline.

## Tools

The copper is generated, so all of it can be rebuilt after a placement change.

- `tools/place_double.py`: idempotent placement.
  - Strips tracks, zones and drawings, swaps M1–M6 to JST PH and places every part from one table.
  - Draws the outline.
- `tools/route_all.py`: runs everything below in order and prints the final DRC (`python3 tools/route_all.py`).
- `tools/route_recipe.py`: scripted critical routing and all the planes, in the locked PCB group `route_recipe`.
  - U10: fan-out, decoupling, the core regulator loop, the crystal, and escapes on all four sides.
  - USB-C and USB-A pairs, through the ESD parts and series resistors.
  - The buck hot loop.
  - The drivers' outputs, VM and IPROPI.
  - The battery entry: PACK+, Q1's drain and gate network.
  - The VCC feeds and the IO header's back side.
- `tools/grid_router.py`: the rest of the signals, from KiCad's list of unconnected pairs, into the group
  `autoroute`. It replaced Freerouting (see pass 8).
- `tools/prune.py`: removes escape vias and stubs the router didn't use (KiCad's `via_dangling` and `track_dangling`).
- `tools/plane_channels.py`: cuts a GND channel out of the In3 power areas under every In2 signal.
- `tools/stitch.py`: GND stitching vias, plus one via in any F.Cu or B.Cu GND island that has none.
- `tools/silk.py`: trims footprint silk to the outline, places the references and puts the logo on the back.
- `tools/fab.py`: Gerbers, drill files, BOM and CPL, with bottom-side placements (see the README).

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

IO4–IO6 stay on PWM channels no motor uses (slice 1B, 4A, 4B), and no IO sits on GPIO26–29.

### Pass 4: USB-C entry and crystal (not committed)

- With USB on U10's north side, J1 → ESD → 27 Ω → U10 stacked vertically left no room for the crystal and buck below
  U10.
- U6 (ESD) moved to the back. The main pair runs from J1's A6/B7 contacts straight down to R44/R45 and U10 pins 52/51
  on F.Cu, with no vias.
- The flipped contacts B6/A7 drop through two vias, join the pair on the back at vias in R44/R45's J1-side pads, and U6
  taps them there.
- Y1 turned to 180°, which saves 0.77 mm of height; U10 sits at y 15.7.

### Pass 5: first Freerouting runs on 4 layers, 66.6 × 32 mm

- F.Cu/B.Cu only: 41 unrouted, stuck for 60+ passes over 20 min. Letting it use In2 brought it to about 27.
- Bottleneck: all four right-hand drivers face J4 with their IN pins, and U15's IN pins are level with J4's right shell
  pin, 0.65 mm away. No via fits between them.
- J4 moved 0.4 mm west (plug centres now 19.5 mm apart, still above the 19.4 mm the dongle needs).
- The board widened by 1.6 mm to 68.2 mm, opening a riser channel between J4/Q1 and the drivers.

### Pass 6: corridor clean-up, 68.2 × 32 mm (commit f8c9602)

- Moved off the corridor south of J4's pins: the gate network (R40, C72, C71), D4, C15 and R52.
- The motor VREF divider moved to the foot of the riser channel.
- FID3 moved below Q1.
- The PACK+ pour lost its lower lobe.
- Freerouting runs of 20–30 min still ended with 27 to 60 connections unrouted.

## Why 6 layers

The handoff's switch criteria held after a real 4-layer attempt:
- three placement iterations (passes 3, 5 and 6),
- the critical nets scripted,
- Freerouting runs of up to 30 min,
- placement nudges where the ratsnest jammed.

| Criterion | 4-layer result |
| --- | --- |
| Connections still unrouted | 27–60 after every run |
| A clean route needs a guideline broken | In2 had to carry the VSYS, VCC and +3V3 areas and also be B.Cu's reference. B.Cu signals could only avoid crossing area edges by staying out of most of the board. |
| Board would grow more than 10 % | Making room for more vias around U10 and the drivers would have needed several mm in both directions |

On 6 layers, F.Cu and B.Cu each get a solid GND reference (In1, In4) and In2 becomes a real signal layer. JLC's
impedance control and filled, capped vias in pads (POFV) are free at 6 layers; the recipe uses vias in pads. The area
didn't change: the 6-layer board keeps pass 6's placement.

## Routing passes on 6 layers (68.2 × 32 mm)

### Pass 7: 6-layer stackup and Freerouting

- Stackup JLC06161H-3313:

  | Layer | Thickness |
  | --- | --- |
  | L1 | 0.035 |
  | PP 3313 (εr 4.1) | 0.0994 |
  | L2 | 0.0152 |
  | core | 0.55 |
  | L3 | |
  | PP 2116 | 0.1088 |
  | L4 | |
  | core | 0.55 |
  | L5 | |
  | PP 3313 | 0.0994 |
  | L6 | 0.035 |

- USB: JLC's impedance calculator (2026-10-20; differential, non-coplanar, L1 over L2, gap 0.127 mm) gives
  0.1234 mm for 90 Ω. The USB class and `thegoose.kicad_dru` use 0.124 mm tracks at a 0.127 mm gap.
- Freerouting 2.1.0 on the 6-layer DSN went badly:
  - Planes block its vias, so In1, In3 and In4 had to be stripped from the DSN.
  - It routed over keepouts on In2 (circle keepouts are ignored, and octagon keepouts were violated).
  - Netless wiring floods its log with millions of "net not found" lines.
  - It hugs pin rows, then never rips up.
  - Results swung between runs: the best run left 12 unrouted, with shorts against copper of the dropped power nets.
    The next run with tighter keepouts left 63.

### Pass 8: a small deterministic router (`tools/grid_router.py`)

The router works on three layers (F.Cu, In2, B.Cu) on a 0.05 mm grid.
- **Clearances:** two obstacle maps. Default-class signals keep 0.15 mm from other Default nets and 0.2 mm from
  everything else (power classes, USB, the switch nodes); other classes keep 0.2 mm. Holes keep 0.25 mm to copper and
  0.5 mm to a new via's hole.
- **Search:** A* with 8 directions and no corner cutting. Vias go only where all three layers are clear.
- **Cost:** In2 over an In3 power area costs 1.6× per cell. Cells just outside a fine-pitch pin's halo cost 4×, so
  routes don't run along a pin row.
- **Geometry:** paths are straightened into 45° segments between cell centres, so the grid check is exact.
- **Order:** the rails (+3V3, +1V1, VBUS, the LDO nets) first, then the shortest pairs. Each search starts from
  anywhere on the source's connected copper.

| Run | Change | Result |
| --- | --- | --- |
| 1 | one 0.34 mm halo for every net | 47 of 65 pairs routed; the 0.4 mm pitch U10 pins had no free cell |
| 2 | class-aware clearances, exact 45° geometry | 57 of 64 |
| 3 | rails first, start from whole connected clusters | 60 of 64 (U10's west side: IO2, IO3, IO5, M6B) |
| 4–6 | soft cost along pin rows, pair-order experiments | 58–61 of 64 |
| 7 | U10's west escapes scripted (see below) | 57 of 58 |
| 8 | U10's south-west escapes scripted | 54 of 54: 0 unconnected |

Runs 4–6 showed the west side can't be left to a shortest-path router. Three things make it hard:
- R55–R60 put a via column at x 16.81, 1.7 mm from U10's pin toes.
- C41, C47 and C50 add a second via column at x 18.3–18.5.
- J1's shell pegs sit just north.

There is room for three F.Cu lanes. The IO fan only stays planar if the longest net takes the innermost lane, and A*
routes the shortest pair first. So `route_recipe.py` now scripts the west side (`u10_west`):
- IO2–IO4 on F.Cu lanes at x 17.92, 17.60 and 17.28.
- IO1 on B.Cu at x 17.9, through a via just inside the pin ring.
- IO5 along the toe strip, west between C47's vias, then on In2.
- IO6 down the toe strip and north on F.Cu.

`u10_southwest` scripts M5/M6 (pins 16–19) the same way. Four lanes run west between the pin toes and Y1's top pads,
then south at x 15.6/15.95 to U17, so no signal crosses the crystal.

`prune.py` then removed 8 escape vias the router had bypassed. It first snaps the touching track ends to each via's
centre: an earlier version that didn't broke 8 connections. `stitch.py` added 33 grid and edge vias, plus 13 for bare
GND islands. That linked the last loose F.Cu/B.Cu GND island, leaving 0 errors and 0 unconnected (commit 28103cd).

### Pass 9: silkscreen, In3 channels, IO1 to B.Cu

- **Silk:** `silk.py` trimmed 49 footprint silk items that ran past the outline (the connectors overhang every edge),
  which cleared 43 silk-to-edge warnings. It placed 100 references beside their parts on their own side, clear of
  pads, other silk and the edge; that cleared 39 silk-over-copper and 20 silk-overlap warnings. The goose logo had
  been left off the board by `place_double.py`; it now sits on the back under J4 at 80 % (5.5 × 6.8 mm), the largest
  size that fits clear of every back part.
- **In3 channels:** the first `plane_channels.py` laid one GND zone along every In2 signal. KiCad keeps only one
  outline per zone, so most of it was silently lost, and over the GND background it overlapped the fill and left
  copper slivers. It now cuts the channels out of the power areas themselves, and the GND background fills them.
  Each area is reset from the recipe's polygon first, so reruns are safe. Pieces a channel cuts off become their own
  zones; pieces under 2 mm² are dropped.
- **IO1 moved to B.Cu:** with real channels, IO1's In2 run at x 17.95 cut the In3 VCC band (J12, U14, the USB-A feed)
  off from the VCC block over J5. On B.Cu it doesn't touch In3.
- `route_all.py` now rebuilds the whole board from the placement in about 10 minutes.

### Pass 10: the core regulator rebuilt to RP2350 Fig. 26 (2026-10-20)

The pre-order review (`docs/preorder-review.md`) found the RP2354's core SMPS broke RP2350 datasheet §6.3.8.1:
C_OUT (C52) was on the back, there was no 4.7 µF C_IN at VREG_VIN, VREG_FB was sensed at the DVDD network, and every
inner layer was solid under L3 and VREG_LX. `route_recipe.py` now has `vreg()`, which copies Fig. 26 (the Pico 2's
layout) straight out from pins 47–50, with the same pin order and orientation:

- **Parts:** two new 4.7 µF caps, C85 (C_IN) and C86 (C_OUT), CL05A475MP5NRNC (C23733, basic), on the front. C85
  sits 0.4 mm off the pin toes, with its +3V3 pad over pin 49 (VREG_VIN) and its GND pad over pin 47 (VREG_PGND). C86
  is above it, and L3 above that at 0°, with pad 1 (the dot, +1V1) over C86's +1V1 pad. The column sits 0.07 mm east
  of pin 48 so VREG_FB clears C85. C52 moved to the back at DVDD pin 23 as the second 4.7 µF that RPi recommends.
- **Footprint:** the caps use `hexy:C_0402_1005Metric_RP2350VREG`: KiCad's 0402 with each pad trimmed to 0.45 mm on its
  inner side, so VREG_LX (0.2 mm) runs between the pads as in Fig. 26.
- **Copper:**
  - LX runs straight up from pin 48 between the cap pads and along L3's south edge into its LX pad.
  - Both GND pads and PGND form an island with two vias side by side, the single GND point. The "VREG corner" rule
    area keeps the F.Cu pour out, and the old "U10 PGND" zone (PGND straight to the exposed pad) is gone.
  - VREG_FB has its own 0.127 mm track from C86's +1V1 pad, west of C85. Its old via into the DVDD network is gone.
  - +1V1 for DVDD leaves through a via in L3's +1V1 pad. It runs on In2 down the VOUT side, inside the pin ring, to
    pin 39's via; the grid router joins pins 6 and 23 from there.
  - "VREG cut-out" (a rule area with no fills) clears In1–In3 under L3, the LX node and the VIN/VOUT pads, as in
    Fig. 27. The GND island's vias stay outside it, on the planes.
- **Spacing:** Fig. 26 is tighter than the board's 0.2 mm power-class clearance. `thegoose.kicad_dru` allows 0.15 mm
  between items inside "VREG corner" (the USB rules still hold) and exempts the 0.2 mm PGND stub from the GND width
  rule. grid_router keeps every other net off F.Cu and In2 there.
- **Making room:**
  - R44/R45 moved west (x 21.82 / 23.30), so R45 sits over pin 51 and D+ runs under R45's pad to pin 52. The pair
    now turns toward the resistors below the flipped contacts' vias. R44/R45 stay 0603: no basic 27 Ω 0402 exists.
  - U6 moved 0.25 mm south. Its VP pad joins C49's +3V3 pad on B.Cu, round the east side of its D+ pad (pass 12;
    first it sat on a via in C85's pad), which replaces its old hop via where the GND island's vias now are.
  - U6's D+ loop moved 0.56 mm west, with its GND via, clear of R44's pad. R46 turned to 0° and moved west, clear of
    the loop and C41.
  - R99's GND via was under L3's LX pad. R99's GND now goes on B.Cu to C51's GND via.
  - L3's silk dot moved from beside pad 1 (where R45 now is) to just outside pad 1's long edge, and its courtyard was
    trimmed to match.
- **L3 is machine-placed:** DNP is off, LCSC C42411119. `fab.py` puts it in `jlc_bom.csv`/`jlc_cpl.csv` as Top,
  rotation 0, with pad 1 (the dot) west. Check it in JLC's preview.
- **Also:** C74 changed to the 50 V CL05B104KB54PNC (C307331, basic).
- **Result:** `route_all.py` gives 0 errors, 0 unconnected and 0 parity issues; the grid router routed 52 of 52 pairs in
  one round. ERC: 0.

### Pass 11: L1 to the Zeng Yi HMS0530-2R2M (2026-10-20)

L1 changed from the hand-placed Coilcraft XAL5030-222MEC ($6.72) to the Zeng Yi HMS0530-2R2M (LCSC C18734448, about
$0.10), which JLC places. It uses a new footprint, `hexy:L_ZengYi_HMS0530`, with the datasheet's land: 1.9 × 2.5 mm
pads at ±2.05 mm, 6.0 mm outer span. Pin 1 is on SW. The XAL5030 STEP is the stand-in 3D model (0.3 mm taller).

- **What moved:** the datasheet land is 0.8 mm longer than the XAL's.
  - L1 moved 0.06 mm east, to x 18.9.
  - U4, C73, C74 and C14 moved 0.2 mm east, so U4's courtyard clears L1's. C73 can't go further east without meeting
    J3's courtyard, and C74's GND via U8 on the back.
  - The M6A/M6B lanes (`u10_southwest`) now jog 0.35 mm west at y 22.9/23.25, below M5B's diagonal, to x 15.25/15.6.
    That keeps 0.2 mm between M6B and L1's VCC pad.
- **Copper:** L1's VCC pad drops to the B.Cu trunk through two columns of three 0.6 mm vias (it was one column of four
  in the XAL's taller pad). The rest of the buck recipe follows the pads.
- **Logo:** `silk.py` now tries a fixed spot first (`LOGO_SPOTS`): board-local (3.2, 12.8) at 180°, where it was put by
  hand to clear C11's reference. The rebuild had moved it.
- **Result:** `route_all.py` gives 0 errors, 0 unconnected and 0 parity issues, with the same 9 `lib_footprint_mismatch`
  warnings. ERC: 0. `fab.py` and `fab.py --panel` both list L1.

### Pass 12: 0.3 mm signal via drill, one JLC BOM line per part (2026-10-20)

- **Vias:** every 0.45 mm via goes from a 0.25 mm drill to 0.3 mm, so the smallest hole is 0.3 mm and JLC's small-via
  surcharge drops. The 0.45 mm diameter stays, so no copper moves; the annular ring is 0.075 mm.
  - The new size is set in the Default, Rail and USB net classes, in the board's minimum annular ring (0.075 mm) and
    through-hole size (0.3 mm, so DRC now flags anything smaller), and in `route_recipe.py`, `grid_router.py` and
    `stitch.py`.
  - The rebuild has 158 vias at 0.45/0.3 and 51 at 0.6/0.3, with none left at 0.25.
- **Fixes the bigger holes needed:**
  - IO4's lane (x 17.28 → 17.285) and IO6's (17.08 → 17.075) were 0.245 mm from IO5's via holes.
  - The +3V3 via in C85's pad for U6's VP can't keep 0.25 mm hole clearance between the FB and LX tracks at 0.3 mm.
    U6's VP now joins C49's +3V3 pad on B.Cu, round the east side of U6's D+ pad.
  - The router took QSPI_SS (R46 to SW2) across B.Cu under J1's west half, which cut the B.Cu pour round J1's shell
    pad into an island (a starved thermal). `grid_router.py` now keeps B.Cu clear in that pocket (`J1_WEST`).
- **Logo:** `silk.py` counted the logo's own current outline as an obstacle, so the logo swapped between two spots on
  alternate rebuilds. It now skips it, and the logo stays at (3.2, 12.8).
- **BOM:** `fab.py` writes one `jlc_bom.csv` line per LCSC number, for both the board and `--panel`. C50–C52 and
  C85/C86 (C23733 on two footprints) were two lines. The board's BOM went from 42 to 41 lines, and the panel's from 48
  to 47. No other LCSC number is on two lines.
- **Result:** 0 errors, 0 unconnected and 0 parity issues, with the same 9 `lib_footprint_mismatch` warnings. ERC: 0.

### Pass 13: external core LDO instead of L3 (2026-10-20)

JLC had 3 of L3 (the Abracon AOTA-B201610S3R3-101-T, the only inductor RPi approves for the RP2354's switching
regulator), and no in-stock substitute is polarity-marked, which RP2350 datasheet §6.3.8.2 requires. The datasheet's
§6.3.7 (Fig. 24) allows DVDD from an external 1.1 V supply instead, with no inductor, so the core now runs from an LDO.

- **Schematic (MCU sheet):** L3 removed. U12 TLV74311PDBVR (C485147, 1.1 V 300 mA, SOT-23-5, local symbol
  `hexyhustle:TLV74311PDBV`) from +3V3 to +1V1, EN tied to IN, with C87 (input) and C86 (output), both C23733.
  VREG_FB (50) to GND, VREG_LX (48) no-connect; VREG_VIN keeps C85 and VREG_AVDD keeps R42/C51. The +1V1 PWR_FLAG
  went, since U12's OUT drives the net. C85/C86 are back on KiCad's stock 0402 (the trimmed `RP2350VREG` land was only
  for LX between the pads). ERC: 0.
- **Placement:** U12 at 180° in the pocket between U10's NE corner and J12, OUT (pin 5) the SW pad; C86 west of it in
  the strip by U10, C87 under its IN pad, clear of the east escape vias and the USB-A pair. C85 moved 0.1 mm north,
  because the stock 0402 courtyard touched U10's.
- **Recipe (`vreg()`):** VIN and PGND stubs into C85 as before, C85's GND pad on its own via. FB inward to a GND via
  inside the pin ring, 0.35 mm west of pin 50 so it keeps 0.2 mm and the 0.25 mm hole clearance to C49's pad on the
  back. U12's OUT into C86 and down a via to In2, which runs north of the AVDD via and down inside the pin ring to pin
  39's via. IN and EN join round the east side of U12's GND pad; IN goes to C87 and to a +3V3 via between the pad
  columns (inside In3's +3V3 area); U12's, C86's and C87's GND pads each get a via.
- **Rules:** "VREG corner" shrank to pins 47-50, C85 and the FB stub, where the 0.2 mm stubs still need the 0.15 mm
  spacing and GND width exemptions; "VREG cut-out" (In1-In3 under L3 and LX) is gone, and the grid router now keeps
  only F.Cu out of the corner. The LX switch-node clearance rule went with the net.
- **Parity:** the two no-connect pads (U10 pin 48, U12 pin 4) carry KiCad's `unconnected-(...)` nets, as the other
  NC pins do.
- **Result:** 0 errors, 0 unconnected and 0 parity issues, with the same 9 `lib_footprint_mismatch` warnings. ERC: 0.
  168 vias at 0.45/0.3 and 51 at 0.6/0.3.

## Plane strategy (6 layers)

- F.Cu: parts, the USB pairs, short signals and the scripted escapes, with a GND pour. In1: solid GND.
- In2: signals over a GND fill. In2 references In3 (0.11 mm away), so `plane_channels.py` keeps In3 GND under every
  In2 signal.
- In3: GND background with three power areas:
  - +3V3 under U10 and U12 (the cut-out under L3 and the LX node went with L3, pass 13)
  - VCC over J5 and along the top edge to J12, U14 and the USB-A feed
  - VSYS over the right column, Q1's drain, the bottom strip, the buck input and the left drivers
- In4: solid GND.
- B.Cu: the back-side parts and signals, with a GND pour.
- VCC to J5 runs on a 1 mm B.Cu trunk from the buck's output caps up the west side. D3 and the buck's feedback (taken
  at the output caps) hang off it.
- The F.Cu and B.Cu GND pours are stitched to the inner planes at about a 3 mm pitch wherever both pours are present
  and no part sits above. There is also a ring 0.9 mm inside the outline.

## Vias in pads

These need filled and capped vias (JLC POFV, free on 6 layers):
- the exposed pads of U10 and U4, and the drivers' footprint thermal vias
- the caps under U10, each sitting on its supply via
- R44/R45's J1-side pads
- Y1's XIN pad
- the IO resistors' U10-side pads
- several power pads

## Trade-offs

- **6 layers cost more per board than 4.** In return, every signal has a solid or channelled reference, impedance
  control is free, POFV is free, and the board didn't grow.
- **Router output:** octilinear 0.15 mm tracks, some of them long.
  - SW2's line to R46 (QSPI_SS for BOOT) runs about 48 mm with 3 vias. SW2 sits in the far corner from U10.
  - MOT_VREF runs 38 mm from the divider to the far drivers.
  - The motor IN lines cross the board from U10 to the right-hand drivers on In2 and F.Cu.
  - None of these carry fast edges.
- **USB pairs:** routed by the recipe as coupled pairs at 0.124/0.127 mm. Track totals per net differ by up to 4 mm,
  counting the flipped-contact branch and the ESD taps. At full speed (12 Mbit/s, 4–20 ns edges) that skew is
  negligible, so the lengths weren't tuned.
- **In3 power areas** are cut by the GND channels under In2 signals. Two slivers under 2 mm² were dropped. DRC
  confirms every power pin is still connected.
- **27 references are hidden:**
  - FID1–FID6
  - the caps packed under U10 (C41, C47–C50, C52–C56) and C85 by the core supply pins
  - C38, C39, C71, R40, R56, R58, R100, R104, R106, R114: no 0.8 mm spot clear of pads and other silk
  They are still on the fab layers.
- **Connector silk** (M1–M6, J3) was trimmed at the outline, and the motor connectors lost the body detail between
  their pins and the edge so their references fit. Pin 1 marks stay.

## Shortfalls

- **No teardrops.** Every signal-to-pad joint passes DRC at 0.15 mm, and JLC's 6-layer annular ring is met, so they
  were left out.
- **Hidden references:** see the list above.
- **Edge rails:** JLC's Standard PCBA needs 5 mm edge rails or a panel for boards under 70 × 70 mm. Parts overhang all
  four edges, so the rails need a routed gap (not V-cut); see the README.
- **JLC's placement preview** still has to confirm:
  - the bottom-side rotations: fab.py uses kicad-jlcpcb-tools' convention, (180 − angle) plus the package offset
  - the HTSOP-8 offset for the drivers
  - J1's and U8's anchors, which fab.py flags as CHECK lines
