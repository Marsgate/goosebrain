"""Route the 3S pack board (kicad-pack/goosepack.kicad_pcb, edited in place), or with --board=pack2s the 2S pack
(kicad-pack-2s/goosepack2s.kicad_pcb: no R66, so no Kelvin lines, and the ground split, pack path and pours of
PACK2S below).

Run with KiCad's Python after tools/place_pack.py compact:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        tools/route_pack.py setup
    .../python3 tools/route_pack.py route
    .../python3 tools/route_pack.py finish

Each step takes --pcb=FILE to work on a copy instead (with its .kicad_pro and .kicad_dru beside it).

Stackup JLC04161H-7628: F.Cu (parts and signals), In1.Cu (ground), In2.Cu (PACK+ and signals), B.Cu (signals and
ground).

setup:
- net classes in goosepack.kicad_pro: Default 0.15/0.15 mm; Plane (PACK+, BAT_N, PACK-) and Power (the rest of the
  pack path) 0.4 mm tracks at 0.2 mm, Charger (VBUS, PMID, SYS, switch nodes) 0.3 mm at 0.2 mm.
  goosepack.kicad_dru holds the 0.3 mm copper-to-edge rule and lets those classes neck to 0.2 mm at fine-pitch pins.
- In1 is a power layer, left out of routing, split: BAT_N (the cells' negative, the protector's ground) under the
  protector and the cell side, PACK- (the charger's and the brain's ground) everywhere else. In2 carries PACK+ along a
  band from F1 to J2 (the pack current), under a rule area that keeps tracks out; the rest of In2 is a third routing
  layer.
- F.Cu pours for each hop of the pack path, all short: J3 to F1 (CELL+), J3 to R66 (BAT_N), R66 to Q2 (PROT_SNS),
  Q2 to Q3 (PROT_FET_D), Q3 to J2 (PACK-), and F1's PACK+ pad, which drops to the In2 plane through a block of vias
  under the fuse. J2's and J3's barrels reach every layer.
- the charger's power stage on F.Cu (power_stage(), around tools/place_pack.py's placement): SYS and PMID from U7's
  pins out under their rows of caps, SW1 and SW2 from the pins to L2's pads (SW1 on over C18's SW1 pad), PGND from
  its pin out between L2's pads to a row of vias under L2's body, and short pours from the VBUS, BAT and REGN pins to
  their caps. BTST2 runs straight up to C19 over pin 19, and SW2 from C19 by a via and In2 back to a via beside L2's
  SW2 pad; BTST1 runs from pin 4 to C18 (under L2) by B.Cu; SDRV, SDA, SCL
  and the east ground pins have necks to vias under U7, and VBUS a strip under U7 from its east pins to pins 2 and 3;
  BATP, ILIM_HIZ and TS (U7's crowded north-east corner) and J1's CC2 and north VBUS pads short escapes to vias, and
  C36 (packed) a stub out of its SDRV pad.
- Kelvin sense lines (kelvin()): B.Cu tracks from vias at the inner edges of R66's pads to R68 (SRP side, BAT_N) and
  R69 (SRN side, PROT_SNS) by U13. Rule areas keep the ground fills off R68's line, so BAT_N meets it only at R66.
- every SMD pad on a plane net near its plane gets a stub and a via to it (fanout), except R68's sense pad; U7's
  pins fan out under its body, which leaves J1's pin row its exits. No via lands within 0.2 mm of an SMD pad.
route: tools/grid_router.py --board=pack (Freerouting 2.1 stalled at 25-40 unrouted here and ignores its pass limits)
on KiCad's unconnected pairs. It skips BAT_N and PACK- and routes the rest at each class width: signals, the Power nets
the pours don't reach (CELL+ to R61) and PACK+ out to the charger's BAT pins and caps (charge current only). Nets go in
ROUTE_ORDER (STAT out to the LED by J1, SYS out to its far bulk cap, BTST1 and PROG, which grid_router's own order
leaves walled in, then D- before D+ and SDA, which share J1's and U7's east exits; the rest follow in that order; --order=NET,... replaces it). The router can't rip up on its own; ROUTE_FIX (--fix=) rips some
nets and routes them again after the first pass (it used to re-route PMID after SW2; the current order needs none).
finish:
- setup's vias that routing left dangling removed (the tracks that met in them now meet at their centre); the
  router's track ends inside a setup via but off its centre moved to it, and each routed VBUS via gets a second one
  beside it, where DRC allows both.
- Charger, Power and Plane tracks widened to 0.4 mm wherever DRC still passes; VBUS and PACK+ on In2 to 0.6 or
  0.5 mm first (about 1 A on 0.5 oz inner copper).
- F.Cu, In2.Cu and B.Cu ground fills, split like In1, and a B.Cu PACK+ pour under the band where routing left
  room; GND stitching vias; zone fill.

Everything setup adds sits in the PCB group "route_pack" (the sense lines in "kelvin"), the router's copper in
"autoroute" and finish's in "route_pack_finish"; setup clears all tracks and zones first, so the three steps can run
again after the placement changes.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import packcfg  # noqa: E402
import place_pack as pp  # noqa: E402
PCB = Path(next((a[6:] for a in sys.argv if a.startswith("--pcb=")), packcfg.PCB))
PRO = PCB.with_suffix(".kicad_pro")              # --pcb=FILE: work on a copy (with its .kicad_pro and .kicad_dru)
PCB_ARG = [a for a in sys.argv if a.startswith("--pcb=")]
GROUP = "route_pack"
MM = 1e6
OX, OY = 100.0, 100.0
W, H = 50.0, 23.0
VIA_D, VIA_DRILL = 0.6, 0.3
SMALL_VIA = (0.45, 0.3)         # setup vias where a 0.6 mm one doesn't fit (BTST1 beside pin 4), as the router's
                                # signal vias

PLANE = ["/PACK+", "/BAT_N", "/PACK-"]
POWER = ["/CELL+", "/PROT_SNS", "/PROT_FET_D"]
CHARGER = ["/VBUS", "/PMID", "/CHG_SYS", "/SW1", "/SW2"]
# Charger nets route at 0.3 mm: the BQ25798's SYS, SW and PMID pads are 0.2 mm wide at 0.46 mm pitch, and a wider
# track can't reach them at 0.2 mm clearance. finish widens them to 0.4 mm wherever that still clears.
CHARGER_W, WIDE = 0.3, 0.4

# In1/F.Cu/B.Cu split: BAT_N west of this line, PACK- east of it. It runs between the protector and the charger
# (x 28 above y 8, west of R79), under U13's south edge to x 21.5 (R74's PACK- pad stays east), then between Q2 and Q3
# (x 20) down to the bottom edge.
BAT_N_AREA = [(0, 0), (28.0, 0), (28.0, 8.0), (21.5, 8.0), (21.5, 12.0), (20.0, 12.0), (20.0, H), (0, H)]
PACK_N_AREA = [(28.0, 0), (W, 0), (W, H), (20.0, H), (20.0, 12.0), (21.5, 12.0), (21.5, 8.0),
               (28.0, 8.0)]                                                   # the rest; drawn as its own shape
BOARD = [(0, 0), (W, 0), (W, H), (0, H)]
# In2 carries PACK+ only along this band (F1's vias to J2's barrel); everywhere else In2 is a third routing layer, and
# a rule area keeps signal tracks out of the band. The charger's PACK+ pads (U7's BAT pins, R30, C33, C34) take only
# the charge current and are routed as tracks: a branch of the plane up to them walled in U7's west pins.
PACK_P_AREA = [(7.6, 13.1), (32.4, 13.1), (32.4, 18.9), (7.6, 18.9)]
FAN_REACH = 3.0                 # PACK+ pads further than this from the band are left to the router
# F.Cu pours along the pack path (board-local mm, x right, y down)
PATH = {
    "/CELL+": [(0.3, 12.1), (9.3, 12.1), (9.3, 13.8), (7.4, 13.8), (7.4, 18.6), (0.3, 18.6)],
    "/BAT_N": [(0.3, 18.8), (7.0, 18.8), (7.0, H - 0.3), (0.3, H - 0.3)],
    "/PROT_SNS": [(12.6, 16.0), (14.1, 16.0), (14.1, 17.4), (15.0, 17.4), (15.0, 21.25), (12.55, 21.25),
                  (12.55, H - 0.3), (10.6, H - 0.3), (10.6, 18.6), (12.6, 18.6)],          # takes R71 too
    "/PROT_FET_D": [(17.7, 17.45), (22.5, 17.45), (22.5, H - 0.3), (17.7, H - 0.3)],
    "/PACK-": [(25.2, 18.7), (31.9, 18.7), (31.9, H - 0.3), (25.2, H - 0.3)],
    "/PACK+": [(8.0, 14.8), (12.5, 14.8), (12.5, 18.4), (8.0, 18.4)],
}
FUSE_VIAS = [(x, y) for x in (8.6, 9.4) for y in (15.4, 16.2, 17.0, 17.8)]   # F1's PACK+ pad down to In2
DRAIN_VIAS = []                 # 2S: PROT_FET_D down to a B.Cu pour
BAND_CLEAR = False              # 2S: no other net's vias in PACK_P_AREA, no tracks on B.Cu there either
PAD_VIA = 0.2                   # a via's copper keeps this far from every SMD pad (no vias in pads)

# The 2S pack (--board=pack2s): board size from its outline, then the same pack-path pours around its own placement
# (tools/place_pack.py compact2s). The protector senses across Q2 + Q3, so there is no R66 and no Kelvin sense. Ground
# splits at one vertical line, XB: the BAT_N parts (J3, Q2's sources, U13, C62, C64, R71) west of it, the PACK- parts
# (Q3, J2, R73, R74, the charger) east, and R94 across it.
if packcfg.BOARD == "pack2s":
    _bb = pcbnew.LoadBoard(str(PCB)).GetBoardEdgesBoundingBox()
    W, H = round(_bb.GetWidth() / MM * 2) / 2, round(_bb.GetHeight() / MM * 2) / 2
    XB = pp.XB_2S
    BAT_N_AREA = [(0, 0), (XB, 0), (XB, H), (0, H)]
    PACK_N_AREA = [(XB, 0), (W, 0), (W, H), (XB, H)]
    BOARD = [(0, 0), (W, 0), (W, H), (0, H)]
    # The PACK+ band carries the pack current from F1 to J2 on In2 and B.Cu (no F.Cu room past R71 and R74), so on
    # 2S it keeps every other net's tracks and vias out on both layers, and J2's P+ pad joins it solid.
    PACK_P_AREA = [(7.3, 12.9), (23.5, 12.9), (23.5, 17.1), (7.3, 17.1)]
    BAND_CLEAR = True
    PATH = {
        "/CELL+": [(0.3, 12.5), (6.85, 12.5), (6.85, 17.2), (0.3, 17.2)],
        "/BAT_N": [(0.3, 17.5), (6.95, 17.5), (6.95, 21.3), (4.6, 21.3), (4.6, H - 0.3), (0.3, H - 0.3)],
        "/PROT_FET_D": [(9.55, 17.5), (16.85, 17.5), (16.85, H - 0.3), (9.55, H - 0.3)],   # into Q3's body gap
        "/PACK-": [(17.15, 18.6), (23.5, 18.6), (23.5, H - 0.3), (17.15, H - 0.3)],
        "/PACK+": [(7.1, 13.9), (12.1, 13.9), (12.1, 17.05), (7.1, 17.05)],
    }
    FUSE_VIAS = [(x, y) for x in (7.6, 8.4, 9.2) for y in (14.3, 15.1, 15.9, 16.7)]
    # the drains' heat: a B.Cu copy of the PROT_FET_D pour, stitched through vias in Q3's body gap
    DRAIN_VIAS = [(x, y) for x in (15.2, 16.1) for y in (18.5, 19.5, 20.5, 21.5)]


def v(x, y):
    return pcbnew.VECTOR2I(int(round((OX + x) * MM)), int(round((OY + y) * MM)))


def net_classes():
    """Write the Power and Charger classes into the project file (pcbnew reads it with the board)."""
    pro = json.loads(PRO.read_text())
    ns = pro["net_settings"]
    base = next(c for c in ns["classes"] if c["name"] == "Default")
    base.update(track_width=0.15, clearance=0.15, via_diameter=0.45, via_drill=0.3)
    classes = [base]
    for name, width in (("Plane", 0.4), ("Power", 0.4), ("Charger", CHARGER_W)):
        c = dict(base, name=name, track_width=width, clearance=0.2, via_diameter=VIA_D, via_drill=VIA_DRILL,
                 priority=len(classes))
        classes.append(c)
    ns["classes"] = classes
    brain = json.loads((ROOT / "kicad/thegoose.kicad_pro").read_text())   # JLC limits, as on the brain
    pro.setdefault("board", {})["design_settings"] = brain["board"]["design_settings"]
    rules = pro["board"]["design_settings"]["rules"]      # 0.3 mm drills keep JLC's standard via (0.25 mm costs
    rules.update(min_through_hole_diameter=0.3, min_via_annular_width=0.075)  # about $37 more per order: TG155 + Kelvin test)
    ns["netclass_patterns"] = [{"netclass": "Plane", "pattern": n} for n in PLANE] + \
                              [{"netclass": "Power", "pattern": n} for n in POWER] + \
                              [{"netclass": "Charger", "pattern": n} for n in CHARGER]
    PRO.write_text(json.dumps(pro, indent=2) + "\n")


class Builder:
    def __init__(self, b, group=GROUP):
        self.b = b
        self.grp = next((g for g in b.Groups() if g.GetName() == group), None)
        if self.grp is None:
            self.grp = pcbnew.PCB_GROUP(b)
            self.grp.SetName(group)
            b.Add(self.grp)

    def net(self, name):
        return self.b.FindNet(name)

    def zone(self, name, net, layer, pts, prio, solid=True, min_width=0.2, clearance=0.2):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer)
        z.SetNet(self.net(net))
        z.SetZoneName(name)
        z.SetAssignedPriority(prio)
        z.SetMinThickness(int(min_width * MM))
        z.SetLocalClearance(int(clearance * MM))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(int(0.25 * MM))
        z.SetThermalReliefSpokeWidth(int(0.3 * MM))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        if pts:
            ol = z.Outline()
            ol.NewOutline()
            for x, y in pts:
                ol.Append(v(x, y))
        self.b.Add(z)
        return z

    def pour(self, name, net, rects, prio=10):
        """F.Cu zone over the union of rectangles (x0, y0, x1, y1), solid to pads, 0.15 mm minimum width."""
        z = self.zone(name, net, pcbnew.F_Cu, [], prio, min_width=0.15)
        outline(z, union(rects))
        return z

    def nofill(self, name, layers, rects):
        """Rule area: no zone fills on these layers."""
        z = pcbnew.ZONE(self.b)
        z.SetIsRuleArea(True)
        ls = pcbnew.LSET()
        for L in layers:
            ls.AddLayer(L)
        z.SetLayerSet(ls)
        z.SetZoneName(name)
        z.SetDoNotAllowZoneFills(True)
        for flag in (z.SetDoNotAllowTracks, z.SetDoNotAllowVias, z.SetDoNotAllowPads, z.SetDoNotAllowFootprints):
            flag(False)
        outline(z, union(rects))
        self.b.Add(z)
        return z

    def router_keepout(self, nets, layers, polys):
        """Rule areas (one per polygon) that allow everything, so DRC ignores them, named so tools/grid_router.py
        keeps these nets out."""
        ls = pcbnew.LSET()
        for L in layers:
            ls.AddLayer(L)
        for pts in polys:
            z = pcbnew.ZONE(self.b)
            z.SetIsRuleArea(True)
            z.SetLayerSet(ls)
            z.SetZoneName("router keepout " + ",".join(nets))
            for flag in (z.SetDoNotAllowTracks, z.SetDoNotAllowVias, z.SetDoNotAllowPads, z.SetDoNotAllowFootprints,
                         z.SetDoNotAllowZoneFills):
                flag(False)
            ol = z.Outline()
            ol.NewOutline()
            for x, y in pts:
                ol.Append(v(x, y))
            self.b.Add(z)

    def keepout(self, name, layer, pts):
        """Rule area: no tracks (vias and the zone's own fill are allowed)."""
        z = pcbnew.ZONE(self.b)
        z.SetIsRuleArea(True)
        z.SetLayer(layer)
        z.SetZoneName(name)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetDoNotAllowZoneFills(False)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(v(x, y))
        self.b.Add(z)
        return z

    def path(self, net, layer, pts, width):
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            self.track(net, layer, ax, ay, bx, by, width)

    def track(self, net, layer, ax, ay, bx, by, width):
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(v(ax, ay))
        t.SetEnd(v(bx, by))
        t.SetWidth(int(width * MM))
        t.SetLayer(layer)
        t.SetNet(self.net(net))
        self.b.Add(t)
        self.grp.AddItem(t)
        return t

    def via(self, net, x, y, size=(VIA_D, VIA_DRILL)):
        t = pcbnew.PCB_VIA(self.b)
        t.SetPosition(v(x, y))
        t.SetWidth(int(size[0] * MM))
        t.SetDrill(int(size[1] * MM))
        t.SetNet(self.net(net))
        self.b.Add(t)
        self.grp.AddItem(t)
        return t


def union(rects):
    s = pcbnew.SHAPE_POLY_SET()
    for x0, y0, x1, y1 in rects:
        r = pcbnew.SHAPE_POLY_SET()
        r.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            r.Append(v(x, y))
        s.BooleanAdd(r)
    return s


def seg_poly(a, c, r):
    """The rectangle within r of segment a-c (ends squared off r past each end)."""
    dx, dy = c[0] - a[0], c[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy, nx, ny = dx / L * r, dy / L * r, -dy / L * r, dx / L * r
    return [(a[0] - ux + nx, a[1] - uy + ny), (c[0] + ux + nx, c[1] + uy + ny), (c[0] + ux - nx, c[1] + uy - ny),
            (a[0] - ux - nx, a[1] - uy - ny)]


def outline(z, polys):
    """Copy a SHAPE_POLY_SET into a zone's outline (ZONE.SetOutline takes ownership, which Python can't give)."""
    ol = z.Outline()
    ol.RemoveAllContours()
    for i in range(polys.OutlineCount()):
        src = polys.Outline(i)
        ol.NewOutline()
        for j in range(src.PointCount()):
            ol.Append(src.CPoint(j))


def pad(b, ref, num=None, net=None):
    f = next(f for f in b.GetFootprints() if f.GetReference() == ref)
    return next(p for p in f.Pads() if (num is None or p.GetNumber() == num) and (net is None or p.GetNetname() == net))


def box(p):
    """A pad's bounding box, board-local (x0, y0, x1, y1)."""
    bb = p.GetBoundingBox()
    return (bb.GetLeft() / MM - OX, bb.GetTop() / MM - OY, bb.GetRight() / MM - OX, bb.GetBottom() / MM - OY)


NECK = 0.12                     # half-width of the pours' necks between U7's 0.45 mm pitch power pins


def power_stage(b, k):
    """Pours and vias for U7's power stage (see tools/place_pack.py power_stage): U7's power pins face west, SYS north
    and PMID south, L2's SW2 pad north and SW1 south. Every pour keeps 0.2 mm from the next."""
    pin = {n: box(pad(b, "U7", n)) for n in ("25", "26", "27", "28", "29")}
    y = {n: (bx[1] + bx[3]) / 2 for n, bx in pin.items()}
    xo = pin["25"][0]                                    # the pins' outer ends
    sw2, sw1 = box(pad(b, "L2", net="/SW2")), box(pad(b, "L2", net="/SW1"))
    lx0, lx1 = sw2[0], sw2[2]
    xs1 = xo - 0.2                                       # SYS and PMID strips, 0.8 mm wide, beside the pins
    xs0 = xs1 - 0.8
    rx1 = xs0 - 0.2                                      # the SW pours' east edge
    pin_in = xo + 0.5                                    # pours reach this far onto the pins
    sys_pads = [box(pad(b, r, net="/CHG_SYS")) for r in pp.SYS_ROW]
    pmid_pads = [box(pad(b, r, net="/PMID")) for r in pp.PMID_ROW]
    st, sb, sx = min(p[1] for p in sys_pads), max(p[3] for p in sys_pads), min(p[0] for p in sys_pads)
    pt, pb, px = min(p[1] for p in pmid_pads), max(p[3] for p in pmid_pads), min(p[0] for p in pmid_pads)
    assert sb <= sw2[1] - 0.2 and pt >= sw1[3] + 0.2, "a cap row is too close to L2"
    k.pour("F SYS", "/CHG_SYS", [(xs1, y["25"] - 0.1, pin_in, y["25"] + 0.1), (xs0, st, xs1, y["25"] + 0.1),
                                 (sx, st, xs1, sb)])
    k.pour("F PMID", "/PMID", [(xs1, y["29"] - 0.1, pin_in, y["29"] + 0.1), (xs0, y["29"] - 0.1, xs1, pb),
                               (px, pt, xs1, pb)])
    k.pour("F SW2", "/SW2", [(rx1 - 0.4, y["26"] - NECK, pin_in, y["26"] + NECK),
                             (lx1 - 0.3, sw2[1], rx1, y["26"] - NECK)])
    c18 = box(pad(b, "C18", net="/SW1"))                # C18's SW1 pad, under the pour's south end
    k.pour("F SW1", "/SW1", [(rx1 - 0.4, y["28"] - NECK, pin_in, y["28"] + NECK),
                             (lx1 - 0.3, y["28"] + NECK, rx1, sw1[3]), (c18[0] - 0.05, sw1[3] - 0.1, rx1, c18[3])])
    n0, n1 = rx1 - 0.6, lx1 - 0.5                        # PGND: a neck to n0, 0.74 mm wide to n1, then L2's gap
    k.pour("F PGND", "/PACK-", [(n0 - 0.05, y["27"] - NECK, pin_in, y["27"] + NECK),
                                (n1 - 0.05, y["26"] - NECK + 0.2, n0, y["28"] + NECK - 0.2),
                                (lx0 - 0.5, sw2[3] + 0.2, n1, sw1[1] - 0.2)])
    vias = [(lx1 + 0.1 - 0.85 * i, y["27"]) for i in range(5)]
    sv = (lx1 + 0.6, (sw2[1] + y["26"] - NECK) / 2)       # SW2's via beside L2, for C19
    vias += [sv + ("/SW2",)]
    for x, yy, *net in vias:
        k.via(net[0] if net else "/PACK-", x, yy)
    # SDRV (the NW corner pin) is boxed in by the SYS strip, BAT's pins and C33: a neck east under the BAT pins to a via
    # under U7's body (no exposed pad), clear of pin 25. C36 hangs off the via on another layer.
    sd = box(pad(b, "U7", "24"))
    ny = sd[3] - 0.05                                    # the neck's centre, just inside the pad's inner edge
    vx = pin["25"][2] + PAD_VIA + 0.05 + VIA_D / 2      # east of pin 25's inner end
    k.track("/SDRV", pcbnew.F_Cu, sd[2] - 0.1, ny, vx, ny, 0.15)
    k.track("/SDRV", pcbnew.F_Cu, vx, ny, vx, ny + 0.3, 0.15)
    k.via("/SDRV", vx, ny + 0.3)
    # U7's east pins face J1 0.4 mm away, and J1's pins need that corridor for their own exits, so everything on the
    # east side leaves under U7's body (no exposed pad), made before the fanout takes the room:
    # - VBUS: its east pins (8 and the SE corner, 9) sit past D+/D-, which J1 also has between its VBUS pads. A strip
    #   under the body, inside the south pins' inner ends, joins them to pins 2 and 3 (and their pour) on F.Cu.
    # - SDA (pin 15) and SCL (pin 14), the east side's north end: a neck west from each pin to a via.
    # - the ground pins (10, 11, 13): stubs in to one via.
    p2, p3, p8, p9 = (box(pad(b, "U7", n)) for n in ("2", "3", "8", "9"))
    north = box(pad(b, "U7", "18"))[3]                  # the north pins' inner ends
    sy0, sy1 = p8[1] - 0.6, p8[1] - 0.25                 # the strip, 0.25 mm inside the south pins
    vbus = [(p8[0], p9[1], p9[2], p8[3]), (pin["29"][2] + 0.2, sy0, p8[0], sy1), (p8[0], sy1 - 0.2, p8[2], p8[1] + 0.1),
            (p2[0], sy1 - 0.1, p3[2], p2[1] + 0.1)]     # joins the F VBUS pour below
    sda, scl = box(pad(b, "U7", "15")), box(pad(b, "U7", "14"))
    ya, yc = (sda[1] + sda[3]) / 2, (scl[1] + scl[3]) / 2
    va = (sda[0] - 1.0, max(ya, north + PAD_VIA + VIA_D / 2 + 0.05))
    vc = (scl[0] - 1.3, yc + 0.5)
    k.path("/CHG_SDA", pcbnew.F_Cu, [(sda[0] + 0.1, ya), (va[0], ya), va], 0.15)
    k.path("/CHG_SCL", pcbnew.F_Cu, [(scl[0] + 0.1, yc), (scl[0] - 0.6, yc), vc], 0.15)
    k.via("/CHG_SDA", *va)
    k.via("/CHG_SCL", *vc)
    p10, p11, p13 = (box(pad(b, "U7", n)) for n in ("10", "11", "13"))
    ge = (p11[0] - 0.65, p11[1] - 0.05)
    y10, y11, y13 = (p10[1] + p10[3]) / 2, p11[1] + 0.12, (p13[1] + p13[3]) / 2   # 11's stub 0.22 mm off QON (12)
    k.path("/PACK-", pcbnew.F_Cu, [(p10[0] + 0.1, y10), (p10[0] - 0.15, y10 - 0.25), ge], 0.2)
    k.path("/PACK-", pcbnew.F_Cu, [(p11[0] + 0.1, y11), (p11[0] - 0.25, y11), ge], 0.2)
    k.path("/PACK-", pcbnew.F_Cu, [(p13[0] + 0.1, y13), (p13[0] - 0.25, y13), ge], 0.2)
    k.via("/PACK-", *ge)
    # the north row's east end, by C19: BATP (pin 18) to a via just north of it, clear of BTST2's straight run up to
    # C19; ILIM_HIZ (pin 17) up and east over TS's corner pad to a via; TS (16) east to a via under J1's courtyard
    p18, p17, p16 = box(pad(b, "U7", "18")), box(pad(b, "U7", "17")), box(pad(b, "U7", "16"))
    x18, x17, top = (p18[0] + p18[2]) / 2, (p17[0] + p17[2]) / 2, p17[1]
    vbp = (x18 + 0.15, top - 0.75)
    vil = (p16[2] - 0.1, top - 0.6)
    vts = (p16[2] + PAD_VIA + VIA_D / 2 + 0.05, (p16[1] + p16[3]) / 2)
    k.path("/BATP", pcbnew.F_Cu, [(x18, top + 0.1), vbp], 0.15)
    k.path("/ILIM_HIZ", pcbnew.F_Cu, [(x17, top + 0.1), (x17, top - 0.25), (vil[0], top - 0.25), vil], 0.15)
    k.path("/TS", pcbnew.F_Cu, [(p16[2] - 0.1, vts[1]), vts], 0.15)
    for net, at in (("/BATP", vbp), ("/ILIM_HIZ", vil), ("/TS", vts)):
        k.via(net, *at)
    # J1's CC2 (B5) and its north VBUS pads (A9/B4) both need the gap between U7 and J1, past the unused SBU1 (A8):
    # a via just west of each
    b5, a9 = box(pad(b, "J1", "B5")), box(pad(b, "J1", "A9"))
    vcc = (b5[0] - 0.67, (b5[1] + b5[3]) / 2 + 0.25)
    vvb = (a9[0] - PAD_VIA - VIA_D / 2 - 0.07, (a9[1] + a9[3]) / 2)
    k.track("/CC2", pcbnew.F_Cu, b5[0] + 0.1, (b5[1] + b5[3]) / 2, *vcc, 0.15)
    k.track("/VBUS", pcbnew.F_Cu, a9[0] + 0.1, vvb[1], *vvb, 0.3)
    k.via("/CC2", *vcc)
    k.via("/VBUS", *vvb)
    # C19's boot loop, all laid here (the router ran short of lanes for it in every order): BTST2 straight up from pin
    # 19 to C19's BTST2 pad over it, and SW2 from a via just east of C19's SW2 pad on In2 west and down to SW2's via
    p19, b19, c19 = box(pad(b, "U7", "19")), box(pad(b, "C19", net="/BTST2")), box(pad(b, "C19", net="/SW2"))
    k.track("/BTST2", pcbnew.F_Cu, (p19[0] + p19[2]) / 2, p19[1] + 0.1, (p19[0] + p19[2]) / 2, b19[3] - 0.1, 0.15)
    vs = (c19[2] + PAD_VIA + VIA_D / 2 + 0.05, (c19[1] + c19[3]) / 2)
    k.track("/SW2", pcbnew.F_Cu, c19[2] - 0.1, vs[1], *vs, 0.3)
    sw2_run = [vs, (sv[0] + (sv[1] - vs[1]), vs[1]), sv]  # west, then 45 degrees down (straight would hit BATP's via)
    k.path("/SW2", pcbnew.In2_Cu, sw2_run, 0.4)
    k.via("/SW2", *vs)
    # ILIM_HIZ (a high-impedance node that sets the input current clamp) stays 1 mm off that run on B.Cu
    k.router_keepout(["/ILIM_HIZ"], (pcbnew.B_Cu,), [seg_poly(a, c, 1.0) for a, c in zip(sw2_run, sw2_run[1:])])
    # BTST1 (pin 4, south side) to C18 under L2: down to a small via beside the pin (C22 sits west of the pins for
    # it), B.Cu west under the PMID strip, up by a via beside C18's BTST1 pad
    p4, bt = box(pad(b, "U7", "4")), box(pad(b, "C18", net="/BTST1"))
    vp = ((p4[0] + p4[2]) / 2 - 0.13, p4[3] + PAD_VIA + SMALL_VIA[0] / 2 + 0.05)
    vc = (bt[0] - PAD_VIA - SMALL_VIA[0] / 2 - 0.05, (bt[1] + bt[3]) / 2)
    k.path("/BTST1", pcbnew.F_Cu, [((p4[0] + p4[2]) / 2, p4[3] - 0.1), vp], 0.15)
    k.path("/BTST1", pcbnew.B_Cu, [vp, (vp[0] - abs(vp[1] - vc[1]), vc[1]), vc], 0.15)
    k.track("/BTST1", pcbnew.F_Cu, *vc, bt[0] + 0.1, vc[1], 0.15)
    k.via("/BTST1", *vp, SMALL_VIA)
    k.via("/BTST1", *vc, SMALL_VIA)
    # pins to their caps: VBUS (C22), BAT (C33), REGN (C35): over the pins, and down to the cap's pad only as wide as
    # both
    for name, net, pins, cap in (("F VBUS", "/VBUS", ("2", "3"), "C22"), ("F BAT", "/PACK+", ("22", "23"), "C33"),
                                 ("F REGN", "/REGN", ("5",), "C35")):
        px = [box(pad(b, "U7", n)) for n in pins]
        cb = box(pad(b, cap, net=net))
        x0, x1, y0, y1 = min(p[0] for p in px), max(p[2] for p in px), min(p[1] for p in px), max(p[3] for p in px)
        k.pour(name, net, [(x0, y0, x1, y1), (max(x0, cb[0]), min(y0, cb[1]), min(x1, cb[2]), max(y1, cb[3]))] +
               (vbus if net == "/VBUS" else []))
    return len(vias) + 13


def sdrv_cap(b, k):
    """C36 (SDRV's 1 nF) is packed wherever there's room, and its SDRV pad got walled in there in every route order
    tried: a 0.15 mm stub out of the pad, 0.6 mm past it, gives the router a way in. Out of the pad's toe if that
    clears every other net's copper, else down or up. Returns False if none does."""
    clr = Clearance(b)
    f = next(f for f in b.GetFootprints() if f.GetReference() == "C36")
    sd = box(pad(b, "C36", net="/SDRV"))
    c = f.GetPosition()
    cx, cy = c.x / MM - OX, c.y / MM - OY
    px, py = (sd[0] + sd[2]) / 2, (sd[1] + sd[3]) / 2
    toe = (sd[2] + 0.6, py) if px > cx else (sd[0] - 0.6, py)
    if abs(py - cy) > abs(px - cx):
        toe = (px, sd[3] + 0.6) if py > cy else (px, sd[1] - 0.6)
    for ex, ey in (toe, (px, sd[3] + 0.6), (px, sd[1] - 0.6)):
        start = math.hypot(sd[2] - sd[0], sd[3] - sd[1]) / 2
        if 0.3 < ex < W - 0.3 and 0.3 < ey < H - 0.3 and clr.seg_ok("/SDRV", px, py, ex, ey, 0.075, start=start):
            k.track("/SDRV", pcbnew.F_Cu, px, py, ex, ey, 0.15)
            return True
    return False


KELVIN_W = 0.2


def kelvin(b):
    """R66's Kelvin taps: a via inside each pad's inner edge, B.Cu to beside R68's BAT_N pad and R69's PROT_SNS pad.
    BAT_N's line runs up the west column and ends on the north resistor (R68), PROT_SNS's up the east one to R69, so
    they don't cross. Fills stay off BAT_N's line (rule areas) and R68's pad takes no zone, so the only BAT_N copper it
    meets is R66's pad; on F.Cu both taps' vias sit in notches in R66's pours, joined to the pads by their stubs."""
    k = Builder(b, "kelvin")
    r1, r2 = box(pad(b, "R66", net="/BAT_N")), box(pad(b, "R66", net="/PROT_SNS"))
    ym = (r1[1] + r1[3]) / 2
    off = PAD_VIA + VIA_D / 2
    vb, vs = (r1[2] + off, ym), (r2[0] - off, ym)
    p68, p69 = pad(b, "R68", net="/BAT_N"), pad(b, "R69", net="/PROT_SNS")
    p68.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_NONE)
    f68, f69 = box(p68), box(p69)
    tb, ts = (f68[0] - off, (f68[1] + f68[3]) / 2), (f69[0] - off, (f69[1] + f69[3]) / 2)
    assert tb[1] < ts[1], "R68 must sit north of R69"
    cb, cs = tb[0] - 1.3, tb[0] - 0.8                    # the two columns
    jb = r1[1] - 0.4                                     # BAT_N's run east, north of R66
    bat = [vb, (vb[0], jb), (cb, jb), (cb, tb[1]), tb]
    sns = [vs, (cs, vs[1]), (cs, ts[1]), ts]
    for net, pts in (("/BAT_N", bat), ("/PROT_SNS", sns)):
        k.path(net, pcbnew.B_Cu, pts, KELVIN_W)
        k.via(net, *pts[0])
        k.via(net, *pts[-1])
    k.track("/BAT_N", pcbnew.F_Cu, r1[2], ym, *vb, KELVIN_W)
    k.track("/PROT_SNS", pcbnew.F_Cu, r2[0], ym, *vs, KELVIN_W)
    k.track("/BAT_N", pcbnew.F_Cu, *tb, f68[0] + 0.1, tb[1], KELVIN_W)
    k.track("/PROT_SNS", pcbnew.F_Cu, *ts, f69[0] + 0.1, ts[1], KELVIN_W)
    inner = (pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    h = 0.6
    k.nofill("Kelvin R66 BAT_N", inner, [(vb[0] - 1.0, vb[1] - 1.0, vb[0] + 1.0, vb[1] + 1.0)])
    # on F.Cu each tap's via sits clear of R66's pours too, joined to its pad only by the stub from the inner edge
    k.nofill("Kelvin R66 taps", (pcbnew.F_Cu,), [(r1[2] + 0.05, vb[1] - h, vb[0] + h, vb[1] + h),
                                                 (vs[0] - h, vs[1] - h, r2[0] - 0.05, vs[1] + h)])
    k.nofill("Kelvin R68", (pcbnew.F_Cu,) + inner, [(tb[0] - h, tb[1] - h, f68[2] + 0.3, tb[1] + h),
                                                    (f68[0] - 0.3, f68[1] - 0.3, f68[2] + 0.3, f68[3] + 0.3)])
    c = KELVIN_W / 2 + 0.25
    k.nofill("Kelvin BAT_N line", (pcbnew.B_Cu,), [(min(ax, bx) - c, min(ay, by) - c, max(ax, bx) + c, max(ay, by) + c)
                                                    for (ax, ay), (bx, by) in zip(bat, bat[1:])])


def clear(tracks):
    """Remove the group's items and every zone (and with tracks, every track and via), save, and start this script
    again in a fresh process: pcbnew's lists go stale after removals."""
    b = pcbnew.LoadBoard(str(PCB))
    grp = next((g for g in b.Groups() if g.GetName() == GROUP), None)
    doomed = list(b.Zones()) + (list(grp.GetItems()) if grp else []) + (list(b.GetTracks()) if tracks else [])
    for item in doomed:
        b.Remove(item)
    b.Save(str(PCB))
    os.execv(sys.executable, [sys.executable, __file__, sys.argv[1], "--cleared"] + PCB_ARG)


PLANES = {"/PACK-": PACK_N_AREA, "/BAT_N": BAT_N_AREA, "/PACK+": PACK_P_AREA}   # net: where its plane is
STUB = 0.4                      # Plane class width; narrower at fine-pitch pins


INWARD = {"U7"}                 # these parts' plane pins fan out under their bodies only


def band_ok(net, x, y):
    """With BAND_CLEAR, only PACK+ may put a via in the PACK+ band (fanout's fallback, for a pad inside the band with no
    other way to its plane, still may)."""
    return not BAND_CLEAR or net == "/PACK+" or poly_dist(x, y, PACK_P_AREA) >= VIA_D / 2 + 0.2


def fanout(b, k):
    """A short stub and a via from every SMD pad on a plane net to its plane, unless a pack-path pour takes the pad.
    Vias keep 0.2 mm from every other net's copper and 0.5 mm hole to hole; they may sit under a part's body."""
    clr = Clearance(b)
    clr.crt = []                                # a tented via under a part's body is fine; copper clearance rules
    done, failed, joined = 0, [], set()          # joined: pads that reach their plane
    for f in b.GetFootprints():
        for p in f.Pads():
            net = p.GetNetname()
            if net not in PLANES or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not p.IsOnLayer(pcbnew.F_Cu) or \
                    p.GetLocalZoneConnection() == pcbnew.ZONE_CONNECTION_NONE:       # R68's Kelvin pad
                continue
            c = p.GetPosition()
            px, py = c.x / MM - OX, c.y / MM - OY
            if net in PATH and inside(px, py, PATH[net]) or any(
                    t.GetNetname() == net and p.HitTest(t.GetStart()) for t in k.grp.GetItems()
                    if t.Type() == pcbnew.PCB_TRACE_T):      # a setup stub already takes it to a via
                joined.add(p.m_Uuid.AsString())
                continue
            if net == "/PACK+" and poly_dist(px, py, PLANES[net]) > FAN_REACH:
                continue
            hx, hy = p.GetBoundingBox().GetWidth() / MM / 2, p.GetBoundingBox().GetHeight() / MM / 2
            stub = min(STUB, 2 * min(hx, hy))       # no wider than a fine-pitch pin
            best = None
            fc = f.GetPosition()
            inx, iny = fc.x / MM - OX - px, fc.y / MM - OY - py   # toward the part's centre
            for i in range(32):
                a = i * math.pi / 16
                dx, dy = math.cos(a), math.sin(a)
                if f.GetReference() in INWARD and dx * inx + dy * iny <= 0:
                    continue
                edge = min(hx / abs(dx) if abs(dx) > 1e-9 else 1e9, hy / abs(dy) if abs(dy) > 1e-9 else 1e9)
                for step in range(26):
                    d = edge + 0.5 + step * 0.1
                    x, y = px + dx * d, py + dy * d
                    if best and d >= best[0]:
                        break
                    if not (0.6 < x < W - 0.6 and 0.6 < y < H - 0.6) or not inside(x, y, PLANES[net]) or \
                            not band_ok(net, x, y):
                        continue
                    if clr.ok(net, x, y) and clr.seg_ok(net, px, py, x, y, stub / 2, start=edge):
                        best = (d, x, y)
                        break
            if best is None:
                failed.append((f, p))
                continue
            _, x, y = best
            clr.add_track(k.track(net, pcbnew.F_Cu, px, py, x, y, stub))
            clr.add_track(k.via(net, x, y))
            joined.add(p.m_Uuid.AsString())
            done += 1
    # the rest: a track to the nearest copper of the same net on F.Cu that reaches the plane (a neighbouring pin that
    # has its fan-out, a via), or to a new via further out
    left = []
    for f, p in failed:
        net, c = p.GetNetname(), p.GetPosition()
        px, py = c.x / MM - OX, c.y / MM - OY
        hx, hy = p.GetBoundingBox().GetWidth() / MM / 2, p.GetBoundingBox().GetHeight() / MM / 2
        stub = min(STUB, 2 * min(hx, hy))
        targets = [(q.GetPosition().x / MM - OX, q.GetPosition().y / MM - OY) for g in b.GetFootprints()
                   for q in g.Pads() if q.GetNetname() == net and q.IsOnLayer(pcbnew.F_Cu) and q != p and
                   (q.m_Uuid.AsString() in joined or q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)]
        targets += [(t.GetEnd().x / MM - OX, t.GetEnd().y / MM - OY) for t in k.grp.GetItems()
                    if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == net]
        targets = [(x, y, False) for x, y in targets if 0.05 < math.hypot(x - px, y - py) < 4.0]
        targets += [(px + i * 0.1, py + j * 0.1, True) for i in range(-45, 46, 2) for j in range(-45, 46, 2)
                    if inside(px + i * 0.1, py + j * 0.1, PLANES[net]) and clr.ok(net, px + i * 0.1, py + j * 0.1)]
        best = None                             # to same-net copper, or to a new via: straight, or one bend
        for x, y, new_via in targets:
            if clr.seg_ok(net, px, py, x, y, stub / 2, start=min(hx, hy)):
                L = math.hypot(x - px, y - py)
                if best is None or L < best[0]:
                    best = (L, [(px, py), (x, y)], new_via)
            for i in range(16):
                a = i * math.pi / 8
                dx, dy = math.cos(a), math.sin(a)
                edge = min(hx / abs(dx) if abs(dx) > 1e-9 else 1e9, hy / abs(dy) if abs(dy) > 1e-9 else 1e9)
                for d in (0.4, 0.7, 1.0, 1.4):
                    mx, my = px + dx * (edge + d), py + dy * (edge + d)
                    L = edge + d + math.hypot(x - mx, y - my)
                    if best and L >= best[0]:
                        continue
                    if clr.seg_ok(net, px, py, mx, my, stub / 2, start=edge) and \
                            clr.seg_ok(net, mx, my, x, y, stub / 2):
                        best = (L, [(px, py), (mx, my), (x, y)], new_via)
        if best is None:
            left.append(f"{f.GetReference()}.{p.GetNumber()}")
            continue
        pts = best[1]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            clr.add_track(k.track(net, pcbnew.F_Cu, ax, ay, bx, by, stub))
        if best[2]:
            clr.add_track(k.via(net, *pts[-1]))
        joined.add(p.m_Uuid.AsString())
        done += 1
    return done, left


def setup():
    if "--cleared" not in sys.argv:
        net_classes()
        clear(tracks=True)                     # the router's previous result goes too
    b = pcbnew.LoadBoard(str(PCB))
    b.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    b.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)
    k = Builder(b)
    k.zone("In1 BAT_N", "/BAT_N", pcbnew.In1_Cu, BAT_N_AREA, 1, solid=False)
    k.zone("In1 PACK-", "/PACK-", pcbnew.In1_Cu, PACK_N_AREA, 0, solid=False)
    k.zone("In2 PACK+", "/PACK+", pcbnew.In2_Cu, PACK_P_AREA, 5, solid=BAND_CLEAR)
    k.keepout("In2 PACK+ corridor" + (" no vias" if BAND_CLEAR else ""), pcbnew.In2_Cu, PACK_P_AREA)
    if BAND_CLEAR:                                       # tools/grid_router.py reads "no vias" off the name
        k.keepout("B PACK+ corridor no vias", pcbnew.B_Cu, PACK_P_AREA)
        k.zone("B PROT_FET_D", "/PROT_FET_D", pcbnew.B_Cu, PATH["/PROT_FET_D"], 10)
    for x, y in DRAIN_VIAS:
        k.via("/PROT_FET_D", x, y)
    for net, pts in PATH.items():
        k.zone(f"F {net[1:]} path", net, pcbnew.F_Cu, pts, 10)
    for x, y in FUSE_VIAS:
        k.via("/PACK+", x, y)
    stage = power_stage(b, k)
    if packcfg.BOARD == "pack":
        kelvin(b)
    if not sdrv_cap(b, k):
        print("no room for a stub out of C36's SDRV pad")
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())               # fanout checks against the pours' fills
    done, failed = fanout(b, k)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(str(PCB))
    print(f"setup: {len(list(b.Zones()))} zones, {len(FUSE_VIAS)} fuse vias, {stage} power stage vias, "
          f"{done} plane fan-outs -> {PCB}")
    if failed:
        print("no room to fan out:", " ".join(failed))


