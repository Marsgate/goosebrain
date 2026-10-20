"""Place the brain board as a compact double-sided board (kicad/thegoose.kicad_pcb, edited in place).

Run with KiCad's Python:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/place_double.py

What it does, every run (idempotent):
- removes all tracks, vias and zones, and the old outline and board drawings
- swaps M1-M6 to JST PH right-angle (S2B-PH-K) if they are still XH, keeping each footprint's schematic link and fields
- puts every footprint at the side, position and rotation in PLACE below (board-local mm, origin at the board's
  top-left corner, x right, y down), and draws the rectangular outline with rounded corners

Routing comes after this, from tools/route_recipe.py and Freerouting.
"""
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "kicad/thegoose.kicad_pcb"
LIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"
PH = ("Connector_JST.pretty", "JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal")

MM = 1e6
OX, OY = 99.95, 99.95          # board top-left corner in KiCad coordinates (unchanged from the old board)
W, H = 68.2, 32.0              # outline (a 2 mm riser channel between J4 and the right drivers)
R_CORNER = 1.0                 # corner radius

PORT_OV = 1.4                  # USB-C, USB-A and XT30 faces this far past the top/bottom edge: flush with a
                               # 1.15 mm case wall at 0.25 mm from the board (J1's shell pads set the limit)

PITCH = 6.95                   # right-wall PH connectors stack at this pitch (courtyards just touch)
TOP = 0.0                      # courtyard top of the first connector in the right column

PLACE = {}                     # ref: (side, x, y, rot); x, y = footprint origin in board-local mm


def put(ref, side, x, y, rot):
    PLACE[ref] = (side, x, y, rot)


# ---- left wall: J5 (IO header) at the top, M5 and M6 below it, each driver beside its connector ----------------------
J5_Y = 1.75                                         # pin 1 row; courtyard top at the board edge
put("J5", "F", 10.84, J5_Y, 0)                      # 3 x 6 RA header, plastic face 4.4 mm inside the left wall
LEFT_Y0 = (16.45, 23.45)                            # courtyard tops of M5 and M6 (7 mm courtyards)
for (m, u), y0 in zip([("M5", "U3"), ("M6", "U17")], LEFT_Y0):
    put(m, "F", 4.35, y0 + 2.475, -90)              # pin 1 at the origin, pin 2 2 mm below
    put(u, "F", 10.75, y0 + 3.475, 180)             # OUT side (pins 5-8) faces the connector, IN pins face U10
# ---- right wall: M1-M4 with their drivers -------------------------------------------------------------------------
for i, (m, u) in enumerate([("M1", "U1"), ("M2", "U15"), ("M3", "U2"), ("M4", "U16")]):
    y0 = TOP + i * PITCH
    put(m, "F", W - 4.35, y0 + 4.475, 90)
    put(u, "F", W - 10.75, y0 + 3.475, 0)

# ---- top wall: J1 (USB-C) over the MCU, J12 (LED stick, vertical) in the gap, J4 (USB-A) --------------------------
# J1 and J4 plug centres are 19.5 mm apart: a 24 mm wide dongle in J4 clears a USB-C cable in J1.
J1X = 23.1
put("J1", "F", J1X, 2.555 - 0.27, 180)              # face PORT_OV past the edge; shell pads 0.3 mm from it
put("J12", "F", J1X + 7.62, 6.67, 90)            # courtyard touches J1's
J4_DY = PORT_OV + 0.355                             # J4's face sat 0.355 mm inside the edge
put("J4", "F", J1X + 23.0, 13.35 - J4_DY, 180)     # pin 1 (VBUS); plug centre 19.5 mm east of J1's

