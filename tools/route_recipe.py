"""Scripted routing for the brain's critical nets (kicad/thegoose.kicad_pcb, edited in place).

Run with KiCad's Python after tools/place_double.py:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/route_recipe.py

Everything this script adds (tracks, vias, zones it owns) sits in the PCB group "route_recipe", locked. Each run deletes
that group's items and builds them again, so it can be re-run after any placement change; Freerouting fills in the
rest afterwards and treats the locked copper as fixed. Coordinates come from pad positions, so they follow the parts.

U10 (RP2354A) sits at 0 deg: W column = pins 1-15 (pin 1 at the top), S row = pins 16-30 (16 at the west end),
E column = pins 31-45 (31 at the bottom), N row = pins 46-60 (46 at the east end). Pad pitch 0.4 mm; the pads run
from 3.05 to 3.85 mm off the centre and the exposed pad is 3.4 mm square.
"""
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "kicad/thegoose.kicad_pcb"
GROUP = "route_recipe"
MM = 1e6
OX, OY = 99.95, 99.95
LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "1": pcbnew.In1_Cu, "2": pcbnew.In2_Cu, "3": pcbnew.In3_Cu,
         "4": pcbnew.In4_Cu}

XIN, XOUT, XC = "Net-(U10-XIN)", "Net-(U10-XOUT)", "Net-(C57-Pad1)"
LX, AVDD = "Net-(U10-VREG_LX)", "Net-(U10-VREG_AVDD)"
SW, BST = "Net-(U4-SW)", "Net-(U4-BST)"
USB = {"P": "USB_P", "N": "USB_N", "MP": "/MCU & USB/USB_MCU_P", "MN": "/MCU & USB/USB_MCU_N",
       "AP": "/MCU & USB/USBA_P", "AN": "/MCU & USB/USBA_N", "GP": "/MCU & USB/USBA_GPIO_P",
       "GN": "/MCU & USB/USBA_GPIO_N"}
WU = 0.124                  # USB pair track width (90 ohm at a 0.127 mm gap on JLC06161H-3313, see thegoose.kicad_dru)
GU = 0.127                  # USB pair gap


class Recipe:
    def __init__(self, board):
        self.b = board
        self.items = []
        self.fp = {f.GetReference(): f for f in board.GetFootprints()}

    # ---- lookups ------------------------------------------------------------------------------------------------
    def net(self, name):
        n = self.b.FindNet(name)
        if n is None:
            for cand in self.b.GetNetsByName().values():
                if cand.GetNetname().endswith("/" + name):
                    return cand
            raise KeyError(name)
        return n

    def pad(self, ref, num):
        """Pad centre in board-local mm. The first pad with this number wins."""
        for p in self.fp[ref].Pads():
            if p.GetNumber() == str(num):
                q = p.GetPosition()
                return (q.x / MM - OX, q.y / MM - OY)
        raise KeyError((ref, num))

    def padnet(self, ref, num):
        for p in self.fp[ref].Pads():
            if p.GetNumber() == str(num):
                return p.GetNetname()
        raise KeyError((ref, num))

    def padof(self, ref, net):
        """Centre of the pad of ref on this net."""
        for p in self.fp[ref].Pads():
            if p.GetNetname() == net or p.GetNetname().endswith("/" + net):
                q = p.GetPosition()
                return (q.x / MM - OX, q.y / MM - OY)
        raise KeyError((ref, net))

    def pos(self, ref):
        q = self.fp[ref].GetPosition()
        return (q.x / MM - OX, q.y / MM - OY)

    # ---- copper -------------------------------------------------------------------------------------------------
    @staticmethod
    def v(x, y):
        return pcbnew.VECTOR2I(int(round((OX + x) * MM)), int(round((OY + y) * MM)))

    def _own(self, item):
        item.SetLocked(True)
        self.b.Add(item)
        self.items.append(item)

    def track(self, net, layer, pts, w):
        ni = self.net(net)
        for a, c in zip(pts[:-1], pts[1:]):
            if abs(a[0] - c[0]) < 1e-6 and abs(a[1] - c[1]) < 1e-6:
                continue
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(self.v(*a))
            t.SetEnd(self.v(*c))
            t.SetLayer(LAYER[layer])
            t.SetWidth(int(round(w * MM)))
            t.SetNet(ni)
            self._own(t)

    def via(self, net, x, y, d=0.45, drill=0.25):
        vi = pcbnew.PCB_VIA(self.b)
        vi.SetPosition(self.v(x, y))
        vi.SetWidth(int(round(d * MM)))
        vi.SetDrill(int(round(drill * MM)))
        vi.SetViaType(pcbnew.VIATYPE_THROUGH)
        vi.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        vi.SetNet(self.net(net))
        self._own(vi)
        return (x, y)

    def blocked(self, x, y, d, net, clr=0.2):
        """True if a through via of diameter d at (x, y) would come within clr of other-net copper or the edge."""
        rad = d / 2
        W = self.b.GetBoardEdgesBoundingBox()
        if (x - rad < 0.3 or y - rad < 0.3 or x + rad > W.GetWidth() / MM - 0.3
                or y + rad > W.GetHeight() / MM - 0.3):
            return True
        for f in self.b.GetFootprints():
            for pd in f.Pads():
                if pd.GetNetname() == net and net:
                    continue
                bb = pd.GetBoundingBox()
                x0, y0 = bb.GetLeft() / MM - OX, bb.GetTop() / MM - OY
                x1, y1 = bb.GetRight() / MM - OX, bb.GetBottom() / MM - OY
                dx = max(x0 - x, 0, x - x1)
                dy = max(y0 - y, 0, y - y1)
                if (dx * dx + dy * dy) ** 0.5 < rad + clr:
                    return True
        for t in self.b.GetTracks():
            if t.GetClass() == "PCB_VIA":            # any via: keep drilled holes apart (JLC 0.5 mm hole to hole)
                q = t.GetPosition()
                if ((q.x / MM - OX - x) ** 2 + (q.y / MM - OY - y) ** 2) ** 0.5 < (d + t.GetWidth(pcbnew.F_Cu) / MM) / 2 + 0.3:
                    return True
            if t.GetNetname() == net:
                continue
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                if ((q.x / MM - OX - x) ** 2 + (q.y / MM - OY - y) ** 2) ** 0.5 < rad + t.GetWidth(pcbnew.F_Cu) / MM / 2 + clr:
                    return True
                continue
            a, c = t.GetStart(), t.GetEnd()
            ax, ay, cx, cy = a.x / MM - OX, a.y / MM - OY, c.x / MM - OX, c.y / MM - OY
            vx, vy = cx - ax, cy - ay
            L2 = vx * vx + vy * vy
            u = 0 if L2 == 0 else max(0, min(1, ((x - ax) * vx + (y - ay) * vy) / L2))
            px, py = ax + u * vx, ay + u * vy
            if ((px - x) ** 2 + (py - y) ** 2) ** 0.5 < rad + t.GetWidth() / MM / 2 + clr:
                return True
        return False

    def vias_where_free(self, net, cands, d=0.6, drill=0.3, n=None):
        """Drop a via at each free candidate spot (up to n); returns the spots used."""
        used = []
        for x, y in cands:
            if n is not None and len(used) >= n:
                break
            if not self.blocked(x, y, d, net):
                self.via(net, x, y, d, drill)
                used.append((x, y))
        return used

    def zone(self, net, layer, pts, priority=10, clearance=0.2, min_w=0.2, solid=True, name=""):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(LAYER[layer])
        z.SetNet(self.net(net))
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(int(round((OX + x) * MM)), int(round((OY + y) * MM)))
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(int(round(clearance * MM)))
        z.SetMinThickness(int(round(min_w * MM)))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid is True else
                           pcbnew.ZONE_CONNECTION_THT_THERMAL if solid == "tht" else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(int(0.25 * MM))
        z.SetThermalReliefSpokeWidth(int(0.4 * MM))
        if name:
            z.SetZoneName(name)
        self._own(z)
        return z

    def rule_area(self, name, x0, y0, x1, y1):
        """Netless rule area on F.Cu and B.Cu that forbids nothing; thegoose.kicad_dru keys rules off its name."""
        z = pcbnew.ZONE(self.b)
        z.SetIsRuleArea(True)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        ls.AddLayer(pcbnew.B_Cu)
        z.SetLayerSet(ls)
        for setter in ("SetDoNotAllowTracks", "SetDoNotAllowVias", "SetDoNotAllowPads", "SetDoNotAllowZoneFills",
                       "SetDoNotAllowFootprints"):
            getattr(z, setter)(False)
        z.SetZoneName(name)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            ol.Append(int(round((OX + x) * MM)), int(round((OY + y) * MM)))
        self._own(z)