ROUTE_ORDER = ["/STAT", "/CHG_SYS", "/BTST1", "/PROG", "/USB_DM", "/USB_DP", "/CHG_SDA"]
ROUTE_ORDER = next((a[8:].split(",") for a in sys.argv if a.startswith("--order=")), ROUTE_ORDER)   # route --order=
ROUTE_FIX = None                                  # (rip these, then route in this order); route --fix=NET,..:NET,..
ROUTE_FIX = next(([n.split(",") for n in a[6:].split(":")] for a in sys.argv if a.startswith("--fix=")), ROUTE_FIX)


def route():
    kpy, cli = sys.executable, shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
    gr = str(ROOT / "tools/grid_router.py")
    with tempfile.TemporaryDirectory() as d:
        def drc():
            subprocess.run([cli, "pcb", "drc", "--format", "json", "-o", f"{d}/drc.json", str(PCB)], capture_output=True)
            return json.loads(Path(f"{d}/drc.json").read_text())
        pack = [packcfg.FLAG, f"--pcb={PCB}"]
        subprocess.run([kpy, gr, "--rip=*"] + pack, check=True)                 # then DRC lists every pair
        drc()
        subprocess.run([kpy, gr, f"{d}/drc.json", "--first=" + ",".join(ROUTE_ORDER)] + pack, check=True)
        if ROUTE_FIX:
            subprocess.run([kpy, gr, "--rip=" + ",".join(ROUTE_FIX[0])] + pack, check=True)
            drc()
            subprocess.run([kpy, gr, f"{d}/drc.json", "--first=" + ",".join(ROUTE_FIX[1])] + pack, check=True)
        left = drc()["unconnected_items"]
    print(f"route: {len(left)} unconnected")


