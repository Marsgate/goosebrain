# How the 3S pack board was made

This is the process that took `kicad-pack/goosepack` from a split-off schematic to a JLC order, between 2026-10-19 and 2026-10-28. Use it as the recipe for the next pack (the 2S pack in `kicad-pack-2s/`). The board itself is described in README.md ("The pack board"), and the parts in PARTS.md. This file covers the steps, the tools and what went wrong along the way.

Every pcbnew script runs with KiCad's Python:

```bash
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/<script>.py ...
```

Below, `kpy` means that interpreter.

## 1. Schematic

- The pack was split off the brain on 2026-10-19 (commit `b8bfc36`). The KiCad schematic is the source of truth.
- Parts follow the PARTS.md rule: JLC basic or preferred where possible, with the LCSC number in the `LCSC` field.
- Gates: `kicad-cli sch erc` has no errors, and the board passes `--schematic-parity` (see step 5).
- **DNP means "hand-placed":** `fab.py` leaves DNP parts out of the JLC BOM and CPL but keeps their pads. On 2026-10-28 every SMD part on the 3S pack went to JLC, because the power parts (L2, Q2, Q3, R66, TH1, F1) sit on pours and are hard to solder with an iron. To clear DNP, change `(dnp yes)` to `(dnp no)` in the `.kicad_sch` and `(attr smd dnp)` to `(attr smd)` in the `.kicad_pcb`, then update PARTS.md's Asm column and the README's assembly list.

## 2. Placement: `tools/place_pack.py compact`

```bash
kpy tools/place_pack.py compact            # 50 x 23 mm, every part on top
kpy tools/place_pack.py compact --size 48x22 --reach 9 --out /tmp/try.kicad_pcb
```

- **The rules it enforces:**
  - Every part is on the top side, so JLC's Economic PCBA works.
  - Every passive sits within `COMPACT_REACH`, 9 mm, of the pin it serves (its "anchor": U7, U13, J1, Q2, Q3, L2).
  - It clears tracks, zones and drawings, then draws the outline.
- **Fixed spots, then packing:** connectors, ICs, FETs and the fuse go at fixed spots. The passives are then packed on a 0.25 mm grid, in the order of the `CHARGER` and `PROTECTOR` lists.
  - The order is a layout decision: PMID caps first, then the BAT caps, the I2C pull-ups and so on, following TI's layout guide.
  - The protector's cell filters are listed C before R, so the cell → R → C → pin chains don't cross.
- **The charger power stage follows TI's BQ25798 layout example** (SLUSDV2C §8.4.2):
  - U7's power pins face west into L2.
  - The SYS caps sit in a row north of L2 and the PMID caps in a row south of it.
  - PGND runs out between L2's pads.
  - The first layout ignored the example and scored 2.4/5 in review. The rework is what made it route.
- **Size search:** 50 × 23 mm was the smallest size that both packed with every passive within 9 mm and routed. 45.5 × 20.5 mm packs only with passives 13–22 mm from their pins, and it didn't route.
- **Lanes:** keep `ESCAPE` (0.8 mm) clear west and north of U7 for its escape vias. Give U13's filter strip at least 3.8 mm (`U13_LEFT`). With 2.3 mm, the filters were packed 6 mm away and didn't route.
- **Connectors:** J3 and J2 are `SolderWire-1.5sqmm_1x02_P6mm` pads for 16 AWG pigtails. J11 stays a vertical B4B-XH-A, because JST XH has no wire-to-wire male. J1 (USB-C) overhangs the east edge by 1.4 mm.

## 3. Routing: `tools/route_pack.py setup | route | finish`

```bash
kpy tools/route_pack.py setup
kpy tools/route_pack.py route        # about 8-10 minutes
kpy tools/route_pack.py finish
```

Every step takes `--pcb=FILE` (with its `.kicad_pro` and `.kicad_dru` copied beside it), so you can try changes on copies in parallel.

- **setup** does four things:
  - It writes the net classes into the `.kicad_pro`:
    - Default 0.15 mm.
    - Plane and Power 0.4 mm.
    - Charger 0.3 mm, because the BQ25798's 0.2 mm pads at 0.46 mm pitch take nothing wider at 0.2 mm clearance.
  - It splits In1 into BAT_N and PACK- (`BAT_N_AREA` and `PACK_N_AREA`) and puts the In2 PACK+ band (`PACK_P_AREA`) under a rule area.
  - It draws the F.Cu pack-path pours (`PATH`), the charger power stage (`power_stage()`) and the Kelvin sense lines from R66.
  - It lays the connections no route order could fit: U7's corner escape vias, J1's CC2 and north VBUS escapes, the C18 and C19 boot loops, and the C36 SDRV stub. It also adds router-only keepouts named `router keepout NET`.
