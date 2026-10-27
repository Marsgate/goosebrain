"""Grid router for the brain's remaining signal connections (kicad/thegoose.kicad_pcb, edited in place).

Run with KiCad's Python after tools/route_recipe.py and a zone fill, on KiCad's DRC report in JSON:
    kicad-cli pcb drc --format json --schematic-parity -o drc.json kicad/thegoose.kicad_pcb
    .../python3 tools/grid_router.py drc.json [--clear] [--first=NET,NET...] [--board=pack] [--pcb=FILE]
    .../python3 tools/grid_router.py --rip=NET,NET... [--board=pack] [--pcb=FILE]

--rip removes the router's copper on those nets (the "autoroute" group; --rip=* all of it) and exits: run DRC again, then route them
afterwards in a new order (the router has no rip-up of its own).

--board=pack routes the 3S pack board (kicad-pack/goosepack.kicad_pcb) instead, after tools/route_pack.py setup: its
ground planes (BAT_N, PACK-) are already fanned out and skipped (PACK+ is routed out to the charger), every F.Cu/In2.Cu/B.Cu zone is an obstacle, the
In2 PACK+ corridor's rule area keeps tracks out, a rule area named "router keepout NET,NET..." (which allows everything,
so DRC ignores it) keeps those nets' tracks and vias out on its layers, each net routes at its class width (Default 0.15 mm, Charger
0.3 mm, Power 0.4 mm), and no via lands within PAD_VIA of an SMD pad of any net (no vias in pads). None of the
brain's pockets or In3 power costs apply.

Freerouting 2.1 did poorly here: it ignored keepouts on inner layers, hugged pin rows and then couldn't rip up, and its
results swung between 12 and 63 unrouted on identical runs (see ROUTING_LOG.md). This router is small and
deterministic:

- three routing layers on a 0.05 mm grid: F.Cu, In2.Cu and B.Cu. In1 and In4 are solid GND; In3 carries the power
  areas, so In2 costs more over them (tools/plane_channels.py later lays In3 GND under every In2 signal).
- every copper item of another net is inflated by its clearance plus half the track width; a cell is free for a net
  only if no other net's halo covers it. Two maps: one for Default-class signals (0.15 mm to other Default nets,
  0.2 mm to everything else) and one for the other classes (0.2 mm). Drilled holes keep 0.25 mm to copper and 0.5 mm
  to a new via's hole. F.Cu stays out from under J4's shell, B.Cu out of the pocket by J1's west shell pad, F.Cu
  out of the core supply corner by pins 47-50 ("VREG corner"), and copper keeps 0.3 mm from the edge.
- each unconnected pair in the DRC report is routed with A* (8 directions, no corner cutting; a via where all three
  layers are free) from anywhere on one side's connected copper to anywhere on the other's, the rails first and then
  the shortest pairs first. Cells just outside the halo of a fine-pitch pin cost more for other nets, so a route
  doesn't run along a pin row and seal off the other pins' escapes. Paths only use 0/45/90 degree moves between cell centres, so the grid check
  is exact; the path is then straightened into as few 45-degree segments as fit, and the new copper joins the maps
  before the next pair.
- results go into the PCB group "autoroute"; --clear removes the previous group first. Refill zones and re-run DRC
  afterwards, and repeat until nothing is left (each DRC lists the next pairs of a partly routed net).
"""
import heapq
import json
import math
import os
import sys
from array import array
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import route_recipe as rr  # noqa: E402

PACK = "--board=pack" in sys.argv
PCB = ROOT / ("kicad-pack/goosepack.kicad_pcb" if PACK else "kicad/thegoose.kicad_pcb")
PCB = Path(next((a[6:] for a in sys.argv if a.startswith("--pcb=")), PCB))   # --pcb=FILE: route a copy instead
GROUP = "autoroute"
MM = 1e6
OX, OY = (100.0, 100.0) if PACK else (rr.OX, rr.OY)
G = 0.025 if PACK else 0.05     # grid pitch, mm (the pack's 0.45 mm BQ25798 pitch needs the finer grid)
HW = 0.075                      # half a 0.15 mm track: the halos are drawn for it
MARGIN = 0.01
CLR_T, CLR_W = 0.15, 0.2        # Default to Default; everything else (USB, switch nodes, power classes)
HOLE_CLR = 0.25                 # copper to a drilled hole
HOLE_TO_HOLE = 0.5              # JLC, between drilled holes
EDGE = 0.3                      # copper to board edge
CORNER = 1.0                    # outline corner radius
VIA_D, VIA_DRILL = 0.45, 0.3
VIAS = [(VIA_D, VIA_DRILL)]     # sizes a new via can take (diameter, drill); bit i of Grid.noholes rules out size i
SIGNAL_VIAS = POWER_VIAS = (0,)
if PACK:                        # signals 0.45/0.25; power-class nets keep a 0.3 mm drill, 0.6 mm pad where it fits
    VIAS = [(0.45, 0.25), (0.6, 0.3), (0.5, 0.3)]
    SIGNAL_VIAS, POWER_VIAS = (0,), (1, 2)
