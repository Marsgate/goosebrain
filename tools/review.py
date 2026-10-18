"""Render, check and summarise the KiCad design for a design-review loop.

    .venv/bin/python tools/review.py sch [--out DIR]
    .venv/bin/python tools/review.py pcb [--out DIR] [--baseline DIR]

Each run writes a numbered folder under build/review/<sch|pcb>/ (or --out):

    summary.md     gates and findings, the file to read first
    summary.json   the same, machine-readable
    images/*.png   full views plus zoomed tiles, sized for reading

Gates (the hard checks every iteration must pass):
    sch: ERC has no errors; the schematic netlist matches the SKiDL netlist.
    pcb: DRC has no errors and no new warnings compared with --baseline;
         nothing is unrouted; schematic parity is clean; power nets meet
         their minimum track width.

The exit code is 0 when every gate passes.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
KICAD_APP = Path("/Applications/KiCad/KiCad.app/Contents")
KICAD_CLI = KICAD_APP / "MacOS/kicad-cli"
KICAD_PYTHON = KICAD_APP / "Frameworks/Python.framework/Versions/Current/bin/python3"
SCH = ROOT / "kicad/thegoose.kicad_sch"
PCB = ROOT / "kicad/thegoose.kicad_pcb"
SKIDL_NET = ROOT / "build/goosebrain.net"

# Minimum track width (mm) per power net. Starting points, not datasheet
# limits; pours (GND, the pack path) leave only short stubs. The pack path
# carries all motor current, with stall peaks of several amps. The charger
# nets carry up to 3 A once firmware raises the input limit. Motor outputs
# carry up to ~1 A per DRV8848 bridge.
POWER_NETS = {
    "/Power & charging/PACK+": 1.0, "VBAT": 1.0, "VSYS": 1.0,  # pack, fuse, switch
    "VBUS": 0.5, "/Power & charging/CHG_SYS": 0.5, "Net-(U7-PMID)": 0.5,
    "Net-(U7-SW1)": 0.5, "Net-(U7-SW2)": 0.5,
    "VCC": 0.5, "GND": 0.4,
}
POWER_NET_PREFIXES = {"Net-(M": 0.4}

# Schematic-parity findings that aren't real mismatches: board-only parts
# (mounting holes, logo) and the empty Datasheet field.
PARITY_IGNORE_REFS = ("REF**", "G***")
PARITY_IGNORE_FIELDS = ("Field 'Datasheet' differs",)

TILE_PX = 1400  # tiles are cut so text stays legible when viewed
SCH_DPI = 300  # schematic pages are A4/A3
PCB_DPI = 1200  # boards are small; this shows pad-level detail

sys.path.insert(0, str(ROOT / "circuit"))
from compare_netlists import fmt, load  # noqa: E402


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, **kwargs)


def next_run_dir(kind, out):
    if out:
        path = Path(out)
    else:
        base = ROOT / "build/review" / kind
        base.mkdir(parents=True, exist_ok=True)
        n = 1 + max((int(p.name) for p in base.iterdir() if p.name.isdigit()), default=0)
        path = base / f"{n:02d}"
    (path / "images").mkdir(parents=True, exist_ok=True)
    return path


# Images ----------------------------------------------------------------------


def svg_to_png(svg, png, dpi):
    """Render an SVG, crop it to its content and cut zoomed tiles.

    Returns the list of PNG paths written (full view first).
    """
    doc = pymupdf.open(svg)
    pix = doc[0].get_pixmap(dpi=dpi, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    bg = Image.new("RGB", img.size, img.getpixel((1, 1)))
    diff = ImageChops.difference(img, bg).convert("L").point(lambda v: 255 if v > 30 else 0)
    box = diff.getbbox()
    if box:
        pad = 40
        img = img.crop((
            max(box[0] - pad, 0), max(box[1] - pad, 0),
            min(box[2] + pad, img.width), min(box[3] + pad, img.height),
        ))

    written = []
    full = img.copy()
    full.thumbnail((2000, 2000))
    full.save(png)
    written.append(png)

    # Overlapping tiles at full render resolution, for reading small text.
    if img.width > TILE_PX or img.height > TILE_PX:
        step = int(TILE_PX * 0.85)
        cols = range(0, max(img.width - TILE_PX, 0) + step, step)
        rows = range(0, max(img.height - TILE_PX, 0) + step, step)
        for r, y in enumerate(rows):
            for c, x in enumerate(cols):
                tile = img.crop((x, y, min(x + TILE_PX, img.width), min(y + TILE_PX, img.height)))
                path = png.with_name(f"{png.stem}_tile_r{r}c{c}.png")
                tile.save(path)
                written.append(path)
    return written


# Schematic -------------------------------------------------------------------


def review_sch(out):
    results = {"kind": "sch", "gates": {}, "images": []}

    # SKiDL is the text source of truth; regenerate its netlist first.
    skidl = run(ROOT / ".venv/bin/python", ROOT / "circuit/goosebrain.py")
    if skidl.returncode != 0:
        results["gates"]["skidl"] = {"pass": False, "detail": skidl.stderr[-2000:]}

    erc_json = out / "erc.json"
    run(KICAD_CLI, "sch", "erc", "--format", "json", "--severity-all", "-o", erc_json, SCH)
    violations = [v for s in json.loads(erc_json.read_text())["sheets"] for v in s["violations"]]
    by_severity = Counter(v["severity"] for v in violations)
    results["erc"] = {
        "counts": dict(by_severity),
        "types": dict(Counter(f"{v['severity']}:{v['type']}" for v in violations)),
        "violations": [
            {"type": v["type"], "severity": v["severity"], "description": v["description"],
             "items": [i["description"] for i in v["items"]]}
            for v in violations
        ],
    }
    results["gates"]["erc_errors"] = {"pass": by_severity.get("error", 0) == 0,
                                      "detail": f"{by_severity.get('error', 0)} error(s)"}

    sch_net = out / "schematic.net"
    run(KICAD_CLI, "sch", "export", "netlist", "-o", sch_net, SCH)
    results["gates"]["netlist_matches_skidl"] = compare_nets(sch_net, SKIDL_NET)

    svg_dir = out / "svg"
    run(KICAD_CLI, "sch", "export", "svg", "--exclude-drawing-sheet", "-o", svg_dir, SCH)
    for svg in sorted(svg_dir.glob("*.svg")):
        results["images"] += [str(p.relative_to(out)) for p in svg_to_png(svg, out / "images" / f"{svg.stem}.png", SCH_DPI)]
    return results


def compare_nets(actual_path, reference_path):
    actual_parts, actual_nets = load(actual_path)
    ref_parts, ref_nets = load(reference_path)
    diffs = []
    for ref in sorted(set(ref_parts) ^ set(actual_parts)):
        diffs.append(f"part {ref} only in {'SKiDL' if ref in ref_parts else 'KiCad'}")
    for ref in sorted(set(ref_parts) & set(actual_parts)):
        for key in ("value", "footprint", "mpn", "lcsc"):
            a, b = actual_parts[ref][key].strip(), ref_parts[ref][key].strip()
            if a != b:
                diffs.append(f"part {ref} {key}: KiCad {a!r}, SKiDL {b!r}")
    a_conns = {n for n in actual_nets.values() if len(n) > 1}
    r_conns = {n for n in ref_nets.values() if len(n) > 1}
    diffs += [f"only in SKiDL: {fmt(n)}" for n in r_conns - a_conns]
    diffs += [f"only in KiCad: {fmt(n)}" for n in a_conns - r_conns]
    return {"pass": not diffs, "detail": "MATCH" if not diffs else f"{len(diffs)} difference(s)",
            "diffs": diffs}


# PCB -------------------------------------------------------------------------

PCB_VIEWS = {
    # name: (layers, extra kicad-cli args)
    "top": ("F.Cu,F.Silkscreen,F.Mask,Edge.Cuts", []),
    "bottom": ("B.Cu,B.Silkscreen,B.Mask,Edge.Cuts", ["--mirror"]),
    "inner1": ("In1.Cu,Edge.Cuts", []),
    "inner2": ("In2.Cu,Edge.Cuts", []),
    "inner3": ("In3.Cu,Edge.Cuts", []),
    "inner4": ("In4.Cu,Edge.Cuts", []),
    "assembly_top": ("F.Fab,F.Courtyard,F.Silkscreen,Edge.Cuts", []),
}

TRACK_METRICS = r"""
import json, sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
nets = {}
for t in b.GetTracks():
    n = nets.setdefault(t.GetNetname(), {"min_width": None, "length": 0.0, "vias": 0, "segments": 0})
    if t.GetClass() == "PCB_VIA":
        n["vias"] += 1
        continue
    w = pcbnew.ToMM(t.GetWidth())
    n["min_width"] = w if n["min_width"] is None else min(n["min_width"], w)
    n["length"] += pcbnew.ToMM(t.GetLength())
    n["segments"] += 1