CURRENT = {"/VBUS", "/PACK+"}  # about 1 A each: the charger's input (ILIM_HIZ caps it at 1.13 A) and charge current
INNER_W = (0.6, 0.5)            # their widths to try on In2 first: JLC's inner copper is 0.5 oz


def widen(b):
    """The router's Charger, Power and Plane tracks to WIDE (VBUS and PACK+ on In2 to INNER_W first), then a DRC run:
    every widened segment that DRC flags steps down to its next width, or back to its own, until DRC flags none.
    Returns how many ended up wider."""
    own, steps = {}, {}
    for t in b.GetTracks():
        grp = t.GetParentGroup()
        if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() in CHARGER + POWER + PLANE and \
                grp and grp.GetName() == "autoroute":
            inner = t.GetNetname() in CURRENT and t.GetLayer() == pcbnew.In2_Cu
            ws = [int(w * MM) for w in (INNER_W if inner else ()) + (WIDE,) if w * MM > t.GetWidth() + 1]
            if ws:
                own[t.m_Uuid.AsString()], steps[t.m_Uuid.AsString()] = t.GetWidth(), ws
                t.SetWidth(ws.pop(0))
    cli = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
    live = set(own)                                      # tracks still on a widened width DRC may flag
    with tempfile.TemporaryDirectory() as d:
        while True:
            b.Save(str(PCB))
            subprocess.run([cli, "pcb", "drc", "--format", "json", "-o", f"{d}/drc.json", str(PCB)],
                           capture_output=True)
            drc = json.loads(Path(f"{d}/drc.json").read_text())
            bad = {i["uuid"] for v in drc["violations"] if v["severity"] == "error" for i in v["items"]} & live
            if not bad:
                return sum(1 for t in b.GetTracks() if t.m_Uuid.AsString() in own and
                           t.GetWidth() > own[t.m_Uuid.AsString()])
            for t in b.GetTracks():
                u = t.m_Uuid.AsString()
                if u in bad:
                    if steps[u]:
                        t.SetWidth(steps[u].pop(0))
                    else:
                        t.SetWidth(own[u])
                        live.discard(u)