# ---- MCU straight under J1: the USB pair runs down J1's A6/B7 contacts, through R44/R45 into pins 52/51 ------------
# U6 (ESD) sits on the back under R44/R45: it taps the pair through vias in R44/R45's J1-side pads and takes the
# flipped contacts B6/A7 through two vias, so the main path (A6/B7) has no vias.
U10X, U10Y = J1X - 0.1, 15.7
put("U10", "F", U10X, U10Y, 0)                      # USB on the north side, IO on the west, motors east and south
put("R44", "F", J1X - 1.28, 9.9, 90)                # D+ (A6 at J1X + 0.25)
put("R45", "F", J1X + 0.2, 9.9, 90)                 # D- (B7 at J1X + 0.75), over pin 51, west of the core regulator
put("Y1", "F", U10X - 1.9, U10Y + 6.83, 180)       # XIN pad (NE) under pin 21; M5/M6 leave west above it
# Core supply: the on-chip regulator isn't used (RP2350 datasheet Fig. 24). C85 (VREG_VIN 4.7 uF) right off the pins,
# +3V3 pad over pin 49 and GND pad over pin 47 (VREG_PGND). U12 (TLV74311, 1.1 V LDO) sits in the pocket between U10's
# NE corner and J12, at 180 deg so OUT (pin 5) is its SW pad, nearest U10; C86 (its 4.7 uF output) in the strip west
# of it, +1V1 pad (pad 1) south; C87 (its 4.7 uF input) under its IN pad, clear of the east escape vias.
VREG_X = U10X + 2.07                                # C85 centre; pin 48 is at U10X + 2.0
put("C85", "F", VREG_X, U10Y - 4.65, 0)             # pads 0.5 mm off the pin toes; courtyard clear of U10
put("U12", "F", U10X + 7.6, U10Y - 4.7, 180)        # IN/GND/EN on the east column, OUT/NC on the west
put("C86", "F", U10X + 4.9, U10Y - 5.3, 90)         # LDO output
put("C87", "F", U10X + 8.3, U10Y - 1.95, 270)       # LDO input, pad 1 (+3V3) north, under IN; clear of the USB-A pair

# ---- buck under the MCU at the bottom; a channel at x 15-16 stays open for the M6 lines --------------------------
put("L1", "F", 18.9, 27.8, 180)                     # SW pad (pin 1) east toward U4's SW pin, VCC pad west, 0.2 mm
                                                   # clear of the M6B lane (x 15.6 here, see u10_southwest)
put("U4", "F", 25.72, 27.2, 180)                    # VIN pins east, SW pin at the west-bottom; courtyard clear of L1
put("C74", "F", 30.2, 26.2, 180)                     # 100 nF, VSYS pad against pin 3 (VIN)
put("C73", "F", 30.28, 28.9, 90)                    # 10 uF, VSYS pad level with pin 2 (VIN)
put("C14", "F", 25.72, 30.9, 0)                     # BST to SW, under U4

# ---- bottom wall: J3 (XT30) right of the buck, Q1 east of it, SW1 under U16, SW2 in the corner --------------------
J3_DY = PORT_OV + 0.43                              # J3's face sat 0.43 mm inside the edge
put("J3", "F", 36.1, H + 0.5 - 13.64 + J3_DY, 180)  # face PORT_OV past the bottom edge
put("Q1", "F", 48.75, 20.5, 90)                     # source pins (PACK+) at the bottom-west, drain (VSYS) on top
put("SW1", "F", W - 11.56, H + 0.75 - 2.475, 180)   # lever 1.7 mm past the case wall
put("SW2", "F", W - 3.4, H + 0.25 - 2.325, 0)       # under M4, push from the bottom wall

# USB-A series resistors at the source, east of U10's pins 36/37
put("R48", "F", 30.4, U10Y + 0.1, 0)                  # east of the escape vias for pins 32-35 and 40-43
put("R49", "F", 30.4, U10Y + 1.14, 0)
put("FID1", "F", 1.9, 1.9, 0)                      # left strip, where J5's plugs come in
put("FID2", "F", 1.9, 14.6, 0)
put("FID3", "F", 49.5, 28.4, 0)                    # below Q1, west of SW1

# ---- back side ------------------------------------------------------------------------------------------------------
# Motor drivers: 100 nF beside pin 5 (VM) under the OUT pins, 10 uF across the gap below the exposed pad, IPROPI
# resistor under the IN pins next to pin 1. U16's 10 uF goes beside its IN pins: SW1 is under its gap.
for (u, csmall, cbig, r), i in zip([("U1", "C4", "C3", "R101"), ("U15", "C76", "C75", "R102"),
                                     ("U2", "C7", "C6", "R103"), ("U16", "C78", "C77", "R104")], range(4)):
    yc = TOP + i * PITCH + 3.475
    put(csmall, "B", W - 7.55, yc + 1.6, 90)
    put(cbig, "B", W - 10.8, yc + 3.15, 0)
    put(r, "B", W - 13.7, yc - 1.6, 270)            # IPROPI pad north, by the via past pin 1
