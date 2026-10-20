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
W, H = 66.3, 34.0              # outline
R_CORNER = 1.0                 # corner radius

PITCH = 6.95                   # PH courtyard height: connectors stack at this pitch
TOP = 0.0                      # courtyard top of the first connector in each side column

PLACE = {}                     # ref: (side, x, y, rot); x, y = footprint origin in board-local mm


def put(ref, side, x, y, rot):
    PLACE[ref] = (side, x, y, rot)


# ---- side columns: motor connectors on the walls, each driver beside its connector -----------------------------------
# PH courtyard overhang past the wall is 2.425 mm (body face 1.95 mm out), as the XH parts sat on the old board.
for i, (m, u) in enumerate([("M5", "U3"), ("M6", "U17")]):
    y0 = TOP + i * PITCH
    put(m, "F", 4.35, y0 + 2.475, -90)              # pin 1 at the origin, pin 2 2 mm below
    put(u, "F", 10.75, y0 + 3.475, 180)             # OUT side (pins 5-8) faces the connector
put("J5", "F", 10.84, TOP + 2 * PITCH + 1.68 + 1.5, 0)  # 3 x 6 RA header under M6, plastic face 4.4 mm inside the wall
for i, (m, u) in enumerate([("M1", "U1"), ("M2", "U15"), ("M3", "U2"), ("M4", "U16")]):
    y0 = TOP + i * PITCH
    put(m, "F", W - 4.35, y0 + 4.475, 90)
    put(u, "F", W - 10.75, y0 + 3.475, 0)

# ---- top wall: J12 (LED stick, vertical), J1 (USB-C), J4 (USB-A) ---------------------------------------------------
put("J12", "F", 19.0, 6.67, 90)
put("J1", "F", 28.55, 2.555, 180)                   # mouth 1.65 mm past the wall, as before
put("J4", "F", 46.19, 13.35, 180)

# ---- MCU: USB on the east side, fed by the ESD + series-resistor chain straight down from J1 ------------------------
put("U10", "F", 22.7, 14.7, -90)
put("U6", "F", 28.55, 10.0, 90)                     # D+ in pin 6 out pin 1 (west column), D- in 4 out 3 (east)
put("R44", "F", 27.6, 13.6, 90)
put("R45", "F", 29.5, 13.6, 90)
put("Y1", "F", 16.8, 14.1, 90)                      # XIN pad faces U10's west side
put("L3", "F", 28.6, 16.7, 180)                     # LX pad level with pin 48

# ---- power entry and buck, under the MCU (a signal channel stays open between them at y 18.9-22.8) ---------------
put("U4", "F", 21.0, 25.43, 180)                    # VIN pins east toward Q1, SW pin at the west-bottom
put("L1", "F", 18.5, 30.97, -90)                    # SW pad up, under U4's SW pin; VCC pad down
put("C14", "F", 23.6, 29.15, 0)                     # BST (east) to SW (west), under U4
put("C74", "F", 25.5, 25.43, 180)                   # VSYS pad against the VIN pins
put("C73", "F", 26.3, 27.05, 180)
put("Q1", "F", 31.15, 26.65, -90)                   # gate and source on top (PACK+ from J3), drain (VSYS) below

# USB-A series resistors, front, in the gap between J4's pins and J3 (each in line with its J4 pin)
put("R48", "F", 41.69, 16.8, 90)
put("R49", "F", 43.69, 16.8, 90)

# ---- bottom wall: J3 under J4, the switches in the bottom-right corner ---------------------------------------------
put("J3", "F", 34.2 + 4.67, H - 13.13, 180)         # mouth out through the bottom wall, courtyard 0.5 past it
put("SW1", "F", 55.0, H + 0.25 - 2.475, 180)        # under U16, lever out through the bottom wall
put("SW2", "F", 63.25, H + 0.25 - 2.325, 0)         # under M4, push from the bottom wall
put("FID1", "F", 2.2, H - 2.0, 0)
put("FID2", "F", 49.9, 17.0, 0)
put("FID3", "F", 26.8, H - 1.8, 0)

# ---- back side ------------------------------------------------------------------------------------------------------
# Motor drivers: 100 nF beside pin 5 (VM) under the OUT pins, 10 uF across the gap below the exposed pad, IPROPI
# resistor under the IN pins next to pin 1.
for (u, csmall, cbig, r), i in zip([("U1", "C4", "C3", "R101"), ("U15", "C76", "C75", "R102"),
                                     ("U2", "C7", "C6", "R103"), ("U16", "C78", "C77", "R104")], range(4)):
    yc = TOP + i * PITCH + 3.475
    put(csmall, "B", W - 7.55, yc + 1.6, 90)
    put(cbig, "B", W - 10.8, yc + 3.15, 0)
    put(r, "B", W - 13.7, yc - 1.6, 90)
for (u, csmall, cbig, r), i in zip([("U3", "C11", "C10", "R105"), ("U17", "C80", "C79", "R106")], range(2)):
    yc = TOP + i * PITCH + 3.475
    put(csmall, "B", 7.6, yc - 1.6, 90)
    put(cbig, "B", 10.8, yc + 3.15, 0)
    put(r, "B", 13.7, yc + 1.6, 90)