VIA_COST = 1.5 / G              # in cells (1.5 mm)
IN2_POWER_COST = 1.6            # per cell on In2 over an In3 power area
SOFT, SOFT_COST = 0.45, 4.0     # cells this far beyond a fine-pitch pad's halo cost more for other nets, so routes
FINE = 0.45                     # don't run along a pin row and seal off its escapes; FINE: pad width counted as fine
LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
SKIP = {"GND", "VSYS", "VCC", "PACK+"}            # carried by planes, pours and the recipe
WIDE = {"+3V3", "+1V1", "VBUS", "Net-(D2-K)", "Net-(D2-A)"}
SWITCH = {"Net-(U4-SW)"}
CLASS_W = {}                                      # pack: track width by net class (others 0.15, WIDE nets 0.2)
if PACK:
    SKIP = {"/BAT_N", "/PACK-"}                   # planes; route_pack.py setup fanned every pad out
    WIDE, SWITCH = set(), {"/SW1", "/SW2"}
    CLASS_W = {"Charger": 0.3, "Power": 0.4, "Plane": 0.4}
NARROW = 0.2                                      # pack: where the class width doesn't fit (the DRC minimum)
PAD_VIA = 0.2                                     # pack: a via's copper keeps this far from every SMD pad, its own
                                                 # net's too, so solder can't wick down it
SMALL_ZONES = {"U10 back GND", "Y1 guard", "U4 VIN", "PACK+ J3-Q1", "VSYS Q1 drain", "PACK+ gate net"}
J4_SHELL = (34.1, 0.0, 51.1, 10.55)               # no F.Cu under J4's shell (above its pin row)
J1_WEST = (17.98, 0.0, 20.6, 7.6)                 # no B.Cu between IO1's lane and J1's west shell pad: a route there
                                                 # cuts the B.Cu pour round the pad off into an island
FREE, BLOCKED = -1, -2
KEEPOUT = "router keepout "                       # pack: rule areas named this plus net names
DIAG = math.sqrt(0.5) * G


def lpos(v):
    return (v.x / MM - OX, v.y / MM - OY)


def bpos(x, y):
    return pcbnew.VECTOR2I(int(round((OX + x) * MM)), int(round((OY + y) * MM)))


def seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - (ax + u * vx), py - (ay + u * vy))


def inside(px, py, edges):
    c = False
    for (ax, ay), (bx, by) in edges:
        if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
            c = not c
    return c


def poly_dist(px, py, edges):
    if inside(px, py, edges):
        return 0.0
    return min(seg_dist(px, py, a[0], a[1], b[0], b[1]) for a, b in edges)


