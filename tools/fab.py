"""Build the fab package for the brain (kicad/thegoose.kicad_pcb, into build/fab/), the 3S battery pack
(kicad-pack/goosepack.kicad_pcb, into build/fab-pack/) or the 2S pack (kicad-pack-2s/goosepack2s.kicad_pcb, into
build/fab-pack2s/).

Writes:
- gerbers/: Gerbers for all 4 copper layers, mask, paste, silk and outline, plus Excellon drill files (PTH and NPTH)
- thegoose-gerbers.zip / goosepack-gerbers.zip / goosepack2s-gerbers.zip: the gerbers/ folder, ready to upload to JLCPCB
- bom.csv: the full BOM, every purchased part, grouped, with MPN, manufacturer, LCSC number and how it's assembled
- jlc_bom.csv / jlc_cpl.csv: JLC's PCBA BOM and placement files, machine-placed SMD parts only (both sides on the
  brain: order Standard PCBA, assembly side "Both Sides")

Assembly classes:
- "JLC SMT": SMD with an LCSC number and not DNP. These go in the JLC files.
- "JLC THT" (--panel only): through-hole parts with an LCSC number. These go in the panel's JLC files.
- "Hand-solder": through-hole connectors and the switch, soldered after the boards arrive (single-board package).
- "Hand-place": SMD parts marked DNP (on the brain D4, U14, F2 and SW2), bought separately and placed by hand.

Coordinates use the same absolute frame as the Gerbers (X right, Y up, mm, seen from the top for both sides), so JLC
lines them up without an offset. Top-side rotations are KiCad's plus the per-package offsets in JLC_ROTATION, which
were read off JLC's placement preview. Bottom-side parts get Layer "Bottom" and rotation (180 - KiCad + offset): JLC
doesn't mirror bottom parts the way KiCad does (KiBot's JLCPCB template: mirror_bottom, offsets added). JLC has changed
its bottom-side convention before, so the script lists every bottom part to check. Check each part's orientation in
JLC's placement preview before paying.

Panel (brain only, --panel): JLC's Standard PCBA needs edge rails on boards under 70 x 70 mm, and parts overhang
every edge of the brain so its ports sit flush with the case wall. KiKit builds a 1-up panel from tools/panel.json into
build/fab-panel/thegoose-panel.kicad_pcb: a full frame, 88.3 x 74.1 mm (JLC wants at least 70 mm on each side), with
a 6 mm routed gap above and below the board (SW1's lever reaches 4.5 mm past the bottom edge by its fab outline, J1/J4
1.9 mm past the top) and 5 mm beside it (M1-M6 reach 2.4 mm past the sides),
mouse-bite tabs at fixed spots where nothing overhangs (tools/panel_tabs.py), JLC's 1.152 mm tooling holes and three
1 mm fiducials, front and back. Every output above is then built from the panel into build/fab-panel/, with these
differences: coordinates are the panel's, and the through-hole parts with an LCSC number go in jlc_bom.csv and
jlc_cpl.csv too ("JLC THT"), since the overhanging connectors can be fitted while the board is still in the panel. It
also checks that no part reaches a rail and no tab sits under an overhanging part, and renders the panel front and back
into build/fab-panel/renders/. KiKit runs from build/kikit-venv (see KIKIT below).

Usage: python3 tools/fab.py [--board brain|pack|pack2s] [--panel]
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KICAD_APP = Path("/Applications/KiCad/KiCad.app/Contents")
KICAD_CLI = KICAD_APP / "MacOS/kicad-cli"
KICAD_PYTHON = KICAD_APP / "Frameworks/Python.framework/Versions/Current/bin/python3"
# board name -> (PCB file, output folder, Gerber zip name)
BOARDS = {
    "brain": (ROOT / "kicad/thegoose.kicad_pcb", ROOT / "build/fab", "thegoose-gerbers.zip"),
    "pack": (ROOT / "kicad-pack/goosepack.kicad_pcb", ROOT / "build/fab-pack", "goosepack-gerbers.zip"),
    "pack2s": (ROOT / "kicad-pack-2s/goosepack2s.kicad_pcb", ROOT / "build/fab-pack2s", "goosepack2s-gerbers.zip"),
}

# KiKit, installed into a venv on KiCad's own Python so it can import pcbnew:
#   /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
#       -m venv --system-site-packages build/kikit-venv && build/kikit-venv/bin/pip install kikit
KIKIT = ROOT / "build/kikit-venv/bin/kikit"
PANEL_PRESET = ROOT / "tools/panel.json"
PANEL_OUT = ROOT / "build/fab-panel"
PANEL_PCB = PANEL_OUT / "thegoose-panel.kicad_pcb"

LAYERS = ("F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,"
          "F.Mask,B.Mask,Edge.Cuts")

# JLC's part models sit at a different zero rotation from KiCad's footprints for some packages. Each entry is
# (footprint-name regex, degrees added to KiCad's rotation), checked against pin 1 in JLC's placement preview on
# 2026-10-18. SOT-23-5/6, SOIC, SO-8EP, TSSOP, SSOP and TDSON models came out 90 degrees counter-clockwise of their
# pads; the 3-pin SOT-23 came out 180 degrees off. QFNs, SOT-89, two-terminal parts, the crystal, USB-C and the BOOT
# switch matched. The motor drivers' Texas_HTSOP-8 (DRV8251A) matches with no offset (preview, 2026-10-20). First
# match wins.
JLC_ROTATION = [
    (r"^SOT-23-3$", 180),
    (r"^(SOT-23-[56]|SOIC-|Diodes_SO-8EP|TSSOP-|SSOP-|TDSON-)", -90),
]
# Parts whose JLC model sits at its own rotation, by LCSC number, added to the package offset. U8's HT7550-1 (C16106,
# SOT-89-3 on the back) came out 180 degrees off in the preview on 2026-10-20. J5's WingTAT 2011-3X06G00RB 3x6
# right-angle header (C51953246, front, panel only) lay across its holes with the pins toward the bottom edge at 0, and
# sat right at 270 (rotated 90 degrees clockwise in the preview, 2026-10-20). The JST PH connectors (M1-M6 S2B-PH-K
# C173752, J12 B3B-PH-K C131339) and J3's XT30PW-M (C431092) came out turned 180 degrees, housings inboard and pins at
# the edge, and SW1's slide switch (C393937) had its lever pointing into the board instead of out through the bottom
# edge (second and third previews, 2026-10-20). JLC's EasyEDA footprints for C131339 and C173752 confirm it: at 0 their
# pin 1 is the right-hand pin and the housing lies on the other side of the pin row from KiCad's, a 180 degree turn.
JLC_PART_ROTATION = {"C16106": 180, "C51953246": -90, "C173752": 180, "C131339": 180, "C431092": 180, "C393937": 180}
# Footprints JLC centres on their pads, not the footprint origin, so the CPL gives the pad centre. J1's USB-C origin
# sits 1.15 mm toward the board edge from its pads, and the preview showed the model shifted that far out. U8's SOT-89-3
# model sat 0.3 mm toward its tab, short of the pin pads, at the footprint origin (second preview, 2026-10-20).
JLC_PAD_CENTRE = [r"^USB_C_Receptacle_ShouHan_", r"^SOT-89-3$"]
# Footprints whose JLC model is centred on the middle of the pad centres, not of the pad copper: J3's XT30PW-M
# (C431092) sits midway between its pin row and its peg row, 5 mm from each, but its pin pads (3.5 mm) are bigger than
# its peg pads (1.4 mm), so the copper's centre is 0.525 mm toward the pins and the pins sat off-centre in their holes
# (preview, 2026-10-20). J4's USB-A (C456018) is the same: JLC's EasyEDA footprint is centred on its pad centres, and
# our shell pads make the copper's centre 0.525 mm off.
JLC_PIN_CENTRE = [r"^AMASS_XT30PW-M", r"^USB_A_ShouHan_AF90"]


def jlc_offset(footprint, lcsc=""):
    name = footprint.split(":")[-1]
    extra = JLC_PART_ROTATION.get(lcsc, 0)
    for pattern, offset in JLC_ROTATION:
        if re.match(pattern, name):
            return offset + extra
    return extra


def jlc_rotation(footprint, rot, bottom=False, lcsc=""):
    """JLC rotation for one part: top keeps KiCad's angle, bottom mirrors it (180 - angle); both add the offset."""
    base = 180 - rot if bottom else rot
    return (base + jlc_offset(footprint, lcsc)) % 360