# ---------------------------------------------------------------------------------------------------------------------
# U10 fan-out. Supplies that can't leave outward drop through vias in the ring between the pad ends and the exposed
# pad; the 100 nF caps sit on the back on those vias (pad 1 on the via, GND pad toward the exposed pad; positions in
# tools/place_double.py CAP_ON_VIA). Pins 1 and 44/45 go outward. VREG_PGND (47) joins the exposed pad through a small
# F.Cu zone; VREG_AVDD (46) leaves east under the LX track, which runs north of pins 46/47 to L3.
# ---------------------------------------------------------------------------------------------------------------------
def u10_fanout(r):
    cx, cy = r.pos("U10")

    def p(dx, dy):
        return (cx + dx, cy + dy)

    w = 0.15
    V = {}
    V["a"] = r.via("+3V3", *p(-2.45, 2.4))          # pins 11 (W) and 20 (S)
    r.track("+3V3", "F", [p(-3.2, 1.2), p(-2.72, 1.2), p(-2.72, 2.13), V["a"]], w)
    r.track("+3V3", "F", [p(-1.2, 3.2), p(-1.2, 2.75), p(-2.1, 2.75), V["a"]], w)
    V["b"] = r.via("+1V1", *p(0.05, 2.35))          # pin 23
    r.track("+1V1", "F", [p(0.0, 3.2), p(0.0, 2.6), V["b"]], w)
    V["xo"] = r.via(XOUT, *p(-0.25, 4.5))           # pin 22 outward, to R43 on the back
    r.track(XOUT, "F", [p(-0.4, 3.7), p(-0.4, 4.15), V["xo"]], w)
    V["d"] = r.via("+3V3", *p(2.45, 2.4))           # pin 30
    r.track("+3V3", "F", [p(2.8, 3.2), p(2.8, 3.05), p(2.7, 2.6), V["d"]], w)   # steep, between pins 29 and 31
    V["e"] = r.via("+1V1", *p(-2.4, -0.8))          # pin 6
    r.track("+1V1", "F", [p(-3.2, -0.8), V["e"]], w)
    V["f"] = r.via("+3V3", *p(-4.5, -3.0))          # pin 1, outward
    r.track("+3V3", "F", [p(-3.7, -2.8), p(-4.2, -2.8), V["f"]], w)
    V["g"] = r.via("+3V3", *p(2.45, 0.3))           # pin 38
    r.track("+3V3", "F", [p(3.2, 0.0), p(2.75, 0.0), p(2.6, 0.15), V["g"]], w)
    V["h"] = r.via("+1V1", *p(2.45, -0.75))         # pin 39
    r.track("+1V1", "F", [p(3.2, -0.4), p(2.75, -0.4), V["h"]], w)
    V["i"] = r.via("+3V3", *p(4.55, -2.6))          # pins 44 and 45, joined, outward
    r.track("+3V3", "F", [p(3.7, -2.4), p(4.12, -2.4), p(4.12, -2.8), p(3.7, -2.8)], w)
    r.track("+3V3", "F", [p(4.12, -2.6), V["i"]], w)
    V["j"] = r.via("+3V3", *p(-0.2, -2.4))          # pins 53 and 54, joined
    r.track("+3V3", "F", [p(-0.4, -3.2), p(-0.4, -2.8), p(0.0, -2.8), p(0.0, -3.2)], w)
    r.track("+3V3", "F", [p(-0.2, -2.8), V["j"]], w)
    V["k"] = r.via("+1V1", *p(0.62, -2.4))          # pin 50 (VREG_FB)
    r.track("+1V1", "F", [p(1.2, -3.2), p(1.2, -2.75), V["k"]], w)
    V["l"] = r.via("+3V3", *p(1.6, -2.4))           # pin 49 (VREG_VIN)
    r.track("+3V3", "F", [p(1.6, -3.2), V["l"]], w)
    # PGND (47) to the exposed pad, plus the GND via under C49's GND pad
    r.zone("GND", "F", [p(2.2, -3.25), p(2.65, -3.25), p(2.65, -1.5), p(1.45, -1.5), p(1.45, -1.75), p(2.2, -1.75)],
           priority=30, clearance=0.2, min_w=0.15, solid=True, name="U10 PGND")
    r.via("GND", *p(2.56, -2.4))
    # VREG_AVDD (46) east to its via; C51 and R42 sit on the back by it
    V["n"] = r.via(AVDD, *p(4.4, -3.6))
    r.track(AVDD, "F", [p(2.8, -3.6), V["n"]], w)
    c51, r42 = r.padof("C51", AVDD), r.padof("R42", AVDD)
    r.track(AVDD, "B", [V["n"], (V["n"][0], c51[1] + 0.35), (c51[0], c51[1] + 0.35), c51], 0.2)
    r.track(AVDD, "B", [c51, r42], 0.2)
    r3 = r.padof("R42", "+3V3")
    r.track("+3V3", "B", [r3, (r3[0], r3[1] - 0.65)], 0.2)
    r.via("+3V3", r3[0], r3[1] - 0.65)
    c51g = r.padof("C51", "GND")
    r.track("GND", "B", [c51g, (c51g[0], c51g[1] - 0.6)], 0.4)
    r.via("GND", c51g[0], c51g[1] - 0.6)
    # LX: north of pins 46/47, then east to L3's LX pad
    lxp = r.padof("L3", LX)
    r.track(LX, "F", [p(2.0, -3.75), (cx + 2.0, lxp[1])], 0.2)
    r.track(LX, "F", [(cx + 2.0, lxp[1]), lxp], 0.3)
    # L3's +1V1 pad down to C52 on the back
    l3 = r.padof("L3", "+1V1")
    c52 = r.padof("C52", "+1V1")
    r.track("+1V1", "F", [l3, (l3[0], c52[1])], 0.4)
    V["l3"] = r.via("+1V1", l3[0], c52[1])
    c52g = r.padof("C52", "GND")
    r.via("GND", c52g[0], c52g[1] + 0.05)
    # exposed pad: 3 x 3 GND vias (filled and capped)
    for dx in (-1.13, 0.0, 1.13):
        for dy in (-1.13, 0.0, 1.13):
            r.via("GND", *p(dx, dy))
    # back GND pad of every ring cap: a small B.Cu GND zone under the exposed pad joins them to its vias
    r.zone("GND", "B", [p(-2.05, -1.95), p(2.05, -1.95), p(2.05, 2.85), p(-2.05, 2.85)], priority=30,
           clearance=0.2, min_w=0.2, solid=True, name="U10 back GND")
    # extra +3V3 caps beside U10: each pad straight down to its plane
    for ref in ("C46", "C47", "C50"):
        for net in ("+3V3", "GND"):
            q = r.padof(ref, net)
            r.vias_where_free(net, [q, (q[0] + 0.6, q[1]), (q[0] - 0.6, q[1])], d=0.45, drill=0.25, n=1)
    # GND pads of the two outward caps get their own vias
    g = r.padof("C41", "GND")                        # (C45's GND pad reaches the B.Cu GND fill)
    r.via("GND", *g)
    return V


