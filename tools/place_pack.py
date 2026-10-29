"""Place the 3S pack board (kicad-pack/goosepack.kicad_pcb) in one of three layouts, or with --board=pack2s the 2S
pack (kicad-pack-2s/goosepack2s.kicad_pcb) in its own compact layout (see compact2s).

Run with KiCad's Python:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        tools/place_pack.py {vertical,rightangle,ontop,compact} [--size WxH] [--reach MM] [--out FILE]

The first two put the board on the Ovonic 3S 450 mAh pack (50.5 x 25 x 14 mm), lead end at x 0, USB end at x W:
- vertical:   50 x 24 mm, J3 (XT30UPB-M) and J11 (B4B-XH-A) stand up at the lead end, as in the schematic.
- rightangle: 64 x 24 mm, plus a 29 mm wide head that runs 14 mm past the pack's lead end. J3 becomes an XT30PW-M
              and J11 an S4B-XH-A, side by side in the head with both mouths out through the lead end (they need
              27.9 mm of edge). The swap is board-only: the schematic still names the vertical parts, so update it
              before keeping this layout.

ontop puts the Ovonic pack on the board instead: 58 x 25.5 mm, the pack on the front (F) side over x 7.5-58 with TH2
under it, J3 (XT30UPB-M) and J11 (B4B-XH-A) standing up in the 7.5 mm strip past the pack's lead end, and every SMD
part on the back (B) side, facing away from the pack. J2's lead is soldered from the back.

compact ignores the pack's size and makes the board as small as it goes (--size, default 50 x 23 mm, the smallest
where every passive lands within 9 mm of the pin it serves; 45.5 x 20.5 packs only by sending the charger's last
passives 13-22 mm away, and doesn't route): every part on the front. J3 becomes solder pads for a 16 AWG pigtail ending in an XT30U-M that the pack's own XT30 plugs
into, and J2 moves to the same pads; J11 stays a vertical B4B-XH-A, since JST XH has no wire-to-wire male to make a
balance pigtail from. (TH2, the cell NTC, is gone since 2026-10-26: R79, a fixed 10k, holds the charger's TS pin at
25 C.)

What it does, every run: removes tracks, zones and drawings, places the connectors, ICs, FETs and fuse at fixed spots
(board-local mm, origin at the board's top-left corner, x right, y down), packs the passives next to the pins they
serve, and draws the outline. Without --out it edits the board in place.
"""
import argparse
import math
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import packcfg  # noqa: E402

BOARD = packcfg.BOARD           # "pack" (3S, the default) or "pack2s" (--board=pack2s)
PCB = packcfg.PCB
SOURCE = PCB                    # the board read (its parts, nets and fields); --in FILE reads another copy
LIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"
MODELS = ROOT / "kicad/3dmodels"

MM = 1e6
OX, OY = 100.0, 100.0          # board top-left corner in KiCad coordinates
H = 24.0                       # board height; main() changes it for the ontop layout
H_ONTOP = 25.5                 # J3 and J11 end to end down the strip need 24.8 mm
STRIP = 7.5                    # ontop: connector strip past the pack's lead end
R_CORNER = 1.0
EDGE = 0.3                     # copper and courtyards keep this far inside the outline
GRID = 0.25                    # passive packing grid
MAX_REACH = None               # if set, mm: a passive on an anchor's net must sit this close to one of its pins
COMPACT = (50.0, 23.0)         # smallest compact board that packs with every passive within COMPACT_REACH
COMPACT_REACH = 9.0            # compact: mm from a passive's pad to its anchor pin (45.5 x 20.5 packs without it;
                               # 8 left no room once the power stage's via lanes were kept clear)
U13_LEFT = 17.3                # compact: U13's courtyard west edge; the 3.8 mm strip by J11 holds its VC filters and
                               # VDD caps (15.8 left only 2.3 mm: the filters got packed 6 mm away and didn't route)
LED_EDGE = "--led=stat" not in sys.argv   # compact: LED1 on the right edge over J1, or (--led=stat) packed by U7's STAT
ESCAPE = 0.8                   # compact: mm kept clear west and north of U7 for its pins' escape vias
WIRE16 = ("Connector_Wire", "SolderWire-1.5sqmm_1x02_P6mm_D1.7mm_OD3mm")   # 16 AWG pigtail pads

# Charger parts in BQ25798 layout order (SLUSE22 section 11): PMID caps nearest, then the BAT caps and the BATP sense
# resistor, the I2C pull-ups (their pins face J1, so they go first or end up 8 mm away; SDA's first), the status LED
# by STAT (U7's south-west corner, so STAT doesn't cross the PMID and VBUS pours), the TS divider
# and the ILIM_HIZ divider (their pins are in U7's crowded corner by J1), the SYS caps, the boot caps, then VBUS and
# the rest.
CHARGER = ["C24", "C25", "C26", "C33", "R98", "R97", "R30", "LED1", "R36", "R32", "R33", "R34", "R35", "R79", "C34",
           "C27", "C28", "C29", "C30", "C31", "C32", "C23", "C18", "C19", "C35", "D1", "R95", "R96", "C20", "C21",
           "C22", "C36", "R31", "R78"]