# Runs inside KiCad's Python: dump every footprint with its fields, attributes and geometry.
FOOTPRINTS = r"""
import json, sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1]); mm = pcbnew.ToMM
rows = []
for f in b.GetFootprints():
    a = f.GetAttributes()
    fields = {fl.GetName(): fl.GetText() for fl in f.GetFields()}
    pads = [p for p in f.Pads() if p.GetAttribute() in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_PTH)]
    if pads:
        bb = pads[0].GetBoundingBox()
        for p in pads[1:]:
            bb.Merge(p.GetBoundingBox())
        pad_mid = [mm(bb.GetCenter().x), mm(bb.GetCenter().y)]
        xs, ys = [p.GetPosition().x for p in pads], [p.GetPosition().y for p in pads]
        pin_mid = [mm((min(xs) + max(xs)) // 2), mm((min(ys) + max(ys)) // 2)]
    else:
        pad_mid = pin_mid = None
    # Courtyard and fab outline extents, for the panel's rail and tab clearance check
    body = None
    for it in f.GraphicalItems():
        if it.GetLayerName() in ("F.Courtyard", "B.Courtyard", "F.Fab", "B.Fab") and not isinstance(it, pcbnew.PCB_TEXT):
            bb = it.GetBoundingBox()
            box = [mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())]
            body = box if body is None else [min(body[0], box[0]), min(body[1], box[1]),
                                             max(body[2], box[2]), max(body[3], box[3])]
    rows.append({
        "ref": f.GetReference(), "value": f.GetValue(), "footprint": f.GetFPIDAsString(),
        "smd": bool(a & pcbnew.FP_SMD), "tht": bool(a & pcbnew.FP_THROUGH_HOLE),
        "dnp": f.IsDNP(), "no_bom": f.IsExcludedFromBOM(), "side": f.GetLayerName(),
        "x": mm(f.GetPosition().x), "y": mm(f.GetPosition().y), "rot": f.GetOrientationDegrees(),
        "pad_mid": pad_mid, "pin_mid": pin_mid, "body": body, "mpn": fields.get("MPN", ""), "mfr": fields.get("Manufacturer", ""),
        "lcsc": fields.get("LCSC Part #", ""),
    })
e = b.GetBoardEdgesBoundingBox()
print(json.dumps({"edge": [mm(e.GetLeft()), mm(e.GetTop()), mm(e.GetRight()), mm(e.GetBottom())], "parts": rows}))
"""