# ---------------------------------------------------------------------------------------------------------------------
# U10 escapes. The 0.4 mm pitch east and south pads are too tight for the autorouter's own fan-out, so each GPIO that
# leaves on another layer gets a short F.Cu stub fanning out to a via on a 0.7 mm pitch. Freerouting takes it from
# the via.
# ---------------------------------------------------------------------------------------------------------------------
ESC_E = [(43, 29.35, -2.5), (42, 29.1, -1.8), (41, 29.1, -1.1), (40, 29.1, -0.4),      # pin, via x, via dy
         (35, 28.4, 1.5), (34, 28.4, 2.2), (33, 28.4, 2.9), (32, 28.4, 3.6)]
ESC_S = [24, 25, 26, 27, 28]                         # fan to a via row 21.1 mm down, 0.8 mm apart


def u10_escapes(r):
    cx, cy = r.pos("U10")
    for pin, vx, vdy in ESC_E:                       # upper group fans up-right, lower group down-right
        q = r.pad("U10", pin)
        net = r.padnet("U10", pin)
        vy = cy + vdy
        bend = max(vx - 0.35 - abs(vy - q[1]), q[0] + 0.55)
        r.track(net, "F", [q, (bend, q[1]), (vx - 0.3, vy), (vx, vy)], 0.15)
        r.via(net, vx, vy)
    for i, pin in enumerate(ESC_S):                  # parallel 45-degree fan to a row 0.8 mm apart
        q = r.pad("U10", pin)
        net = r.padnet("U10", pin)
        vx, vy = cx + 0.6 + 0.8 * i, cy + 5.8
        r.track(net, "F", [q, (q[0], vy - (vx - q[0])), (vx, vy)], 0.15)
        r.via(net, vx, vy)


# ---------------------------------------------------------------------------------------------------------------------
# U10 west side: IO1-IO6 to the vias in R55-R60's U10-side pads (a column at x 16.81, one per J5 row). Between that
# column and the pins there is room for three F.Cu lanes west of C41's vias and J1's shell peg, so:
# - IO2-IO4 (pins 3-5) run straight west and turn north on lanes 0.32 mm apart, the higher pin on the eastern lane.
# - IO1 (pin 2) drops through a via just inside the pin ring and runs north on In2, west of J1's shell pegs.
# - IO5 (pin 12) runs up the strip between the pin toes and C47/C50's vias, west between C47's two vias, and drops to
#   In2 for the run north (it would cross IO1-IO4 on F.Cu).
# - IO6 (pin 13) runs down the same strip, under C50, and north on F.Cu to its via.
# ---------------------------------------------------------------------------------------------------------------------
W_LANES = {"IO2_GPIO": 17.92, "IO3_GPIO": 17.60, "IO4_GPIO": 17.28}