FINISH = "route_pack_finish"
STITCH = 2.5                    # stitching via pitch


class Clearance:
    """Where a new through via fits: 0.2 mm copper to every other net (pads, tracks, vias and F.Cu zone fills), 0.5 mm
    hole to hole, PAD_VIA from every SMD pad, outside courtyards."""
    def __init__(self, b, skip_courtyard=()):
        self.copper, self.holes, self.crt, self.smd = [], [], [], []
        for f in b.GetFootprints():
            if f.GetReference() not in skip_courtyard:
                f.BuildCourtyardCaches()
                bb = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd).BBox()
                self.crt.append((bb.GetLeft() / MM - OX, bb.GetTop() / MM - OY, bb.GetRight() / MM - OX,
                                 bb.GetBottom() / MM - OY))
            grow = 0.4 if f.GetReference().startswith("FID") else 0.0   # fiducials keep 0.6 mm clear
            for p in f.Pads():
                bb = p.GetBoundingBox()
                self.copper.append(("box", p.GetNetname(), (bb.GetLeft() / MM - OX - grow, bb.GetTop() / MM - OY - grow,
                                                            bb.GetRight() / MM - OX + grow,
                                                            bb.GetBottom() / MM - OY + grow)))
                if p.GetDrillSize().x:
                    c = p.GetPosition()
                    self.holes.append((c.x / MM - OX, c.y / MM - OY, p.GetDrillSize().x / MM / 2))
                elif p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                    self.smd.append(self.copper[-1][2])
        for t in b.GetTracks():
            self.add_track(t)
        for z in b.Zones():
            if z.GetIsRuleArea() or not z.IsOnLayer(pcbnew.F_Cu):
                continue
            fp = z.GetFilledPolysList(pcbnew.F_Cu)
            for i in range(fp.OutlineCount()):
                ol = fp.Outline(i)
                pts = [(ol.CPoint(j).x / MM - OX, ol.CPoint(j).y / MM - OY) for j in range(ol.PointCount())]
                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                self.copper.append(("zone", z.GetNetname(), (pts, (min(xs), min(ys), max(xs), max(ys)))))

    def add_track(self, t):
        a, c = t.GetStart(), t.GetEnd()
        seg = (a.x / MM - OX, a.y / MM - OY, c.x / MM - OX, c.y / MM - OY, t.GetWidth() / MM / 2)
        self.copper.append(("seg", t.GetNetname(), seg))
        if t.Type() == pcbnew.PCB_VIA_T:
            self.holes.append((seg[0], seg[1], t.GetDrillValue() / MM / 2))

    def ok(self, net, x, y, courtyards=True):
        r = VIA_D / 2
        if courtyards and any(x0 - r < x < x1 + r and y0 - r < y < y1 + r for x0, y0, x1, y1 in self.crt):
            return False
        if any(math.hypot(x - hx, y - hy) < hr + VIA_DRILL / 2 + 0.5 for hx, hy, hr in self.holes):
            return False
        if any(math.hypot(max(x0 - x, 0, x - x1), max(y0 - y, 0, y - y1)) < r + PAD_VIA - 1e-4
               for x0, y0, x1, y1 in self.smd):
            return False
        return self.copper_ok(net, x, y, r)

    def seg_ok(self, net, ax, ay, bx, by, hw, start=0.0):
        """A track from a to b clears other nets (checked from `start` mm along it, past its own pad)."""
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(L / 0.05))
        return all(self.copper_ok(net, ax + (bx - ax) * i / n, ay + (by - ay) * i / n, hw)
                   for i in range(n + 1) if L * i / n >= start)

    def copper_ok(self, net, x, y, r):
        for kind, n, g in self.copper:
            if n == net:
                continue
            if kind == "box":
                x0, y0, x1, y1 = g
                d = math.hypot(max(x0 - x, 0, x - x1), max(y0 - y, 0, y - y1))
            elif kind == "zone":
                pts, (x0, y0, x1, y1) = g
                if x < x0 - 1 or x > x1 + 1 or y < y0 - 1 or y > y1 + 1:
                    continue
                d = poly_dist(x, y, pts)
            else:
                ax, ay, bx, by, hw = g
                vx, vy = bx - ax, by - ay
                L2 = vx * vx + vy * vy
                u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
                d = math.hypot(x - ax - u * vx, y - ay - u * vy) - hw
            if d < r + 0.2 - 1e-4:
                return False
        return True