ANCHORS = ("U7", "U13", "J1", "Q2", "Q3", "L2")   # a passive on one of their nets goes next to their pins
# Protector parts: the VDD filter, then the cell filters' caps (each across two adjacent VC pins, so they land beside
# U13's pins in pin order), then their resistors further out, so the cell -> R -> C -> pin chains don't cross.
PROTECTOR = ["R61", "C62", "C63", "C66", "C65", "C64", "C67", "R65", "R64", "R63", "R62", "R68", "R69", "C68", "R70",
             "R71", "R72", "R73", "R74", "R75", "R76", "R77", "R94", "TH1"]
GROUNDS = {"/PACK-", "/BAT_N"}  # every passive touches one of these; they don't say where it belongs
CHARGER_DX = 0.0                # compact: how far the charger corner (U7_AT, PACK_ZONE) sits west of the 3S pack's


def load_fp(lib, name):
    return pcbnew.FootprintLoad(LIB + lib + ".pretty", name)


def swap(b, ref, lib, name, value, mpn, model=None, lcsc=None, attrs=None):
    """Replace a footprint, keeping its schematic link, fields and pad nets."""
    old = next(f for f in b.GetFootprints() if f.GetReference() == ref)
    if name in old.GetFPIDAsString():
        if attrs is not None:                   # swapped on an earlier run: the flags still apply
            old.SetAttributes(attrs)
        return
    new = load_fp(lib, name)
    new.SetFPID(pcbnew.LIB_ID(lib, name))
    new.SetReference(ref)
    new.SetValue(value)
    new.SetPath(old.GetPath())
    new.SetSheetname(old.GetSheetname())
    new.SetSheetfile(old.GetSheetfile())
    for fld in old.GetFields():
        if fld.GetName() in ("Reference", "Value", "Footprint"):
            continue
        text = {"MPN": mpn, "LCSC Part #": lcsc or fld.GetText()}.get(fld.GetName(), fld.GetText())
        new.SetField(fld.GetName(), text)
        new.GetField(fld.GetName()).SetVisible(False)
        new.GetField(fld.GetName()).SetLayer(pcbnew.F_Fab)
    if model:
        new.Models().clear()
        m = pcbnew.FP_3DMODEL()
        m.m_Filename, (ox, oy, oz), rz = model
        m.m_Offset = pcbnew.VECTOR3D(ox, oy, oz)
        m.m_Rotation = pcbnew.VECTOR3D(0, 0, rz)
        new.Models().push_back(m)
    # library flags like "exclude from BOM" would break parity, so keep the old part's (or the ones given)
    new.SetAttributes(old.GetAttributes() if attrs is None else attrs)
    nets = {p.GetNumber(): p.GetNet() for p in old.Pads()}
    b.Remove(old)
    b.Add(new)
    for p in new.Pads():
        if p.GetNumber() in nets:
            p.SetNet(nets[p.GetNumber()])


