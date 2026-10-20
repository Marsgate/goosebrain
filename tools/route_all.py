"""Rebuild all of the brain's copper from its placement (kicad/thegoose.kicad_pcb, edited in place).

    python3 tools/route_all.py

Runs, in order, with KiCad 10's Python and kicad-cli (both in /Applications):
1. clears the generated groups ("autoroute", "stitch", "plane_channels"),
2. tools/route_recipe.py: the scripted critical routing and the planes,
3. tools/grid_router.py on KiCad's list of unconnected pairs, refilling and re-checking until nothing is left
   (at most ROUNDS times),
4. tools/prune.py until no dangling via or stub is left,
5. tools/plane_channels.py: In3 GND under every In2 signal,
6. tools/stitch.py: GND stitching vias,
7. tools/silk.py: references and logo,
8. a final DRC with zones refilled and the schematic-parity check, which it prints.
Placement itself is tools/place_double.py, run before this when parts move.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "kicad/thegoose.kicad_pcb"
KPY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
KCLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
DRC = ROOT / "build/route_all-drc.json"
ROUNDS = 3

CLEAR = r"""
import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1])
n = 0
for g in [g for g in b.Groups() if g.GetName() == sys.argv[2]]:
    for it in list(g.GetItems()):
        b.Remove(it)
        n += 1
    b.Remove(g)
b.Save(sys.argv[1])
print("cleared %d items of %s" % (n, sys.argv[2]))
"""

FILL = r"""
import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1])
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(sys.argv[1])
"""


def kpy(*args):
    out = subprocess.run([KPY, *args], capture_output=True, text=True, cwd=ROOT)
    for line in (out.stdout + out.stderr).splitlines():
        if line.strip() and "wxApp" not in line and "Debug:" not in line and "swig/python detected" not in line:
            print("   ", line)
    if out.returncode:
        sys.exit("failed: %s" % " ".join(args[:1]))


def drc(final=False):
    DRC.parent.mkdir(exist_ok=True)
    args = [KCLI, "pcb", "drc", "--format", "json", "--severity-all", "-o", str(DRC)]
    if final:
        args += ["--schematic-parity", "--refill-zones", "--save-board"]
    subprocess.run(args + [str(PCB)], capture_output=True, cwd=ROOT)
    d = json.load(open(DRC))
    errors = [v for v in d["violations"] if v["severity"] == "error"]
    warnings = {}
    for v in d["violations"]:
        if v["severity"] == "warning":
            warnings[v["type"]] = warnings.get(v["type"], 0) + 1
    return d, errors, warnings


def step(title, *args):
    print(title)
    kpy(*args)


def main():
    for group in ("autoroute", "stitch", "plane_channels"):     # one process each: pcbnew's lists go stale after
        step("clear", "-c", CLEAR, str(PCB), group)            # removals
    step("recipe", "tools/route_recipe.py")
    step("fill", "-c", FILL, str(PCB))
    for k in range(ROUNDS):
        d, errors, _ = drc()
        left = len([u for u in d["unconnected_items"]           # GND pour islands are stitch.py's job
                    if not all("[GND]" in i["description"] for i in u["items"])])
        print("DRC: %d errors, %d unconnected" % (len(errors), left))
        if not left:
            break
        step("grid router, round %d" % (k + 1), "tools/grid_router.py", str(DRC))
        step("fill", "-c", FILL, str(PCB))
    for k in range(5):
        d, errors, warnings = drc()
        if not warnings.get("via_dangling") and not warnings.get("track_dangling"):
            break
        step("prune", "tools/prune.py", str(DRC))
        step("fill", "-c", FILL, str(PCB))
    step("plane channels", "tools/plane_channels.py")
    step("fill", "-c", FILL, str(PCB))
    step("stitch", "tools/stitch.py")
    step("fill", "-c", FILL, str(PCB))
    step("silk", "tools/silk.py")
    d, errors, warnings = drc(final=True)
    print("final DRC: %d errors, %d unconnected, %d parity issues; warnings %s" % (
        len(errors), len(d["unconnected_items"]), len(d.get("schematic_parity", [])), warnings or "none"))


if __name__ == "__main__":
    main()
