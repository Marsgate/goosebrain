"""Fine-pitch escapes for tools/route_llm.py: a straight stub from each signal pad out past its toe.

A* on a pin row finds the shortest pair first and seals the other pins in (ROUTING_LOG.md, pass 8). Giving every pin a
stub first leaves one free cell per net outside the row, so the order no longer matters there. Each stub runs from the
pad's centre away from the part's centre (diagonally for a corner pad), on the pad's layer, as long as the grid maps
allow: up to REACH past the toe, at the net's class width, else 0.2 mm, else 0.15 mm (Default nets only: Power and
Charger have a 0.2 mm floor). A ref escapes all its pins ("U7"), a ref.pin just that one ("U7.5"). Stubs join the maps as they're
laid, so neighbours keep their clearance. Pads already joined to a track, plane nets and unconnected pins are left
alone.
"""
import math

import grid_router as gr
import pcbnew

REACH = (0.8, 0.6, 0.45, 0.3)          # mm past the toe, longest first
WIDTHS = (None, 0.2, 0.15)             # None: the net's class width


def _ok_line(g, rt, l, ax, ay, bx, by):
    n = max(1, int(math.hypot(bx - ax, by - ay) / (gr.G / 2)))
    for k in range(n + 1):
        x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
        cx, cy = int(x / gr.G), int(y / gr.G)
        if not (0 <= cx < g.nx and 0 <= cy < g.ny) or not rt.ok(l * g.plane + cy * g.nx + cx):
            return False
    return True


def add(b, g, rt, grp, refs, nets):
    out, want = [], {}
    for r in refs:
        ref, _, pin = r.partition(".")
        want.setdefault(ref, set()).add(pin or None)
    for ref, pins in want.items():
        f = b.FindFootprintByReference(ref)
        fc = gr.lpos(f.GetPosition())
        for p in f.Pads():
            net = p.GetNetname()
            if None not in pins and p.GetNumber() not in pins:
                continue
            if not net or net in gr.SKIP or net.startswith("unconnected-") or not gr.pad_layers(p):
                continue
            if any(c.GetClass() in ("PCB_TRACK", "PCB_VIA") for c in b.GetConnectivity().GetConnectedItems(p)):
                continue
            l = gr.pad_layers(p)[0]
            pc = gr.lpos(p.GetPosition())
            vx, vy = pc[0] - fc[0], pc[1] - fc[1]
            sz = p.GetSize()
            if abs(sz.x - sz.y) < 0.02 * gr.MM:                  # a square corner pad: straight out diagonally
                dx, dy = math.copysign(math.sqrt(0.5), vx), math.copysign(math.sqrt(0.5), vy)
                toe = sz.x / gr.MM / 2
            elif abs(vx) > abs(vy):
                dx, dy, toe = math.copysign(1, vx), 0.0, max(sz.x, sz.y) / gr.MM / 2
            else:
                dx, dy, toe = 0.0, math.copysign(1, vy), max(sz.x, sz.y) / gr.MM / 2
            done = None
            rt.use(g.nid(net), None)
            floor = 0.15 if rt.width <= 0.15 + 1e-6 else 0.2
            for w in WIDTHS:
                if w is not None and w < floor - 1e-6:
                    continue
                rt.use(g.nid(net), w)
                if w is None and rt.width > gr.NARROW and not gr.CLASS_W:
                    continue
                for L in REACH:
                    ex, ey = pc[0] + dx * (toe + L), pc[1] + dy * (toe + L)
                    # snap the end to a cell centre so A* can start from it
                    ex, ey = (int(ex / gr.G) + 0.5) * gr.G, (int(ey / gr.G) + 0.5) * gr.G
                    if _ok_line(g, rt, l, pc[0] + dx * toe, pc[1] + dy * toe, ex, ey):
                        done = (rt.width, L, ex, ey)
                        break
                if done:
                    break
            if not done:
                out.append({"pad": f"{ref}.{p.GetNumber()}", "net": net, "stub": None})
                continue
            w, L, ex, ey = done
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(p.GetPosition())
            t.SetEnd(gr.bpos(ex, ey))
            t.SetLayer(gr.LAYERS[l])
            t.SetWidth(int(round(w * gr.MM)))
            t.SetNet(nets[net])
            b.Add(t)
            grp.AddItem(t)
            g.seg([l], g.nid(net), pc[0], pc[1], ex, ey, w / 2)
            out.append({"pad": f"{ref}.{p.GetNumber()}", "net": net, "stub": {"width": w, "past_toe_mm": L}})
    return out
