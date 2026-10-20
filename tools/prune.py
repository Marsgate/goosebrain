"""Remove dangling vias and track stubs from the routing (kicad/thegoose.kicad_pcb, edited in place).

Run with KiCad's Python on a DRC report in JSON, after tools/grid_router.py and a zone fill:
    kicad-cli pcb drc --format json --severity-all -o drc.json kicad/thegoose.kicad_pcb
    .../python3 tools/prune.py drc.json

The recipe drops a via at the end of several escape stubs so a route can leave on another layer. When the router
reaches the stub on its own layer instead, the via ends up connected on one layer only (KiCad's "via_dangling"), and a
stub left behind by a removed via is a "track_dangling". This removes the items DRC flags, from the "route_recipe"
and "autoroute" groups only. Before a via goes, every track end of its net that lands on the via's copper gets a short
segment to the via's centre, so the tracks it joined stay joined. Repeat (fill, DRC, prune) until it removes nothing.
"""
import json
import sys
from pathlib import Path

import pcbnew

PCB = Path(__file__).resolve().parent.parent / "kicad/thegoose.kicad_pcb"
GROUPS = {"route_recipe", "autoroute"}


def main():
    drc = json.load(open(sys.argv[1]))
    flagged = {i["uuid"] for v in drc.get("violations", []) if v["type"] in ("via_dangling", "track_dangling")
               for i in v["items"]}
    b = pcbnew.LoadBoard(str(PCB))
    gone = []
    for t in b.GetTracks():
        g = t.GetParentGroup()
        if t.m_Uuid.AsString() in flagged and g is not None and g.GetName() in GROUPS:
            gone.append(t)
    for v in gone:
        if v.GetClass() != "PCB_VIA":
            continue
        c, r = v.GetPosition(), v.GetWidth(pcbnew.F_Cu) / 2 + 10000
        joins = []
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetCode() != v.GetNetCode() or t in gone:
                continue
            for e in (t.GetStart(), t.GetEnd()):
                if e != c and (e.x - c.x) ** 2 + (e.y - c.y) ** 2 <= r * r:
                    joins.append((t, pcbnew.VECTOR2I(e)))
        # join each end to the via's centre with a short segment rather than moving the end: the segment stays
        # inside the via's copper, so it can't break a clearance the way a moved (now slanted) track can
        for t, e in joins:
            s = pcbnew.PCB_TRACK(b)
            s.SetStart(e)
            s.SetEnd(c)
            s.SetLayer(t.GetLayer())
            s.SetWidth(t.GetWidth())
            s.SetNetCode(t.GetNetCode())
            b.Add(s)
            t.GetParentGroup().AddItem(s) if t.GetParentGroup() else None
    for t in gone:
        t.GetParentGroup().RemoveItem(t)
        b.Remove(t)
    b.Save(str(PCB))
    print("prune: removed %d dangling items" % len(gone))


if __name__ == "__main__":
    main()