def poly_dist(x, y, pts):
    if inside(x, y, pts):
        return 0.0
    d = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        vx, vy = bx - ax, by - ay
        u = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy)))
        d.append(math.hypot(x - ax - u * vx, y - ay - u * vy))
    return min(d)


def inside(x, y, pts):
    c = False
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            c = not c
    return c


def drop_unused_vias(b):
    """Remove setup's vias that routing left dangling (an escape the router met on its own layer, a boot cap's SW via):
    every track end inside such a via moves to its centre, so the tracks still meet, then a setup stub that nothing
    else meets there goes too; and the router's dangling slivers under 0.1 mm. Returns how many vias went."""
    cli = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([cli, "pcb", "drc", "--refill-zones", "--format", "json", "-o", f"{d}/drc.json", str(PCB)],
                       capture_output=True)
        drc = json.loads(Path(f"{d}/drc.json").read_text())
    dangling = {i["uuid"] for v in drc["violations"] if v["type"] == "via_dangling" for i in v["items"]}
    vias = [t for t in b.GetTracks() if t.m_Uuid.AsString() in dangling and t.GetParentGroup() and
            t.GetParentGroup().GetName() == GROUP]
    tracks = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    doomed = []
    for via in vias:
        c, r = via.GetPosition(), via.GetWidth(pcbnew.F_Cu) / 2
        at = []
        for t in tracks:
            for end, move in ((t.GetStart(), t.SetStart), (t.GetEnd(), t.SetEnd)):
                if (end.x - c.x) ** 2 + (end.y - c.y) ** 2 <= r * r:
                    move(c)
                    at.append(t)
        if len(at) == 1 and at[0].GetParentGroup() and at[0].GetParentGroup().GetName() == GROUP:
            doomed.append(at[0])                         # a stub out to nothing
        doomed.append(via)
    stubs = {i["uuid"] for v in drc["violations"] if v["type"] == "track_dangling" for i in v["items"]}
    doomed += [t for t in tracks if t.m_Uuid.AsString() in stubs and t.GetLength() < 0.1 * MM and
               t.GetParentGroup() and t.GetParentGroup().GetName() == "autoroute"]   # the router's slivers
    for item in doomed:
        if item.GetParentGroup():                        # leave no group pointing at a removed item
            item.GetParentGroup().RemoveItem(item)
        b.Remove(item)
    return len(vias)


