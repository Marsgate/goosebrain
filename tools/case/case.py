"""Brain case v3 for the 68.2 x 32 mm double-sided goosebrain with flush ports.

A closed box with all four walls outside the board. Every port overhangs the board edge so its face is flush with
the outer wall: the JSTs and J5 by 1.9 mm (left/right walls 1.65 mm), J1/J4/J3 by 1.4 mm (top/bottom walls 1.15
mm), each 0.25 mm off the board edge. The box splits at the board's top face: the board drops into the tray onto a
ledge, the cover comes down on it with a lip that holds it, and the connector openings sit in the cover's walls.
The WS2812B stick sits under a diffuser window in the lid.

Frame = KiCad 3D-model frame of a footprint at the board's top-left outline corner: X = board x, Y = -board y,
Z = board z - 1.6 (board top = 0). Board-local numbers (bx, by, bz; bz = 0 at the board's bottom face) come from
the board STEP export (argv[2]).
"""
import sys
from build123d import *

BT = 1.6
EX0, EX1, EY0, EY1 = 0.03, 68.23, 0.03, 32.02   # board outline
CLR = 0.25                       # board edge -> inner wall
WX0, WX1 = -1.9, 70.15           # left/right outer faces = J5/M5/M6 and M1-M4 faces
WY0, WY1 = -1.375, 33.42         # top/bottom outer faces = J1/J4 and J3 faces
IX0, IX1, IY0, IY1 = EX0 - CLR - 0.03, EX1 + CLR, EY0 - CLR, EY1 + CLR
ZF0, ZF1 = -3.5, -2.0            # floor (2 mm gap under the board)
ZL0, ZL1 = 10.6, 12.1            # lid (USB-A top 9.28, LED stick under the lid)
LEDGE, LIP = 1.0, 0.8            # board ledge (tray) and hold-down lip (cover), measured in from the board edge
R = 1.5
C = 0.3                          # clearance round parts

def P(bx, by, bz):
    return Vector(bx, -by, bz - BT)