zones = [{"net": z.GetNetname(), "layers": [b.GetLayerName(l) for l in z.GetLayerSet().Seq()]}
         for z in b.Zones()]
bb = b.GetBoardEdgesBoundingBox()
print(json.dumps({"nets": nets, "zones": zones,
                  "board_mm": [pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())],
                  "copper_layers": b.GetCopperLayerCount()}))
"""


def parity_ignored(p):
    if p["description"].startswith(PARITY_IGNORE_FIELDS):
        return True
    return all(i.removeprefix("Footprint ").startswith(PARITY_IGNORE_REFS) for i in p["items"])


def review_pcb(out, baseline):
    results = {"kind": "pcb", "gates": {}, "images": []}

    drc_json = out / "drc.json"
    run(KICAD_CLI, "pcb", "drc", "--format", "json", "--schematic-parity", "--severity-all",
        "--refill-zones", "-o", drc_json, PCB)
    drc = json.loads(drc_json.read_text())
    violations = drc["violations"]
    types = Counter(f"{v['severity']}:{v['type']}" for v in violations)
    results["drc"] = {
        "types": dict(types),
        "unconnected": len(drc["unconnected_items"]),
        "parity": [
            {"type": v["type"], "description": v["description"],
             "items": [i["description"] for i in v["items"]]}
            for v in drc["schematic_parity"]
        ],
        "violations": [
            {"type": v["type"], "severity": v["severity"], "description": v["description"],
             "items": [i["description"] for i in v["items"]]}
            for v in violations if v["severity"] == "error"
        ],
    }
    errors = sum(n for k, n in types.items() if k.startswith("error:"))
    results["gates"]["drc_errors"] = {"pass": errors == 0, "detail": f"{errors} error(s)"}
    results["gates"]["unrouted"] = {"pass": not drc["unconnected_items"],
                                    "detail": f"{len(drc['unconnected_items'])} unconnected item(s)"}
    parity = [p for p in results["drc"]["parity"] if not parity_ignored(p)]
    results["gates"]["schematic_parity"] = {
        "pass": not parity,
        "detail": f"{len(parity)} issue(s), {len(drc['schematic_parity']) - len(parity)} ignored",
        "diffs": [f"{p['type']}: {p['description']} ({', '.join(p['items'])})" for p in parity],
    }

    if baseline:
        base = json.loads((Path(baseline) / "summary.json").read_text())["drc"]["types"]
        new = {k: n - base.get(k, 0) for k, n in types.items() if n > base.get(k, 0)}
        results["gates"]["no_new_drc"] = {"pass": not new, "detail": new or "none new"}

    metrics = json.loads(run(KICAD_PYTHON, "-c", TRACK_METRICS, PCB).stdout)
    results["metrics"] = metrics
    thin = []
    for net, info in metrics["nets"].items():
        need = POWER_NETS.get(net) or next(
            (w for p, w in POWER_NET_PREFIXES.items() if net.startswith(p)), None)
        if need and info["min_width"] is not None and info["min_width"] + 1e-6 < need:
            thin.append(f"{net}: {info['min_width']:.2f} mm < {need} mm")
    results["gates"]["power_track_width"] = {"pass": not thin, "detail": thin or "ok"}

    for name, (layers, extra) in PCB_VIEWS.items():
        svg = out / "svg" / f"{name}.svg"
        svg.parent.mkdir(exist_ok=True)
        run(KICAD_CLI, "pcb", "export", "svg", "--mode-single", "--layers", layers,
            "--page-size-mode", "2", "--exclude-drawing-sheet", *extra, "-o", svg, PCB)
        if svg.exists():
            results["images"] += [str(p.relative_to(out)) for p in svg_to_png(svg, out / "images" / f"{name}.png", PCB_DPI)]

    render = out / "images" / "render_top.png"
    run(KICAD_CLI, "pcb", "render", "--side", "top", "--quality", "high", "--width", "2000",
        "--height", "1700", "--background", "opaque", "-o", render, PCB)
    if render.exists():
        results["images"].append(str(render.relative_to(out)))
    return results


# Summary ---------------------------------------------------------------------


def write_summary(out, results):
    (out / "summary.json").write_text(json.dumps(results, indent=2))
    passed = all(g["pass"] for g in results["gates"].values())
    lines = [f"# {results['kind'].upper()} review: {'ALL GATES PASS' if passed else 'GATES FAILING'}", "",
             "## Gates", ""]
    for name, g in results["gates"].items():
        lines.append(f"- [{'x' if g['pass'] else ' '}] {name}: {g['detail']}")
        lines += [f"  - {d}" for d in g.get("diffs", [])[:20]]
    if "erc" in results:
        lines += ["", "## ERC", ""] + [f"- {k}: {n}" for k, n in sorted(results["erc"]["types"].items())]
    if "drc" in results:
        lines += ["", "## DRC", ""] + [f"- {k}: {n}" for k, n in sorted(results["drc"]["types"].items())]
        m = results["metrics"]
        lines += ["", "## Board", "",
                  f"- {m['board_mm'][0]:.1f} x {m['board_mm'][1]:.1f} mm, {m['copper_layers']} copper layers",
                  f"- zones: {', '.join(z['net'] + ' on ' + '/'.join(z['layers']) for z in m['zones']) or 'none'}"]
    lines += ["", "## Images", "", "Full views first; `_tile_` images are zoomed sections.", ""]
    lines += [f"- {p}" for p in results["images"]]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=["sch", "pcb"])
    parser.add_argument("--out", help="output folder (default: next numbered folder)")
    parser.add_argument("--baseline", help="earlier pcb review folder to compare DRC against")
    args = parser.parse_args()

    out = next_run_dir(args.kind, args.out)
    results = review_sch(out) if args.kind == "sch" else review_pcb(out, args.baseline)
    passed = write_summary(out, results)
    print(out / "summary.md")
    print("ALL GATES PASS" if passed else "GATES FAILING")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