def snap_to_vias(b):
    """The router's track ends that land inside one of setup's vias but off its centre (the router meeting an escape
    via) move to the centre. Returns (track, setter, old end) for each move, so DRC can undo it."""
    def grp(t, name):
        return t.GetParentGroup() is not None and t.GetParentGroup().GetName() == name
    vias = [(t.GetPosition(), t.GetWidth(pcbnew.F_Cu) / 2) for t in b.GetTracks()
            if t.Type() == pcbnew.PCB_VIA_T and grp(t, GROUP)]
    moved = []
    for t in b.GetTracks():
        if t.Type() != pcbnew.PCB_TRACE_T or not grp(t, "autoroute"):
            continue
        for end, move in ((t.GetStart(), t.SetStart), (t.GetEnd(), t.SetEnd)):
            for c, r in vias:
                d2 = (end.x - c.x) ** 2 + (end.y - c.y) ** 2
                if 0 < d2 <= r * r:
                    move(c)
                    moved.append((t, move, end))
                    break
    return moved


TWIN = ("/VBUS",)               # nets whose routed vias get a second via beside them (the charger's ~1 A input)
TWIN_AT = 0.85                  # mm along the via's inner or back layer track


def twin_vias(b):
    """A second via for each routed via on a TWIN net: TWIN_AT along its In2 or B.Cu track, tied back to the first by
    an F.Cu track. Returns the (via, track) pairs added; DRC decides which stay."""
    grp = next((g for g in b.Groups() if g.GetName() == "autoroute"), None)
    if grp is None:
        return []
    tracks = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    added = []
    for via in [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() in TWIN and
                t.GetParentGroup() and t.GetParentGroup().GetName() == "autoroute"]:
        c = via.GetPosition()
        for t in tracks:
            if t.GetNetname() != via.GetNetname() or t.GetLayer() == pcbnew.F_Cu:
                continue
            far = t.GetEnd() if t.GetStart() == c else t.GetStart() if t.GetEnd() == c else None
            if far is None or t.GetLength() < (TWIN_AT + 0.3) * MM:
                continue
            u = TWIN_AT * MM / t.GetLength()
            p = pcbnew.VECTOR2I(int(c.x + (far.x - c.x) * u), int(c.y + (far.y - c.y) * u))
            nv = pcbnew.PCB_VIA(b)
            nv.SetPosition(p)
            nv.SetWidth(via.GetWidth(pcbnew.F_Cu))
            nv.SetDrill(via.GetDrillValue())
            nv.SetNet(via.GetNet())
            st = pcbnew.PCB_TRACK(b)
            st.SetStart(c)
            st.SetEnd(p)
            st.SetWidth(int(0.3 * MM))
            st.SetLayer(pcbnew.F_Cu)
            st.SetNet(via.GetNet())
            for item in (nv, st):
                b.Add(item)
                grp.AddItem(item)
            added.append((nv, st))
            break
    return added


