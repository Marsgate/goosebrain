---
name: pcb-loop
description: Lay out or improve the KiCad PCB (kicad/thegoose.kicad_pcb) by repeated render → critique → fix iterations through the KiCad MCP server, with Freerouting for signal routing, until the board is ready to order from JLCPCB. Use after the schematic is final (run schematic-loop first), or when asked to place, route, tidy or review the board.
---

# PCB loop: screenshot, analyse, improve

Run this only after the schematic is final: the schematic review's gates
pass, and the user has accepted the drawing. The board follows the
schematic. Never add connections on the board that aren't in the schematic.

## Before starting

1. Check the KiCad MCP server's tools are loaded (`mcp__kicad__*`; use its
   `search_tools` to find board, routing, DRC and Freerouting tools). If they
   are missing, stop and tell the user.
2. Run `check_freerouting` through MCP. If Java or the Freerouting JAR is
   missing, ask the user before downloading anything.
3. Note `git status`. Never commit.
4. Bring the board up to date with the schematic: update the PCB from the
   schematic through MCP. Footprints link by reference designator.
5. Run the baseline review and keep its folder as the DRC baseline:

   ```bash
   .venv/bin/python tools/review.py pcb
   ```

   Pass that folder as `--baseline` to every later run, so new DRC warnings
   fail the `no_new_drc` gate.

## Phases

Work through these in order. Each phase runs the iteration below until its
exit condition holds, then moves on. Run one iteration per phase even if the
board already exists. When improving a finished board, start at the phase
the user names (default: Finish).

1. **Rules.** Set up design rules and net classes for JLC 4-layer: a power
   class for each net in `POWER_NETS` in `tools/review.py` (pack path,
   charger, `VCC`, `GND`) and the motor outputs (`Net-(M…)`), with widths at
   least those listed there; a 90 Ω differential class for both USB pairs;
   and the default class at 0.2 mm track and space. Exit when DRC runs clean on rules
   alone.
2. **Placement.** Place connectors on edges first, then each switcher (the
   BQ25798 charger, the AP64500 buck, the RP2354A core regulator) as one
   tight cluster, then the MCU with its decoupling and crystal, then drivers
   with their caps, then the rest. Judge with the critic's placement,
   switchers and decoupling scores. Exit when those
   three are 4 or more.
3. **Power routing.** Route power by hand through MCP: pack (J3) through F1
   and Q1 to the drivers and buck, the charger's switching loop, buck
   output, motor outputs, short GND via stubs. Add pours (GND on inner and
   outer layers, the pack path `VBAT`/`VSYS` where it helps), plus thermal
   vias under the exposed pads. Exit when power_paths and ground are 4 or more.
4. **Signal routing.** Run Freerouting for everything left, then fix its
   output by hand where the critic flags problems. Exit when the `unrouted`
   gate passes and routing is 4 or more.
5. **Finish.** Silkscreen (references, +/−, motor and IO port numbers),
   then a final pass on manufacturability. Exit on the stopping rule below.

## Each iteration

1. **Critique.** Start a **new** `pcb-critic` agent (never resume one). Pass
   it only the latest review folder. Tell it which phase you're in, so it
   doesn't flag unrouted nets during placement.
2. **Plan.** Take at most five findings, majors first, that belong to the
   current phase or an earlier one. Respect its KEEP list. Pass
   `[electrical]` findings to the user.
3. **Restore point.** Use MCP's `snapshot_project`, or copy
   `kicad/thegoose.kicad_pcb` into the review folder as `before.kicad_pcb`.
4. **Edit** through MCP. Refill zones after any copper change.
5. **Re-review** with `--baseline`. A failing gate is fixed now, or the
   change is reverted from the restore point.
6. **Look yourself** at the tiles around each change: no slivers, no
   acute angles, nothing on top of pads.
7. **Log** to `build/review/pcb/LOG.md`: iteration, phase, folder, critic
   scores, fixes applied and skipped.

## Stopping

Stop at the first of:

- in the Finish phase, every gate passes, the critic's **overall is 4.5 or
  more** and it has no major findings;
- **10 iterations** across all phases;
- **two iterations in a row without a higher overall score** in the same
  phase. Keep the best-scoring board.

## Report

Tell the user:

- per-phase start and end scores, and gate status;
- before and after `render_top.png` and `top.png`, sent with SendUserFile;
- remaining findings and any `[electrical]` ones;
- that nothing is committed, and that they should open the board in KiCad
  and look before ordering.