def u10_west(r):
    w = 0.15

    def ends(sig):
        pin = next(p for p in r.fp["U10"].Pads() if p.GetNetname() == sig)
        q = pin.GetPosition()
        return (q.x / MM - OX, q.y / MM - OY), r.padof("R" + str(54 + int(sig[2])), sig)

    for sig, x in W_LANES.items():
        q, v = ends(sig)
        top = v[1] + (x - v[0])                       # 45-degree run into the via from the south-east
        if sig == "IO4_GPIO":                         # bottom pin: step onto its lane with a 45-degree jog
            r.track(sig, "F", [q, (x + 0.2, q[1]), (x, q[1] - 0.2), (x, top), v], w)
        else:
            r.track(sig, "F", [q, (x, q[1]), (x, top), v], w)
    q, v = ends("IO1_GPIO")
    vi = (q[0] + 1.0, q[1])
    r.track("IO1_GPIO", "F", [q, vi], w)
    r.via("IO1_GPIO", *vi)
    x = 17.95
    r.track("IO1_GPIO", "2", [vi, (vi[0] - 1.3, vi[1] - 1.3), (vi[0] - 1.3, vi[1] - 2.3),
                              (x, vi[1] - 2.3 - (vi[0] - 1.3 - x)), (x, v[1] + (x - v[0])), v], w)
    q, v = ends("IO5_GPIO")
    xs = q[0] - 0.71                                  # the strip between the pin toes and the 18.3 via column
    vi = (17.55, 16.7)
    r.track("IO5_GPIO", "F", [q, (xs, q[1]), (xs, vi[1]), vi], w)
    r.via("IO5_GPIO", *vi)
    r.track("IO5_GPIO", "2", [vi, (vi[0], v[1] + (vi[0] - v[0])), v], w)
    q, v = ends("IO6_GPIO")
    x = 17.08
    r.track("IO6_GPIO", "F", [q, (xs, q[1]), (xs, 18.85), (x, 18.85), (x, v[1] + (x - v[0])), v], w)


# ---------------------------------------------------------------------------------------------------------------------
# U10 south-west: M5 and M6 (pins 16-19) to the IN pins of U3 and U17. The four lines run west in the strip between
# the pin toes and Y1's top pads, each pin one lane lower than the pin west of it, so nothing crosses: M5A straight
# across to U3, M5B down to U3's IN2, M6A and M6B down two lanes east of U3 to U17. No signal runs over the crystal.
# ---------------------------------------------------------------------------------------------------------------------
def u10_southwest(r):
    w = 0.15
    p = {n: r.pad("U10", n) for n in (16, 17, 18, 19)}
    u3 = {n: r.pad("U3", n) for n in (2, 3)}
    u17 = {n: r.pad("U17", n) for n in (2, 3)}
    r.track("GPIO12_M5A", "F", [p[16], (p[16][0], u3[3][1]), u3[3]], w)
    y = 19.9
    xd = u3[2][0] + 1.1 + (u3[2][1] - y)              # 45 degrees down into U3 pin 2, ending at its toe
    r.track("GPIO13_M5B", "F", [p[17], (p[17][0], y), (xd, y), (u3[2][0] + 1.1, u3[2][1]), u3[2]], w)
    for pin, net, y, x, dst in ((18, "GPIO14_M6A", 20.25, 15.6, u17[3]), (19, "GPIO15_M6B", 20.6, 15.95, u17[2])):
        r.track(net, "F", [p[pin], (p[pin][0], y), (x, y), (x, dst[1]), dst], w)


# ---------------------------------------------------------------------------------------------------------------------
# USB-C. J1 sits at 180 deg, so its data pads run west to east B6 (P), A7 (N), A6 (P), B7 (N). A6/B7 go straight down
# to R44/R45 and on into U10 pins 52/51 with no vias. The flipped contacts B6/A7 drop through vias; on the back they
# join the pair at vias in R44/R45's J1-side pads, and U6 (ESD) taps it there.
# ---------------------------------------------------------------------------------------------------------------------
def usb_c(r):
    a6, b7 = r.pad("J1", "A6"), r.pad("J1", "B7")
    b6, a7 = r.pad("J1", "B6"), r.pad("J1", "A7")
    r44j, r45j = r.padof("R44", USB["P"]), r.padof("R45", USB["N"])
    r44m, r45m = r.padof("R44", USB["MP"]), r.padof("R45", USB["MN"])
    u52, u51 = r.pad("U10", 52), r.pad("U10", 51)
    yd = r44j[1] - 0.4 - abs(a6[0] - r44j[0])        # where the main pair turns toward R44/R45
    r.track(USB["P"], "F", [a6, (a6[0], yd), (r44j[0], r44j[1] - 0.4), r44j], WU)
    r.track(USB["N"], "F", [b7, (b7[0], yd), (r45j[0], r45j[1] - 0.4), r45j], WU)
    # R44/R45 to U10: converge on pins 52/51 (0.4 mm apart)
    yt = u52[1] - 0.55
    r.track(USB["MP"], "F", [r44m, (r44m[0], yt - abs(r44m[0] - u52[0])), (u52[0], yt)], WU)
    r.track(USB["MN"], "F", [r45m, (r45m[0], yt - abs(r45m[0] - u51[0])), (u51[0], yt)], WU)
    r.track(USB["MP"], "F", [(u52[0], yt), u52], WU)
    r.track(USB["MN"], "F", [(u51[0], yt), u51], WU)
    # flipped contacts B6/A7 through vias; on the back they join the pair at vias in R44/R45's J1-side pads
    vb6 = r.via(USB["P"], b6[0] - 0.1, b6[1] + 1.265)
    va7 = r.via(USB["N"], a7[0], a7[1] + 1.065)
    r.track(USB["P"], "F", [b6, (b6[0], b6[1] + 0.9), vb6], WU)
    r.track(USB["N"], "F", [a7, va7], WU)
    vp = r.via(USB["P"], *r44j)
    vn = r.via(USB["N"], *r45j)
    r.track(USB["P"], "B", [vb6, vp], WU)
    r.track(USB["N"], "B", [va7, (vn[0], va7[1]), vn], WU)
    # U6 (ESD, back, 0 deg): N on its top row right under R45's via, P on its bottom row, reached round the west
    # side; GND leaves west from pin 2 inside the P loop, +3V3 east from pin 5
    un = max([r.pad("U6", "3"), r.pad("U6", "4")], key=lambda q: q[0])
    up = min([r.pad("U6", "1"), r.pad("U6", "6")], key=lambda q: q[0])
    r.track(USB["N"], "B", [vn, un], WU)
    xw = up[0] - 1.7
    r.track(USB["P"], "B", [vp, (xw, vp[1]), (xw, up[1]), up], WU)
    # U6's bonded I/O pin pairs (1/6 = D+, 3/4 = D-) joined under its body
    r.track(USB["N"], "B", [r.pad("U6", "3"), r.pad("U6", "4")], WU)
    r.track(USB["P"], "B", [r.pad("U6", "1"), r.pad("U6", "6")], WU)
    g2, s5 = r.pad("U6", "2"), r.pad("U6", "5")
    r.track("GND", "B", [g2, (g2[0] - 1.1, g2[1])], 0.4)
    r.via("GND", g2[0] - 1.1, g2[1])
    r.track("+3V3", "B", [s5, (s5[0] + 1.1, s5[1])], 0.3)
    r.via("+3V3", s5[0] + 1.1, s5[1])
    # GND return via beside the flipped-contact vias
    r.via("GND", vb6[0] - 0.65, vb6[1] + 0.55)
    # CC pull-downs: a via from each CC pad, then on the back to its 5.1k; their GND pads get a via each
    for cc, ref, dx, gdx in (("A5", "R99", 0.65, 0.65), ("B5", "R100", -0.25, -0.65)):
        c = r.pad("J1", cc)
        n = r.padnet("J1", cc)
        rp = r.padof(ref, n)
        vc = r.via(n, c[0] + dx, c[1] + 1.2)
        r.track(n, "F", [c, (c[0], c[1] + 0.65), vc], 0.15)
        r.track(n, "B", [vc, (rp[0], vc[1]), rp], 0.15)
        g = r.padof(ref, "GND")
        r.track("GND", "B", [g, (g[0] + gdx, g[1])], 0.4)
        r.via("GND", g[0] + gdx, g[1])
    # rule area: the pair splits and necks down at J1, R44/R45, U6 and U10's pins
    r.rule_area("USB fan-out", xw - 0.6, a6[1] - 0.6, max(b7[0], r45j[0], un[0]) + 1.0, u52[1] + 0.5)


