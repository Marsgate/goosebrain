"""Copy kicad/thegoose.kicad_pcb into a separate, unrouted KiCad project for routing by hand.

Writes kicad/<name>.kicad_pcb with the same placement, nets and outline, plus <name>.kicad_pro and <name>.kicad_dru
copied from thegoose's, so the net classes, widths and custom DRC rules apply. It sits next to thegoose so the
${KIPRJMOD} footprint, symbol and 3D-model paths still resolve. It has no schematic, so open the board on its own.

Removed: every track and via, the local power pours and the In3 power-plane splits.
Kept: the board-wide GND pours (unfilled, press B to fill) and the rule areas. --bare removes the GND pours too.

The copy is a snapshot. Re-run with --force to take a fresh one after the placement changes; that discards whatever
has been routed in the copy.

Usage: .venv/bin/python tools/unroute.py [--name thegoose-manual] [--bare] [--force]
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KICAD_PYTHON = Path("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3")
SRC = ROOT / "kicad/thegoose"

# Runs inside KiCad's Python: strip the routing from argv[1] and save it as argv[2].
STRIP = r"""
import json, sys, pcbnew
src, dst, bare = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
b = pcbnew.LoadBoard(src)
edges = b.GetBoardEdgesBoundingBox()
board_area = edges.GetWidth() * edges.GetHeight()
out = {"tracks": 0, "vias": 0, "zones_removed": 0, "planes_kept": [], "rule_areas_kept": 0}
# Wrap everything before the first Remove(): after it, SWIG hands back untyped objects.
tracks, zones = list(b.GetTracks()), list(b.Zones())
for t in tracks:
    out["vias" if t.GetClass() == "PCB_VIA" else "tracks"] += 1
    b.Remove(t)
for z in zones:
    if z.GetIsRuleArea():
        out["rule_areas_kept"] += 1
        continue
    if not bare and z.GetNetname() == "GND" and z.Outline().Area() > 0.9 * board_area:
        z.UnFill()
        z.SetLocked(False)
        out["planes_kept"].append(b.GetLayerName(z.GetLayer()))
        continue
    out["zones_removed"] += 1
    b.Remove(z)
pcbnew.SaveBoard(dst, b, True)
print(json.dumps(out))
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", default="thegoose-manual", help="base name of the new project in kicad/")
    ap.add_argument("--bare", action="store_true", help="remove the board-wide GND pours too")
    ap.add_argument("--force", action="store_true", help="overwrite an existing copy, discarding its routing")
    args = ap.parse_args()

    dst = ROOT / "kicad" / args.name
    if dst == SRC:
        sys.exit("refusing to overwrite thegoose itself")
    pcb = dst.with_suffix(".kicad_pcb")
    if pcb.exists() and not args.force:
        sys.exit(f"{pcb.relative_to(ROOT)} exists; pass --force to replace it and lose its routing")

    run = subprocess.run([str(KICAD_PYTHON), "-c", STRIP, str(SRC.with_suffix(".kicad_pcb")), str(pcb),
                          "1" if args.bare else "0"], capture_output=True, text=True)
    if run.returncode:
        sys.exit(run.stderr)
    # SWIG prints memory-leak notices to stdout at exit, after the stats line.
    stats = json.loads(next(line for line in run.stdout.splitlines() if line.startswith("{")))

    pro = json.loads(SRC.with_suffix(".kicad_pro").read_text())
    pro["meta"]["filename"] = dst.with_suffix(".kicad_pro").name
    dst.with_suffix(".kicad_pro").write_text(json.dumps(pro, indent=2) + "\n")
    shutil.copyfile(SRC.with_suffix(".kicad_dru"), dst.with_suffix(".kicad_dru"))
    if SRC.with_suffix(".kicad_prl").exists():  # layer visibility and view settings, not tracked in git
        shutil.copyfile(SRC.with_suffix(".kicad_prl"), dst.with_suffix(".kicad_prl"))

    print(f"wrote {pcb.relative_to(ROOT)} (+ .kicad_pro, .kicad_dru)")
    print(f"removed {stats['tracks']} tracks, {stats['vias']} vias, {stats['zones_removed']} copper zones")
    print(f"kept GND pours on {', '.join(stats['planes_kept']) or 'no layers'} (unfilled) "
          f"and {stats['rule_areas_kept']} rule areas")


if __name__ == "__main__":
    main()
