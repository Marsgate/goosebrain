"""One routing pass of tools/grid_router.py with a machine-readable report of what failed and why.

Run with KiCad's Python on a DRC report in JSON (the board is edited in place, like grid_router.py):
    .../python3 tools/route_llm.py drc.json report.json [--board=pack|pack2s] [--clear] [--first=NET,...] [--rip=NET,...]
        [--escape=REF,...]

It routes exactly as grid_router.main() does (same grid, maps, A*, order and emit), so the router itself stays one file.
On top of that:
- --rip=NET,... removes those nets' tracks and vias from the "autoroute" group before routing, so they route again
  after --first.
- --escape=REF[.PIN],... first gives every signal pad of those parts (or just the named pins) a short stub straight out past the pad's
  toe (tools/escape.py), checked against the same maps, so A* starts outside the pin row.
- every pair that fails gets a diagnosis instead of a log line:
    "pad_sealed"   no free cell on the pad for this net's width: the nets whose clearance covers it
    "trapped"      the reachable copper from one end is under 1 mm^2: an escape problem at that pin
    "walled_off"   both ends have room but no path: how close the search got, and the nets that form the wall there
  with the pad's part and pin, whether it is a fine-pitch pad, and a suggested next move.
report.json: {"routed": [...], "failed": [...], "summary": {...}}. Positions are board mm (KiCad coordinates).
"""
import collections
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grid_router as gr  # noqa: E402  (reads --board=pack from sys.argv)

import pcbnew  # noqa: E402

G, FREE, BLOCKED = gr.G, gr.FREE, gr.BLOCKED
TRAPPED_MM2 = 1.0
FLOOD_LIMIT = 400_000
WINDOW = 3.0                   # mm around the pair that the diagnosis looks at


def arg(name):
    return next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith(f"--{name}=")), [])


def describe(kind, it):
    """Part, pin, layer and whether it's a fine-pitch pad, for one end of a pair."""
    if kind == "pad":
        sz = it.GetSize()
        return {"kind": "pad", "ref": it.GetParentFootprint().GetReference(), "pin": it.GetNumber(),
                "fine_pitch": min(sz.x, sz.y) / gr.MM <= gr.FINE,
                "at_mm": [round(it.GetPosition().x / gr.MM, 3), round(it.GetPosition().y / gr.MM, 3)]}
    if kind == "zone":
        return {"kind": "zone", "name": it.GetZoneName()}
    p = it.GetPosition() if kind == "via" else it.GetStart()
    return {"kind": kind, "at_mm": [round(p.x / gr.MM, 3), round(p.y / gr.MM, 3)]}


COPPER = []                    # (layer index, net, x0, y0, x1, y1) of every pad, track and via (bounding boxes)