put("C77", "B", W - 13.7, TOP + 3 * PITCH + 3.475 + 1.3, 90)
put("C78", "B", W - 7.55, TOP + 3 * PITCH + 3.475 + 1.45, 90)   # clear of SW1's mounting pad
for (u, csmall, cbig, r), y0 in zip([("U3", "C11", "C10", "R105"), ("U17", "C80", "C79", "R106")], LEFT_Y0):
    yc = y0 + 3.475
    put(csmall, "B", 7.6, yc - 1.6, 270)            # VSYS pad north, by pin 5 (VM)
    put(cbig, "B", 10.8, yc + 3.15, 0)
    put(r, "B", 13.7, yc + 1.6, 90)

# MCU decoupling on the back under U10. Each cap sits on its supply's via in the ring between U10's pads and its
# exposed pad, with its GND pad on a via into the exposed pad (offsets from U10's centre; see tools/route_recipe.py).
# 0402 pad 1 (the supply) sits on the via; pad 2 (GND) points to the exposed pad. Back 0402: rot 0 puts pad 1 west,
# 90 south, 180 east, 270 north, 0.48 mm from the centre.
CAP_ON_VIA = [("C42", -2.45, 2.4, 0), ("C54", 0.05, 2.35, 90), ("C43", 2.45, 2.4, 180), ("C44", 2.45, 0.3, 180),
              ("C55", 2.45, -0.75, 180), ("C53", -2.4, -0.8, 0), ("C48", -0.2, -2.4, 270), ("C49", 1.6, -2.4, 0),
              ("C41", -4.5, -3.0, 90), ("C45", 4.55, -2.6, 0)]
PAD1 = {0: (-0.48, 0.0), 90: (0.0, 0.48), 180: (0.48, 0.0), 270: (0.0, -0.48)}
for ref, vx, vy, rot in CAP_ON_VIA:
    put(ref, "B", U10X + vx - PAD1[rot][0], U10Y + vy - PAD1[rot][1], rot)
put("C46", "B", 41.7, 30.6, 90)                    # extra +3V3 100 nF at U9's output, under D2
put("C47", "B", U10X - 4.1, U10Y - 0.1, 90)         # extra +3V3 100 nF, W
put("C50", "B", U10X - 4.1, U10Y + 2.1, 90)         # +3V3 4.7 uF, SW
put("C52", "B", U10X + 0.6, U10Y + 3.35, 0)         # second +1V1 4.7 uF at DVDD pin 23, beside C54
put("C51", "B", 27.6, U10Y - 5.36, 90)                      # VREG_AVDD 4.7u, by the pin 46 via
put("R42", "B", 28.7, U10Y - 5.36, 270)                     # 33R +3V3 to VREG_AVDD
put("R46", "B", U10X - 4.0, U10Y - 5.1, 0)         # QSPI_SS to SW2, west of pin 60 and of U6's D+ loop
# crystal load caps and XOUT resistor on the back under Y1
put("C56", "B", U10X - 0.32, U10Y + 6.8, 0)         # XIN load cap, by the via in Y1's XIN pad
put("C57", "B", U10X - 4.0, U10Y + 6.7, 270)        # XOUT-side load cap, by Y1's SW pad
put("R43", "B", U10X - 1.4, U10Y + 4.6, 180)        # 1k XOUT, from the via outside pin 22
# USB-C: ESD under R44/R45, CC pull-downs beside it
put("U6", "B", J1X + 0.5, U10Y - 4.7, 0)           # N pins on the top row (under R45), P on the bottom; VP pad
                                                   # joins C49's +3V3 pad round the east side
