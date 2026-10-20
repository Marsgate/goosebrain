# Task: build and route the double-sided goosebrain brain board

You're working on its own: no one will answer questions while you work. Keep going until the brain board is compact, fully routed and manufacturable, and follows normal circuit-design practice, or until you run out of usage. Make sensible decisions yourself and write down why in the log (see Deliverables). Don't stop at a placement or a partly routed board.

## Where things are

- **Repo:** `/Volumes/code/goosebrain-manual`. The board is `kicad/thegoose.kicad_pcb`, with its project `thegoose.kicad_pro`, custom rules `thegoose.kicad_dru` and four schematic sheets. Read `README.md` and `PARTS.md` first. They hold the stackup, net classes, routing rules, mechanical notes, the assembly split and the reasoning behind each part.
- **Uncommitted work:** the working tree has uncommitted changes (schematics, board, `hexy.pretty` footprints, new STEP models in `kicad/3dmodels/`). They are the current design. Don't use a fresh worktree from `main`, because it would miss them.
  - Work in this checkout.
  - Create a branch named `double-sided`.
  - Commit everything as it stands as the baseline ("Baseline before double-sided build").
  - The board holds an old, partial Freerouting autoroute. Copy it to `kicad/reference/thegoose-autoroute-partial.kicad_pcb` before you strip it.
  - Commit at each milestone. Don't push.
- **Placement concept to start from:** `/Volumes/code/goosebrain-manual/build/concept/` (git-ignored, so read it at this absolute path).
  - `ph.py` → `build_double_sw()` builds the target concept, `ph_double_sw.kicad_pcb`: 66.3 × 32 mm, unrouted.
  - `conceptlib.py` has the placement helpers.
  - `options.html` and `r3d/three.html` are the comparison pages.
  - It's a starting point, not a requirement. Move anything to make the routing clean.