# ---------------------------------------------------------------------------------------------------------------------
# USB-A. U10 pins 37 (D+) / 36 (D-) east through R48/R49 (22 R at the source), then a coupled run along the gap between
# J4's pins and J3's body, up into J4 pins 3 (D+) and 2 (D-). U11 (ESD) and the 15k host pull-downs R109/R114 sit on
# the back on J4's own pins, so the pair needs no vias.
# ---------------------------------------------------------------------------------------------------------------------
def usb_a(r):
    u37, u36 = r.pad("U10", 37), r.pad("U10", 36)
    r48g, r49g = r.padof("R48", USB["GP"]), r.padof("R49", USB["GN"])
    r48a, r49a = r.padof("R48", USB["AP"]), r.padof("R49", USB["AN"])
    jp, jn = r.pad("J4", 3), r.pad("J4", 2)
    xs = u37[0] + 0.75
    xs = r48g[0] - 0.42                              # straight east between the escape groups, then fan to R48/R49
    r.track(USB["GP"], "F", [u37, (xs, u37[1]), (xs + abs(u37[1] - r48g[1]), r48g[1]), r48g], WU)
    r.track(USB["GN"], "F", [u36, (xs, u36[1]), (xs + abs(u36[1] - r49g[1]), r49g[1]), r49g], WU)
    yp = jp[1] + 2.3                                 # coupled run between J4's pins and J3's pads: D+ on top
    yn = yp + WU + GU
    r.track(USB["AP"], "F", [r48a, (r48a[0] + abs(r48a[1] - yp), yp), (jp[0] - 0.4, yp), (jp[0], yp - 0.4), jp], WU)
    r.track(USB["AN"], "F", [r49a, (r49a[0] + abs(r49a[1] - yn), yn), (jn[0] - 0.4, yn), (jn[0], yn - 0.4), jn], WU)
    # back: U11 (270 deg) and the pull-downs hang off J4's own pins
    upb = max([r.pad("U11", "1"), r.pad("U11", "6")], key=lambda q: q[1])
    unb = max([r.pad("U11", "3"), r.pad("U11", "4")], key=lambda q: q[1])
    r.track(USB["AP"], "B", [jp, (jp[0], upb[1] + 0.6), upb], WU)
    r.track(USB["AN"], "B", [jn, (jn[0], unb[1] + 0.6), unb], WU)
    # U11's bonded I/O pin pairs (1/6 = D+, 3/4 = D-) joined along its pin columns
    r.track(USB["AP"], "B", [r.pad("U11", "1"), r.pad("U11", "6")], WU)
    r.track(USB["AN"], "B", [r.pad("U11", "3"), r.pad("U11", "4")], WU)
    rp, rn = r.padof("R109", USB["AP"]), r.padof("R114", USB["AN"])
    r.track(USB["AP"], "B", [upb, (rp[0], upb[1]), rp], 0.2)
    r.track(USB["AN"], "B", [unb, (rn[0], unb[1]), rn], 0.2)
    for ref in ("R109", "R114"):
        g = r.padof(ref, "GND")
        r.track("GND", "B", [g, (g[0], g[1] - 0.6)], 0.4)
        r.via("GND", g[0], g[1] - 0.6)
    g2, v5 = r.pad("U11", "2"), r.pad("U11", "5")
    r.track("GND", "B", [g2, (g2[0], g2[1] - 0.75)], 0.4)
    r.via("GND", g2[0], g2[1] - 0.75)
    r.track("VCC", "B", [v5, (v5[0], v5[1] + 0.85)], 0.5)
    r.via("VCC", v5[0], v5[1] + 0.85, d=0.6, drill=0.3)
    r.rule_area("USB fan-out", u37[0] - 0.5, r48g[1] - 0.7, r49a[0] + 1.3, r49g[1] + 0.7)
    r.rule_area("USB fan-out", jp[0] - 1.0, upb[1] - 2.9, jn[0] + 1.0, yn + 0.5)


# ---------------------------------------------------------------------------------------------------------------------
# Crystal. Y1 is on the front under pins 21/22: XIN runs straight to its NW pad; XOUT drops through a via outside pin 22
# to R43 on the back and comes up again at Y1's SE pad. The load caps sit on the back under Y1.
# ---------------------------------------------------------------------------------------------------------------------
def crystal(r, V):
    u21 = r.pad("U10", 21)
    yxi = r.padof("Y1", XIN)                         # Y1 at 180 deg: XIN pad NE, under pin 21
    r.track(XIN, "F", [u21, (yxi[0], yxi[1])], 0.15)
    vxi = r.via(XIN, *yxi)                           # via in Y1's XIN pad, down to C56
    c56 = r.padof("C56", XIN)
    r.track(XIN, "B", [vxi, c56], 0.2)
    r43o, r43c = r.padof("R43", XOUT), r.padof("R43", XC)
    r.track(XOUT, "B", [V["xo"], r43o], 0.15)
    c57 = r.padof("C57", XC)                         # C57 at 270 deg: XC pad north, GND pad south
    r.track(XC, "B", [r43c, (c57[0], r43c[1]), c57], 0.15)
    yxc = r.padof("Y1", XC)                          # SW pad
    vxc = r.via(XC, c57[0] - 0.7, c57[1])
    r.track(XC, "B", [c57, vxc], 0.15)
    r.track(XC, "F", [vxc, (vxc[0], yxc[1]), yxc], 0.2)
    y = r.pos("Y1")
    r.via("GND", *y)                                 # between Y1's four pads: C56's GND and the guard
    for num in ("2", "4"):
        r.via("GND", *r.pad("Y1", num))
    # B.Cu GND under the crystal's south half: joins C56/C57's GND pads to the centre via and guards XIN/XC
    r.zone("GND", "B", [(y[0] - 2.4, y[1] - 0.2), (y[0] + 2.3, y[1] - 0.2), (y[0] + 2.3, y[1] + 1.25),
                        (y[0] - 2.4, y[1] + 1.25)], priority=30, clearance=0.2, min_w=0.2, solid=True, name="Y1 guard")