class Grid:
    def __init__(self, W, H, classes):
        self.W, self.H = W, H
        self.nx, self.ny = int(math.ceil(W / G)), int(math.ceil(H / G))
        self.plane = self.nx * self.ny
        self.maps = [array("i", [FREE]) * (3 * self.plane), array("i", [FREE]) * (3 * self.plane)]
        self.noholes = bytearray(self.plane)      # bit i set where a new via of VIAS[i] would sit too close to
                                                 # another hole (pack: or its copper too close to an SMD pad)
        self.in2_power = bytearray(self.plane)
        self.soft = array("i", [FREE]) * (3 * self.plane)
        self.netid, self.netname, self.tight = {}, [], []
        self.keep = {}                            # net name: cells (3 layers) its tracks and vias stay out of
        self.classes = classes

    def nid(self, name):
        if name not in self.netid:
            self.netid[name] = len(self.netname)
            self.netname.append(name)
            self.tight.append(self.classes.get(name, "Default") == "Default" and name not in SWITCH)
        return self.netid[name]

    def box(self, x0, y0, x1, y1):
        return (max(0, int(x0 / G)), max(0, int(y0 / G)),
                min(self.nx - 1, int(x1 / G) + 1), min(self.ny - 1, int(y1 / G) + 1))

    def mark(self, m, i, n):
        v = m[i]
        if v == FREE:
            m[i] = n
        elif v != n:
            m[i] = BLOCKED

    def shape(self, layers, n, bbox, dist, base, hole=False):
        """Mark cells near a shape: dist(px, py) is the distance to it, base its own half-size beyond that."""
        if hole:
            r1 = r2 = base + HOLE_CLR + HW + MARGIN
        else:
            r1 = base + (CLR_T if self.tight[n] else CLR_W) + HW + MARGIN
            r2 = base + CLR_W + HW + MARGIN
        x0, y0, x1, y1 = bbox
        cx0, cy0, cx1, cy1 = self.box(x0 - r2, y0 - r2, x1 + r2, y1 + r2)
        m1, m2 = self.maps
        for y in range(cy0, cy1 + 1):
            py = (y + 0.5) * G
            for x in range(cx0, cx1 + 1):
                d = dist((x + 0.5) * G, py)
                if d <= r2:
                    j = y * self.nx + x
                    for l in layers:
                        i = l * self.plane + j
                        self.mark(m2, i, n)
                        if d <= r1:
                            self.mark(m1, i, n)

    def seg(self, layers, n, ax, ay, bx, by, half):
        self.shape(layers, n, (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)),
                   lambda px, py: seg_dist(px, py, ax, ay, bx, by), half)

    def poly(self, layers, n, pts):
        edges = list(zip(pts, pts[1:] + pts[:1]))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.shape(layers, n, (min(xs), min(ys), max(xs), max(ys)), lambda px, py: poly_dist(px, py, edges), 0.0)

    def hole(self, n, cx, cy, d):
        self.shape([0, 1, 2], n, (cx, cy, cx, cy), lambda px, py: math.hypot(px - cx, py - cy), d / 2, hole=True)
        for i, (_, drill) in enumerate(VIAS):
            r = d / 2 + HOLE_TO_HOLE + drill / 2
            cx0, cy0, cx1, cy1 = self.box(cx - r, cy - r, cx + r, cy + r)
            for y in range(cy0, cy1 + 1):
                for x in range(cx0, cx1 + 1):
                    if math.hypot((x + 0.5) * G - cx, (y + 0.5) * G - cy) <= r:
                        self.noholes[y * self.nx + x] |= 1 << i

    def novia(self, pts):
        """No via's copper within PAD_VIA of this polygon."""
        edges = list(zip(pts, pts[1:] + pts[:1]))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        r = max(d for d, _ in VIAS) / 2 + PAD_VIA
        cx0, cy0, cx1, cy1 = self.box(min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r)
        for y in range(cy0, cy1 + 1):
            for x in range(cx0, cx1 + 1):
                dist = poly_dist((x + 0.5) * G, (y + 0.5) * G, edges)
                for i, (d, _) in enumerate(VIAS):
                    if dist <= d / 2 + PAD_VIA:
                        self.noholes[y * self.nx + x] |= 1 << i

    def soften(self, l, n, pts):
        edges = list(zip(pts, pts[1:] + pts[:1]))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        r = (CLR_T if self.tight[n] else CLR_W) + HW + MARGIN + SOFT
        cx0, cy0, cx1, cy1 = self.box(min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r)
        for y in range(cy0, cy1 + 1):
            for x in range(cx0, cx1 + 1):
                if poly_dist((x + 0.5) * G, (y + 0.5) * G, edges) <= r:
                    self.mark(self.soft, l * self.plane + y * self.nx + x, n)

    def block(self, l, i):
        self.maps[0][l * self.plane + i] = BLOCKED
        self.maps[1][l * self.plane + i] = BLOCKED


def pad_polys(p, L):
    sp = p.GetEffectivePolygon(L, pcbnew.ERROR_OUTSIDE)
    return [[lpos(sp.Outline(k).CPoint(i)) for i in range(sp.Outline(k).PointCount())] for k in range(sp.OutlineCount())]


def pad_layers(p):
    if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
        return []
    return [i for i, L in enumerate(LAYERS) if p.IsOnLayer(L)]


