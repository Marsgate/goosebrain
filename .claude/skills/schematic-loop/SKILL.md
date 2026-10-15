---
name: schematic-loop
description: Improve the KiCad schematic (kicad/thegoose.kicad_sch) by repeated render → critique → fix iterations through the KiCad MCP server, until it reads well and every gate still passes. Use when asked to draw, tidy, lay out or improve the schematic, or to bring the drawing in line with circuit/goosebrain.py.
---

# Schematic loop: screenshot, analyse, improve

The drawing is the human-readable view of the circuit. `circuit/goosebrain.py`
(SKiDL) is the text source of truth for connectivity. The loop changes how
the drawing looks; it never changes what is connected unless the task says
so, and then the change goes into SKiDL **first**.

## Before starting

1. Check the KiCad MCP server's tools are loaded (they're named
   `mcp__kicad__*`; use its `search_tools` to find schematic tools). If
   they're missing, stop and tell the user. Don't hand-edit `.kicad_sch`
   S-expressions except for a one-off fix the MCP tools can't do, and say
   when you did.
2. Note `git status`. Never commit; the user reviews the result.
3. Run the baseline review:

   ```bash
   .venv/bin/python tools/review.py sch
   ```

   It prints the folder it wrote (e.g. `build/review/sch/01`). Both gates
   (ERC errors, netlist matches SKiDL) must pass before you start. If the
   netlist doesn't match, ask whether SKiDL or the drawing is right.

If the task is an electrical change: edit `circuit/goosebrain.py`, run it,
then make the drawing match through MCP until the netlist gate passes again.
Then continue with the loop below for readability.

## Each iteration

1. **Critique.** Start a **new** `schematic-critic` agent (never resume an
   old one, so it judges with fresh eyes). Pass it only the latest review
   folder path. It returns scores and a ranked findings list.
2. **Plan.** Take the top findings, at most five per iteration, majors first.
   Skip anything that would change connectivity, or that conflicts with the
   critic's KEEP list. Pass `[electrical]` findings to the user; don't act on
   them.
3. **Save a restore point:** copy `kicad/thegoose.kicad_sch` into the review
   folder as `before.kicad_sch`.
4. **Edit** through MCP: move, rotate and align symbols, reroute wires, add
   or move labels, no-connect flags and text notes. Keep to KiCad's 1.27 mm
   (50 mil) grid so wires stay connected.
5. **Re-review:** run `tools/review.py sch` again. If a gate fails, fix it
   now. If you can't, restore `before.kicad_sch` and drop that change.
6. **Look yourself.** Read the new full image and the tiles around what you
   changed, and confirm each fix landed with no side effects (overlaps,
   dangling wires, labels detached from wires).
7. **Log** to `build/review/sch/LOG.md`: iteration number, review folder,
   critic overall score, fixes applied and skipped.

## Stopping

Stop at the first of:

- every gate passes, the critic's **overall is 4.5 or more**, and it has no
  major findings;
- **6 iterations**;
- **two iterations in a row without a higher overall score.** Restore the
  best-scoring iteration's `before.kicad_sch` from the next folder, or keep
  the current one if it scored best.

## Report

Tell the user:

- start and end overall scores, and per-criterion scores at the end;
- before and after images: the first and last review folders' full views,
  sent with SendUserFile;
- what changed, what the critic still flags, and any `[electrical]` findings;
- that nothing is committed.
