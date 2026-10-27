"""Place every reference designator on the brain board (kicad/thegoose.kicad_pcb, edited in place), or with `pack`
on the 3S pack board (kicad-pack/goosepack.kicad_pcb, which has no logo).

Run with KiCad's Python after routing:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/silk.py [pack]

Each reference goes on its part's side (F.Silkscreen or B.Silkscreen), 0.8 mm tall with a 0.15 mm stroke (the
project's minimum), at the first spot around the part's courtyard where it clears every pad and through-hole pad on
that side by 0.1 mm, all other silk and the board edge. Spots are tried above, below, left and right of the
part's courtyard and over its body, in both orientations and slid along each side, then further out. Fiducials and parts with no free spot keep a hidden
reference; the script lists them (their references are still on the fab layers). First, footprint silk outside the
outline is removed or cut back to it (several connectors overhang the edge), and the motor connectors lose the body
detail between their pins and the edge so their references fit; pin 1 marks stay. The goose logo goes to the first
free spot on the back that no part covers, before the references, shrunk in steps down to half size if it has to.

On the pack board, footprint silk that lands on another part's pad (a pin 1 mark beside a cap placed flush against
its IC) is nudged clear; the pigtail pads get polarity labels (B-/B+ at J3, the cells; P-/P+ at J2, the output) and
J11's pins B0-B3 in a row, 1 mm tall, before the references; and no reference goes over another part's courtyard.
"""
import os
import sys
from pathlib import Path

import pcbnew

PACK = "pack" in sys.argv[1:]
PCB = Path(__file__).resolve().parent.parent / ("kicad-pack/goosepack.kicad_pcb" if PACK else
                                                "kicad/thegoose.kicad_pcb")
MM = 1e6
H, T = 0.8, 0.15                # text height and stroke
GAP = 0.1                       # to pads and other silk
EDGE = 0.25                     # to the board edge
OX = OY = 99.95                 # board top-left corner in KiCad coordinates
LOGO_SPOTS = [(3.225, 12.825, 180)]  # board-local logo spot tried first (left strip, clear of C11's reference)
LABELS = "pack_labels"          # pack: PCB group holding the polarity and balance labels
LABEL_H = 1.0
# (footprint, pad): label. J3's and J2's square pads are the negative ones.
PAD_LABELS = {("J3", "1"): "B-", ("J3", "2"): "B+", ("J2", "1"): "P-", ("J2", "2"): "P+"}
BAL_LABELS = ("B0", "B1", "B2", "B3")   # J11's pins 1-4: the cell taps (not C0-C3, which read as capacitors)
# pack: references placed by hand (KiCad x, y, angle), where they're clear; the search places them otherwise
REF_AT = {"C68": (115.9, 107.0, 90), "C67": (119.6, 109.26, 0), "J2": (131.5, 115.5, 0), "C34": (133.9, 118.6, 0)}


def mm(v):
    return int(round(v * MM))


def grow(bb, d):
    b = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
    b.Inflate(mm(d))
    return b


def clip(a, c, box):
    """Liang-Barsky: the part of segment a-c inside box (x0, y0, x1, y1), or None."""
    x0, y0, x1, y1 = box
    dx, dy = c[0] - a[0], c[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy)


