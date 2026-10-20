"""GND stitching vias for the brain board (kicad/thegoose.kicad_pcb, edited in place).

Run with KiCad's Python after routing (tools/route_recipe.py, tools/grid_router.py, tools/plane_channels.py) and a
zone fill:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/stitch.py

Ties the F.Cu and B.Cu GND pours to In1/In2/In3/In4 GND: a ring of vias 0.9 mm inside the outline every 2.5 mm, and
a 3 mm field across the board. A via goes in only where the F.Cu and B.Cu GND fills both cover it, it clears every
other net (the grid router's maps: 0.2 mm copper, 0.5 mm hole to hole) and it sits outside every courtyard, so no via
lands under a part. Then every F.Cu or B.Cu GND island that has no via and no through-hole GND pin gets one, so no
island hangs off SMD pads alone. The vias sit in the PCB group "stitch"; each run replaces it. Refill zones
afterwards.
"""
import math
import os
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grid_router as gr  # noqa: E402

PCB = gr.PCB
GROUP = "stitch"
MM = gr.MM
RING_IN, RING_STEP, FIELD_STEP = 0.9, 2.5, 3.0
D, DRILL = 0.45, 0.25
CRT_MARGIN = 0.15


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
    nets = {str(k): v for k, v in b.GetNetsByName().items()}
    bb = b.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / MM, bb.GetHeight() / MM
    g = gr.Grid(W, H, {k: v.GetNetClassName() for k, v in nets.items()})
    gr.build(b, g)
    rt = gr.Router(g)
    rt.use(g.nid("GND"))
    fills = []
    for z in b.Zones():
        if z.GetNetname() == "GND" and z.GetZoneName() in ("F GND", "B GND"):
            fills.append(z.GetFilledPolysList(z.GetFirstLayer()))
    crt = []
    for f in b.GetFootprints():
        for L in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            ps = f.GetCourtyard(L)
            if ps.OutlineCount():
                crt.append(ps)

    def fits(x, y):
        cx, cy = int(x / gr.G), int(y / gr.G)
        if not (2 <= cx < g.nx - 2 and 2 <= cy < g.ny - 2) or not rt.via_ok(cx, cy):
            return None
        px, py = (cx + 0.5) * gr.G, (cy + 0.5) * gr.G
        v = gr.bpos(px, py)
        for ps in fills:
            if not ps.Contains(v):
                return None
        for ps in crt:
            if ps.Contains(v, -1, int(CRT_MARGIN * MM + D / 2 * MM)):
                return None
        return px, py

    pts = []
    k = int((W - 2 * RING_IN) / RING_STEP)
    for i in range(k + 1):
        x = RING_IN + i * (W - 2 * RING_IN) / k
        pts += [(x, RING_IN), (x, H - RING_IN)]
    k = int((H - 2 * RING_IN) / RING_STEP)
    for i in range(1, k):
        y = RING_IN + i * (H - 2 * RING_IN) / k
        pts += [(RING_IN, y), (W - RING_IN, y)]
    y = FIELD_STEP / 2
    while y < H:
        x = FIELD_STEP / 2
        while x < W:
            pts.append((x, y))
            x += FIELD_STEP
        y += FIELD_STEP
    grp = pcbnew.PCB_GROUP(b)
    grp.SetName(GROUP)
    b.Add(grp)
    n = 0
    for x, y in pts:
        spot = None
        for dx, dy in ((0, 0), (0.3, 0), (-0.3, 0), (0, 0.3), (0, -0.3), (0.4, 0.4), (-0.4, -0.4), (0.4, -0.4),
                       (-0.4, 0.4)):
            spot = fits(x + dx, y + dy)
            if spot:
                break
        if not spot:
            continue
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(gr.bpos(*spot))
        v.SetWidth(int(round(D * MM)))
        v.SetDrill(int(round(DRILL * MM)))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(nets["GND"])
        b.Add(v)
        grp.AddItem(v)
        g.seg([0, 1, 2], rt.n, spot[0], spot[1], spot[0], spot[1], D / 2)
        g.hole(rt.n, spot[0], spot[1], DRILL)
        n += 1
    # every island of the F.Cu and B.Cu GND fills needs at least one via or through-hole GND pin, or it hangs off
    # SMD pads alone: give each bare island a via, inside a courtyard if nothing else fits
    holes = [gr.lpos(t.GetPosition()) for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    holes += [gr.lpos(p.GetPosition()) for f in b.GetFootprints() for p in f.Pads()
              if p.GetNetname() == "GND" and p.GetDrillSize().x > 0]
    holes += [(gr.lpos(v.GetPosition())) for v in grp.GetItems()]
    extra = 0
    for z in b.Zones():
        if z.GetNetname() != "GND" or z.GetZoneName() not in ("F GND", "B GND"):
            continue
        fp = z.GetFilledPolysList(z.GetFirstLayer())
        for k in range(fp.OutlineCount()):
            isl = pcbnew.SHAPE_POLY_SET()
            isl.AddOutline(fp.Outline(k))
            for h in range(fp.HoleCount(k)):
                isl.AddHole(fp.Hole(k, h))
            if any(isl.Contains(gr.bpos(*h)) for h in holes):
                continue
            bb = isl.BBox()
            x0, y0 = gr.lpos(bb.GetOrigin())
            x1, y1 = gr.lpos(bb.GetEnd())
            spot = None
            for use_crt in (False, True):
                y = y0 + 0.1
                while y < y1 and not spot:
                    x = x0 + 0.1
                    while x < x1 and not spot:
                        cx, cy = int(x / gr.G), int(y / gr.G)
                        px, py = (cx + 0.5) * gr.G, (cy + 0.5) * gr.G
                        if 2 <= cx < g.nx - 2 and 2 <= cy < g.ny - 2 and isl.Contains(gr.bpos(px, py)) \
                                and rt.via_ok(cx, cy) and (use_crt or not any(
                                    ps.Contains(gr.bpos(px, py), -1, int(CRT_MARGIN * MM + D / 2 * MM)) for ps in crt)):
                            spot = (px, py)
                        x += 0.1
                    y += 0.1
                if spot:
                    break
            if not spot:
                print("stitch: no room for a via in the %s island at %.1f, %.1f" % (z.GetZoneName(), x0, y0))
                continue
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(gr.bpos(*spot))
            v.SetWidth(int(round(D * MM)))
            v.SetDrill(int(round(DRILL * MM)))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(nets["GND"])
            b.Add(v)
            grp.AddItem(v)
            g.seg([0, 1, 2], rt.n, spot[0], spot[1], spot[0], spot[1], D / 2)
            g.hole(rt.n, spot[0], spot[1], DRILL)
            holes.append(spot)
            extra += 1
    b.Save(str(PCB))
    print("stitch: %d GND vias (of %d spots), %d more for bare pour islands" % (n, len(pts), extra))


if __name__ == "__main__":
    main()
