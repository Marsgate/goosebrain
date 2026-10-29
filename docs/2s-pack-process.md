# The 2S pack board: differences from the 3S process

The 2S pack (`kicad-pack-2s/goosepack2s`) was taken from an unplaced copy of the 3S schematic to a routed, DRC-clean board on 2026-10-28 by following [3s-pack-process.md](3s-pack-process.md). This file lists only what is different. Run every tool with `--board=pack2s` (`silk.py` and `review.py` take `pack2s` / `--board pack2s`), and with KiCad's Python as there.

```bash
kpy tools/place_pack.py compact --board=pack2s
kpy tools/route_pack.py setup --board=pack2s
kpy tools/route_pack.py route --board=pack2s      # about 5 minutes
kpy tools/route_pack.py finish --board=pack2s
kpy tools/silk.py pack2s
python3 tools/review.py pcb --board pack2s
python3 tools/fab.py --board pack2s
```

The 3S defaults are untouched: `place_pack.py compact` on the 3S board gives the same placement as before the switch (checked footprint by footprint), and `kicad-pack/` was not modified. `tools/packcfg.py` holds the switch: `--board=NAME` on the command line, or `PACK_BOARD` in the environment. `route_pack.py` sets the variable itself because it re-runs itself between stages.

## Schematic sync first

The 2S board was a snapshot of the 3S board from 2026-10-19, so it had missed what the 3S pack changed since. The schematic was brought in line before placing, or schematic parity would have failed:

- J2 and J3 are the `SolderWire-1.5sqmm_1x02_P6mm` pigtail pads (J3 is the "Cell pigtail", an XT30U-M, C99101, as on 3S).
- C18 and C19 are 0402 (C192385), so C18 fits under L2.
- D1 is an SMBJ15A (C19077569). The 3S pack moved to it because the SMBJ20A's 32.4 V clamp is over the BQ25798's 30 V VBUS limit, and the 2S charger is the same circuit.
- R34 is the RALEC RTT025231FTH (C11631), as on 3S.

TH2 (the cell NTC, DNP) was kept at first, as the brief said. On 2026-10-28 it became R79, a fixed 10 k on the front in the charger's TS strip, as on 3S (where it changed on 2026-10-26): the cells sit on the front with the parts, so no NTC on the board can touch them, and with TH2 open the charger reads "too cold" and never charges. The HY2120 has no NTC input, so the 2S pack has no temperature sensing at all (3S keeps TH1 on its protector). Re-placing after the swap moved only R79 (from the back) and C36 (3.25 mm west).

## Placement (`compact2s` in `tools/place_pack.py`)

