# goosebrain rev 2: manual routing

This repo is goosebrain rev 2 with all the routing removed, ready to be routed by hand. The schematic, parts and placement are done. What's left is the copper: tracks, vias, planes and pours.

It was copied on 2026-10-19 from [Marsgate/goosebrain](https://github.com/Marsgate/goosebrain), branch `rev2-rp2350`: commit `0ed7122` plus the uncommitted changes in the working tree at the time. That repo keeps its own AI-routed board. Nothing here syncs back to it, so change anything you like.

## The board

- **Board:** 88.5 × 47 mm, 6 layers, 1.6 mm thick.
- **What it is:** an RP2354A robot controller for six DC motors and six IO ports. It runs from an internal 3S LiPo that charges over USB-C, and a USB-A port hosts a 2.4 GHz controller dongle.
- **Parts:** the part numbers and the reasons behind them are in [PARTS.md](PARTS.md). It mentions `circuit/goosebrain.py`, which is goosebrain's circuit-as-code source and isn't in this repo.

## Opening it

Open `kicad/thegoose.kicad_pro` in KiCad 10. The project carries its own libraries:

- `hexy.pretty`: the custom footprints.
- `hexyhustle.kicad_sym`: the custom symbols.
- `3dmodels`: the custom 3D models.

## What's on the board now

- **Placement:** every part is placed as in goosebrain's board on 2026-10-19.
- **Airwires:** DRC reports 444 unconnected items.
- **GND pours:** each of the six layers has a board-wide GND pour. They're unfilled, so press **B** to fill them.
- **In3:** in the AI routing, In3 was the power layer, with VSYS, VCC (5 V), VBAT and +3V3 areas over a GND background. Only the GND background is left here.
- **Removed:** the AI's tracks, vias, local power pours and plane splits.
- **"USB fan-out" rule areas:** five of these sit around the USB pads. They don't block anything. They only exempt the short fan-out segments where a pair has to split from the diff-pair gap check. Move or delete them to suit your own fan-out.
- **DRC warnings:**
  - 24 silkscreen-to-edge warnings come with the placement.
  - The schematic-parity check flags the board-only `REF**` footprints that aren't in the schematic. That's expected.
  - The schematic passes ERC with no violations.

## Routing rules

The net classes are set in the project file, and the custom DRC rules are in `kicad/thegoose.kicad_dru`.

| Class | Nets | Track | Clearance | Via (dia / drill) |
|---|---|---|---|---|
| Default | signals | 0.15 mm | 0.15 mm | 0.45 / 0.25 mm |
| Pack | PACK+, VBAT, VSYS | 1.0 mm min | 0.2 mm | 0.8 / 0.4 mm |
| Charger | VBUS, CHG_SYS, U7 PMID/SW1/SW2 | 0.5 mm min | 0.2 mm | 0.6 / 0.3 mm |
| 5V | VCC | 0.5 mm min | 0.2 mm | 0.6 / 0.3 mm |
| GND | GND | 0.4 mm min | 0.2 mm | 0.6 / 0.3 mm |
| Motor | motor outputs | 0.4 mm min | 0.2 mm | 0.6 / 0.3 mm |
| Rail | +3V3, +1V1 | 0.2 mm | 0.2 mm | 0.45 / 0.25 mm |
| USB | USB pairs | 0.15 mm | 0.15 mm (0.2 mm to other nets) | 0.45 / 0.25 mm |

- **USB pairs:**
  - Route them as differential pairs: 0.15 mm tracks with a 0.20 mm gap.
  - That gives about 90 Ω on F.Cu over In1 GND, or on B.Cu over In4 GND.
  - Keep In1 and In4 solid GND under them.
- **Power widths:** the minimums in the table are DRC rules. Pours on those nets don't have to meet them.
- **Pack path:** the pack path (PACK+ through the fuse and switch to VSYS) carries all the motor current, with stall peaks of several amps.
- **Switch nodes:** signals keep 0.2 mm from the buck switch node (U4 SW), the RP2354 core regulator node (U10 VREG_LX) and the pack-path nets (BAT_N, PROT_SNS, PROT_FET_D).
- **Board edge:** copper keeps 0.3 mm from the edge, JLC's limit for routed edges.
- **Stale entries in the rules file:**
  - Some comments mention goosebrain's review tooling and its KiCad MCP server. Neither is part of this repo.
  - The IO-header courtyard rule names J6–J10, which no longer exist. The IO ports are now one 3 × 6 header, J5.

## Ordering boards

Build the fab package:

```bash
python3 tools/fab.py
```

It needs KiCad 10 in `/Applications` and writes these files to `build/fab/`:

- `thegoose-gerbers.zip`: the Gerbers and drill files.
- `jlc_bom.csv` and `jlc_cpl.csv`: JLC's assembly BOM and placement files.
- `bom.csv`: the full BOM.

**JLCPCB board options:**

| Option | Setting |
|---|---|
| Layers | 6 |
| Thickness | 1.6 mm |
| Surface finish | ENIG |
| Impedance control | Yes, stackup JLC06161H-3313 |
| Via covering | Epoxy-filled and capped, if you put vias in pads |

**Assembly:**

- Order Economic PCBA, top side only, and upload `jlc_bom.csv` and `jlc_cpl.csv`.
- In JLC's placement preview, check the orientation of every IC, diode, LED, crystal and the USB-C receptacle before you pay. The per-package rotation offsets are in `JLC_ROTATION` in `tools/fab.py`.
- **D4 (SMF14A TVS):** its cathode band must face east, toward R86. Reversed, it shorts VSYS.
- **J1 (USB-C):** its footprint origin is 1.1 mm off its pad centre.
- **L3:** it isn't stocked at JLC, so buy it from Digi-Key and fit it before first power. Pin 1 (the dot) goes to the +1V1 side.
- **Through-hole parts:** hand-solder the connectors (J3, J4, J5, J11, J12, M1–M6) and the power switch (SW1). Clip their leads flush, because the case has 1 mm under the board.