def box(x0, x1, y0, y1, z0, z1):
    return Pos(P((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) * Box(x1 - x0, y1 - y0, z1 - z0)

def rbox(x0, x1, y0, y1, z0, z1, r):
    return fillet(box(x0, x1, y0, y1, z0, z1).edges().filter_by(Axis.Z), r)

def ring(z0, z1, inset):        # a frame inside the walls reaching `inset` over the board edge
    return box(IX0 - 0.1, IX1 + 0.1, IY0 - 0.1, IY1 + 0.1, z0, z1) \
         - box(EX0 + inset, EX1 - inset, EY0 + inset, EY1 - inset, z0 - 1, z1 + 1)

tray = rbox(WX0, WX1, WY0, WY1, ZF0, BT, R) - box(IX0, IX1, IY0, IY1, ZF1, BT + 1)
tray += ring(ZF1, 0, LEDGE)
cover = rbox(WX0, WX1, WY0, WY1, BT, ZL1, R) - box(IX0, IX1, IY0, IY1, BT - 1, ZL0)
cover += ring(BT, BT + 0.8, LIP)

# --- relief for every part that reaches into a wall, ledge or lip -------------------------------------------------
board = import_step(sys.argv[2] if len(sys.argv) > 2 else "board.step")
O = 99.925
M = max(LEDGE, LIP) + 0.1
regions = [  # (x0, x1, y0, y1, side the cut opens to)
    (WX0 - 1, EX0 + M, WY0 - 1, WY1 + 1, "left"),
    (EX1 - M, WX1 + 1, WY0 - 1, WY1 + 1, "right"),
    (WX0 - 1, WX1 + 1, WY0 - 1, EY0 + M, "top"),
    (WX0 - 1, WX1 + 1, EY1 - M, WY1 + 1, "bot"),
]
cuts = []
for part in board.children:
    if "PCB" in part.label:
        continue
    bb = part.bounding_box()
    px0, py0, px1, py1 = bb.min.X - O, -bb.max.Y - O, bb.max.X - O, -bb.min.Y - O
    for x0, x1, y0, y1, side in regions:
        if px1 < x0 or px0 > x1 or py1 < y0 or py0 > y1:
            continue
        # a part only needs a pocket where it reaches into the ledge, lip or inner half of a wall; what reaches the
        # outer half of the wall is a port face (or SW1's lever) and gets an opening through it
        mx, my = {"left": ((IX0 + WX0) / 2, None), "right": ((IX1 + WX1) / 2, None),
                  "top": (None, (IY0 + WY0) / 2), "bot": (None, (IY1 + WY1) / 2)}[side]   # mid-plane of the wall
        inner = {"left": (mx, x1, y0, y1), "right": (x0, mx, y0, y1),
                 "top": (x0, x1, my, y1), "bot": (x0, x1, y0, my)}[side]
        outer = {"left": (x0, mx, y0, y1), "right": (mx, x1, y0, y1),
                 "top": (x0, x1, y0, my), "bot": (x0, x1, my, y1)}[side]
        for zx0, zx1, zy0, zy1, through in [(*inner, False), (*outer, True)]:
            hit = part & Pos(O + (zx0 + zx1) / 2, -(O + (zy0 + zy1) / 2), 0) * Box(zx1 - zx0, zy1 - zy0, 60)
            if not hit or hit.volume < 1e-6:
                continue
            hb = hit.bounding_box()
            hx0, hy0, hx1, hy1 = hb.min.X - O, -hb.max.Y - O, hb.max.X - O, -hb.min.Y - O
            if not through:               # keep the pocket's clearance inside the inner half
                if side == "left":  hx0 = max(hx0, mx + C)
                if side == "right": hx1 = min(hx1, mx - C)
                if side == "top":   hy0 = max(hy0, my + C)
                if side == "bot":   hy1 = min(hy1, my - C)
            if through:
                if side == "left":  hx0 = WX0 - 1
                if side == "right": hx1 = WX1 + 1
                if side == "top":   hy0 = WY0 - 1
                if side == "bot":   hy1 = WY1 + 1
                if "SK12" in part.label:
                    hx1 += 2.0            # SW1 lever travel
            cuts.append(box(hx0 - C, hx1 + C, hy0 - C, hy1 + C, hb.min.Z - C, hb.max.Z + C))
# SW2 (BOOT) ends at the board edge: a pin hole through the bottom wall at its plunger
cuts.append(Pos(P(64.8, (IY1 + WY1) / 2, 3.3)) * Rot(90, 0, 0) * Cylinder(1.0, WY1 - IY1 + 2))
for c in cuts:
    tray -= c
    cover -= c

# --- LED stick (8x WS2812B, 51 x 10.2 mm) under a diffuser window in the lid ---------------------------------------
SX, SY = 34.13, 22.0             # centre; clear of J4/J5 (y < 14) and J12
PITCH, N = 6.35, 8
stick_z1 = ZL0 - 1.6             # LED tops touch the lid
stick = box(SX - 25.5, SX + 25.5, SY - 5.1, SY + 5.1, stick_z1 - 1.6, stick_z1)
leds = [box(SX + (i - 3.5) * PITCH - 2.5, SX + (i - 3.5) * PITCH + 2.5, SY - 2.5, SY + 2.5, stick_z1, ZL0)
        for i in range(N)]
cover -= rbox(SX - 25, SX + 25, SY - 3.2, SY + 3.2, ZL0 - 0.01, ZL1 + 0.01, 1.0)
diffuser = rbox(SX - 25 + 0.05, SX + 25 - 0.05, SY - 3.15, SY + 3.15, ZL0, ZL1, 0.95)
cover += box(SX - 27.5, SX - 25.7, SY - 5.1, SY + 5.1, stick_z1 - 1.6, ZL0)   # stick rails
cover += box(SX + 25.7, SX + 27.5, SY - 5.1, SY + 5.1, stick_z1 - 1.6, ZL0)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    tray.color = cover.color = Color(0.93, 0.93, 0.9)
    stick.color = Color(0.05, 0.05, 0.05)
    diffuser.color = Color(1, 1, 1)
    for l in leds:
        l.color = Color(1, 0.97, 0.85)
    export_step(tray, f"{out}/case_tray.step")
    export_step(cover, f"{out}/case_cover.step")
    export_step(diffuser, f"{out}/case_diffuser.step")
    export_step(Compound(children=[stick] + leds, label="led_stick"), f"{out}/led_stick.step")
    bb = (tray + cover).bounding_box()
    print("outer", round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2), "cuts", len(cuts))