def trim(b, inner):
    """Footprint silk off the board goes; segments crossing the edge are cut back to it. The motor connectors (M1-M6)
    also lose the body detail between their pins and the board edge, which leaves room for their reference."""
    box = (inner.GetLeft(), inner.GetTop(), inner.GetRight(), inner.GetBottom())
    gone = []
    for f in b.GetFootprints():
        if f.GetPadCount() == 0:                        # the logo: placed whole by place_logo()
            continue
        pads = None
        if f.GetReference().startswith("M") and f.GetReference()[1:].isdigit():
            pads = True
            pb = pcbnew.BOX2I()
            for p in f.Pads():
                pb.Merge(p.GetBoundingBox())
            right = pb.GetCenter().x > (box[0] + box[2]) / 2
        for g in list(f.GraphicalItems()):
            if g.GetClass() == "PCB_FIELD" or not (g.IsOnLayer(pcbnew.F_SilkS) or g.IsOnLayer(pcbnew.B_SilkS)):
                continue
            gb = g.GetBoundingBox()
            if pads is not None and ((right and gb.GetLeft() > pb.GetRight() + mm(0.3)) or
                                     (not right and gb.GetRight() < pb.GetLeft() - mm(0.3))):
                gone.append((f, g))
                continue
            if inner.Contains(gb.GetOrigin()) and inner.Contains(gb.GetEnd()):
                continue
            if g.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                a, c = g.GetStart(), g.GetEnd()
                seg = clip((a.x, a.y), (c.x, c.y), box)
                r = mm(1.0)                             # rounded corners: keep out of the corner squares too
                if seg and any((q[0] < box[0] + r or q[0] > box[2] - r) and (q[1] < box[1] + r or q[1] > box[3] - r)
                               for q in seg):
                    flat = abs(seg[1][0] - seg[0][0]) >= abs(seg[1][1] - seg[0][1])
                    seg = clip(seg[0], seg[1], (box[0] + r, box[1], box[2] - r, box[3]) if flat else
                               (box[0], box[1] + r, box[2], box[3] - r))
                if seg and (seg[0][0] - seg[1][0]) ** 2 + (seg[0][1] - seg[1][1]) ** 2 > mm(0.2) ** 2:
                    g.SetStart(pcbnew.VECTOR2I(int(seg[0][0]), int(seg[0][1])))
                    g.SetEnd(pcbnew.VECTOR2I(int(seg[1][0]), int(seg[1][1])))
                    continue
            elif inner.Intersects(gb):
                continue                                # arcs and polygons partly inside stay whole
            gone.append((f, g))
    for f, g in gone:                                   # (pcbnew's item lists go stale if removed while iterating)
        f.Remove(g)
    return len(gone)


def place_logo(b, inner, obst):
    """Move the goose logo (the one footprint without pads) to a free spot on the back: clear of back pads, through-hole
    pads, back silk and back courtyards, so no part covers it. It shrinks (80, 65, then 50 %) until it fits. Returns
    where it went, or None if it doesn't fit even at half size."""
    logo = next((f for f in b.GetFootprints() if f.GetPadCount() == 0 and f.IsFlipped()), None)
    if logo is None:
        return None
    crt = [grow(f.GetCourtyard(pcbnew.B_CrtYd).BBox(), 0.2) for f in b.GetFootprints()
           if f.GetPadCount() and f.GetCourtyard(pcbnew.B_CrtYd).OutlineCount()]
    blocks = [o for own, o in obst[pcbnew.B_SilkS]] + crt
    shapes = [g for g in logo.GraphicalItems() if g.GetClass() != "PCB_FIELD"]

    def extent():
        lb = pcbnew.BOX2I()
        for g in shapes:
            lb.Merge(g.GetBoundingBox())
        return lb

    for x, y, ang in LOGO_SPOTS:                        # the chosen spot first, if it's still free
        logo.SetOrientationDegrees(ang)
        logo.SetPosition(pcbnew.VECTOR2I(int(round((OX + x) * MM)), int(round((OY + y) * MM))))
        lb = extent()
        if inner.Contains(lb.GetOrigin()) and inner.Contains(lb.GetEnd()) and not any(o.Intersects(lb) for o in blocks):
            obst[pcbnew.B_SilkS].append((None, grow(lb, GAP)))
            logo.Reference().SetVisible(False)
            return ((OX + x), (OY + y), ang, 1.0, lb.GetWidth() / MM, lb.GetHeight() / MM)
    size = 1.0
    for scale in (1.0, 0.8, 0.65, 0.5):
        if scale != size:                               # shrink every shape about the logo's own centre
            c = extent().GetCenter()
            for g in shapes:
                g.Move(pcbnew.VECTOR2I(-c.x, -c.y))
                g.Scale(scale / size)
                g.Move(c)
            size = scale
        for ang in (0, 90, 180, 270):
            logo.SetOrientationDegrees(ang)
            y = inner.GetTop()
            while y < inner.GetBottom():
                x = inner.GetLeft()
                while x < inner.GetRight():
                    logo.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
                    lb = extent()
                    if inner.Contains(lb.GetOrigin()) and inner.Contains(lb.GetEnd()) and \
                            not any(o.Intersects(lb) for o in blocks):
                        obst[pcbnew.B_SilkS].append((None, grow(lb, GAP)))
                        logo.Reference().SetVisible(False)
                        return (x / MM, y / MM, ang, scale, lb.GetWidth() / MM, lb.GetHeight() / MM)
                    x += mm(0.5)
                y += mm(0.5)
    return None