- **route** runs `tools/grid_router.py --board=pack` on KiCad's unconnected pairs.
  - It skips the plane nets.
  - It routes the `ROUTE_ORDER` nets first (STAT, CHG_SYS, BTST1, PROG, USB_DM, USB_DP, CHG_SDA), then the rest in the router's own order.
- **finish** cleans up and fills:
  - It removes dangling setup vias and snaps track ends to via centres.
  - It doubles the VBUS vias.
  - It widens the power tracks wherever DRC still passes.
  - It draws the ground fills on F.Cu, In2 and B.Cu (split like In1), stitches them every 2.5 mm, and fills the zones.
  - It runs in stages and restarts when a widening breaks DRC.
- **Groups:** setup's copper goes in the group `route_pack`, the router's in `autoroute` and finish's in `route_pack_finish`. setup clears everything, so all three steps can run again after any placement change.

**What we learned:**

- **Freerouting 2.1 was dropped.** It stalled at 25–40 unrouted connections and ignores `-mp`, `--router.max_passes` and environment limits.
- **The grid router has no rip-up,** so `ROUTE_ORDER` and setup's escapes are what make the board complete. Any placement change can break a working order.
  - If every order just trades the same few failures, the area is a lane short. Fix the placement or lay those nets in setup; don't keep searching orders.
- **To search orders**, run several on copies in parallel:

  ```bash
  kpy tools/route_pack.py route --pcb=FILE --order=NET,... --fix=NET,...
  ```

  `tools/route_loop.py <setup.kicad_pcb> <workdir> [attempt ...]` automates the diagnose-and-retry loop. Each attempt runs `tools/route_llm.py`, which is grid_router plus a diagnosis of every failed pair, and can add `--escape=U7` and `--first=NET,...`. It writes the failures, the nets in the way and a hint to `loop_report.json`. That loop found the current order.
- **U7's east side faces J1, 0.4 mm away.** Its east pins, VBUS and J1's CC2/VBUS pads therefore need setup escapes.
- **Vias:** 0.45/0.3 mm for signals and 0.6/0.3 mm for power, with no via within 0.2 mm of an SMD pad (no via-in-pad).
  - Keep the drill at **0.3 mm**. A 0.25 mm drill made JLC add a 4-wire Kelvin test and TG155, about $37 more for 5 boards.
  - On 2026-10-28 the router's signal vias moved from 0.25 to 0.3 mm drill (`grid_router.py`, `route_pack.py`).
- **DRC straight after `route` shows stale In1 plane errors.** Always check with zones refilled (step 5).

## 4. Silkscreen: `tools/silk.py pack`

```bash
kpy tools/silk.py pack
```

- It places each reference where it clears pads, other silk and the edge, and hides the ones that don't fit (44 on the 3S pack). All references stay on the fab layers.
- It adds the polarity labels: B−/B+ by J3, P−/P+ by J2, and B0–B3 under J11.
- It trims footprint silk at the board edge. That trim is why J11 shows a `lib_footprint_mismatch` warning, and so does U7, whose pin-1 mark was moved.

## 5. Checks

```bash
kicad-cli sch erc --severity-all kicad-pack/goosepack.kicad_sch
kicad-cli pcb drc --refill-zones --schematic-parity --severity-all --format json -o /tmp/drc.json kicad-pack/goosepack.kicad_pcb
```

**Target:** 0 errors, 0 unconnected items and 0 parity issues. The only warnings should be the two `lib_footprint_mismatch` ones (J11 and U7).

**Fresh-eyes review:** `tools/review.py pcb --board pack` writes a review folder under `build/review/pcb-pack/`. Hand it to the `pcb-critic` agent and start a new agent each round.

- The 3S pack went from 2.4 to 3.4 to 3.5 of 5. The last review found no blockers.
- Fix what it ranks highest, then re-run steps 3–5.

**Open items** are kept in the README under "Open layout items". For the 3S pack they are the boot-loop length, C36's distance, Q2/Q3 thermals and the land pattern for R66.

## 6. Renders