# ---------------------------------------------------------------------------------------------------------------------
# Buck hot loop on the front: VIN caps against pins 2/3, the SW node from pin 8 to L1, BST cap under U4.
# ---------------------------------------------------------------------------------------------------------------------
def buck(r):
    p2, p3, p8, p1 = r.pad("U4", 2), r.pad("U4", 3), r.pad("U4", 8), r.pad("U4", 1)
    c74v, c73v = r.padof("C74", "VSYS"), r.padof("C73", "VSYS")
    l1s = r.padof("L1", SW)
    r.zone("VSYS", "F", [(p3[0] - 0.75, p3[1] - 0.45), (c74v[0] + 0.35, c74v[1] - 0.45),
                         (c74v[0] + 0.35, c73v[1] + 0.55), (p2[0] - 0.75, p2[1] + 0.45)],
           priority=20, clearance=0.2, min_w=0.2, solid=True, name="U4 VIN")
    for dy in (-0.35, 0.35):
        r.via("VSYS", c74v[0] - 0.5, (p2[1] + p3[1]) / 2 + dy, d=0.6, drill=0.3)
    r.track(SW, "F", [p8, (l1s[0], p8[1])], 0.8)
    c14s, c14b = r.padof("C14", SW), r.padof("C14", BST)
    r.track(SW, "F", [c14s, (p8[0] + 0.3, c14s[1] - 0.6), (p8[0] + 0.3, p8[1])], 0.4)
    r.track(BST, "F", [p1, (p1[0], c14b[1] - 0.6), (c14b[0] + 0.3, c14b[1] - 0.6), c14b], 0.3)
    for ref in ("C74", "C73"):
        g = r.padof(ref, "GND")
        r.via("GND", g[0] + 0.55, g[1], d=0.6, drill=0.3)
        r.via("GND", g[0], g[1] + (0.75 if ref == "C73" else -0.65), d=0.6, drill=0.3)
    # U4 exposed pad: 2 x 3 GND vias
    cx, cy = r.pos("U4")
    for dx in (-0.6, 0.6):
        for dy in (-1.1, 0.0, 1.1):
            r.via("GND", cx + dx, cy + dy, d=0.6, drill=0.3)
    # VCC out of L1 onto the B.Cu trunk (vias also reach the In3 GND plane only by clearance)
    l1v = r.padof("L1", "VCC")
    for dy in (-1.6, -0.55, 0.55, 1.6):
        r.via("VCC", l1v[0], l1v[1] + dy, d=0.6, drill=0.3)
    for ref in ("C5", "C8", "C12"):                  # west half of each GND pad, clear of L1's SW pad
        g = r.padof(ref, "GND")
        r.via("GND", g[0] - 0.25, g[1], d=0.6, drill=0.3)


# ---------------------------------------------------------------------------------------------------------------------
# Motor drivers. OUT1/OUT2 run straight to their PH connector at 0.6 mm. VM (pin 5) drops through two vias in the
# 100 nF cap's VSYS pad on the back into the In3 VSYS area; the 10 uF joins on the back. IPROPI leaves pin 1 through a via
# beside the pin to its 1.2k on the back. GND (pin 7, exposed pad) is the F.Cu pour plus the footprint's thermal vias.
# ---------------------------------------------------------------------------------------------------------------------
DRIVERS = [("U1", "M1", "C4", "C3", "R101"), ("U15", "M2", "C76", "C75", "R102"), ("U2", "M3", "C7", "C6", "R103"),
           ("U16", "M4", "C78", "C77", "R104"), ("U3", "M5", "C11", "C10", "R105"), ("U17", "M6", "C80", "C79", "R106")]


def drivers(r):
    for u, m, cs, cb, ri in DRIVERS:
        ux, uy = r.pos(u)
        right = ux > 33
        sg = 1 if right else -1
        for pin, mpin in (("6", "1"), ("8", "2")):
            a, mp = r.pad(u, pin), r.pad(m, mpin)
            net = r.padnet(u, pin)
            r.track(net, "F", [a, (mp[0] - sg * 1.1, a[1]), mp], 0.6)
        vm = r.pad(u, "5")
        cv = r.padof(cs, "VSYS")
        r.track("VSYS", "F", [vm, (vm[0] + sg * 0.32, cv[1])], 1.0)
        r.via("VSYS", vm[0] + sg * 0.32, cv[1], d=0.6, drill=0.3)
        r.via("VSYS", vm[0] - sg * 0.55, cv[1] + (0.05 if right else -0.05), d=0.6, drill=0.3)
        bv = r.padof(cb, "VSYS")
        if right and ((bv[0] - cv[0]) ** 2 + (bv[1] - cv[1]) ** 2) ** 0.5 < 4.0:
            r.track("VSYS", "B", [(vm[0] - sg * 0.55, cv[1] + 0.05), bv], 1.0)
        else:                                        # via just beyond the VSYS pad, away from the GND pad
            g = r.padof(cb, "GND")
            ux, uy = bv[0] - g[0], bv[1] - g[1]
            L = (ux * ux + uy * uy) ** 0.5
            ux, uy = ux / L, uy / L
            cands = [(bv[0] + ux * 0.95 + uy * k, bv[1] + uy * 0.95 - ux * k) for k in (0.0, 0.5, -0.5)]
            for spot in r.vias_where_free("VSYS", cands, n=1):
                r.track("VSYS", "B", [bv, spot], 1.0)
        # right drivers: IN2, IN1 and VREF each take a short stub west to a via, so the riser channel stays clear
        if right:
            for pin in ("2", "3", "4"):
                q = r.pad(u, pin)
                vx = q[0] - 1.97
                r.track(r.padnet(u, pin), "F", [q, (vx, q[1])], 0.15)
                r.via(r.padnet(u, pin), vx, q[1])
        # IPROPI: via just past pin 1's outer end, then its resistor on the back
        p1 = r.pad(u, "1")
        rp = r.padof(ri, r.padnet(u, "1"))
        vy = p1[1] - 0.65 if right else p1[1] + 0.65
        vi = r.via(r.padnet(u, "1"), p1[0] + (0.0 if right else -0.07), vy)
        r.track(r.padnet(u, "1"), "F", [p1, vi], 0.2)
        r.track(r.padnet(u, "1"), "B", [vi, rp], 0.2)