def build(b, g):
    # board edge and rounded corners
    lim = EDGE + HW + MARGIN
    for y in range(g.ny):
        py = (y + 0.5) * G
        for x in range(g.nx):
            px = (x + 0.5) * G
            bad = px < lim or py < lim or px > g.W - lim or py > g.H - lim
            if not bad:
                cx = CORNER if px < CORNER else (g.W - CORNER if px > g.W - CORNER else None)
                cy = CORNER if py < CORNER else (g.H - CORNER if py > g.H - CORNER else None)
                bad = cx is not None and cy is not None and math.hypot(px - cx, py - cy) > CORNER - lim
            if bad:
                for l in range(3):
                    g.block(l, y * g.nx + x)
    for f in b.GetFootprints():
        for p in f.Pads():
            n = g.nid(p.GetNetname() or "<pad %s:%s>" % (f.GetReference(), p.GetNumber()))
            fine = min(p.GetSize().x, p.GetSize().y) / MM <= FINE
            for l in pad_layers(p):
                for poly in pad_polys(p, LAYERS[l]):
                    g.poly([l], n, poly)
                    if fine:
                        g.soften(l, n, poly)
                    if PACK and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                        g.novia(poly)
            if p.GetDrillSize().x > 0:
                c = lpos(p.GetPosition())
                g.hole(n, c[0], c[1], max(p.GetDrillSize().x, p.GetDrillSize().y) / MM)
            if f.GetReference().startswith("FID"):     # fiducials: copper keeps 0.6 mm from the 1 mm pad
                c = lpos(p.GetPosition())
                g.seg(pad_layers(p), n, c[0], c[1], c[0], c[1], 0.5 + 0.6 - CLR_T)
    for t in b.GetTracks():
        n = g.nid(t.GetNetname())
        if t.GetClass() == "PCB_VIA":
            c = lpos(t.GetPosition())
            g.seg([0, 1, 2], n, c[0], c[1], c[0], c[1], t.GetWidth(pcbnew.F_Cu) / MM / 2)
            g.hole(n, c[0], c[1], t.GetDrillValue() / MM)
        elif t.GetLayer() in LAYERS:
            a, c = lpos(t.GetStart()), lpos(t.GetEnd())
            g.seg([LAYERS.index(t.GetLayer())], n, a[0], a[1], c[0], c[1], t.GetWidth() / MM / 2)
    for z in b.Zones():
        if z.GetIsRuleArea() or not (PACK or z.GetZoneName() in SMALL_ZONES):
            continue
        n = g.nid(z.GetNetname())
        for L in LAYERS if PACK else (pcbnew.F_Cu, pcbnew.B_Cu):
            if z.IsOnLayer(L):
                fp = z.GetFilledPolysList(L)
                for k in range(fp.OutlineCount()):
                    ol = fp.Outline(k)
                    g.poly([LAYERS.index(L)], n, [lpos(ol.CPoint(i)) for i in range(ol.PointCount())])
    if PACK:                                      # per-net keepouts: "router keepout NET,NET..."
        for z in b.Zones():
            if not (z.GetIsRuleArea() and z.GetZoneName().startswith(KEEPOUT)):
                continue
            for k in range(z.Outline().OutlineCount()):
                ol = z.Outline().Outline(k)
                edges = [(lpos(ol.CPoint(i)), lpos(ol.CPoint((i + 1) % ol.PointCount())))
                         for i in range(ol.PointCount())]
                xs, ys = [e[0][0] for e in edges], [e[0][1] for e in edges]
                cx0, cy0, cx1, cy1 = g.box(min(xs) - 0.3, min(ys) - 0.3, max(xs) + 0.3, max(ys) + 0.3)
                for name in z.GetZoneName()[len(KEEPOUT):].split(","):
                    kb = g.keep.setdefault(name.strip(), bytearray(3 * g.plane))
                    for l, L in enumerate(LAYERS):
                        if not z.IsOnLayer(L):
                            continue
                        for y in range(cy0, cy1 + 1):
                            for x in range(cx0, cx1 + 1):
                                if poly_dist((x + 0.5) * G, (y + 0.5) * G, edges) <= HW + MARGIN:
                                    kb[l * g.plane + y * g.nx + x] = 1
    if PACK:                                      # the In2 PACK+ corridor: no tracks
        for z in b.Zones():
            if z.GetIsRuleArea() and z.GetDoNotAllowTracks() and z.IsOnLayer(pcbnew.In2_Cu):
                ol = z.Outline().Outline(0)
                edges = [(lpos(ol.CPoint(i)), lpos(ol.CPoint((i + 1) % ol.PointCount())))
                         for i in range(ol.PointCount())]
                bb = z.GetBoundingBox()
                (x0, y0), (x1, y1) = lpos(bb.GetOrigin()), lpos(bb.GetEnd())
                cx0, cy0, cx1, cy1 = g.box(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5)
                for y in range(cy0, cy1 + 1):
                    for x in range(cx0, cx1 + 1):
                        if poly_dist((x + 0.5) * G, (y + 0.5) * G, edges) <= HW + MARGIN:
                            g.block(1, y * g.nx + x)
        return
    x0, y0, x1, y1 = J4_SHELL
    cx0, cy0, cx1, cy1 = g.box(x0, y0, x1, y1)
    for y in range(cy0, cy1 + 1):
        for x in range(cx0, cx1 + 1):
            g.block(0, y * g.nx + x)
    x0, y0, x1, y1 = J1_WEST
    cx0, cy0, cx1, cy1 = g.box(x0, y0, x1, y1)
    for y in range(cy0, cy1 + 1):
        for x in range(cx0, cx1 + 1):
            g.block(2, y * g.nx + x)
    # the RP2354 core supply corner (route_recipe.vreg): no other net on F.Cu by pins 47-50 and C85
    for z in b.Zones():
        if z.GetIsRuleArea() and z.GetZoneName() == "VREG corner":
            bb = z.GetBoundingBox()
            (x0, y0), (x1, y1) = lpos(bb.GetOrigin()), lpos(bb.GetEnd())
            cx0, cy0, cx1, cy1 = g.box(x0, y0, x1, y1)
            for y in range(cy0, cy1 + 1):
                for x in range(cx0, cx1 + 1):
                    g.block(0, y * g.nx + x)
    # In3 power areas, for the In2 cost
    for poly in (rr.PWR_33, rr.PWR_VCC, rr.pwr_vsys(g.W, g.H)):
        edges = list(zip(poly, poly[1:] + poly[:1]))
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        cx0, cy0, cx1, cy1 = g.box(min(xs), min(ys), max(xs), max(ys))
        for y in range(cy0, cy1 + 1):
            for x in range(cx0, cx1 + 1):
                if inside((x + 0.5) * G, (y + 0.5) * G, edges):
                    g.in2_power[y * g.nx + x] = 1