# MCU decoupling under U10 (pins: N y 11.25, W x 19.25, S y 18.15, E x 26.15)
put("C43", "B", 20.35, 13.0, 90)                    # pin 20 IOVDD
put("C54", "B", 20.35, 15.2, 90)                    # pin 23 DVDD
put("C44", "B", 20.35, 17.25, 90)                   # pin 30 IOVDD
put("C42", "B", 21.99, 12.35, 0)                    # pin 11 IOVDD
put("C53", "B", 23.99, 12.35, 0)                    # pin 6 DVDD
put("C41", "B", 25.55, 10.2, 90)                    # pin 1 IOVDD
put("C45", "B", 22.25, 17.0, 90)                    # pin 38 IOVDD
put("C55", "B", 23.25, 17.0, 90)                    # pin 39 DVDD
put("C46", "B", 24.6, 17.0, 90)                     # pin 44 ADC_AVDD
put("C47", "B", 25.65, 19.65, 90)                   # pin 45 IOVDD
put("C48", "B", 27.15, 14.75, 0)                    # pin 53 USB_OTP_VDD
put("C49", "B", 27.15, 13.55, 0)                    # pin 54 QSPI_IOVDD
put("C50", "B", 27.3, 16.3, 0)                      # pin 49 VREG_VIN 4.7u
put("C52", "B", 30.1, 17.45, 0)                     # +1V1 out at L3 4.7u
put("C51", "B", 27.3, 18.4, 0)                      # pin 46 VREG_AVDD 4.7u
put("R42", "B", 29.6, 19.0, 0)                      # 33R +3V3 to VREG_AVDD
put("R46", "B", 27.4, 12.35, 0)                     # QSPI_SS to SW2
# crystal parts under Y1
put("C56", "B", 18.1, 16.85, 0)                     # XIN load cap
put("C57", "B", 15.95, 14.1, 90)                    # XOUT-side load cap
put("R43", "B", 17.2, 14.1, 90)                     # 1k XOUT
# USB-C: CC pull-downs under J1's CC pads
put("R99", "B", 30.3, 7.4, 0)                       # CC1
put("R100", "B", 26.8, 7.4, 0)                      # CC2
# USB-only 5 V, the OR diodes and the 3.3 V LDO under J3 (the back under J4 stays free for the M1/M2 route)
put("U8", "B", 37.0, 26.4, 0)
put("C37", "B", 40.2, 26.4, 90)
put("C38", "B", 41.9, 26.4, 90)
put("D2", "B", 44.0, 26.4, 90)
put("D3", "B", 46.6, 26.4, 90)
put("U9", "B", 41.0, 31.3, 0)
put("C39", "B", 38.2, 31.3, 90)
put("C40", "B", 44.2, 31.3, 90)
# USB-A: ESD at J4's signal pins, 15k host pull-downs beside it, PTC and VBUS cap by pin 1
put("U11", "B", 42.7, 9.6, 0)
put("R109", "B", 39.9, 9.6, 90)
put("R114", "B", 45.5, 9.6, 90)
put("F2", "B", 47.0, 16.6, 0)
put("C59", "B", 50.35, 15.6, 90)
# LED buffer below J12
put("U14", "B", 17.6, 10.1, 0)
put("C69", "B", 21.1, 10.1, 90)
# power entry: gate network at Q1's gate, R41 at the switch, VSYS bulk and TVS under the drain row
put("R40", "B", 28.9, 23.4, 90)
put("C71", "B", 30.1, 23.4, 90)
put("C72", "B", 32.35, 23.6, 0)
put("R41", "B", 58.2, 28.9, 0)
put("C15", "B", 29.4, 32.65, 0)
put("D4", "B", 31.75, 30.35, 0)
put("R52", "B", 27.4, 21.3, 0)
put("R53", "B", 25.4, 21.3, 0)
put("C61", "B", 24.2, 19.65, 90)
# buck passives: output caps under L1, feedback and compensation by U4's west pins, RT by pin 4
put("C5", "B", 18.6, 32.5, 0)
put("C8", "B", 19.95, 29.9, 0)
put("C12", "B", 23.4, 32.5, 0)
put("R26", "B", 18.5, 22.4, 0)
put("R27", "B", 18.5, 23.4, 0)
put("R28", "B", 18.5, 24.6, 0)
put("C16", "B", 18.5, 25.6, 0)
put("R25", "B", 24.6, 23.5, 0)
# VREF divider in the gap between J4 and J3
put("R107", "B", 36.6, 16.3, 0)
put("R108", "B", 38.6, 16.3, 0)
put("C81", "B", 40.6, 16.3, 0)
# IO series resistors beside J5's signal column
for k, r in enumerate(["R55", "R56", "R57", "R58", "R59", "R60"]):
    put(r, "B", 15.9, TOP + 2 * PITCH + 1.68 + 1.5 + 2.54 * k, 90)
put("FID4", "B", 3.2, 24.0, 0)
put("FID5", "B", 49.8, 21.5, 0)
put("FID6", "B", 13.9, 1.6, 0)
# test pads under J3 (TP1 nearest U10), fiducials spread over the back
for k, tp in enumerate(["TP1", "TP2", "TP3", "TP4"]):
    put(tp, "B", 31.0 + 2.1 * (k % 2), 26.0 + 2.1 * (k // 2), 0)


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
    outline(b)
    b.Save(str(PCB))
    print(f"placed {len(PLACE)} footprints on {W} x {H} mm")


if __name__ == "__main__":
    main()