# ---------------------------------------------------------------------------------------------------------------------
# Battery entry: PACK+ from J3 pad 2 to Q1's source pins as an F.Cu pour; Q1's drain pins in a VSYS pour with vias into
# the In3 VSYS area; the gate network (R40, C72 from PACK+, C71 to VSYS) on the back under Q1.
# ---------------------------------------------------------------------------------------------------------------------
def battery(r):
    j = r.pad("J3", "2")
    src = [r.pad("Q1", n) for n in ("1", "2", "3")]
    drn = [r.pad("Q1", n) for n in ("5", "6", "7", "8")]
    x1 = max(q[0] for q in src) + 0.45
    ys = src[0][1]
    r.zone("PACK+", "F", [(j[0] - 1.9, j[1] - 1.85), (j[0] + 2.0, j[1] - 1.85), (src[0][0] - 1.1, ys - 3.4),
                          (x1, ys - 1.6), (x1, ys + 1.2), (src[0][0] - 1.35, ys + 1.2), (j[0] - 1.9, j[1] + 2.3)],
           priority=20, clearance=0.2, min_w=0.25, solid=True, name="PACK+ J3-Q1")
    yd = drn[0][1]
    xa, xb = min(q[0] for q in drn) - 0.45, max(q[0] for q in drn) + 0.28
    r.zone("VSYS", "F", [(xa, yd - 1.45), (xb, yd - 1.45), (xb, yd + 0.98), (xa, yd + 0.98)], priority=20,
           clearance=0.2, min_w=0.25, solid=True, name="VSYS Q1 drain")
    r.vias_where_free("VSYS", [(x, yd - 1.0) for x in (xa + 0.45, xa + 1.3, xa + 2.15, xa + 3.0, xa + 3.85)] +
                      [(x, yd + 0.65) for x in (xa + 0.45, xa + 1.3, xa + 2.15, xa + 3.0, xa + 3.85)], d=0.6, drill=0.3)
    # gate network: PACK+ pads of R40/C72 via a small B.Cu pour fed through a via in the F.Cu PACK+ pour
    rp, cp = r.padof("R40", "PACK+"), r.padof("C72", "PACK+")
    vpk = (min(rp[0], cp[0]) - 0.75, (rp[1] + cp[1]) / 2)   # west of R40/C72's PACK+ pads, inside the F.Cu pour
    r.via("PACK+", *vpk, d=0.6, drill=0.3)
    xe = max(rp[0], cp[0]) + 0.5                     # east edge of the B.Cu PACK+ patch, clear of the gate pads
    r.zone("PACK+", "B", [(vpk[0] - 0.5, rp[1] - 0.55), (xe, rp[1] - 0.55), (xe, cp[1] + 0.75),
                          (vpk[0] - 0.5, cp[1] + 0.75)], priority=20, clearance=0.2, min_w=0.2, solid=True,
           name="PACK+ gate net")
    r.via("VSYS", *r.padof("R52", "VSYS"))          # battery-sense divider top, straight into In3 VSYS
    for ref in ("C15", "C71", "D4"):
        v = r.padof(ref, "VSYS")
        r.vias_where_free("VSYS", [v, (v[0], v[1] + 0.6), (v[0], v[1] - 0.6), (v[0] + 0.6, v[1])], d=0.6, drill=0.3, n=1)
    for ref in ("D4", "C15"):
        g = r.padof(ref, "GND")
        r.vias_where_free("GND", [g, (g[0], g[1] + 0.6), (g[0], g[1] - 0.6), (g[0] + 0.6, g[1])], d=0.6, drill=0.3, n=1)


# ---------------------------------------------------------------------------------------------------------------------
# VCC side feeds. The In3 VCC area covers J5 and a band under J1/J12/U14. F2 (USB-A VBUS PTC) and U11 sit outside it
# under J4, so a 0.5 mm B.Cu track along the top edge carries VCC to them; U11's supply pin hops over to it on In2.
# ---------------------------------------------------------------------------------------------------------------------
def vcc(r):
    f2v, f2b = r.padof("F2", "VCC"), r.padof("F2", "Net-(J4-VBUS)")
    yt = 1.05
    v0 = r.via("VCC", 35.9, yt, d=0.6, drill=0.3)
    r.track("VCC", "B", [v0, (f2v[0], yt), f2v], 0.5)
    u5 = r.pad("U11", "5")
    vu = (u5[0], u5[1] + 0.85)                       # U11's VCC via (usb_a)
    vh = r.via("VCC", u5[0] + 1.45, 6.9, d=0.6, drill=0.3)
    r.track("VCC", "2", [vu, (vh[0], vu[1] - 1.45), vh], 0.5)    # on In2, not under J4's shell on F.Cu
    r.track("VCC", "B", [vh, (vh[0], yt)], 0.5)
    jv = r.pad("J4", "1")
    c59 = r.padof("C59", "Net-(J4-VBUS)")
    r.track("Net-(J4-VBUS)", "B", [f2b, (f2b[0], jv[1] - 1.2), jv], 0.5)
    r.track("Net-(J4-VBUS)", "B", [f2b, (c59[0], f2b[1]), c59], 0.5)
    g = r.padof("C59", "GND")
    r.via("GND", g[0], g[1] - 0.75, d=0.6, drill=0.3)
    r.track("GND", "B", [g, (g[0], g[1] - 0.75)], 0.5)
    # U14 (LED buffer) and C69 sit in the VCC band: their VCC pads straight down to In2
    u14 = r.padof("U14", "VCC")
    r.via("VCC", u14[0], u14[1] - 0.9, d=0.6, drill=0.3)
    r.track("VCC", "B", [u14, (u14[0], u14[1] - 0.9)], 0.5)
    c69 = r.padof("C69", "VCC")
    r.via("VCC", c69[0] - 0.7, c69[1], d=0.6, drill=0.3)
    r.track("VCC", "B", [c69, (c69[0] - 0.7, c69[1])], 0.5)
    for ref in ("U14", "C69"):
        for pd in r.fp[ref].Pads():
            if pd.GetNetname() == "GND":
                q = pd.GetPosition()
                gx, gy = q.x / MM - OX, q.y / MM - OY
                r.vias_where_free("GND", [(gx, gy + 0.85), (gx, gy - 0.85), (gx + 0.8, gy), (gx - 0.8, gy)],
                                  d=0.45, drill=0.25, n=1)
    # J12 data out of U14 to J12 pin 2, inside the band
    j2, u4 = r.pad("J12", "2"), r.padof("U14", "Net-(J12-Pin_2)")
    r.track("Net-(J12-Pin_2)", "B", [u4, (j2[0] + 1.3, u4[1]), (j2[0] + 1.3, j2[1]), j2], 0.25)
    # LED_DIN arrives on F.Cu; a via by U14 pin 2 drops it inside the band
    ld = r.padof("U14", "LED_DIN")
    vl = r.via("LED_DIN", ld[0], ld[1] + 1.05)
    r.track("LED_DIN", "B", [ld, vl], 0.2)
    # VCC trunk on B.Cu from the buck's output caps (under L1) up the west side to J5's VCC column; D3 and the
    # buck's feedback divider (R26, sensed at the output caps) hang off it
    c5 = r.padof("C5", "VCC")
    c12 = r.padof("C12", "VCC")
    j17 = r.pad("J5", "17")
    xt = c5[0] - 0.85
    r.track("VCC", "B", [(xt, c12[1]), (xt, 16.0), (j17[0], 16.0), j17], 1.0)
    d3 = r.padof("D3", "VCC")
    r.track("VCC", "B", [(xt, d3[1]), d3], 0.5)
    r26 = r.padof("R26", "VCC")
    r.track("VCC", "B", [(xt, 24.2), (r26[0], 24.2), r26], 0.5)


