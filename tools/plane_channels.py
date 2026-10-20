"""Keep every In2 signal over GND on In3 (kicad/thegoose.kicad_pcb, edited in place).

Run with KiCad's Python after routing (tools/route_recipe.py + Freerouting):
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/plane_channels.py

On JLC06161H-3313, In2 sits 0.11 mm above In3 and 0.55 mm below In1, so In2 signals reference In3, which carries the
VSYS, VCC and +3V3 areas. This script draws one In3 GND zone, above the power areas in priority, along every In2
track of a signal net (track width plus MARGIN each side), so no In2 signal runs over a power area or crosses the
edge between two of them. The zone is clipped to the power areas (plus MARGIN), since over the GND background it isn't
needed. (F.Cu references In1 and B.Cu references In4, both solid GND.) Power nets are left alone.
The zone sits in the PCB group "plane_channels"; each run replaces it. Refill zones afterwards.
"""
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "kicad/thegoose.kicad_pcb"
GROUP = "plane_channels"
MM = 1e6
MARGIN = 0.5                    # GND each side of an In2 signal, beyond its edge
SIG, REF = pcbnew.In2_Cu, pcbnew.In3_Cu
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
        if t.GetClass() == "PCB_VIA" or t.GetLayer() != SIG or t.GetNetname() in POWER:
            continue
        a, c = t.GetStart(), t.GetEnd()
        r = t.GetWidth() / 2 + int(MARGIN * MM)
        dx, dy = c.x - a.x, c.y - a.y
        L = (dx * dx + dy * dy) ** 0.5
        ux, uy = (dx / L, dy / L) if L else (1.0, 0.0)
        nx, ny = -uy * r, ux * r
        ex, ey = ux * r, uy * r
        ps.NewOutline()
        for px, py in ((a.x - ex + nx, a.y - ey + ny), (c.x + ex + nx, c.y + ey + ny),
                       (c.x + ex - nx, c.y + ey - ny), (a.x - ex - nx, a.y - ey - ny)):
            ps.Append(int(px), int(py))
        n += 1
    # only where a power area is: over the GND background the channel would just overlap it (and leave slivers)
    areas = pcbnew.SHAPE_POLY_SET()
    for z in b.Zones():
        if z.IsOnLayer(REF) and not z.GetIsRuleArea() and z.GetNetname() in POWER and z.GetNetname() != "GND":
            areas.BooleanAdd(z.Outline())
    areas.Inflate(int(MARGIN * MM), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, int(0.005 * MM))
    if n:
        ps.Simplify()
        ps.BooleanIntersection(areas)
        z = pcbnew.ZONE(b)
        z.SetLayer(REF)
        z.SetNet(b.FindNet("GND"))
        z.SetOutline(ps)
        z.SetAssignedPriority(50)
        z.SetLocalClearance(int(0.2 * MM))
        z.SetMinThickness(int(0.2 * MM))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetZoneName("In3 GND under In2 signals")
        b.Add(z)
        g = pcbnew.PCB_GROUP(b)
        g.SetName(GROUP)
        b.Add(g)
        g.AddItem(z)
    b.Save(str(PCB))
    print("plane_channels: %d In2 signal segments" % n)


if __name__ == "__main__":
    main()