def nudge_marks(b, inner):
    """Footprint silk on another part's pad moves 0.1-0.8 mm (whichever way, straight or diagonal, clears every pad
    first). Returns how many moved."""
    pads = [(f.GetReference(), grow(p.GetBoundingBox(), GAP)) for f in b.GetFootprints() for p in f.Pads()
            if p.IsOnLayer(pcbnew.F_Cu) or p.GetDrillSize().x > 0]
    moved = 0
    for f in b.GetFootprints():
        ref = f.GetReference()
        for g in f.GraphicalItems():
            if g.GetClass() == "PCB_FIELD" or not g.IsOnLayer(pcbnew.F_SilkS):
                continue
            if not any(own != ref and o.Intersects(g.GetBoundingBox()) for own, o in pads):
                continue
            for step in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8):
                done = False
                for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1), (-0.7, -0.7), (0.7, -0.7), (-0.7, 0.7), (0.7, 0.7)):
                    d = pcbnew.VECTOR2I(mm(dx * step), mm(dy * step))
                    g.Move(d)
                    gb = g.GetBoundingBox()
                    if inner.Contains(gb.GetOrigin()) and inner.Contains(gb.GetEnd()) and \
                            not any(o.Intersects(gb) for own, o in pads if own != ref) and \
                            not any(o.Intersects(gb) for own, o in pads if own == ref):
                        done = True
                        break
                    g.Move(pcbnew.VECTOR2I(-d.x, -d.y))
                if done:
                    moved += 1
                    break
    return moved