class Placer:
    def __init__(self, b, rects):
        self.b, self.rects = b, rects     # the board as rectangles (x0, y0, x1, y1)
        self.boxes = {"F": [], "B": []}   # placed courtyards per side, (x0, y0, x1, y1) board-local
        self.placed = set()               # refs whose pads count as targets for the passives

    def fp(self, ref):
        return next((f for f in self.b.GetFootprints() if f.GetReference() == ref), None)

    def pose(self, ref, side, rot, x=0.0, y=0.0):
        f = self.fp(ref)
        if f.IsFlipped() != (side == "B"):
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetOrientationDegrees(rot)
        f.SetPosition(pcbnew.VECTOR2I(int(round((OX + x) * MM)), int(round((OY + y) * MM))))
        return f

    def crt(self, f):
        layer = pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd
        f.BuildCourtyardCaches()              # the cache doesn't follow rotations
        bb = f.GetCourtyard(layer).BBox()
        return (bb.GetLeft() / MM - OX, bb.GetTop() / MM - OY, bb.GetRight() / MM - OX, bb.GetBottom() / MM - OY)

    def mouth_rot(self, ref, side, direction):
        """Rotation that points a connector's mouth (pads to courtyard centre) at direction: '-x', '+x', '-y', '+y'."""
        want = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}[direction]
        for rot in (0, 90, 180, 270):
            f = self.pose(ref, side, rot)
            pads = [p.GetPosition() for p in f.Pads() if p.GetNumber()]
            px = sum(v.x for v in pads) / len(pads) / MM - OX
            py = sum(v.y for v in pads) / len(pads) / MM - OY
            x0, y0, x1, y1 = self.crt(f)
            dx, dy = (x0 + x1) / 2 - px, (y0 + y1) / 2 - py
            if dx * want[0] + dy * want[1] > 0.7 * math.hypot(dx, dy):
                return rot
        raise ValueError(ref)

    def face(self, ref, side, net, direction):
        """Rotation that puts the pads on net furthest toward direction."""
        want = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}[direction]
        best = None
        for rot in (0, 90, 180, 270):
            f = self.pose(ref, side, rot)
            c = f.GetPosition()
            pads = [p.GetPosition() for p in f.Pads() if p.GetNetname() == net]
            d = sum((v.x - c.x) * want[0] + (v.y - c.y) * want[1] for v in pads) / len(pads)
            if best is None or d > best[0]:
                best = (d, rot)
        return best[1]

    def pad_xy(self, ref, num):
        v = next(p for p in self.fp(ref).Pads() if p.GetNumber() == num).GetPosition()
        return (v.x / MM - OX, v.y / MM - OY)

    def pad_box(self, ref, num):
        bb = next(p for p in self.fp(ref).Pads() if p.GetNumber() == num).GetBoundingBox()
        return (bb.GetLeft() / MM - OX, bb.GetTop() / MM - OY, bb.GetRight() / MM - OX, bb.GetBottom() / MM - OY)

    def put(self, ref, side, rot, left=None, top=None, right=None, bottom=None, cx=None, cy=None):
        """Place by courtyard edges (or centre) instead of the footprint origin."""
        f = self.pose(ref, side, rot)
        x0, y0, x1, y1 = self.crt(f)
        dx = (left - x0 if left is not None else right - x1 if right is not None else cx - (x0 + x1) / 2)
        dy = (top - y0 if top is not None else bottom - y1 if bottom is not None else cy - (y0 + y1) / 2)
        self.pose(ref, side, rot, dx, dy)
        self.claim(f, side)

    def claim(self, f, side):
        box = self.crt(f)
        tht = any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in f.Pads())
        for s in (("F", "B") if tht else (side,)):
            self.boxes[s].append(box)

    def free(self, box, side, zone):
        x0, y0, x1, y1 = box
        zx0, zy0, zx1, zy1 = zone
        if x0 < zx0 or y0 < zy0 or x1 > zx1 or y1 > zy1:
            return False
        if not any(x0 >= a0 + EDGE and y0 >= b0 + EDGE and x1 <= a1 - EDGE and y1 <= b1 - EDGE
                   for a0, b0, a1, b1 in self.rects):
            return False
        return all(x1 <= a0 or x0 >= a1 or y1 <= b0 or y0 >= b1 for a0, b0, a1, b1 in self.boxes[side])

    def pads_on(self, net, only=None):
        out = []
        for f in self.b.GetFootprints():
            if f.GetReference() in self.placed and (only is None or f.GetReference() in only):
                out += [p.GetPosition() for p in f.Pads() if p.GetNetname() == net]
        return [(v.x / MM - OX, v.y / MM - OY) for v in out]

    def pack(self, refs, side, zone, target=None):
        """Put each part, in order and in whichever of four rotations is best, where its pads sit closest to the
        pads they connect to: an anchor IC's pads on that net if it has any, else any placed part's. Ground pads
        count half, and only toward an anchor's ground pins, so a decoupling cap closes its loop at the IC."""
        for ref in refs:
            f = self.fp(ref)
            goals = []                                # (weight, [target points]) per pad
            reach = []                                # pads that must land within MAX_REACH of an anchor pin
            for i, pd in enumerate(f.Pads()):
                n = pd.GetNetname()
                pts = self.pads_on(n, ANCHORS)
                if n in GROUNDS:
                    goals.append((0.5, pts))
                else:
                    goals.append((1.0, pts or self.pads_on(n)))
                    if pts:
                        reach.append(i)
            if target or not any(pts for _, pts in goals):
                c = target or ((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2)
                goals = None
            best = None
            for rot in (0, 90, 180, 270):
                self.pose(ref, side, rot)
                x0, y0, x1, y1 = self.crt(f)
                w, h = x1 - x0, y1 - y0
                ox, oy = f.GetPosition().x / MM - OX - x0, f.GetPosition().y / MM - OY - y0
                offs = [(pd.GetPosition().x / MM - OX - x0, pd.GetPosition().y / MM - OY - y0) for pd in f.Pads()]
                gx = zone[0]
                while gx + w <= zone[2]:
                    gy = zone[1]
                    while gy + h <= zone[3]:
                        if self.free((gx, gy, gx + w, gy + h), side, zone):
                            if goals is None:
                                d = math.hypot(gx + w / 2 - c[0], gy + h / 2 - c[1])
                            else:
                                dist = [min(math.hypot(gx + dx - tx, gy + dy - ty) for tx, ty in pts) if pts else 0
                                        for (wt, pts), (dx, dy) in zip(goals, offs)]
                                far = min(dist[i] for i in reach) > MAX_REACH if MAX_REACH and reach else False
                                if far and ref not in PACK_ZONE:
                                    gy += GRID
                                    continue
                                d = sum(wt * di for (wt, _), di in zip(goals, dist))
                            if best is None or d < best[0] - 1e-9:
                                best = (d, rot, gx + ox, gy + oy)
                        gy += GRID
                    gx += GRID
            if best is None:
                raise RuntimeError(f"no room for {ref} in {zone}")
            self.pose(ref, side, best[1], best[2], best[3])
            self.claim(f, side)
            self.placed.add(ref)

    def fixed(self, refs):
        self.placed.update(refs)


def outline(b, pts):
    """Closed polygon (clockwise on screen) on Edge.Cuts, outside corners rounded."""
    r = R_CORNER

    def v(x, y):
        return pcbnew.VECTOR2I(int(round((OX + x) * MM)), int(round((OY + y) * MM)))

    def shape(kind):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(kind)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(int(0.05 * MM))
        b.Add(s)
        return s
    n = len(pts)
    ends = []                                   # (corner start, corner end) per vertex
    for i in range(n):
        (ax, ay), (bx, by), (cx, cy) = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1 = ((bx - ax) / math.hypot(bx - ax, by - ay), (by - ay) / math.hypot(bx - ax, by - ay))
        d2 = ((cx - bx) / math.hypot(cx - bx, cy - by), (cy - by) / math.hypot(cx - bx, cy - by))
        if d1[0] * d2[1] - d1[1] * d2[0] > 0:   # outside corner
            st, en = (bx - d1[0] * r, by - d1[1] * r), (bx + d2[0] * r, by + d2[1] * r)
            a = shape(pcbnew.SHAPE_T_ARC)
            a.SetCenter(v(st[0] + d2[0] * r, st[1] + d2[1] * r))
            a.SetStart(v(*st))
            a.SetEnd(v(*en))
            ends.append((st, en))
        else:
            ends.append(((bx, by), (bx, by)))
    for i in range(n):
        s = shape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(v(*ends[i][1]))
        s.SetEnd(v(*ends[(i + 1) % n][0]))


def vertical(p):
    """50 x 24: lead block x 0-15.6, protector x 15.6-31, charger x 31-50."""
    p.put("J11", "F", 0, left=0, top=0)                      # pins along the top edge, plug from above
    p.put("J3", "F", 90, left=0, top=7.2)                    # pins down the lead edge, plug from above
    p.put("J2", "F", 90, left=6.6, top=7.2)                  # output lead pads beside J3
    p.put("F1", "F", 0, left=0, bottom=H - EDGE)             # CELL+ (J3) to PACK+ (J2) along the bottom
    p.put("R66", "F", 0, left=7.7, bottom=H - EDGE)          # BAT_N (J3) to PROT_SNS (Q2)
    p.put("Q2", "F", 0, left=15.6, bottom=H - EDGE)          # sources west, drains east into Q3's
    p.put("Q3", "F", 180, left=23.1, bottom=H - EDGE)
    p.put("U13", "F", 0, cx=21.0, cy=7.6)                    # VC pins west toward J11, SRP/SRN/DSG south
    p.put("J1", "F", p.mouth_rot("J1", "F", "+x"), right=50 + 1.9, cy=12.0)
    p.put("U7", "F", 180, cx=38.0, cy=8.0)                   # VBUS east toward J1, BAT west toward PACK+
    p.put("L2", "F", 180, cx=38.0, cy=13.6)                  # under the SW1/SW2 pads
    return ("J11", "J3", "J2", "F1", "R66", "Q2", "Q3", "U13", "J1", "U7", "L2"), (31.0, 0, 50, H), (13.6, 0, 31.0, H)


def rightangle(p):
    """64 x 24 with a 29 mm head at x 0-16.2: J3/J11 in the head, protector x 16-41, charger x 41-64."""
    p.put("J3", "F", p.mouth_rot("J3", "F", "-x"), left=0, top=HEAD[0] + EDGE)
    p.put("J11", "F", p.mouth_rot("J11", "F", "-x"), left=0, bottom=HEAD[1] - EDGE)
    p.put("J2", "F", 90, left=16.2, cy=12.0)
    p.put("F1", "F", 0, left=16.2, top=EDGE)
    p.put("R66", "F", 0, left=16.2, bottom=H - EDGE)
    p.put("Q2", "F", 0, left=24.4, bottom=H - EDGE)
    p.put("Q3", "F", 180, left=31.9, bottom=H - EDGE)
    p.put("U13", "F", 0, cx=29.0, cy=7.6)
    p.put("J1", "F", p.mouth_rot("J1", "F", "+x"), right=64 + 1.9, cy=12.0)
    p.put("U7", "F", 180, cx=50.0, cy=8.0)
    p.put("L2", "F", 180, cx=50.0, cy=13.6)
    return ("J3", "J11", "J2", "F1", "R66", "Q2", "Q3", "U13", "J1", "U7", "L2"), (41.0, 0, 64, H), (23.5, 0, 41.0, H)


def ontop(p):
    """58 x 25.5, pack on top: J3/J11 up in the strip, back side lead block x 7.5-16, protector to 36.5, charger on."""
    p.put("J3", "F", 90, left=0, top=EDGE)                   # plug from above, beside the pack's end face
    p.put("J11", "F", 90, left=0, bottom=H - EDGE)
    p.put("J2", "B", 90, left=STRIP + 0.5, cy=H / 2)         # output lead soldered from the back
    p.put("F1", "B", 0, left=STRIP + 0.5, top=EDGE)
    p.put("R66", "B", 0, left=STRIP + 0.5, bottom=H - EDGE)
    p.put("Q2", "B", p.face("Q2", "B", "/PROT_FET_D", "+x"), left=16.4, bottom=H - EDGE)
    p.put("Q3", "B", p.face("Q3", "B", "/PROT_FET_D", "-x"), left=23.9, bottom=H - EDGE)
    p.put("U13", "B", p.face("U13", "B", "/PROT_VC3", "-x"), cx=24.5, cy=8.0)
    p.put("J1", "B", p.mouth_rot("J1", "B", "+x"), right=58.0 + 1.9, cy=H / 2)
    p.put("U7", "B", p.face("U7", "B", "/VBUS", "+x"), cx=45.5, cy=8.5)
    return ("J3", "J11", "J2", "F1", "R66", "Q2", "Q3", "U13", "J1", "U7"), (36.5, 0, 58.0, H), (15.9, 0, 36.5, H)


def compact(p):
    """W x H, all parts on the front: power row along the bottom, J11 and the protector above it, charger east."""
    w = p.rects[0][2]
    p.put("J11", "F", 0, left=0, top=0)                      # plug from above
    p.put("U13", "F", p.face("U13", "F", "/PROT_VC3", "-x"), left=U13_LEFT, top=EDGE)  # room by J11 for its filters
    p.put("J3", "F", 90, left=EDGE, bottom=H - EDGE)          # cell pigtail
    p.put("R66", "F", 0, left=4.8, bottom=H - EDGE)          # BAT_N (J3) to PROT_SNS (Q2)
    p.put("Q2", "F", p.face("Q2", "F", "/PROT_FET_D", "+x"), left=12.6, bottom=H - EDGE)
    p.put("Q3", "F", p.face("Q3", "F", "/PROT_FET_D", "-x"), left=20.1, bottom=H - EDGE)
    p.put("J2", "F", 90, left=27.7, bottom=H - EDGE)         # output pigtail, PACK- beside Q3's sources
    p.put("F1", "F", 0, left=4.8, bottom=H - EDGE - 4.2)     # CELL+ (J3) to PACK+, over R66
    p.put("J1", "F", p.mouth_rot("J1", "F", "+x"), right=w + 1.9, cy=H / 2)
    sense(p)
    power_stage(p, w)
    p.put("D1", "F", p.face("D1", "F", "/VBUS", "-x"), right=w - EDGE, bottom=H - EDGE)   # VBUS TVS under J1
    if LED_EDGE:                                        # status LED on the USB end, over J1 (else packed by STAT)
        p.put("LED1", "F", 0, right=w - EDGE, bottom=p.crt(p.fp("J1"))[1])
    return ("J11", "U13", "J3", "R66", "Q2", "Q3", "J2", "F1", "J1", "D1") + (("LED1",) if LED_EDGE else ()) + \
        SENSE + POWER_STAGE, (0, 0, w, H), (0, 0, 32.4, H)


# The 2S pack (--board=pack2s). Its protector is an HY2120-LB (SOT-23-6) that senses current across Q2 + Q3: no R66, no
# Kelvin lines, no TH1. Two HY2213 balancers (U21/U22, with Q4/Q5 and their 1 W bleed resistors R112/R113) sit by J11.
# The charger corner is the 3S pack's, moved west by CHARGER_DX so it still ends at the east edge.
COMPACT_2S = (45.0, 23.0)       # --size overrides
XB_2S = 14.6                    # the ground split's target: BAT_N parts west of it, PACK- parts east (tools/route_pack.py
                                # puts the line between them)
# parts packed in a zone of their own: the protector's BAT_N side by U13, then the east block (PACK- parts, balancers)
WEST_2S = ("R71", "R70", "C62", "C64", "R61", "R63")
EAST_2S = ("U21", "Q4", "U22", "Q5", "C83", "R110", "C84", "R111", "R72", "R73", "R74")
NEAR_2S = {"C83": "U21", "R110": "U21", "C84": "U22", "R111": "U22"}   # packed within NEAR_REACH_2S of their balancer
NEAR_REACH_2S = 3.0
U13_AT_2S = (8.3, 7.0)
R94_AT_2S = (XB_2S, 9.0)        # R94 (BAT_N to PACK-) across the line, BAT_N pad west
R113_AT_2S = (EDGE, 8.2)        # R113's courtyard top-left: under J11 (room for its B0-B2 labels), R112 along the top
                                # edge east of it
R112_AT_2S = (11.2, EDGE)
PROTECTOR_2S = list(WEST_2S + EAST_2S)
FID1_AT_2S = (24.8, 12.0)       # 2S: FID1 and FID2 sit in free spots, not the 3S pack's
FID2_AT_2S = (20.0, 3.0)        # 2S: FID2's target (3S: the board centre, which here is the charger's pocket)


def compact2s(p):
    """W x H, all parts on the front: power row along the bottom edge (J3, Q2, Q3, J2), F1 over it, J11 and the
    balancers' bleed resistors along the top, the protector and the balancers between, the 3S charger corner east."""
    global CHARGER_DX
    w = p.rects[0][2]
    CHARGER_DX = w - 50.0
    p.put("J11", "F", 0, left=0, top=0)                      # plug from above
    p.put("J3", "F", 90, left=EDGE, bottom=H - EDGE)          # cell pigtail
    p.put("Q2", "F", p.face("Q2", "F", "/PROT_FET_D", "+x"), left=p.crt(p.fp("J3"))[2], bottom=H - EDGE)
    p.put("Q3", "F", p.face("Q3", "F", "/PROT_FET_D", "-x"), left=p.crt(p.fp("Q2"))[2], bottom=H - EDGE)
    p.put("J2", "F", 90, left=p.crt(p.fp("Q3"))[2], bottom=H - EDGE)    # output pigtail, PACK- beside Q3's sources
    p.put("F1", "F", 0, left=p.crt(p.fp("J3"))[2], bottom=p.crt(p.fp("Q2"))[1])
    p.put("J1", "F", p.mouth_rot("J1", "F", "+x"), right=w + 1.9, cy=H / 2)
    power_stage(p, w)
    p.put("D1", "F", p.face("D1", "F", "/VBUS", "-x"), right=w - EDGE, bottom=H - EDGE)   # VBUS TVS under J1
    p.put("LED1", "F", 0, right=w - EDGE, bottom=p.crt(p.fp("J1"))[1])
    p.put("R113", "F", 0, left=R113_AT_2S[0], top=R113_AT_2S[1])
    p.put("R112", "F", 0, left=R112_AT_2S[0], top=R112_AT_2S[1])
    p.put("U13", "F", 0, left=U13_AT_2S[0], top=U13_AT_2S[1])
    p.put("R94", "F", p.face("R94", "F", "/PACK-", "+x"), cx=R94_AT_2S[0], cy=R94_AT_2S[1])
    fixed = ("J11", "J3", "Q2", "Q3", "J2", "F1", "J1", "D1", "LED1", "R113", "R112", "U13", "R94")
    return fixed + POWER_STAGE, (0, 0, w, H), (0, 0, 28.3 + CHARGER_DX - 0.25, H)


def zones_2s(w):
    """The 2S protector parts' zones (x0, y0, x1, y1): the BAT_N side west of the split, the rest east of it."""
    pz = 28.3 + (w - 50.0) - 0.25                       # R71's zone: within 9 mm of Q2's gate pad
    return {r: (EDGE, 10.5, XB_2S - 0.15, 13.4) for r in WEST_2S} | \
           {"R71": (12.05, 14.9, XB_2S - 0.15, 17.3)} | \
           {r: (XB_2S + 0.15, 4.4, pz, 17.4) for r in EAST_2S}


# Charger parts packed somewhere other than near their pins, free of MAX_REACH: the TS, ILIM_HIZ and PROG dividers set
# DC levels, and the corner of U7 by J1 (where their pins are) has no room left. TS goes in the strip above the SYS
# row, with C36 (SDRV, reached by a via under U7); ILIM_HIZ and PROG in the pocket west of L2, between the SYS and PMID
# rows, off the board edge; C34, BAT's second bulk cap (C33 is at the pins), south by the PACK+ band's east end.
PACK_ZONE = {r: (28.3, EDGE, 42.8, 2.2) for r in ("R34", "R35", "R79", "C36")} | \
            {"C34": (32.2, 18.9, 37.6, 23.0 - EDGE)} | \
            {r: (28.3, 6.9, 31.3, 11.3) for r in ("R31", "R78", "R32", "R33")}


# U7's power stage, after the BQ25798 layout example (SLUSDV2C section 8.4.2): power pins (SYS, SW2, PGND, SW1, PMID,
# north to south) facing west, L2 across them with SW2's pad north and SW1's south, the SYS caps in a row north of L2
# and the PMID caps in a row south of it, each row's 100 nF cap nearest the pins. tools/route_pack.py pours SYS and
# PMID under the rows' power pads and runs PGND out between L2's pads to vias under its body; U7's power pins reach all
# of it on F.Cu, with no vias in pads. C33 (BAT), C22 (VBUS), C35 (REGN) and C19 (BTST2) sit at their pins, and C18
# (BTST1) under L2 with its SW1 pad on the SW1 pour (route_pack.py lays BTST1 from pin 4); the rest of the bulk caps
# (C23, C31, C34) are packed.
SYS_ROW = ("C32", "C27", "C28", "C29", "C30")    # east to west; tools/route_pack.py pours under them
PMID_ROW = ("C26", "C24", "C25")
POWER_STAGE = ("U7", "L2") + SYS_ROW + PMID_ROW + ("C33", "C22", "C35", "C19", "C18")
U7_AT = (40.0, 9.0)             # U7's centre: east pins (GND, I2C) toward J1, south pins (VBUS, REGN, D+/D-) J1's way
C18_EAST = 0.45                 # C18's courtyard past L2's east edge: its SW1 pad sits under the SW1 pour's end
C22_WEST = 0.27                 # C22 west of VBUS's pins 2 and 3, leaving BTST1 (pin 4) room for its via
VIA_LANE = 0.9                  # mm kept clear beyond the power stage caps' ground pads for their vias
L2_GAP = 2.2                    # mm from U7's power pin ends to L2's pads: the pours' necks and SW vias fit in it


def power_stage(p, w):
    ux, uy = U7_AT[0] + CHARGER_DX, U7_AT[1]
    p.put("U7", "F", p.face("U7", "F", "/SW1", "-x"), cx=ux, cy=uy)
    ux0, uy0, ux1, uy1 = p.crt(p.fp("U7"))
    xo = p.pad_box("U7", "25")[0]                    # the power pins' outer ends
    rot = p.face("L2", "F", "/SW1", "+y")
    p.pose("L2", "F", rot)
    lx1, cx1 = p.pad_box("L2", "1")[2], p.crt(p.fp("L2"))[2]
    p.put("L2", "F", rot, right=xo - L2_GAP + (cx1 - lx1), cy=p.pad_xy("U7", "27")[1])
    _, ly0, cx1, ly1 = p.crt(p.fp("L2"))                 # L2's courtyard where it now sits
    p.put("C18", "F", p.face("C18", "F", "/SW1", "+x"), right=cx1 + C18_EAST, top=ly1)   # under L2's SW1 pad
    for net, refs, edge in (("/CHG_SYS", SYS_ROW, "bottom"), ("/PMID", PMID_ROW, "top")):
        right = ux0
        for ref in refs:                                 # power pad toward L2, ground pad away from it
            rot = p.face(ref, "F", net, "+y" if edge == "bottom" else "-y")
            p.put(ref, "F", rot, right=right, **{edge: ly0 if edge == "bottom" else p.crt(p.fp("C18"))[3]})
            right = p.crt(p.fp(ref))[0]
    bat = [p.pad_xy("U7", n)[0] for n in ("22", "23")]
    p.put("C33", "F", p.face("C33", "F", "/PACK+", "+y"), cx=sum(bat) / 2 - 0.35, bottom=uy0)     # over BAT, clear
    vbus = [p.pad_xy("U7", n)[0] for n in ("2", "3")]                                              # of PROG
    p.put("C22", "F", p.face("C22", "F", "/VBUS", "-y"), cx=sum(vbus) / 2 - C22_WEST, top=uy1)  # BTST1's via east
    p.put("C35", "F", p.face("C35", "F", "/REGN", "-y"), left=p.pad_xy("U7", "4")[0], top=uy1 + ESCAPE)
    p.put("C19", "F", p.face("C19", "F", "/BTST2", "-x"), cx=p.pad_xy("U7", "19")[0] + 0.485, bottom=uy0 - ESCAPE)
    # escape room: the north pins east of C33 and the south pins east of C22 keep ESCAPE clear of passives
    p.boxes["F"] += [(p.crt(p.fp("C33"))[2], uy0 - ESCAPE, ux1, uy0), (p.crt(p.fp("C22"))[2], uy1, ux1, uy1 + ESCAPE),
                     (cx1, ly0, ux0, ly1)]               # and nothing between L2 and U7: the pours' necks
    for ref in SYS_ROW + ("C33",):                       # room for each cap's ground via, beyond its ground pad
        x0, y0, x1, _ = p.crt(p.fp(ref))
        p.boxes["F"].append((x0, y0 - VIA_LANE, x1, y0))
    for ref in PMID_ROW + ("C22", "C35"):
        x0, _, x1, y1 = p.crt(p.fp(ref))
        p.boxes["F"].append((x0, y1, x1, y1 + VIA_LANE))


# Hand-placed protector parts: C62 (VDD) and C63 (AVDD) at pins 1 and 2; R61, which feeds VDD from CELL+, on the
# CELL+ pour's top edge (VDD is the filtered side and runs to U13); and the BQ7791501's current sense, C68 across
# U13's SRP and SRN pins with R68 and R69 (the SRP/SRN filter) west of it. tools/route_pack.py runs Kelvin lines from
# R66's pads up to R68 and R69.
SENSE = ("C62", "C63", "R61", "C68", "R68", "R69")
KELVIN_ROOM = 0.9               # mm kept clear west of R68 and R69 for tools/route_pack.py's Kelvin vias
C62_GAP = 0.3                   # C62 and C63 this far off U13's courtyard: its pin 1 mark is printed there
R61_AT = (8.3, 12.9)            # R61's courtyard centre x and bottom: its CELL+ pad lands inside the pour's top edge


def sense(p):
    x0 = p.crt(p.fp("U13"))[0]
    p.put("C62", "F", p.face("C62", "F", "/PROT_VDD", "+x"), right=x0 - C62_GAP, cy=p.pad_xy("U13", "1")[1])
    p.put("C63", "F", p.face("C63", "F", "/PROT_AVDD", "+x"), right=x0 - C62_GAP, top=p.crt(p.fp("C62"))[3])
    p.put("R61", "F", p.face("R61", "F", "/CELL+", "+y"), cx=R61_AT[0], bottom=R61_AT[1])
    (_, srp), (_, srn) = p.pad_xy("U13", "10"), p.pad_xy("U13", "11")
    p.put("C68", "F", p.face("C68", "F", "/PROT_SRP", "-y"), right=x0, cy=(srp + srn) / 2 - 0.1)
    c0, cy0, _, cy1 = p.crt(p.fp("C68"))                 # R68 and R69 west of it; DSG (pin 12) leaves under them
    p.put("R68", "F", p.face("R68", "F", "/PROT_SRP", "+x"), right=c0, bottom=(cy0 + cy1) / 2)
    p.put("R69", "F", p.face("R69", "F", "/PROT_SRN", "+x"), right=c0, top=(cy0 + cy1) / 2)
    r0, ry0 = p.crt(p.fp("R68"))[:2]                     # the Kelvin lines' vias, west of R68's and R69's pads
    p.boxes["F"].append((r0 - KELVIN_ROOM, ry0, r0, p.crt(p.fp("R69"))[3]))


HEAD = (-2.5, 26.5)            # the right-angle layout's head spans these y
LAYOUTS = {
    "vertical": (50.0, 24.0, "F", vertical, [(0, 0, 50.0, 24.0)], [(0, 0), (50.0, 0), (50.0, 24.0), (0, 24.0)]),
    "rightangle": (64.0, 24.0, "F", rightangle, [(0, HEAD[0], 16.2, HEAD[1]), (16.2, 0, 64.0, 24.0)],
                   [(0, HEAD[0]), (16.2, HEAD[0]), (16.2, 0), (64.0, 0), (64.0, 24.0), (16.2, 24.0), (16.2, HEAD[1]),
                    (0, HEAD[1])]),
    "ontop": (58.0, H_ONTOP, "B", ontop, [(0, 0, 58.0, H_ONTOP)],
              [(0, 0), (58.0, 0), (58.0, H_ONTOP), (0, H_ONTOP)]),
    "compact": (None, None, "F", compact2s if BOARD == "pack2s" else compact, None, None),
}


def build(name, out, size=None, grid=None):
    """Place one layout and save it to out. Returns False if the passives don't fit."""
    global H, GRID
    w, H, smd, layout, rects, poly = LAYOUTS[name]
    if name == "compact":
        w, H = size or (COMPACT_2S if BOARD == "pack2s" else COMPACT)
        rects, poly = [(0, 0, w, H)], [(0, 0), (w, 0), (w, H), (0, H)]
    GRID = grid or GRID
    b = pcbnew.LoadBoard(str(SOURCE))
    doomed = list(b.GetTracks()) + list(b.Zones()) + list(b.Drawings()) + list(b.Groups())
    if doomed:                                  # pcbnew's lists go stale after removals: save and load again
        for item in doomed:
            b.Remove(item)
        with tempfile.TemporaryDirectory() as d:
            b.Save(str(Path(d) / "cleared.kicad_pcb"))
            b = pcbnew.LoadBoard(str(Path(d) / "cleared.kicad_pcb"))
    if name == "rightangle":
        swap(b, "J3", "Connector_AMASS", "AMASS_XT30PW-M_1x02_P2.50mm_Horizontal", "XT30PW-M", "XT30PW-M30.G.Y",
             (str(MODELS / "XT30PW-M.step"), (-2.5, 8.5, 0.0), 180.0))
        swap(b, "J11", "Connector_JST", "JST_XH_S4B-XH-A_1x04_P2.50mm_Horizontal", "Balance", "S4B-XH-A(LF)(SN)")
    if name == "compact":
        for ref in ("C18", "C19"):                      # boot caps: 0402 so C18 fits under L2 (schematic too)
            swap(b, ref, "Capacitor_SMD", "C_0402_1005Metric", "47nF", "0402B473K160NT", lcsc="C192385")
        # no attribute flags, as the 3S pack's old pads had (the 2S board's old J3 is through-hole: DRC compares them)
        swap(b, "J3", *WIRE16, "Cell pigtail", "XT30U-M", lcsc="C99101", attrs=0)
        swap(b, "J2", *WIRE16, "Pack lead", "XT30U-F", attrs=0)
    p = Placer(b, rects)
    fixed, charger, protector = layout(p)
    p.fixed(fixed)
    fids = ((w - 1.6, 1.6), (w - 1.6, H - 1.6), (1.6, H / 2))
    try:
        if name == "compact":                     # no free corner is left once the passives are in: go first
            at = (FID1_AT_2S, FID2_AT_2S) if BOARD == "pack2s" else ((1.8, 8.3), (w / 2, H / 2))
            for fid, (x, y) in zip(("FID1", "FID2", "FID3"), at + ((w - 8.0, H - 1.6),)):
                p.pack([fid], smd, (0, 0, w, H), target=(x, y))
            fids = ()
        zones = zones_2s(w) if BOARD == "pack2s" else {}
        for r in (PROTECTOR_2S if BOARD == "pack2s" else PROTECTOR):
            if r not in fixed:
                z = zones.get(r, protector)
                if r in NEAR_2S and BOARD == "pack2s":      # beside the balancer, wherever it landed
                    x0, y0, x1, y1 = p.crt(p.fp(NEAR_2S[r]))
                    z = (max(EDGE, x0 - NEAR_REACH_2S), max(EDGE, y0 - NEAR_REACH_2S),
                         min(z[2], x1 + NEAR_REACH_2S), min(H - EDGE, y1 + NEAR_REACH_2S))
                p.pack([r], smd, z)
        for r in (["L2"] if "L2" not in fixed else []) + [r for r in CHARGER if r not in fixed and p.fp(r)]:
            z = PACK_ZONE.get(r)
            p.pack([r], smd, (z[0] + CHARGER_DX, z[1], z[2] + CHARGER_DX, z[3]) if z else charger)
        if p.fp("TH2"):                         # the cell NTC, on the cells; R79 replaced it on 2026-10-26
            p.pack(["TH2"], "B" if smd == "F" else "F", (0, 0, w, H), target=(w / 2, H / 2))
        for fid, (x, y) in zip(("FID1", "FID2", "FID3"), fids):
            p.pack([fid], smd, (0, HEAD[0], w, HEAD[1]), target=(x, y))
    except RuntimeError as e:
        print(f"{name} {w} x {H}: {e}")
        return False
    outline(b, poly)
    b.Save(str(out))
    print(f"{name}: {w} x {H} mm -> {out}")
    return True


def main():
    global U13_AT_2S
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("layout", choices=LAYOUTS)
    ap.add_argument("--size", help="compact only: board size WxH in mm")
    ap.add_argument("--search", action="store_true", help="compact only: try sizes, smallest area first")
    ap.add_argument("--reach", type=float, help="max mm from a passive's pad to its anchor pin (fail otherwise)")
    ap.add_argument("--out", help="write here instead of editing the board in place")
    ap.add_argument("--in", dest="src", help="read this board instead of the pack board")
    ap.add_argument("--board", choices=list(packcfg.BOARDS), default="pack", help="the 3S pack (default) or the 2S pack")
    ap.add_argument("--u13", help="2S: U13's courtyard top-left corner X,Y (default %s,%s)" % U13_AT_2S)
    ap.add_argument("--led", choices=("edge", "stat"), default="edge", help="compact: LED1 on the right edge, or by STAT")
    a = ap.parse_args()
    global MAX_REACH
    if a.u13:
        U13_AT_2S = tuple(float(v) for v in a.u13.split(","))
    MAX_REACH = a.reach if a.reach is not None else COMPACT_REACH if a.layout == "compact" else None
    global SOURCE
    SOURCE = Path(a.src) if a.src else PCB
    out = Path(a.out) if a.out else PCB
    if a.search:
        sizes = sorted(((w / 2, h / 2) for w in range(60, 101) for h in range(36, 61) if 600 <= w * h / 4),
                       key=lambda s: s[0] * s[1])
        for size in sizes:
            if size[0] * size[1] >= 1300:
                break
            if build("compact", out, size, grid=0.5):
                print(f"smallest: {size[0]} x {size[1]} mm")
                return
        return
    size = tuple(float(v) for v in a.size.split("x")) if a.size else None
    if not build(a.layout, out, size):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