def drc_errors(b):
    """Saves the board and returns the uuids of every item in a DRC error (zones refilled for the check only)."""
    b.Save(str(PCB))
    cli = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([cli, "pcb", "drc", "--refill-zones", "--format", "json", "-o", f"{d}/drc.json", str(PCB)],
                       capture_output=True)
        drc = json.loads(Path(f"{d}/drc.json").read_text())
    return {i["uuid"] for v in drc["violations"] if v["severity"] == "error" for i in v["items"]}


def restart(stage):
    """pcbnew's lists go stale after removals (and a second LoadBoard in the same process can come back broken), so
    each finish stage that removes items saves and runs the next one in a fresh process."""
    os.execv(sys.executable, [sys.executable, __file__, "finish", stage] + PCB_ARG)


def stitch_back_pads(b, k, clr, fills):
    """A via beside each SMD pad on a ground net that is on B.Cu only (the 2S pack's TH2, until R79 replaced it): fanout only reaches F.Cu pads,
    and a B.Cu fill island that holds just such a pad is cut off from In1. The via sits in that fill, clear of tracks
    and pads (under the part's own body is fine). Returns how many went in."""
    n = 0
    for f in b.GetFootprints():
        for p in f.Pads():
            net = p.GetNetname()
            if net not in ("/BAT_N", "/PACK-") or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or p.IsOnLayer(pcbnew.F_Cu):
                continue
            c = p.GetPosition()
            px, py = c.x / MM - OX, c.y / MM - OY
            area = BAT_N_AREA if net == "/BAT_N" else PACK_N_AREA
            spots = [(px + r * math.cos(i * math.pi / 12), py + r * math.sin(i * math.pi / 12))
                     for r in (0.9, 1.2, 1.5, 1.8, 2.2, 2.6) for i in range(24)]
            for x, y in spots:
                if 0.6 < x < W - 0.6 and 0.6 < y < H - 0.6 and inside(x, y, area) and \
                        fills[(pcbnew.B_Cu, net)].HitTestFilledArea(pcbnew.B_Cu, v(x, y)) and \
                        clr.ok(net, x, y, courtyards=False) and band_ok(net, x, y):
                    clr.add_track(k.via(net, x, y))
                    n += 1
                    break
    return n