def run(*args):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"failed: {' '.join(map(str, args))}\n{r.stdout}\n{r.stderr}")
    return r


def ref_key(ref):
    m = re.match(r"([A-Za-z_]+)(\d*)", ref)
    return (m.group(1), int(m.group(2) or 0)) if m else (ref, 0)


def assembly(fp, panel=False):
    if fp["dnp"] and fp["smd"]:
        return "Hand-place"
    if fp["tht"]:
        return "JLC THT" if panel and fp["lcsc"] and not fp["dnp"] else "Hand-solder"
    if fp["smd"] and fp["lcsc"]:
        return "JLC SMT"
    return None


def build_panel(pcb):
    """Panelize the brain with KiKit into PANEL_PCB and return the panel's preset (for the clearance check)."""
    if not KIKIT.exists():
        sys.exit(f"KiKit not found at {KIKIT.relative_to(ROOT)}; install it as described next to KIKIT in tools/fab.py")
    PANEL_OUT.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(KIKIT), "panelize", "-p", str(PANEL_PRESET), str(pcb), str(PANEL_PCB)],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0 or not PANEL_PCB.exists():
        sys.exit(f"kikit panelize failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    (PANEL_OUT / f"~{PANEL_PCB.stem}.kicad_pro.lck").unlink(missing_ok=True)
    # The footprints' own 3D models are at ${KIPRJMOD}/3dmodels; point the panel's project folder at them for renders
    models = PANEL_OUT / "3dmodels"
    if not models.exists():
        models.symlink_to(Path("../../kicad/3dmodels"))
    return json.loads(PANEL_PRESET.read_text())


def check_panel(board, preset, problems):
    """Check every part clears every rail by 1 mm and no tab sits under a part that overhangs its edge."""
    left, top, right, bottom = board["edge"]
    mm = lambda v: float(v.removesuffix("mm"))
    framing = preset["framing"]
    hgap, vgap = (mm(framing.get("hspace", framing.get("space", "0mm"))),
                  mm(framing.get("vspace", framing.get("space", "0mm"))))
    # rail type -> sides that have a rail
    railed = {"frame": ("top", "bottom", "west", "east"), "railstb": ("top", "bottom"),
              "railslr": ("west", "east")}[framing["type"]]
    opts = dict(part.split("=", 1) for part in preset["tabs"]["arg"].split(";") if part)
    half = float(opts.get("width", "3")) / 2
    tabs = {side: [left + float(x) for x in opts.get(side, "").split(",") if x] for side in ("top", "bottom")}
    worst = {side: (0, "") for side in ("top", "bottom", "west", "east")}
    for fp in board["parts"]:
        if not fp["body"]:
            continue
        x0, y0, x1, y1 = fp["body"]
        for side, over in (("top", top - y0), ("bottom", y1 - bottom), ("west", left - x0), ("east", x1 - right)):
            if over <= 0.05:
                continue
            worst[side] = max(worst[side], (over, fp["ref"]))
            gap = vgap if side in ("top", "bottom") else hgap
            if side in railed and over > gap - 1.0:
                problems.append(f"{fp['ref']}: reaches {over:.2f} mm past the {side} edge, within 1 mm of the rail")
            for x in tabs.get(side, []):
                if x0 - 0.5 < x + half and x - half < x1 + 0.5:
                    problems.append(f"{fp['ref']}: overhangs the {side} edge over the tab at x {x:.2f}")
    for side, (over, ref) in worst.items():
        gap = vgap if side in ("top", "bottom") else hgap
        clear = f"{gap - over:.2f} mm clear of the rail" if side in railed else "no rail"
        where = (f"; tabs at x " + ", ".join(f"{x - left:.1f}" for x in tabs[side]) + " mm from the west edge"
                 if tabs.get(side) else "; no tabs")
        print(f"panel {side}: largest overhang {over:.2f} mm ({ref}, courtyard/fab), {clear}{where}")


def render_panel():
    renders = PANEL_OUT / "renders"
    renders.mkdir(exist_ok=True)
    for side in ("top", "bottom"):
        run(KICAD_CLI, "pcb", "render", "--side", side, "--width", 2400, "--height", 2000, "--quality", "high",
            "-o", renders / f"panel-{side}.png", PANEL_PCB)
    print(f"renders: {renders.relative_to(ROOT)}/panel-top.png, panel-bottom.png")


def main():
    ap = argparse.ArgumentParser(description="Build the JLCPCB fab package for one board.")
    ap.add_argument("--board", choices=BOARDS, default="brain")
    ap.add_argument("--panel", action="store_true",
                    help="brain only: build a KiKit panel with rails and fab it into build/fab-panel/")
    args = ap.parse_args()
    pcb, out, zip_name = BOARDS[args.board]
    problems = []
    if args.panel:
        if args.board != "brain":
            sys.exit("--panel is for the brain only")
        preset = build_panel(pcb)
        check_panel(json.loads(run(KICAD_PYTHON, "-c", FOOTPRINTS, pcb).stdout), preset, problems)
        pcb, out, zip_name = PANEL_PCB, PANEL_OUT, "thegoose-panel-gerbers.zip"

    gerbers = out / "gerbers"
    gerbers.mkdir(parents=True, exist_ok=True)
    for old in gerbers.iterdir():
        old.unlink()

    run(KICAD_CLI, "pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask", "--check-zones",
        "-o", gerbers, pcb)
    run(KICAD_CLI, "pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm",
        "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2", "-o", gerbers, pcb)
    zip_path = out / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gerbers.iterdir()):
            z.write(f, f.name)

    dump = json.loads(run(KICAD_PYTHON, "-c", FOOTPRINTS, pcb).stdout)
    fps = dump["parts"]
    if args.panel:
        x0, y0, x1, y1 = dump["edge"]
        print(f"panel size: {x1 - x0:.1f} x {y1 - y0:.1f} mm")
        if min(x1 - x0, y1 - y0) < 70:
            problems.append("panel is under 70 mm on a side; JLC's Standard PCBA will resize it and add its own rails")
    parts = [fp for fp in fps if fp["mpn"] and (fp["dnp"] or not fp["no_bom"])]
    jlc = ("JLC SMT", "JLC THT")

    groups = {}
    for fp in parts:
        how = assembly(fp, args.panel)
        if how is None:
            problems.append(f"{fp['ref']}: no assembly class (SMD without an LCSC number?)")
            continue
        key = (fp["value"], fp["footprint"], fp["mpn"], fp["lcsc"], how)
        groups.setdefault(key, []).append(fp)

    order = {"JLC SMT": 0, "JLC THT": 1, "Hand-place": 2, "Hand-solder": 3}
    rows = sorted(groups.items(), key=lambda kv: (order[kv[0][4]], ref_key(sorted(f["ref"] for f in kv[1])[0])))
    with open(out / "bom.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Item", "Qty", "References", "Value", "Footprint", "Manufacturer", "MPN", "LCSC Part #",
                    "Assembly"])
        for i, ((value, footprint, mpn, lcsc, how), members) in enumerate(rows, 1):
            refs = sorted((f["ref"] for f in members), key=ref_key)
            w.writerow([i, len(refs), " ".join(refs), value, footprint.split(":")[-1], members[0]["mfr"], mpn, lcsc,
                        how])

    smt = [fp for fp in parts if assembly(fp, args.panel) in jlc]
    # JLC charges a loading fee per BOM line, so one line per LCSC number: parts that share a number but not a
    # footprint go on one line, under the comment and footprint of the larger group
    by_lcsc = {}
    for (value, footprint, mpn, lcsc, how), members in rows:
        if how in jlc:
            by_lcsc.setdefault(lcsc, []).append((value, footprint, mpn, members))
    jlc_lines = []
    for lcsc, gs in by_lcsc.items():
        if len({(g[0], g[2]) for g in gs}) > 1:
            problems.append(f"LCSC {lcsc} is on parts with different values or MPNs: "
                            + "; ".join(f"{g[0]} {g[2]} ({' '.join(f['ref'] for f in g[3])})" for g in gs))
        value, footprint = max(gs, key=lambda g: len(g[3]))[:2]
        refs = sorted((f["ref"] for g in gs for f in g[3]), key=ref_key)
        jlc_lines.append([value, ",".join(refs), footprint.split(":")[-1], lcsc])
    with open(out / "jlc_bom.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        w.writerows(jlc_lines)

    with open(out / "jlc_cpl.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in sorted(smt, key=lambda f: ref_key(f["ref"])):
            bottom = fp["side"] == "B.Cu"
            x, y = fp["x"], fp["y"]
            if fp["pad_mid"]:
                dx, dy = fp["pad_mid"][0] - fp["x"], fp["pad_mid"][1] - fp["y"]
                # Through-hole footprints sit on pin 1; the pad centre is nearer the middle JLC places them by
                name = fp["footprint"].split(":")[-1]
                if any(re.match(pat, name) for pat in JLC_PIN_CENTRE):
                    x, y = fp["pin_mid"]
                elif fp["tht"] or any(re.match(pat, name) for pat in JLC_PAD_CENTRE):
                    x, y = fp["pad_mid"]
                elif (dx * dx + dy * dy) ** 0.5 > 0.25:
                    problems.append(f"{fp['ref']}: anchor is {dx:+.2f}/{dy:+.2f} mm off its pad centre "
                                    f"(the footprint's origin; JLC centres on its own part model, check the preview)")
            w.writerow([fp["ref"], f"{x:.4f}", f"{-y:.4f}", "Bottom" if bottom else "Top",
                        f"{jlc_rotation(fp['footprint'], fp['rot'], bottom, fp['lcsc']):.0f}"])
    bottom_refs = sorted((fp["ref"] for fp in smt if fp["side"] == "B.Cu"), key=ref_key)
    offset_refs = sorted((fp["ref"] for fp in smt if jlc_offset(fp["footprint"], fp["lcsc"])), key=ref_key)

    counts = {how: sum(len(m) for k, m in groups.items() if k[4] == how) for how in order}
    lines = len(jlc_lines)
    print(f"gerbers: {len(list(gerbers.iterdir()))} files -> {zip_path.relative_to(ROOT)}")
    print(f"bom.csv: {len(groups)} lines; placements {counts}")
    print(f"jlc_bom.csv: {lines} lines; jlc_cpl.csv: {len(smt)} placements")
    if bottom_refs:
        print(f"bottom side: {len(bottom_refs)} placements; check their rotation in JLC's preview: "
              + " ".join(bottom_refs))
    if offset_refs:
        print("rotation offsets applied (check pin 1 in JLC's preview): " + " ".join(offset_refs))
    tht_refs = sorted((fp["ref"] for fp in parts if assembly(fp, args.panel) == "JLC THT"), key=ref_key)
    if tht_refs:
        print("through-hole parts in the JLC files, at their pad centre (orientation rechecked in JLC's preview 2026-10-20): "
              + " ".join(tht_refs))
    for p in problems:
        print("CHECK:", p)
    if args.panel:
        render_panel()


if __name__ == "__main__":
    main()