class Router:
    def __init__(self, g):
        self.g = g
        self.cost = array("d", [1e18]) * (3 * g.plane)
        self.came = array("i", [-1]) * (3 * g.plane)
        self.touched = []
        self.vpick = bytearray(3 * g.plane)      # the VIAS size of the via a search used to reach each node
        self.via_offsets_by = []
        for d, drill in VIAS:
            rho = max(d / 2, drill / 2 + HOLE_CLR - CLR_T) - HW - MARGIN + DIAG + DIAG   # cells this close to a via
            # centre must be free: its pad's clearance, or its hole's 0.25 mm to copper where that reaches further
            rc = int(math.ceil(rho / G))
            self.via_offsets_by.append([(dx, dy) for dy in range(-rc, rc + 1) for dx in range(-rc, rc + 1)
                                        if math.hypot(dx, dy) * G <= rho])
        self.via_offsets = self.via_offsets_by[0]
        self.vias = SIGNAL_VIAS
        self.kb = None
        self.n = None

    def use(self, n, width=None):
        g = self.g
        self.n = n
        self.m = g.maps[0] if g.tight[n] else g.maps[1]
        self.width = width or CLASS_W.get(g.classes.get(g.netname[n]), 0.2 if g.netname[n] in WIDE else 2 * HW)
        self.vias = POWER_VIAS if g.classes.get(g.netname[n]) in CLASS_W else SIGNAL_VIAS
        self.kb = g.keep.get(g.netname[n])
        rc = int(math.ceil((self.width / 2 - HW) / G - 1e-9))   # the halos are drawn for HW: a wider track also
        self.ring = [dy * g.nx + dx for dy in range(-rc, rc + 1) for dx in range(-rc, rc + 1)   # needs the cells
                     if (dx or dy) and math.hypot(dx, dy) <= rc]                                # this close free

    def ok(self, i):
        """Cell (node index) usable by the current net's centreline."""
        m, n = self.m, self.n
        v = m[i]
        if v != FREE and v != n or self.kb and self.kb[i]:
            return False
        for d in self.ring:                              # wider tracks (0.2 mm: the four neighbours)
            v = m[i + d]
            if v != FREE and v != n:
                return False
        return True

    def via_ok(self, x, y):
        return self.via_pick(x, y) >= 0

    def via_pick(self, x, y):
        """The first of the current net's via sizes (an index into VIAS) that fits at (x, y), or -1."""
        g = self.g
        m, n = self.m, self.n
        if self.kb and any(self.kb[l * g.plane + y * g.nx + x] for l in range(3)):
            return -1
        for i in self.vias:
            if g.noholes[y * g.nx + x] >> i & 1:
                continue
            fits = True
            for dx, dy in self.via_offsets_by[i]:
                xx, yy = x + dx, y + dy
                if not (0 <= xx < g.nx and 0 <= yy < g.ny):
                    fits = False
                    break
                j = yy * g.nx + xx
                if any(m[l * g.plane + j] not in (FREE, n) for l in range(3)):
                    fits = False
                    break
            if fits:
                return i
        return -1

    def step_ok(self, l, x, y, dx, dy):
        """One grid move from (x, y) on layer l, without cutting a corner."""
        g = self.g
        xx, yy = x + dx, y + dy
        if xx < 1 or yy < 1 or xx >= g.nx - 1 or yy >= g.ny - 1:
            return False
        base = l * g.plane
        if not self.ok(base + yy * g.nx + xx):
            return False
        if dx and dy:
            return self.ok(base + y * g.nx + xx) and self.ok(base + yy * g.nx + x)
        return True

    def search(self, src, dst, limit=1_500_000 if PACK else 4_000_000):
        g = self.g
        nx, plane = g.nx, g.plane
        cost, came, pw, soft, n = self.cost, self.came, g.in2_power, g.soft, self.n
        for i in self.touched:
            cost[i] = 1e18
            came[i] = -1
        self.touched = touched = []
        dxy = [((i % plane) % nx, (i % plane) // nx) for i in dst]
        bx0, bx1 = min(p[0] for p in dxy), max(p[0] for p in dxy)
        by0, by1 = min(p[1] for p in dxy), max(p[1] for p in dxy)

        def h(x, y):
            dx = bx0 - x if x < bx0 else (x - bx1 if x > bx1 else 0)
            dy = by0 - y if y < by0 else (y - by1 if y > by1 else 0)
            return max(dx, dy) + 0.4142 * min(dx, dy)

        heap = []
        for s in src:
            cost[s] = 0.0
            touched.append(s)
            j = s % plane
            heap.append((h(j % nx, j // nx), 0.0, s))
        heapq.heapify(heap)
        steps = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
        pops = 0
        while heap:
            f, gc, i = heapq.heappop(heap)
            if gc > cost[i]:
                continue
            if i in dst:
                path = [i]
                while came[path[-1]] >= 0:
                    path.append(came[path[-1]])
                path.reverse()
                return [(p // plane, (p % plane) % nx, (p % plane) // nx) for p in path]
            pops += 1
            if pops > limit:
                return None
            l, j = divmod(i, plane)
            y, x = divmod(j, nx)
            for dx, dy, c in steps:
                if not self.step_ok(l, x, y, dx, dy):
                    continue
                xx, yy = x + dx, y + dy
                k = l * plane + yy * nx + xx
                if l == 1 and pw[k - plane]:
                    c *= IN2_POWER_COST
                sv = soft[k]
                if sv != FREE and sv != n:
                    c *= SOFT_COST
                ng = gc + c
                if ng < cost[k]:
                    if cost[k] == 1e18:
                        touched.append(k)
                    cost[k] = ng
                    came[k] = i
                    heapq.heappush(heap, (ng + h(xx, yy), ng, k))
            vi = self.via_pick(x, y)
            if vi >= 0:
                for l2 in range(3):
                    if l2 != l:
                        k = l2 * plane + j
                        ng = gc + VIA_COST
                        if ng < cost[k]:
                            if cost[k] == 1e18:
                                touched.append(k)
                            cost[k] = ng
                            came[k] = i
                            self.vpick[k] = vi
                            heapq.heappush(heap, (ng + h(x, y), ng, k))
        return None

    # ---- straightening ------------------------------------------------------------------------------------------
    def line_ok(self, l, a, c):
        dx, dy = c[0] - a[0], c[1] - a[1]
        if dx and dy and abs(dx) != abs(dy):
            return False
        sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
        x, y = a
        for _ in range(max(abs(dx), abs(dy))):
            if not self.step_ok(l, x, y, sx, sy):
                return False
            x, y = x + sx, y + sy
        return True

    def bend(self, l, a, c):
        """Corner point of a 45-degree dog-leg from a to c that fits, or None."""
        dx, dy = c[0] - a[0], c[1] - a[1]
        d = min(abs(dx), abs(dy))
        sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
        for mid in ((a[0] + sx * d, a[1] + sy * d), (c[0] - sx * d, c[1] - sy * d)):
            if self.line_ok(l, a, mid) and self.line_ok(l, mid, c):
                return mid
        return None

    def straighten(self, l, pts):
        out = [pts[0]]
        i = 0
        while i < len(pts) - 1:
            best, bmid, misses = i + 1, None, 0
            for j in range(i + 2, len(pts)):
                mid = self.bend(l, pts[i], pts[j])
                if mid is not None:
                    best, bmid, misses = j, mid, 0
                else:
                    misses += 1
                    if misses > 40:
                        break
            if bmid is not None and bmid != pts[i] and bmid != pts[best]:
                out.append(bmid)
            out.append(pts[best])
            i = best
        # merge collinear runs
        res = [out[0]]
        for q in out[1:]:
            if len(res) >= 2:
                a, c = res[-2], res[-1]
                if (c[0] - a[0]) * (q[1] - c[1]) == (c[1] - a[1]) * (q[0] - c[0]) and \
                        (c[0] - a[0]) * (q[0] - c[0]) + (c[1] - a[1]) * (q[1] - c[1]) > 0:
                    res[-1] = q
                    continue
            if q != res[-1]:
                res.append(q)
        return res


def item_cells(g, rt, kind, it):
    """Usable node indices under an item's own copper."""
    out = set()
    if kind == "pad":
        for l in pad_layers(it):
            for poly in pad_polys(it, LAYERS[l]):
                xs, ys = [q[0] for q in poly], [q[1] for q in poly]
                cx0, cy0, cx1, cy1 = g.box(min(xs), min(ys), max(xs), max(ys))
                edges = list(zip(poly, poly[1:] + poly[:1]))
                for y in range(cy0, cy1 + 1):
                    for x in range(cx0, cx1 + 1):
                        i = l * g.plane + y * g.nx + x
                        if inside((x + 0.5) * G, (y + 0.5) * G, edges) and rt.ok(i):
                            out.add(i)
        return out
    if kind == "zone":                          # a pour's filled copper (pack: the pack-path pours)
        for L in LAYERS:
            if not it.IsOnLayer(L):
                continue
            fp = it.GetFilledPolysList(L)
            for k in range(fp.OutlineCount()):
                ol = fp.Outline(k)
                poly = [lpos(ol.CPoint(i)) for i in range(ol.PointCount())]
                xs, ys = [q[0] for q in poly], [q[1] for q in poly]
                cx0, cy0, cx1, cy1 = g.box(min(xs), min(ys), max(xs), max(ys))
                edges = list(zip(poly, poly[1:] + poly[:1]))
                for y in range(cy0, cy1 + 1):
                    for x in range(cx0, cx1 + 1):
                        i = LAYERS.index(L) * g.plane + y * g.nx + x
                        if inside((x + 0.5) * G, (y + 0.5) * G, edges) and rt.ok(i):
                            out.add(i)
        return out
    if kind == "via":
        a = c = lpos(it.GetPosition())
        r, layers = it.GetWidth(pcbnew.F_Cu) / MM / 2, [0, 1, 2]
    else:
        a, c = lpos(it.GetStart()), lpos(it.GetEnd())
        r, layers = it.GetWidth() / MM / 2, [LAYERS.index(it.GetLayer())] if it.GetLayer() in LAYERS else []
    cx0, cy0, cx1, cy1 = g.box(min(a[0], c[0]) - r, min(a[1], c[1]) - r, max(a[0], c[0]) + r, max(a[1], c[1]) + r)
    for y in range(cy0, cy1 + 1):
        for x in range(cx0, cx1 + 1):
            if seg_dist((x + 0.5) * G, (y + 0.5) * G, a[0], a[1], c[0], c[1]) <= r:
                for l in layers:
                    i = l * g.plane + y * g.nx + x
                    if rt.ok(i):
                        out.add(i)
    return out


def cluster_cells(g, rt, b, kind, it):
    """Usable cells under an item and everything already connected to it (pads, tracks, vias)."""
    out = item_cells(g, rt, kind, it)
    for c in b.GetConnectivity().GetConnectedItems(it):
        k = {"PAD": "pad", "PCB_VIA": "via", "PCB_TRACK": "track", "ZONE": "zone"}.get(c.GetClass())
        if k:
            out |= item_cells(g, rt, k, c.Cast())
    return out


def emit(b, g, rt, grp, netinfo, path):
    n = rt.n
    w = rt.width
    runs, cur = [], [path[0]]
    for p in path[1:]:
        if p[0] != cur[-1][0]:
            runs.append(cur)
            cur = [p]
        else:
            cur.append(p)
    runs.append(cur)
    added = []
    for k, run in enumerate(runs):
        l = run[0][0]
        pts = rt.straighten(l, [(x, y) for _, x, y in run])
        for a, c in zip(pts[:-1], pts[1:]):
            ax, ay, cx, cy = (a[0] + 0.5) * G, (a[1] + 0.5) * G, (c[0] + 0.5) * G, (c[1] + 0.5) * G
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(bpos(ax, ay))
            t.SetEnd(bpos(cx, cy))
            t.SetLayer(LAYERS[l])
            t.SetWidth(int(round(w * MM)))
            t.SetNet(netinfo)
            added.append(t)
            g.seg([l], n, ax, ay, cx, cy, w / 2)
        if k + 1 < len(runs):
            x, y = (run[-1][1] + 0.5) * G, (run[-1][2] + 0.5) * G
            l2, x2, y2 = runs[k + 1][0]
            vd, vdrill = VIAS[rt.vpick[l2 * g.plane + y2 * g.nx + x2]]
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(bpos(x, y))
            v.SetWidth(int(round(vd * MM)))
            v.SetDrill(int(round(vdrill * MM)))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(netinfo)
            added.append(v)
            g.seg([0, 1, 2], n, x, y, x, y, vd / 2)
            g.hole(n, x, y, vdrill)
    for it in added:
        b.Add(it)
        grp.AddItem(it)
    return added


def rip(nets):
    b = pcbnew.LoadBoard(str(PCB))
    doomed = [it for gr in b.Groups() if gr.GetName() == GROUP for it in gr.GetItems()
              if nets == ["*"] or it.GetNetname() in nets]
    for it in doomed:
        b.Remove(it)
    b.Save(str(PCB))
    print("grid_router: ripped %d items on %s" % (len(doomed), ",".join(nets)))


def main():
    r = next((a[6:].split(",") for a in sys.argv if a.startswith("--rip=")), None)
    if r:
        return rip(r)
    drc = json.load(open(sys.argv[1]))
    if "--clear" in sys.argv:
        b = pcbnew.LoadBoard(str(PCB))
        for gr in [gr for gr in b.Groups() if gr.GetName() == GROUP]:
            for it in list(gr.GetItems()):
                b.Remove(it)
            b.Remove(gr)
        b.Save(str(PCB))
        argv = [a for a in sys.argv if a != "--clear"]
        os.execv(sys.executable, [sys.executable] + argv)       # a fresh process: pcbnew's lists go stale after removals
    b = pcbnew.LoadBoard(str(PCB))
    nets = {str(k): v for k, v in b.GetNetsByName().items()}
    classes = {k: v.GetNetClassName() for k, v in nets.items()}
    bb = b.GetBoardEdgesBoundingBox()
    g = Grid(bb.GetWidth() / MM, bb.GetHeight() / MM, classes)
    build(b, g)
    items = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            items[p.m_Uuid.AsString()] = ("pad", p)
    for t in b.GetTracks():
        items[t.m_Uuid.AsString()] = ("via" if t.GetClass() == "PCB_VIA" else "track", t)
    for z in b.Zones():
        if not z.GetIsRuleArea():
            items[z.m_Uuid.AsString()] = ("zone", z)
    pairs = []
    for u in drc.get("unconnected_items", []):
        its = u["items"]
        if len(its) != 2 or its[0]["uuid"] not in items or its[1]["uuid"] not in items:
            print("skip", [i["description"] for i in its])
            continue
        ia, ib = items[its[0]["uuid"]], items[its[1]["uuid"]]
        net = ia[1].GetNetname()
        if net in SKIP:
            continue
        d = math.dist((its[0]["pos"]["x"], its[0]["pos"]["y"]), (its[1]["pos"]["x"], its[1]["pos"]["y"]))
        pairs.append((d, net, ia, ib, its[0]["description"], its[1]["description"]))
    first = next((a[8:].split(",") for a in sys.argv if a.startswith("--first=")), [])
    rank = {net: k for k, net in enumerate(first)}
    pairs.sort(key=lambda p: (p[1] not in WIDE, rank.get(p[1], len(first)), p[0]))  # rails, --first in order, shortest
    grp = next((gr for gr in b.Groups() if gr.GetName() == GROUP), None)
    if grp is None:
        grp = pcbnew.PCB_GROUP(b)
        grp.SetName(GROUP)
        b.Add(grp)
    rt = Router(g)
    ok, failed = 0, []
    for d, net, ia, ib, da, db in pairs:
        path = None
        for width in (None, NARROW):            # pack: class width, else 0.2 mm (tools/route_pack.py finish widens)
            rt.use(g.nid(net), width)
            src, dst = cluster_cells(g, rt, b, *ia), cluster_cells(g, rt, b, *ib)
            if src & dst or (src and dst and (path := rt.search(src, dst))) or rt.width <= NARROW or not CLASS_W:
                break
        if src & dst:
            continue
        if not src or not dst:
            failed.append("%s: no free cell under %s" % (net, da if not src else db))
            continue
        if not path:
            failed.append("%s (%.1f mm): %s -> %s" % (net, d, da, db))
            continue
        emit(b, g, rt, grp, nets[net], path)
        ok += 1
        print("routed %-28s %5.1f mm, %d vias, %.2f mm" % (net, d, sum(1 for p, q in zip(path, path[1:]) if p[0] != q[0]),
                                                           rt.width), flush=True)
    b.Save(str(PCB))
    for f in failed:
        print("FAILED", f)
    print("grid_router: %d routed, %d failed" % (ok, len(failed)))


if __name__ == "__main__":
    main()