- **Tools:**
  - KiCad 10.0.6 CLI: `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`.
  - Python with pcbnew: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`.
  - Freerouting 2.1.0: `~/.kicad-mcp/freerouting.jar` (Java 21 is installed).
  - A kicad MCP server is also available.
  - For 3D renders use `kicad-cli pcb render`. It hides DNP parts, so turn DNP off on a throwaway copy before rendering.
  - For 2D checks, export SVG with `kicad-cli pcb export svg`, convert with `qlmanage -t -s 2000 -o <dir> <file>.svg`, and look at the result.

## Freerouting and pcbnew traps already hit on this board

- `-mp` is ignored. Pass `--router.job_timeout=HH:MM:SS`, or the job never ends.
- Inner-layer zones exported as DSN `(plane …)` block every via. Strip the planes from the DSN, mark the plane layers `(type power)`, and fan power out to the planes separately.
- Netless "USB fan-out" rule areas export as hard keepouts. Remove them from the DSN.
- Freerouting checks only the routed net's clearance, but KiCad uses the larger of the two classes. Set signal clearance to 0.2 mm in the DSN, or KiCad DRC fails.
- `ImportSpecctraSES` replaces all tracks. Re-add locked or netless copper afterwards.
- `pcbnew.LoadBoard()` on a copy outside `kicad/` loses the project net classes. Run DRC and exports on the real board in place.
- Routing signals first and fanning power out afterwards worked much better than the reverse, which walled in U10.
- Don't rely on Freerouting alone. Script the critical nets (below) in `tools/route_recipe.py` so they rebuild after any placement change. Put the recipe's tracks and vias in a PCB group, make the script idempotent, and let Freerouting fill in the rest.

## What to build

### Board and assembly

- Rectangular outline, as small as clean routing allows. Rounded corners up to 1 mm are fine. The concept is 66.3 × 32 mm: beat it if you can, and grow it only if routing needs to.
- Parts on both sides, assembled by JLC as Standard PCBA, both sides.
  - **Front:** all connectors and switches, U10, the six drivers, Q1, U4 with its input caps (C73/C74) and C14, L1, Y1 and L3.
  - **Back:** small SMD parts (passives, small ICs, diodes, F2, test pads), placed under or next to the part each one serves.
  - **Back-side height limit:** 1.6 mm (the 22 µF 1206 caps). The case will leave 2 mm under the board. Update the mechanical notes to match.
  - **Through-hole parts:** front only. No back part may sit on or near a through-hole pin or a driver's thermal vias. Leave room for the solder fillets of hand-soldered pins (≥ 1 mm).
  - **Fiducials:** add three on the back, and keep three on the front.
  - **Panel rails:** check whether JLC needs edge rails or a panel for a board this size with parts on both sides. If it does, plan for "Panel by JLCPCB" or edge rails and say so in the README.

### Parts and ports

- **Keep every part.** Don't remove parts from the schematic.
- **Motor connectors:** switch M1–M6 to JST PH 2.0 mm right-angle (`Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal`, S2B-PH-K-S). Update the schematic symbols (footprint, MPN, LCSC number, which you can find on LCSC), PARTS.md and the README. Note that the motor leads now need PH plugs. PH is rated 2 A against the drivers' 1.34 A current limit.
- **Ports, as in the concept:**
  - Top edge: J1 (USB-C), J12 between J1 and J4, J4 (USB-A).
  - Bottom edge: J3 (XT30, back face on a straight edge so a case rib can support it), SW1, SW2.
  - Left edge: M5, M6, J5. Right edge: M1–M4.
  - You may rearrange these if it clearly helps routing or size, as long as every connector stays reachable from an edge and J3 keeps its supported edge.
- **GPIO swaps:** allowed if they make routing much cleaner (motor IN pins, IO header signals, LED_DIN, spare GPIOs). Change them in the schematic and update the README's firmware section, which pin does what. Don't move pins that have a fixed function: USB, QSPI, crystal, SWD, RUN, the regulator pins, or ADC-only use on GPIO28.
- **3D models:** keep the STEP models in `kicad/3dmodels/` wired up (J3, J5, SW1, SW2, and L1 uses KiCad's XAL5030).

## Layer plan: try 4 layers first

### Phase A: 4 layers (JLC04161H-7628)

Current plan: F.Cu signals, In1 solid GND, In2 power areas (VSYS, VCC, +3V3) over a GND background with a few signals, B.Cu signals.

Make a real attempt:

- at least three placement and routing iterations,
- critical nets scripted,
- Freerouting runs of up to 30 min each,
- placement nudges where the ratsnest jams.

**Switch to 6 layers if any of these is still true after that:**

- connections are still unrouted,
- DRC errors can't be fixed,
- a clean route would need breaking a guideline below: a GND split under USB, the buck loop or the crystal; a power path narrower than its class minimum; signals crossing gaps in their reference plane,
- the board would have to grow by more than about 10 % in area to stay on 4 layers.

Record the reason in the log.

### Phase B: 6 layers

- Use JLC06161H-3313 (or the best-suited JLC 6-layer stackup), with JLC impedance control (it's free on 6-layer).
- Suggested layers: F.Cu signals; In1 solid GND; In2 signals; In3 power (VSYS, VCC, +3V3, +1V1 areas); In4 solid GND; B.Cu signals.
- Work out the USB pair width and gap again for 90 Ω on the new stackup with JLC's impedance calculator, then update `thegoose.kicad_dru`, the net classes and the README stackup table.
- Continue from the Phase A placement rather than starting over.

## Rules and good practice (all must hold)

**DRC**

- All rules in `thegoose.kicad_dru` and the project net classes.
- 0.3 mm copper to the board edge.
- Stay inside JLC's capabilities for the chosen layer count. Default signals 0.15/0.15 mm. Keep vias at 0.45/0.25 mm or larger unless there's a reason not to, and record it.

**Power**

- PACK+ → Q1 → VSYS is the main power path and carries several amps, with stall peaks. Use pours or wide copper (≥ 1.0 mm tracks) and several vias at every layer change.
- Motor outputs: 0.4 mm minimum.
- GND returns must be low-impedance.

**Buck (U4)**

- Keep the hot loop tight: VIN caps, U4, the switch node and L1 on the same side, close together.
- Keep the switch-node copper small.
- Keep FB and COMP routing away from the switch node, with the feedback taken at the output caps.

**RP2354A (U10)**

- Each decoupling cap sits right at its pin. A cap on the back directly under U10 with a short via is fine.
- Keep the core regulator loop (VREG_LX, L3, +1V1 caps) tight.
- Y1 and its load caps close to the pins with a short, guarded route, and no other signals under the crystal.
- Stitch the exposed pad to GND with vias.

**USB**

- Route every pair as a differential pair with matched lengths, over a continuous reference plane.
- Fan the pairs out through the ESD parts first (U6 next to J1, U11 next to J4), then the series resistors. Keep stubs minimal.
- No vias in the pairs if you can avoid them. If one is unavoidable, use a pair of vias with GND return vias next to them.

**Motor drivers**

- Each DRV8251A exposed pad gets a GND via array into the GND plane(s).
- The VM 10 µF + 100 nF caps sit at pin 5 with short loops.
- The IPROPI resistor sits near the driver.
- Leave copper around the drivers to spread heat.

**General**

- GND stitching vias around the edge and between pours.
- No acute angles and no stubs.
- Teardrops on the small signal-to-pad joints, if they help.
- Refill zones before the final DRC.
- Tent the vias; vias in pads only if they're filled (free on 6-layer).

**Silkscreen**

- Every reference readable and clear of pads, on the side its part is on.
- Polarity and pin 1 marks visible, including on the back.
- No silk over exposed copper.

## Done means

- `kicad-cli pcb drc --schematic-parity --severity-error` gives 0 errors and 0 unconnected items, with zones refilled.
- ERC is clean.
- Warnings are reviewed: tidy them or explain why they stay.
- `python3 tools/fab.py` works for double-sided assembly:
  - Bottom-side parts go in the CPL with Layer = Bottom, with JLC's rotation and position conventions for that side.
  - DNP and hand-placed parts stay out of the BOM and CPL as today.
  - CHECK lines are fixed or explained.
  - Check bottom-side rotations against JLC's documentation, and list the parts to check in their placement preview.
- Renders (top, bottom, angled, with DNP shown on a copy) and 2D copper views of every layer are saved under `build/`, and you've looked at them.

## Deliverables

- Branch `double-sided` with the routed board, `tools/route_recipe.py`, and the updated schematic, PARTS.md and README:
  - stackup and layer count
  - dimensions and placement
  - wall openings and box size (outline + 5 mm)
  - the 2 mm gap under the board
  - assembly split, now double-sided
  - firmware pin map, if any pins changed
  - routing status
- `ROUTING_LOG.md` covering:
  - each placement and routing pass and its result (unrouted count, DRC errors)
  - why you did or didn't move to 6 layers
  - trade-offs you made
  - anything you couldn't get to the standard above, and why
- A short summary at the end with: final size and area against today's 73.5 × 43.1 mm (3,169 mm²), the layer count, and what to check before ordering (JLC placement preview, bottom-side rotations, the impedance numbers in JLC's calculator).