def owners(g, m, cells, n):
    """Tally which nets claim a set of node indices (in map m), other than net n. A cell two halos overlap on is
    BLOCKED in the map, so it goes to the nearest copper of another net instead (or to the edge or a keepout)."""
    c = collections.Counter()
    cells = list(cells)
    for i in cells[:: max(1, len(cells) // 300)]:
        v = m[i]
        if v >= 0 and v != n:
            c[g.netname[v]] += 1
        elif v == BLOCKED:
            l = i // g.plane
            x, y = xy(g, i)
            best, who = 0.6, None
            for cl, net, x0, y0, x1, y1 in COPPER:
                if cl == l and net != g.netname[n]:
                    d = math.hypot(max(x0 - x, 0, x - x1), max(y0 - y, 0, y - y1))
                    if d < best:
                        best, who = d, net
            c[who or "<edge or keepout>"] += 1
    return c


def index_copper(b):
    for f in b.GetFootprints():
        for p in f.Pads():
            bb = p.GetBoundingBox()
            (x0, y0), (x1, y1) = gr.lpos(bb.GetOrigin()), gr.lpos(bb.GetEnd())
            for l in gr.pad_layers(p):
                COPPER.append((l, p.GetNetname() or "<unconnected pin>", x0, y0, x1, y1))
    for t in b.GetTracks():
        bb = t.GetBoundingBox()
        (x0, y0), (x1, y1) = gr.lpos(bb.GetOrigin()), gr.lpos(bb.GetEnd())
        ls = [0, 1, 2] if t.GetClass() == "PCB_VIA" else ([gr.LAYERS.index(t.GetLayer())] if t.GetLayer() in gr.LAYERS else [])
        for l in ls:
            COPPER.append((l, t.GetNetname(), x0, y0, x1, y1))


def flood(g, rt, src, win):
    """Every node reachable from src for the current net (same moves as the search), inside win (cell box)."""
    wx0, wy0, wx1, wy1 = win
    seen = set(src)
    todo = list(src)
    frontier = set()
    nx, plane = g.nx, g.plane
    while todo and len(seen) < FLOOD_LIMIT:
        i = todo.pop()
        l, j = divmod(i, plane)
        y, x = divmod(j, nx)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            k = l * plane + (y + dy) * nx + x + dx
            if k in seen or not (wx0 <= x + dx <= wx1 and wy0 <= y + dy <= wy1):
                continue
            if rt.step_ok(l, x, y, dx, dy):
                seen.add(k)
                todo.append(k)
            elif 0 <= x + dx < nx and 0 <= y + dy < g.ny:
                frontier.add(k)
        if rt.via_ok(x, y):
            for l2 in range(3):
                k = l2 * plane + j
                if k not in seen:
                    seen.add(k)
                    todo.append(k)
    return seen, frontier


def xy(g, i):
    j = i % g.plane
    return ((j % g.nx + 0.5) * G, (j // g.nx + 0.5) * G)


def diagnose(g, rt, b, ia, ib, src, dst):
    n = rt.n
    if not src or not dst:
        kind, it = ia if not src else ib
        cells = gr.item_cells(g, _Any(rt), kind, it)
        c = owners(g, rt.m, cells, n)
        return {"reason": "pad_sealed", "at": describe(kind, it),
                "blocked_by": [{"net": k, "cells": v} for k, v in c.most_common(5)],
                "hint": "no room on this pad for a %.2f mm track: escape it by hand (tools/escape.py) or move %s"
                        % (rt.width, ", ".join(k for k, _ in c.most_common(2)))}
    pts = [xy(g, i) for i in list(src)[:50] + list(dst)[:50]]
    win = g.box(min(p[0] for p in pts) - WINDOW, min(p[1] for p in pts) - WINDOW,
                max(p[0] for p in pts) + WINDOW, max(p[1] for p in pts) + WINDOW)
    res = {}
    for side, cells, other in (("a", src, dst), ("b", dst, src)):
        seen, frontier = flood(g, rt, cells, win)
        if side == "a" and seen & dst:
            return {"reason": "search_gave_up", "hint": "a path exists but A* hit its node limit: raise "
                    "Router.search(limit=) or route this pair first (--first={net})", "blocked_by": []}
        res[side] = (seen, frontier)
        area = len({i % g.plane for i in seen}) * G * G
        if area < TRAPPED_MM2:
            kind, it = ia if side == "a" else ib
            c = owners(g, rt.m, frontier, n)
            at = describe(kind, it)
            pin = "%s.%s" % (at["ref"], at["pin"]) if "ref" in at else None
            return {"reason": "trapped", "at": at, "reachable_mm2": round(area, 3),
                    "blocked_by": [{"net": k, "cells": v} for k, v in c.most_common(5)],
                    "hint": "this end can't get out: %s or rip up %s"
                            % ("there's no room for an escape stub here (tried)" if pin in NO_ROOM else
                               "escape just this pin first (--escape=%s)" % pin if pin else
                               "it is a stub or track end: rip this net (--rip=%s)" % g.netname[n],
                               c.most_common(1)[0][0] if c else "its neighbours")}
    seen, frontier = res["a"]
    dpts = [xy(g, i) for i in list(dst)[:: max(1, len(dst) // 20)]]
    best, bi = 1e9, None
    for i in seen:
        p = xy(g, i)
        d = min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in dpts)
        if d < best:
            best, bi = d, i
    near = xy(g, bi)
    wall = [i for i in frontier if math.hypot(xy(g, i)[0] - near[0], xy(g, i)[1] - near[1]) < 1.5]
    c = owners(g, rt.m, wall, n)
    routed = [k for k, _ in c.most_common(3) if k in AUTOROUTED]
    return {"reason": "walled_off", "closest_mm": round(best, 3),
            "closest_at_mm": [round(gr.OX + near[0], 3), round(gr.OY + near[1], 3)],
            "reachable_mm2": round(len({i % g.plane for i in seen}) * G * G, 2),
            "blocked_by": [{"net": k, "cells": v, "autorouted": k in AUTOROUTED} for k, v in c.most_common(5)],
            "hint": ("route this net before %s (--first=%s) or rip them up (--rip=%s)" % (", ".join(routed), "{net}",
                                                                                        ",".join(routed)))
            if routed else "the wall is fixed copper (pads, fan-out, pours): move a part or re-plan the layer"}


class _Any:
    """item_cells() keeps only cells usable by the net; for a sealed pad we want every cell under it."""
    def __init__(self, rt):
        self.rt = rt

    def ok(self, i):
        return True


AUTOROUTED = set()
NO_ROOM = set()                # "REF.PIN" that --escape tried and found no room for a stub
T_DIAG = [0.0]


def rip(b, nets):
    grp = next((x for x in b.Groups() if x.GetName() == gr.GROUP), None)
    if grp is None:
        return 0
    doomed = [it for it in grp.GetItems() if it.Cast().GetNetname() in nets]
    for it in doomed:
        b.Remove(it.Cast())
    return len(doomed)


def main():
    drc_path, report_path = sys.argv[1], sys.argv[2]
    drc = json.load(open(drc_path))
    b = pcbnew.LoadBoard(str(gr.PCB))
    if "--clear" in sys.argv:
        for g0 in [x for x in b.Groups() if x.GetName() == gr.GROUP]:
            for it in list(g0.GetItems()):
                b.Remove(it)
            b.Remove(g0)
    ripped = rip(b, set(arg("rip")))
    if "--clear" in sys.argv or ripped:
        b.Save(str(gr.PCB))
        b = pcbnew.LoadBoard(str(gr.PCB))              # fresh lists: pcbnew's go stale after removals
    grp = next((x for x in b.Groups() if x.GetName() == gr.GROUP), None)
    if grp is not None:
        AUTOROUTED.update(it.Cast().GetNetname() for it in grp.GetItems())
    t0 = time.time()
    nets = {str(k): v for k, v in b.GetNetsByName().items()}
    classes = {k: v.GetNetClassName() for k, v in nets.items()}
    bb = b.GetBoardEdgesBoundingBox()
    g = gr.Grid(bb.GetWidth() / gr.MM, bb.GetHeight() / gr.MM, classes)
    gr.build(b, g)
    items = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            items[p.m_Uuid.AsString()] = ("pad", p)
    for t in b.GetTracks():
        items[t.m_Uuid.AsString()] = ("via" if t.GetClass() == "PCB_VIA" else "track", t)
    for z in b.Zones():
        if not z.GetIsRuleArea():
            items[z.m_Uuid.AsString()] = ("zone", z)
    # after --rip the DRC report is stale for the ripped nets: their pads are paired by nearest neighbour instead
    pairs, seen_nets = [], set()
    for u in drc.get("unconnected_items", []):
        its = u["items"]
        if len(its) != 2 or its[0]["uuid"] not in items or its[1]["uuid"] not in items:
            continue
        ia, ib = items[its[0]["uuid"]], items[its[1]["uuid"]]
        net = ia[1].GetNetname()
        if net in gr.SKIP:
            continue
        d = math.dist((its[0]["pos"]["x"], its[0]["pos"]["y"]), (its[1]["pos"]["x"], its[1]["pos"]["y"]))
        pairs.append((d, net, ia, ib))
        seen_nets.add(net)
    for net in set(arg("rip")) - seen_nets - gr.SKIP:
        pads = [("pad", p) for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
        for a, c in zip(pads, pads[1:]):
            pairs.append((a[1].GetPosition().Distance(c[1].GetPosition()) / gr.MM, net, a, c))
    if grp is None:
        grp = pcbnew.PCB_GROUP(b)
        grp.SetName(gr.GROUP)
        b.Add(grp)
    t_build = time.time() - t0
    rt = gr.Router(g)
    index_copper(b)
    escaped = []
    if arg("escape"):
        import escape
        escaped = escape.add(b, g, rt, grp, arg("escape"), nets)
        NO_ROOM.update(e["pad"] for e in escaped if e["stub"] is None)
    first = arg("first")
    rank = {net: k for k, net in enumerate(first)}
    pairs.sort(key=lambda p: (p[1] not in gr.WIDE, rank.get(p[1], len(first)), p[0]))
    routed, failed = [], []
    for d, net, ia, ib in pairs:
        path = None
        for width in (None, gr.NARROW):
            rt.use(g.nid(net), width)
            src, dst = gr.cluster_cells(g, rt, b, *ia), gr.cluster_cells(g, rt, b, *ib)
            if src & dst or (src and dst and (path := rt.search(src, dst))) or rt.width <= gr.NARROW or not gr.CLASS_W:
                break
        if src & dst:
            continue
        if path:
            gr.emit(b, g, rt, grp, nets[net], path)
            AUTOROUTED.add(net)
            routed.append({"net": net, "pair_mm": round(d, 2), "width": rt.width,
                           "vias": sum(1 for p, q in zip(path, path[1:]) if p[0] != q[0])})
            continue
        t1 = time.time()
        why = diagnose(g, rt, b, ia, ib, src, dst)
        T_DIAG[0] += time.time() - t1
        why["hint"] = why["hint"].replace("{net}", net)
        failed.append({"net": net, "pair_mm": round(d, 2), "width": rt.width, "from": describe(*ia),
                       "to": describe(*ib), **why})
    b.Save(str(gr.PCB))
    by_reason = collections.Counter(f["reason"] for f in failed)
    by_part = collections.Counter(e["ref"] for f in failed for e in (f["from"], f["to"]) if e.get("ref"))
    report = {"summary": {"pairs": len(routed) + len(failed), "routed": len(routed), "failed": len(failed),
                          "by_reason": by_reason, "parts_involved": by_part.most_common(), "ripped_items": ripped,
                          "escape_stubs": escaped, "first": first, "rip": arg("rip"),
                          "seconds": {"build": round(t_build), "diagnose": round(T_DIAG[0]),
                                      "total": round(time.time() - t0)}},
              "failed": failed, "routed": routed}
    json.dump(report, open(report_path, "w"), indent=1)
    print("route_llm: %d routed, %d failed %s" % (len(routed), len(failed), dict(by_reason)))


if __name__ == "__main__":
    main()