- **Board renders:** `kicad-cli pcb render` (top, bottom, iso) into `renders/pack/`.
- **The brain and pack side by side** (`renders/pack/pack_vs_brain_boards.png`) was composed with PIL at one px/mm, with inch rulers.
- **Case renders:** use `tools/case/` (build123d case, `scene.py`, `render.sh`). Light it softly with `--light-camera 0.4 --light-side 0.32 --light-top 0.5 --light-side-elevation 30` and no floor.

## 7. Fab package: `tools/fab.py --board pack`

```bash
python3 tools/fab.py --board pack            # into build/fab-pack/
```

- **Outputs:** `goosepack-gerbers.zip`, `jlc_bom.csv` and `jlc_cpl.csv`.
- **Rotations:** CPL rotations get the per-package offsets in `JLC_ROTATION`, plus per-LCSC offsets. The SO-8 FETs Q2 and Q3 and U13 get offsets.
- **What to check after a run:**
  - The BOM has one line per LCSC number (31 for the 3S pack).
  - The CPL has every JLC-placed part (66).
  - No DNP part you meant JLC to place is missing.
  - F_Paste has openings for every JLC part.

## 8. JLCPCB order (done on 2026-10-28)

The user signs in and pays. Claude never enters passwords or payment details, and confirms the item and total before any checkout.

1. **Upload `goosepack-gerbers.zip` and set the board options:**

   | Option | Setting |
   |---|---|
   | Layers | 4 |
   | Thickness | 1.6 mm |
   | Impedance | JLC04161H-7628 |
   | Surface finish | Lead-free HASL (ENIG adds about $16.70 for 5 boards) |
   | Vias | Tented, 0.3/0.45 mm |
   | Build time | 3–4 days |
   | PCB remark | "Edge rails on the long (north/south) edges only, nothing on the east edge: the USB-C connector overhangs it by 1.4 mm." |

2. **PCBA:** Economic, top side, quantity 2. Upload `jlc_bom.csv` and `jlc_cpl.csv`, then press Process.
   - If the BOM/CPL buttons aren't file inputs, find the `type=file` inputs instead.
3. **BOM page:** every line should be confirmed, with no shortage warnings.
4. **Placement preview:**
   - It often hangs on "Processing files". Reload the same `smt-order?pcbFileNo=` URL and press Next again.
   - Check pin 1 of every IC, FET, diode and LED. On the 3S pack: Q2's pin 1 is top left and Q3's is bottom right, both on the pad-1 marker and the silk triangle.
   - Check that F1, R66, L2 and TH1 sit on their pads, and that U13, U7, D1 and J1 face the right way.
5. **Quote & Order:** set the product description to Research/Education/DIY → "DIY - HS Code 902300", then Save to cart.
6. **Check the account before uploading.** On 2026-10-28 the first quote went into the wrong JLC account.

**Result** (quote Y16): 5 PCBs $13.00 + Economic PCBA for 2 boards $61.37 + UPS Express Saver DDP $26.77 − coupon $13.00 = **$88.14**. Of the PCBA price, JLC placing the six power parts added $19.87, mostly extended-part fees.

## Porting this to another pack

These are the 3S-specific bits to change:

- **Paths:** `tools/place_pack.py`, `route_pack.py`, `silk.py`, `grid_router.py --board=pack`, `review.py --board pack` and `route_loop.py` all hard-code `kicad-pack/goosepack.kicad_pcb`. Only `fab.py` already knows `--board pack2s`.
  - Add a board switch to each rather than forking the scripts. Keep the 3S defaults, so its rebuild doesn't change.
- **Part lists and anchors:** `CHARGER`, `PROTECTOR`, `ANCHORS`, `U13_LEFT` and the fixed spots in `place_pack.py`.
- **In route_pack.py:**
  - the net lists `PLANE`, `POWER` and `CHARGER`;
  - the ground split `BAT_N_AREA` / `PACK_N_AREA`;
  - the `PATH` pours, `PACK_P_AREA` and `FUSE_VIAS`;
  - the Kelvin sense (the 3S pack has R66; the 2S protector senses across Q2 + Q3 and has no shunt);
  - the setup escapes;
  - `ROUTE_ORDER`.
- **The charger's power stage and its setup escapes** (U7, L2, C18/C19, J1) are the same circuit. Reuse them as they are if the charger corner keeps the same placement.
- **Afterwards:** update README's pack section, PARTS.md's Asm column and this file's numbers.