def finish():
    stage = next((a for a in sys.argv if a in ("--dropping", "--snapping", "--cleared")), None)
    if stage is None:                                    # last run's fills and stitching go
        b = pcbnew.LoadBoard(str(PCB))
        grp = next((g for g in b.Groups() if g.GetName() == FINISH), None)
        for item in [z for z in b.Zones() if z.GetZoneName().startswith("fill ")] + \
                (list(grp.GetItems()) if grp else []):
            if item.GetParentGroup():
                item.GetParentGroup().RemoveItem(item)
            b.Remove(item)
        b.Save(str(PCB))
        restart("--dropping")
    if stage == "--dropping":
        b = pcbnew.LoadBoard(str(PCB))
        print(f"finish: removed {drop_unused_vias(b)} unused setup vias", flush=True)
        b.Save(str(PCB))
        restart("--snapping")
    if stage == "--snapping":
        b = pcbnew.LoadBoard(str(PCB))
        snapped = snap_to_vias(b)
        twins = twin_vias(b)
        bad = drc_errors(b)                              # what DRC flags goes back
        for t, move, old in snapped:
            if t.m_Uuid.AsString() in bad:
                move(old)
        kept = 0
        for nv, st in twins:
            if {nv.m_Uuid.AsString(), st.m_Uuid.AsString()} & bad:
                for item in (nv, st):
                    item.GetParentGroup().RemoveItem(item)
                    b.Remove(item)
            else:
                kept += 1
        b.Save(str(PCB))
        print(f"finish: {sum(1 for t, _, _ in snapped if t.m_Uuid.AsString() not in bad)} track ends snapped to via "
              f"centres, {kept} of {len(twins)} second vias kept on {', '.join(TWIN)}", flush=True)
        restart("--cleared")
    b = pcbnew.LoadBoard(str(PCB))
    wide = widen(b)
    k = Builder(b, FINISH)
    for layer, side in ((pcbnew.F_Cu, "F"), (pcbnew.In2_Cu, "In2"), (pcbnew.B_Cu, "B")):
        k.zone(f"fill {side} BAT_N", "/BAT_N", layer, BAT_N_AREA, 1, solid=False)
        k.zone(f"fill {side} PACK-", "/PACK-", layer, PACK_N_AREA, 1, solid=False)
    k.zone("fill B PACK+", "/PACK+", pcbnew.B_Cu, PACK_P_AREA, 2, solid=BAND_CLEAR)   # beside In2, where routing left room

    clr = Clearance(b)
    # stitching: F, In1 and B ground tied together on a grid, where both outer fills reach
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    fills = {(z.GetLayer(), z.GetNetname()): z for z in b.Zones() if z.GetZoneName().startswith("fill ")}
    stitched = 0
    y = 0.9
    while y < H - 0.8:
        x = 0.9
        while x < W - 0.8:
            net = "/BAT_N" if inside(x, y, BAT_N_AREA) else "/PACK-"
            p = v(x, y)
            if all(fills[(L, net)].HitTestFilledArea(L, p) for L in (pcbnew.F_Cu, pcbnew.B_Cu)) and clr.ok(net, x, y) \
                    and band_ok(net, x, y):
                clr.add_track(k.via(net, x, y))
                stitched += 1
            x += STITCH
        y += STITCH
    stitched += stitch_back_pads(b, k, clr, fills)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(str(PCB))
    print(f"finish: {wide} tracks widened to {WIDE} mm, {stitched} stitching vias")


if __name__ == "__main__":
    {"setup": setup, "route": route, "finish": finish}[sys.argv[1]]()
