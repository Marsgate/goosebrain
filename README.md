# thegoose

## Circuit as code

[circuit/goosebrain.py](circuit/goosebrain.py) describes the circuit in [SKiDL](https://github.com/devbisme/skidl) and is the source of truth for parts and connections. PCB layout still lives in KiCad (`kicad/thegoose.kicad_pcb`).

One-time setup (needs KiCad 10 in `/Applications`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Change the circuit:

1. Edit `circuit/goosebrain.py`.
2. Run `.venv/bin/python circuit/goosebrain.py`. It runs SKiDL's ERC and writes `build/goosebrain.net`. Add `--schematic` to also write a KiCad schematic under `build/schematic/`. That schematic is generated for viewing only, so don't edit it.
3. In KiCad's PCB editor, use **File → Import → Netlist** with `build/goosebrain.net`. In that dialog, link footprints by reference designator rather than by unique ID, because SKiDL's symbol IDs differ from the original schematic's.

The generated schematic is electrically correct but laid out automatically, so parts can overlap. `kicad/thegoose.kicad_sch` is the readable, hand-drawn view. It doesn't update itself when the Python changes: edit it too (the schematic loop below does this through the KiCad MCP server), and the netlist check confirms the two still match.

Check a netlist against another one net by net (net names don't need to match):

```bash
python3 circuit/compare_netlists.py REFERENCE.net build/goosebrain.net
```

## Design review loop

Claude improves the schematic and the PCB in a "screenshot, analyse, improve" loop. It edits through the KiCad MCP server, renders the result, has a fresh critic agent score it against a rubric, fixes the top findings, and repeats.

- `.venv/bin/python tools/review.py sch` / `pcb` renders zoomable images and runs the hard checks into `build/review/<sch|pcb>/NN/summary.md`. Schematic gates: no ERC errors, and the netlist matches SKiDL. PCB gates: no DRC errors or new warnings, nothing unrouted, schematic parity, minimum power-track widths.
- `.claude/agents/schematic-critic.md` and `pcb-critic.md` hold the scoring rubrics.
- `.claude/skills/schematic-loop` and `pcb-loop` define the procedure, phases and stopping rules. Ask Claude to "run the schematic loop", then "run the PCB loop" once the schematic is final.

The loop never commits; review the result in KiCad before ordering.

## IO ports

The schematic uses six interchangeable `IO_PORT_1` through `IO_PORT_6` 3-pin headers. Pin order is 1 = IO, 2 = VCC, 3 = GND. Verify this order against the assembled harness before powering a sensor or servo.

Power-review checklist:

- The VCC rail currently has local 100 nF decoupling and bulk capacitors shown in the schematic; its allowable load must be checked against the regulator/module data sheet and the worst-case current of all six attached devices.
- The six ports are intentionally generic, so no total current rating can be confirmed until the actual sensor/servo part numbers and duty cycle are recorded.
- Replace the remaining generic motor values (`~`) with the selected motor part numbers and confirm their footprints before fabrication.
- Document the soldered battery-wire polarity at the battery connector. Add fuse/reverse-polarity/overvoltage protection to the schematic if the physical battery assembly does not already provide it.