put("R99", "B", J1X + 3.25, 8.7, 270)                # CC1
put("R100", "B", J1X - 3.5, 8.7, 270)               # CC2
# USB-only 5 V, the OR diodes and the 3.3 V LDO under J3, between its pins (they move with J3)
put("U8", "B", 34.4, 24.4 + J3_DY, 0)
put("C37", "B", 38.4, 22.8 + J3_DY, 0)
put("C38", "B", 38.4, 24.5 + J3_DY, 0)
put("D2", "B", 42.6, 24.4 + J3_DY, 90)
put("U9", "B", 38.9, 27.4 + J3_DY, 0)
put("C39", "B", 35.4, 28.3 + J3_DY, 90)
put("C40", "B", 44.7, 24.4, 90)
put("D3", "B", 17.05, 19.6, 90)                     # VCC OR diode, VCC pad on the B.Cu VCC trunk
# USB-A: ESD at J4's signal pins, 15k host pull-downs beside it, PTC and VBUS cap by pin 1
J4P1 = J1X + 23.0                                   # J4 pin 1 (VBUS); pins 2/3 (D-/D+) at -2.5/-4.5
put("U11", "B", J4P1 - 3.5, 9.45 - J4_DY, 270)      # D+ column over J4 pin 3, D- over pin 2
put("R109", "B", J4P1 - 6.2, 9.8 - J4_DY, 90)
put("R114", "B", J4P1 - 0.8, 9.8 - J4_DY, 90)
put("F2", "B", J4P1 + 0.5, 5.6 - J4_DY, 270)       # VCC pad north, J4-VBUS pad south toward pin 1
put("C59", "B", J4P1 + 3.3, 5.6 - J4_DY, 90)
# LED buffer under J12's east side
put("U14", "B", 34.75, 4.0, 90)
put("C69", "B", 37.6, 4.0, 90)                      # east of U14: J4's shell peg is under its old spot
# power entry: gate network at Q1's gate, R41 at the switch, VSYS bulk and TVS under the drain side
put("C72", "B", 47.9, 23.95, 0)                    # PACK+ pads of R40/C72 face west onto a small B.Cu PACK+ patch
put("R40", "B", 47.5, 22.4, 0)
put("C71", "B", 45.9, 21.3, 0)                     # gate to VSYS
put("C15", "B", 48.9, 20.65, 0)
put("D4", "B", 48.4, 18.35, 0)
put("R41", "B", 56.6, 27.05, 0)
put("R52", "B", 45.3, 19.3, 270)                   # VSYS end on a via into the In2 VSYS by Q1
put("R53", "B", 29.4, U10Y + 4.24, 0)
put("C61", "B", 29.4, U10Y + 5.24, 0)
# buck passives: output caps under L1, feedback and compensation by U4's west pins, RT by pin 4
put("C5", "B", 17.94, 25.8, 0)
put("C8", "B", 17.94, 28.2, 0)
put("C12", "B", 17.94, 30.6, 0)
put("R26", "B", 22.75, 25.0, 0)
put("R27", "B", 22.75, 26.0, 0)
put("R28", "B", 22.75, 27.0, 0)
put("C16", "B", 22.75, 28.0, 0)
put("R25", "B", 29.4, 24.6, 0)
# motor VREF divider between J4 and Q1
put("R107", "B", W - 15.9, 20.9, 0)                # motor VREF divider at the foot of the riser channel
put("R108", "B", W - 15.9, 21.9, 0)
put("C81", "B", W - 15.9, 22.9, 0)
# IO series resistors in a column beside J5's signal pins, each level with its pin
for k, r in enumerate(["R55", "R56", "R57", "R58", "R59", "R60"]):
    put(r, "B", 16.3, J5_Y + 2.54 * k, 180)          # pad 2 (J5 side) west, pad 1 (U10 side) east
put("FID4", "B", 2.0, 8.0, 0)
put("FID5", "B", 47.2, 30.6, 0)                    # under J3's right edge, by SW1
put("FID6", "B", J1X, 2.2, 0)                      # under J1, between its shell pins
# SWD/RUN/GND test pads in a row south-east of U10, clear of its south-side escape vias
for k, tp in enumerate(["TP1", "TP2", "TP3"]):
    put(tp, "B", 24.7 + 2.15 * k, 23.0, 0)
put("TP4", "B", 24.8, 25.3, 0)                      # GND, beside U4's exposed-pad vias


