"""Keep every B.Cu signal over GND on In2 (kicad/thegoose.kicad_pcb, edited in place).

Run with KiCad's Python after routing (tools/route_recipe.py + Freerouting):
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/in2_channels.py

B.Cu signals reference In2, which carries the VSYS, VCC and +3V3 areas. This script draws one In2 GND zone, above
the power areas in priority, along every B.Cu track of a signal net (track width plus MARGIN each side), so no B.Cu
signal runs over a power area or crosses the edge between two of them. Power nets are left alone. The zone sits in
the PCB group "in2_channels"; each run replaces it. Refill zones afterwards.
"""
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "kicad/thegoose.kicad_pcb"
GROUP = "in2_channels"
MM = 1e6
MARGIN = 0.6                    # GND each side of a B.Cu signal, beyond its edge
POWER = {"GND", "VSYS", "VCC", "PACK+", "+3V3", "+1V1", "VBUS", "Net-(J4-VBUS)", "Net-(D2-K)", "Net-(D2-A)"}


def main():
    b = pcbnew.LoadBoard(str(PCB))
    for g in [g for g in b.Groups() if g.GetName() == GROUP]:
        for it in list(g.GetItems()):
            b.Remove(it)
        b.Remove(g)
    ps = pcbnew.SHAPE_POLY_SET()
    n = 0
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetLayer() != pcbnew.B_Cu or t.GetNetname() in POWER:
            continue
        a, c = t.GetStart(), t.GetEnd()
        r = t.GetWidth() / 2 + int(MARGIN * MM)
        dx, dy = c.x - a.x, c.y - a.y
        L = (dx * dx + dy * dy) ** 0.5
        if L == 0:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = dx / L, dy / L
        nx, ny = -uy * r, ux * r
        ex, ey = ux * r, uy * r
        ps.NewOutline()
        for px, py in ((a.x - ex + nx, a.y - ey + ny), (c.x + ex + nx, c.y + ey + ny),
                       (c.x + ex - nx, c.y + ey - ny), (a.x - ex - nx, a.y - ey - ny)):
            ps.Append(int(px), int(py))
        n += 1
    ps.Simplify()
    z = pcbnew.ZONE(b)
    z.SetLayer(pcbnew.In2_Cu)
    z.SetNet(b.FindNet("GND"))
    z.SetOutline(ps)
    z.SetAssignedPriority(50)
    z.SetLocalClearance(int(0.2 * MM))
    z.SetMinThickness(int(0.2 * MM))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetZoneName("In2 GND under B.Cu signals")
    b.Add(z)
    g = pcbnew.PCB_GROUP(b)
    g.SetName(GROUP)
    b.Add(g)
    g.AddItem(z)
    b.Save(str(PCB))
    print("in2_channels: %d B.Cu signal segments, %d outlines" % (n, ps.OutlineCount()))


if __name__ == "__main__":
    main()
