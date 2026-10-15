# thegoose

## Circuit as code

[circuit/goosebrain.py](circuit/goosebrain.py) describes the circuit in [SKiDL](https://github.com/devbisme/skidl) and is the source of truth for parts and connections. PCB layout still lives in KiCad (`kicad/thegoose.kicad_pcb`).

One-time setup (needs KiCad 10 in `/Applications`):

```bash
python3 -m venv .venv && .venv/bin/pip install skidl==2.3.0
```

Change the circuit:

1. Edit `circuit/goosebrain.py`.
2. Run `.venv/bin/python circuit/goosebrain.py`. It runs SKiDL's ERC and writes `build/goosebrain.net`. Add `--schematic` to also write a KiCad schematic under `build/schematic/`. That schematic is generated for viewing only, so don't edit it.
3. In KiCad's PCB editor, use **File → Import → Netlist** with `build/goosebrain.net`. In that dialog, link footprints by reference designator rather than by unique ID, because SKiDL's symbol IDs differ from the original schematic's.

The generated schematic is electrically correct but laid out automatically, so parts can overlap. `kicad/thegoose.kicad_sch` is the original hand-drawn schematic; it matches the Python as of this conversion, but changes made in the Python won't show up in it.

Check a netlist against another one net by net (net names don't need to match):

```bash
python3 circuit/compare_netlists.py REFERENCE.net build/goosebrain.net
```

## IO ports

The schematic uses six interchangeable `IO_PORT_1` through `IO_PORT_6` 3-pin headers. Pin order is 1 = IO, 2 = VCC, 3 = GND. Verify this order against the assembled harness before powering a sensor or servo.

Power-review checklist:

- The VCC rail currently has local 100 nF decoupling and bulk capacitors shown in the schematic; its allowable load must be checked against the regulator/module data sheet and the worst-case current of all six attached devices.
- The six ports are intentionally generic, so no total current rating can be confirmed until the actual sensor/servo part numbers and duty cycle are recorded.
- Replace the remaining generic motor values (`~`) with the selected motor part numbers and confirm their footprints before fabrication.
- Document the soldered battery-wire polarity at the battery connector. Add fuse/reverse-polarity/overvoltage protection to the schematic if the physical battery assembly does not already provide it.