def place_labels(b, inner, obst):
    """Polarity labels beside J3's and J2's pads and B0-B3 under J11's pins, on F.Silkscreen in the PCB group LABELS,
    each at the first spot beside its pad that clears pads, silk and the edge."""
    grp = next((g for g in b.Groups() if g.GetName() == LABELS), None)
    if grp is None:
        grp = pcbnew.PCB_GROUP(b)
        grp.SetName(LABELS)
        b.Add(grp)
    fp = {f.GetReference(): f for f in b.GetFootprints()}
    jobs = [(text, next(p for p in fp[ref].Pads() if p.GetNumber() == num).GetBoundingBox(), ("left", "right", "top",
                                                                                              "bottom"))
            for (ref, num), text in PAD_LABELS.items()]
    done = []
    j11 = fp["J11"]                                     # one row under J11's pins, each centred on its pin
    under = j11.GetCourtyard(pcbnew.F_CrtYd).BBox().GetBottom()
    row = []
    for text, p in zip(BAL_LABELS, sorted(j11.Pads(), key=lambda p: int(p.GetNumber()))):
        t = pcbnew.PCB_TEXT(b)
        t.SetText(text)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(mm(LABEL_H), mm(LABEL_H)))
        t.SetTextThickness(mm(T))
        t.SetPosition(pcbnew.VECTOR2I(p.GetPosition().x, under + mm(0.15 + LABEL_H / 2 + 0.1)))
        row.append(t)
    if all(not any(o.Intersects(t.GetBoundingBox()) for own, o in obst[pcbnew.F_SilkS]) for t in row):
        for t in row:
            b.Add(t)
            grp.AddItem(t)
            obst[pcbnew.F_SilkS].append((None, grow(t.GetBoundingBox(), GAP)))
            done.append(t.GetText())
    else:                                               # no clear row: each label on its own, under its pin
        for text, p in zip(BAL_LABELS, sorted(j11.Pads(), key=lambda p: int(p.GetNumber()))):
            c = p.GetPosition()
            jobs.append((text, pcbnew.BOX2I(pcbnew.VECTOR2I(c.x - mm(0.1), under - mm(0.1)),
                                            pcbnew.VECTOR2I(mm(0.2), mm(0.1))), ("bottom", "top")))
    for text, bb, sides in jobs:
        t = pcbnew.PCB_TEXT(b)
        t.SetText(text)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(mm(LABEL_H), mm(LABEL_H)))
        t.SetTextThickness(mm(T))
        cx, cy = bb.GetCenter().x, bb.GetCenter().y
        spot = None
        for extra in (0.15, 0.4, 0.8, 1.2, 1.8, 2.5):
            for where in sides:
                for slide in (0.0, -0.5, 0.5, -1.0, 1.0, -1.5, 1.5, -2.0, 2.0):
                    t.SetPosition(pcbnew.VECTOR2I(cx, cy))
                    tb = t.GetBoundingBox()
                    hw, hh, e, sl = tb.GetWidth() / 2, tb.GetHeight() / 2, mm(extra), mm(slide)
                    pos = {"top": (cx + sl, bb.GetTop() - hh - e), "bottom": (cx + sl, bb.GetBottom() + hh + e),
                           "left": (bb.GetLeft() - hw - e, cy + sl), "right": (bb.GetRight() + hw + e, cy + sl)}[where]
                    t.SetPosition(pcbnew.VECTOR2I(int(pos[0]), int(pos[1])))
                    tb = t.GetBoundingBox()
                    if inner.Contains(tb.GetOrigin()) and inner.Contains(tb.GetEnd()) and \
                            not any(o.Intersects(tb) for own, o in obst[pcbnew.F_SilkS]):
                        spot = tb
                        break
                if spot:
                    break
            if spot:
                break
        if spot:
            b.Add(t)
            grp.AddItem(t)
            obst[pcbnew.F_SilkS].append((None, grow(spot, GAP)))
            done.append(text)
        else:
            done.append(text + "(no room)")
    return done