- **Size: 45 × 23 mm** (3S: 50 × 23). Height is set by the charger corner, which is the 3S layout as it was, moved west by `CHARGER_DX` so it still ends at the east edge (U7, L2, the SYS and PMID rows, J1, D1, LED1, the setup escapes). 44 × 23 and below didn't pack: the protector side has the two balancers' parts and the bleed resistors in the space the 3S pack gave to R66 and the BQ7791501's filters.
- **Power row** along the bottom: J3, Q2, Q3, J2, with F1 over Q2. There is no R66, so Q2's sources sit straight on J3's BAT_N pad. R71 is the one passive that must be within 9 mm of Q2's *gate*, and that is why it has its own zone (above Q3's west end).
- **Top:** J11 (B3B, three pins) in the corner, R113 under it and R112 along the top edge, as far apart as the board allows. They are 1 W bleeders (about 0.38 W each while balancing) and are 13 mm from each other. Both are on the front, over the cells' side of the board like every part, so nothing here keeps them off the cells entirely.
- **Zones:** the passives of U13 on the BAT_N side go in a strip west of the ground split; U21/Q4, U22/Q5 and the PACK- parts (R72–R74) go east of it. C83/R110 and C84/R111 are packed within 3 mm of their HY2213 (left to the greedy packer, they landed 6 mm off and the router couldn't reach them).
- The fiducials FID1 and FID2 have their own targets: the 3S ones are in the 2S charger's pocket.

## Ground and pack path (`route_pack.py`, `if packcfg.BOARD == "pack2s"`)

- **One vertical split**, `XB` = 14.6 mm, replaces the 3S staircase. BAT_N (J3, Q2's sources, U13, C62, C64, R71) is west of it, PACK- east, and R94 (BAT_N to PACK-) sits across it. It works because the placement keeps every BAT_N pad west of the line and every PACK- pad east (the zones above).
- **Pours:** CELL+ from J3 to F1, BAT_N from J3 to Q2's sources (stopping short of Q2's gate pad), PROT_FET_D across Q2's and Q3's drains and into Q3's body gap, and PACK- from Q3's sources to J2. PACK+ runs from F1's far pad through 12 vias to a band (y 12.9–17.1 mm) on In2 and B.Cu that runs to J2.
- **The PACK+ band (fixed after the first review, which scored 3.4/5 with two blockers):** F.Cu has no room for PACK+ past R71 and R74, so the whole pack current crosses on the band. On 3S the band only keeps tracks off In2. Here (`BAND_CLEAR`):
  - The band is a rule area on B.Cu too, and `grid_router.py` reads "no vias" off its name, so the router puts no tracks and no vias in it on either layer. Before this, a Q2_G track on B.Cu cut the B.Cu pour off from the fuse vias.
  - `fanout` keeps ground vias off the band unless a pad inside it (R71, R74) has no other way down.
  - J2's P+ pad joins the band solid on both layers instead of through four 0.3 mm spokes.
  - There are 12 fuse vias instead of 8. The fourth row only survives because the band now reaches below it.
- **Drain heat:** a B.Cu copy of the PROT_FET_D pour, joined by 8 vias in Q3's body gap (also from the first review).
- **No Kelvin sense:** `kelvin()` is skipped. HY2120's CS pin reads the drop across Q2 + Q3, and R74 (2 k) and R94 are ordinary signal parts.
- **`finish` stitches back-side ground pads.** TH2's PACK- pad is on B.Cu and `fanout` only reaches front pads, so its B.Cu fill island had no way to In1 (the last unconnected item). `stitch_back_pads()` puts a via beside each such pad. Since TH2 became R79 (on the front) no pad needs it, but it stays for any back-side ground pad.
- **Route order:** the 3S `ROUTE_ORDER` was enough. With it the router completes all 65 pairs in about 5 minutes. The first runs failed on C83 and R110, which were placed too far from their balancer, not on the order. Later, moving U13 0.4 mm east (to clear room for J11's B2 label) cost PROT_CHG. Every order tried after that (PROT_CHG first, or after U13's own nets) only traded it for 4–7 other failures around U13 and U22, so U13 went back.
- **`finish` also drops the router's dangling slivers** (tracks under 0.1 mm with a loose end). One on Q2_G was the last DRC warning beyond the two library mismatches.

## Checks (2026-10-28)

- ERC: no violations.
- `kicad-cli pcb drc --refill-zones --schematic-parity --severity-all`: 0 errors, 0 unconnected, 0 parity. The only warnings are the `lib_footprint_mismatch` on J11 and U7, the same two as on 3S (edge-trimmed silk and the nudged pin 1 mark).
- `fab.py --board pack2s`: 61 JLC placements, 32 BOM lines, nothing hand-placed, J11 hand-soldered. JLC rotation offsets are applied to Q2–Q5, U13, U21 and U22: check their pin 1 in JLC's preview. The `CHECK: J2/J3: no assembly class` lines also appear on 3S: the pigtail pads have no LCSC part.

## Silkscreen

`silk.py pack2s` labels J11's pins B0–B2 (three pins) at 0.8 mm, which is all R113 leaves between J11 and itself. R113 sits 0.1 mm lower than first placed for that. Each label in the row now stays if it is clear, sliding up to 0.6 mm along the row (B2 slides off U13's pin-1 mark). Before, the row was all-or-nothing. On 3S every label fits at its pin, so nothing changes there.

On 2S a polarity label may not sit under another part's body either. The second review found B+ hidden under R113. Between J3's pads there is room for one label, so on top it's B+, beside the round CELL+ pad; B− is the square pad. B−/B+/P−/P+ are also printed on the back beside the pigtail holes.

## Assembly

As on 3S, JLC places every SMD part, all on the front. The power parts on pours (F1, L2, Q2, Q3) had their DNP cleared in the schematic and board on 2026-10-28, after the second review called them unreliable with an iron, and TH2 became R79 the same day. PARTS.md lists the split.

## Reviews

Each round used `review.py pcb --board pack2s` and a fresh `pcb-critic`:

1. **3.4/5, two blockers, both about PACK+.** The fixes are in "Ground and pack path" above.
2. **3.8/5, no layout blockers.** It flagged the hidden B+ label as a cheap safety fix (fixed, see "Silkscreen"). The rest are in the README's open items.

## Open items

See the README's "The 2S pack board".
