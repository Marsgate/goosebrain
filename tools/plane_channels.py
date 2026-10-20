"""Keep every In2 signal over GND on In3 (kicad/thegoose.kicad_pcb, edited in place).

Run with KiCad's Python after routing (tools/route_recipe.py, tools/grid_router.py, tools/prune.py):
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/plane_channels.py

On JLC06161H-3313, In2 sits 0.11 mm above In3 and 0.55 mm below In1, so In2 signals reference In3, which carries the
VSYS, VCC and +3V3 areas over a GND background. This script cuts a channel (the track plus MARGIN each side) out of
each power area wherever an In2 signal track crosses it, so the In3 GND background fills in under the track: no In2
signal runs over a power area or crosses the edge between two of them. (F.Cu references In1 and B.Cu references In4,
both solid GND.) Power-net tracks on In2 are left alone.

Each area is first reset to its polygon in tools/route_recipe.py, so the script can run again after any reroute. Where
a channel splits an area, each extra piece becomes its own zone (same net and settings) in the PCB group
"plane_channels", which each run replaces; pieces under MIN_PIECE are dropped and the GND background fills them. Refill zones and run DRC afterwards: a piece that loses its last via shows
up as an unconnected item.
"""
import os
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import route_recipe as rr  # noqa: E402

PCB = ROOT / "kicad/thegoose.kicad_pcb"
GROUP = "plane_channels"
MM = 1e6
MARGIN = 0.5                    # GND each side of an In2 signal, beyond its edge
MIN_PIECE = 2.0                 # mm^2: smaller pieces of a power area cut off by channels are left to the GND background
SIG, REF = pcbnew.In2_Cu, pcbnew.In3_Cu
POWER = {"GND", "VSYS", "VCC", "PACK+", "+3V3", "+1V1", "VBUS", "Net-(J4-VBUS)", "Net-(D2-K)", "Net-(D2-A)"}


def polyset(pts):
    ps = pcbnew.SHAPE_POLY_SET()
    ps.NewOutline()
    for x, y in pts:
        ps.Append(int(round((rr.OX + x) * MM)), int(round((rr.OY + y) * MM)))
    return ps


def main():
    b = pcbnew.LoadBoard(str(PCB))
    old = [g for g in b.Groups() if g.GetName() == GROUP]
    if old:
        for g in old:
            for it in list(g.GetItems()):
                b.Remove(it)
            b.Remove(g)
        b.Save(str(PCB))
        os.execv(sys.executable, [sys.executable] + sys.argv)    # a fresh process: pcbnew's lists go stale after removals
    bb = b.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / MM, bb.GetHeight() / MM
    areas = {"In3 +3V3": rr.PWR_33, "In3 VCC": rr.PWR_VCC, "In3 VSYS": rr.pwr_vsys(W, H)}
    cut = pcbnew.SHAPE_POLY_SET()
    n = 0
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetLayer() != SIG or t.GetNetname() in POWER:
            continue
        a, c = t.GetStart(), t.GetEnd()
        r = t.GetWidth() / 2 + int(MARGIN * MM)
        dx, dy = c.x - a.x, c.y - a.y
        L = (dx * dx + dy * dy) ** 0.5
        ux, uy = (dx / L, dy / L) if L else (1.0, 0.0)
        nx, ny = -uy * r, ux * r
        ex, ey = ux * r, uy * r
        cut.NewOutline()
        for px, py in ((a.x - ex + nx, a.y - ey + ny), (c.x + ex + nx, c.y + ey + ny),
                       (c.x + ex - nx, c.y + ey - ny), (a.x - ex - nx, a.y - ey - ny)):
            cut.Append(int(px), int(py))
        n += 1
    cut.Simplify()
    zones = [z for z in b.Zones() if z.GetZoneName() in areas and z.IsOnLayer(REF)]
    g = pcbnew.PCB_GROUP(b)
    g.SetName(GROUP)
    b.Add(g)
    extra = 0
    for z in zones:
        shape = polyset(areas[z.GetZoneName()])
        shape.BooleanSubtract(cut)
        keep = [k for k in range(shape.OutlineCount()) if abs(shape.Outline(k).Area()) >= MIN_PIECE * MM * MM]
        keep.sort(key=lambda k: -abs(shape.Outline(k).Area()))
        for i, k in enumerate(keep):
            zz = z if i == 0 else z.Duplicate(False).Cast()
            o = zz.Outline()                            # the zone's own polygon (SetOutline would keep a pointer to
            o.RemoveAllContours()                       # a Python-owned one)
            o.AddOutline(shape.Outline(k))
            for h in range(shape.HoleCount(k)):
                o.AddHole(shape.Hole(k, h))
            if i:
                b.Add(zz)
                g.AddItem(zz)
                extra += 1
    b.Save(str(PCB))
    print("plane_channels: %d In2 signal segments cut out of the In3 power areas (%d extra area pieces)" % (n, extra))


if __name__ == "__main__":
    main()