def staged_back(refs, x0, y0, step=3.2, per_row=12):
    """Park back-side parts in rows below the board until they get real positions."""
    for i, r in enumerate(refs):
        put(r, "B", x0 + (i % per_row) * step, y0 + (i // per_row) * 3.0, 0)


def outline(b):
    """Rectangle with rounded corners on Edge.Cuts."""
    r = R_CORNER
    def seg(x0, y0, x1, y1):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(int(0.05 * MM))
        s.SetStart(pcbnew.VECTOR2I(int((OX + x0) * MM), int((OY + y0) * MM)))
        s.SetEnd(pcbnew.VECTOR2I(int((OX + x1) * MM), int((OY + y1) * MM)))
        b.Add(s)
    def arc(cx, cy, sx, sy, ex, ey):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(int(0.05 * MM))
        s.SetCenter(pcbnew.VECTOR2I(int((OX + cx) * MM), int((OY + cy) * MM)))
        s.SetStart(pcbnew.VECTOR2I(int((OX + sx) * MM), int((OY + sy) * MM)))
        s.SetEnd(pcbnew.VECTOR2I(int((OX + ex) * MM), int((OY + ey) * MM)))
        b.Add(s)
    seg(r, 0, W - r, 0)
    seg(W, r, W, H - r)
    seg(W - r, H, r, H)
    seg(0, H - r, 0, r)
    arc(W - r, r, W - r, 0, W, r)
    arc(W - r, H - r, W, H - r, W - r, H)
    arc(r, H - r, r, H, 0, H - r)
    arc(r, r, 0, r, r, 0)


def swap_to_ph(b, ref):
    old = b.FindFootprintByReference(ref)
    if "JST_PH_S2B-PH-K" in old.GetFPIDAsString():
        return old
    new = pcbnew.FootprintLoad(LIB + PH[0], PH[1])
    new.SetFPID(pcbnew.LIB_ID("Connector_JST", PH[1]))
    new.SetReference(ref)
    new.SetValue(old.GetValue())
    new.SetPath(old.GetPath())
    new.SetSheetname(old.GetSheetname())
    new.SetSheetfile(old.GetSheetfile())
    for fld in old.GetFields():
        if fld.GetName() in ("Reference", "Value", "Footprint"):
            continue
        new.SetField(fld.GetName(), fld.GetText())
        nf = new.GetField(fld.GetName())
        nf.SetVisible(fld.IsVisible())
        nf.SetLayer(pcbnew.F_Fab)
    nets = {p.GetNumber(): p.GetNet() for p in old.Pads()}
    b.Remove(old)
    b.Add(new)
    for p in new.Pads():
        if p.GetNumber() in nets:
            p.SetNet(nets[p.GetNumber()])
    if hasattr(new, "SetFieldsAutoplaced"):
        pass
    return new


def main():
    b = pcbnew.LoadBoard(str(PCB))
    # collect everything first: pcbnew's Drawings() proxy breaks once items start being removed
    doomed = list(b.GetTracks()) + list(b.Zones()) + list(b.Drawings()) + list(b.Groups())
    for item in doomed:
        b.Remove(item)
    for m in ("M1", "M2", "M3", "M4", "M5", "M6"):
        swap_to_ph(b, m)

    placed = set(PLACE)
    rest = sorted(f.GetReference() for f in b.GetFootprints()
                  if f.GetReference() not in placed and not f.GetReference().startswith("G"))
    staged_back(rest, 0.0, H + 6.0)

    for f in b.GetFootprints():
        ref = f.GetReference()
        if ref not in PLACE:
            continue
        side, x, y, rot = PLACE[ref]
        back = side == "B"
        if f.IsFlipped() != back:
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetOrientationDegrees(rot)
        f.SetPosition(pcbnew.VECTOR2I(int(round((OX + x) * MM)), int(round((OY + y) * MM))))
    # fiducials added from the schematic come in with the library's "exclude from BOM" flag; match FID1
    ref_attrs = b.FindFootprintByReference("FID1").GetAttributes()
    for r in ("FID4", "FID5", "FID6"):
        f = b.FindFootprintByReference(r)
        if f:
            f.SetAttributes(ref_attrs)
    outline(b)
    b.Save(str(PCB))
    print(f"placed {len(PLACE)} footprints on {W} x {H} mm")


if __name__ == "__main__":
    main()