# ---------------------------------------------------------------------------------------------------------------------
# IO header: each 330 R sits level with its J5 signal pin; a via in its U10-side pad takes the line to F.Cu, and the
# J5 side runs straight to the pin on the back.
# ---------------------------------------------------------------------------------------------------------------------
def io(r):
    for k, ref in enumerate(["R55", "R56", "R57", "R58", "R59", "R60"]):
        sig = "IO%d_GPIO" % (k + 1)
        pu = r.padof(ref, sig)
        jn = r.padnet(ref, "2") if r.padnet(ref, "1") == r.net(sig).GetNetname() else r.padnet(ref, "1")
        pj = r.padof(ref, jn)
        jp = r.padof("J5", jn)
        r.via(sig, *pu)
        r.track(jn, "B", [pj, jp], 0.25)


# ---------------------------------------------------------------------------------------------------------------------
# Planes (6 layers, JLC06161H-3313): F.Cu signals over In1 (solid GND); In2 signals, with a GND fill; In3 GND with the
# power areas; In4 solid GND under B.Cu signals. In2 sits 0.11 mm above In3 (0.55 mm below In1), so In2 signals
# reference In3: the power areas go where In2 signals don't have to run, and tools/plane_channels.py lays In3 GND under
# any In2 signal that does. In3 power areas: +3V3 under U10 (and L3's +1V1 corner); VCC over J5 and a band under
# J1/J12/U14; VSYS over the right column, Q1's drain, the bottom strip, the buck's input and the left drivers.
# ---------------------------------------------------------------------------------------------------------------------
PWR_33 = [(17.95, 6.95), (31.2, 6.95), (31.2, 12.85), (28.15, 12.85), (28.15, 19.55), (17.95, 19.55)]
PWR_VCC = [(0.0, 0.0), (36.5, 0.0), (36.5, 7.8), (32.6, 7.8), (32.6, 6.7), (17.75, 6.7), (17.75, 16.35), (0.0, 16.35)]


def pwr_vsys(W, H):
    xr = W - 15.2                                    # right block: under the four right drivers and their connectors
    return [(0.0, 16.55), (15.2, 16.55), (15.2, 29.8), (26.4, 29.8), (26.4, 25.6), (31.3, 25.6), (31.3, 29.8),
            (xr, 29.8), (xr, 21.1), (45.0, 21.1), (45.0, 16.75), (xr, 16.75), (xr, 0.0), (W, 0.0), (W, H),
            (0.0, H)]


def planes(r):
    bb = r.b.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / MM, bb.GetHeight() / MM
    full = [(0, 0), (W, 0), (W, H), (0, H)]
    r.zone("GND", "1", full, priority=1, clearance=0.2, min_w=0.2, solid=True, name="In1 GND")
    r.zone("GND", "2", full, priority=1, clearance=0.2, min_w=0.2, solid=True, name="In2 GND fill")
    r.zone("GND", "3", full, priority=1, clearance=0.2, min_w=0.2, solid=True, name="In3 GND")
    r.zone("+3V3", "3", PWR_33, priority=10, clearance=0.2, min_w=0.2, solid=True, name="In3 +3V3")
    r.zone("VCC", "3", PWR_VCC, priority=10, clearance=0.2, min_w=0.25, solid=True, name="In3 VCC")
    r.zone("VSYS", "3", pwr_vsys(W, H), priority=10, clearance=0.2, min_w=0.25, solid=True, name="In3 VSYS")
    r.zone("GND", "4", full, priority=1, clearance=0.2, min_w=0.2, solid=True, name="In4 GND")
    r.zone("GND", "F", full, priority=1, clearance=0.2, min_w=0.2, solid="tht", name="F GND")
    r.zone("GND", "B", full, priority=1, clearance=0.2, min_w=0.2, solid="tht", name="B GND")

def main():
    b = pcbnew.LoadBoard(str(PCB))
    old = [g for g in b.Groups() if g.GetName() == GROUP]
    doomed = []
    for g in old:
        doomed += list(g.GetItems())
    for item in doomed:
        b.Remove(item)
    for g in old:
        b.Remove(g)
    r = Recipe(b)
    V = u10_fanout(r)
    u10_escapes(r)
    u10_west(r)
    u10_southwest(r)
    usb_c(r)
    usb_a(r)
    crystal(r, V)
    buck(r)
    drivers(r)
    battery(r)
    vcc(r)
    io(r)
    if "--no-planes" not in sys.argv:
        planes(r)
    g = pcbnew.PCB_GROUP(b)
    g.SetName(GROUP)
    b.Add(g)
    for item in r.items:
        g.AddItem(item)
    b.Save(str(PCB))
    print("route_recipe: %d items" % len(r.items))


if __name__ == "__main__":
    main()