def main():
    b = pcbnew.LoadBoard(str(PCB))
    edge = b.GetBoardEdgesBoundingBox()
    inner = grow(edge, -EDGE)
    trimmed = trim(b, grow(edge, -0.15))
    old = next((g for g in b.Groups() if g.GetName() == LABELS), None)
    if old is not None and len(old.GetItems()):          # the last run's labels
        for item in list(old.GetItems()):
            b.Remove(item)
        trimmed += 1
    if trimmed:                                         # a fresh process: pcbnew's lists go stale after removals
        b.Save(str(PCB))
        print("silk: %d silk items trimmed" % trimmed, flush=True)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    side_of = {}
    obst = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    cu = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}
    for f in b.GetFootprints():
        side_of[f.GetReference()] = pcbnew.B_SilkS if f.IsFlipped() else pcbnew.F_SilkS
        for p in f.Pads():
            for s, L in cu.items():
                if p.IsOnLayer(L) or p.GetDrillSize().x > 0:
                    obst[s].append((None, grow(p.GetBoundingBox(), GAP)))
        if f.GetPadCount() == 0 and f.IsFlipped():      # the logo itself: it's about to move, so it can't block
            continue
        for g in f.GraphicalItems():
            for s in obst:
                if g.IsOnLayer(s) and g.GetClass() != "PCB_FIELD":
                    obst[s].append((f.GetReference(), grow(g.GetBoundingBox(), GAP)))
    for d in b.GetDrawings():
        for s in obst:
            if d.IsOnLayer(s):
                obst[s].append((None, grow(d.GetBoundingBox(), GAP)))
    logo = place_logo(b, inner, obst)
    crts = []                                           # pack: (ref, courtyard) no other part's reference may cover
    if PACK:
        nudged = nudge_marks(b, inner)
        if nudged:
            print("silk: %d footprint marks nudged off other parts' pads" % nudged)
        labelled = place_labels(b, inner, obst)
        print("silk: labels %s" % " ".join(labelled))
        for f in b.GetFootprints():
            c = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
            if c.OutlineCount():
                crts.append((f.GetReference(), c.BBox()))
    hidden = []
    placed = 0
    # big parts first: they have the fewest good spots relative to their size
    fps = sorted(b.GetFootprints(), key=lambda f: -f.GetBoundingBox(False).GetArea())
    for f in fps:
        ref = f.GetReference()
        r = f.Reference()
        s = side_of[ref]
        if f.GetPadCount() == 0:                        # the logo
            r.SetVisible(False)
            continue
        if ref.startswith("FID"):
            r.SetVisible(False)
            hidden.append(ref)
            continue
        r.SetLayer(s)
        r.SetTextSize(pcbnew.VECTOR2I(mm(H), mm(H)))
        r.SetTextThickness(mm(T))
        r.SetKeepUpright(True)
        r.SetVisible(True)
        crt = f.GetCourtyard(pcbnew.B_CrtYd if s == pcbnew.B_SilkS else pcbnew.F_CrtYd)
        bb = crt.BBox() if crt.OutlineCount() else f.GetBoundingBox(False)
        cx, cy = bb.GetCenter().x, bb.GetCenter().y
        spot = None
        if PACK and ref in REF_AT:                     # a hand-picked spot, if it's clear
            x, y, ang = REF_AT[ref]
            r.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
            r.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
            tb = r.GetBoundingBox()
            if inner.Contains(tb.GetOrigin()) and inner.Contains(tb.GetEnd()) and \
                    not any(o.Intersects(tb) for own, o in obst[s]):
                spot = tb
        for extra in (() if spot else (0.05, 0.3, 0.6, 1.0, 1.5, 2.2)):
            for where in ("top", "bottom", "left", "right", "centre"):
                if where == "centre" and extra > 0.05:
                    continue
                for ang in ((0, 90) if where in ("top", "bottom", "centre") else (90, 0)):
                    for slide in (0.0, -0.5, 0.5, -1.0, 1.0, -1.6, 1.6):
                        r.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
                        r.SetPosition(pcbnew.VECTOR2I(cx, cy))
                        tb = r.GetBoundingBox()
                        hw, hh = tb.GetWidth() / 2, tb.GetHeight() / 2
                        e, sl = mm(extra), mm(slide)
                        pos = {"top": (cx + sl, bb.GetTop() - hh - e), "bottom": (cx + sl, bb.GetBottom() + hh + e),
                               "left": (bb.GetLeft() - hw - e, cy + sl), "right": (bb.GetRight() + hw + e, cy + sl),
                               "centre": (cx + sl, cy)}[where]
                        r.SetPosition(pcbnew.VECTOR2I(int(pos[0]), int(pos[1])))
                        tb = r.GetBoundingBox()
                        if not inner.Contains(tb.GetOrigin()) or not inner.Contains(tb.GetEnd()):
                            continue
                        if any(o.Intersects(tb) for own, o in obst[s]) or \
                                any(own != ref and o.Intersects(tb) for own, o in crts):
                            continue
                        spot = tb
                        break
                    if spot:
                        break
                if spot:
                    break
            if spot:
                break
        if spot:
            obst[s].append((None, grow(spot, GAP)))
            placed += 1
        else:
            r.SetVisible(False)
            hidden.append(ref)
    b.Save(str(PCB))
    print("silk: logo %s; %d references placed, %d hidden: %s" % (
        "at %.1f, %.1f (board-local), %d deg, %.1f x %.1f mm" % (logo[0] - 99.95, logo[1] - 99.95, logo[2],
                                                                logo[4], logo[5])
        if logo else "doesn't fit",
        placed, len(hidden), " ".join(sorted(hidden))))


if __name__ == "__main__":
    main()
