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
- "Hand-solder": through-hole connectors and the switch, soldered after the boards arrive.
- "Hand-place": SMD parts marked DNP (L3, bought from Digi-Key and placed by hand).

Coordinates use the same absolute frame as the Gerbers (X right, Y up, mm, seen from the top for both sides), so JLC
lines them up without an offset. Top-side rotations are KiCad's plus the per-package offsets in JLC_ROTATION, which
were read off JLC's placement preview. Bottom-side parts get Layer "Bottom" and rotation (180 - KiCad + offset): JLC
doesn't mirror bottom parts the way KiCad does (KiBot's JLCPCB template: mirror_bottom, offsets added). JLC has changed
its bottom-side convention before, so the script lists every bottom part to check. Check each part's orientation in
JLC's placement preview before paying.

Usage: python3 tools/fab.py [--board brain|pack|pack2s]
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

LAYERS = ("F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,"
          "F.Mask,B.Mask,Edge.Cuts")

# JLC's part models sit at a different zero rotation from KiCad's footprints for some packages. Each entry is
# (footprint-name regex, degrees added to KiCad's rotation), checked against pin 1 in JLC's placement preview on
# 2026-10-18. SOT-23-5/6, SOIC, SO-8EP, TSSOP, SSOP and TDSON models came out 90 degrees counter-clockwise of their
# pads; the 3-pin SOT-23 came out 180 degrees off. QFNs, SOT-89, two-terminal parts, the crystal, USB-C and the BOOT
# switch matched. The motor drivers' Texas_HTSOP-8 (DRV8871, now DRV8251A on the same footprint) was added after that
# check and is assumed to follow the other SOIC-family packages; confirm it in JLC's placement preview. First match wins.
JLC_ROTATION = [
    (r"^SOT-23-3$", 180),
    (r"^(SOT-23-[56]|SOIC-|Diodes_SO-8EP|Texas_HTSOP-8|TSSOP-|SSOP-|TDSON-)", -90),
]


def jlc_offset(footprint):
    name = footprint.split(":")[-1]
    for pattern, offset in JLC_ROTATION:
        if re.match(pattern, name):
            return offset
    return 0


def jlc_rotation(footprint, rot, bottom=False):
    """JLC rotation for one part: top keeps KiCad's angle, bottom mirrors it (180 - angle); both add the offset."""
    base = 180 - rot if bottom else rot
    return (base + jlc_offset(footprint)) % 360

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
    else:
        pad_mid = None
    rows.append({
        "ref": f.GetReference(), "value": f.GetValue(), "footprint": f.GetFPIDAsString(),
        "smd": bool(a & pcbnew.FP_SMD), "tht": bool(a & pcbnew.FP_THROUGH_HOLE),
        "dnp": f.IsDNP(), "no_bom": f.IsExcludedFromBOM(), "side": f.GetLayerName(),
        "x": mm(f.GetPosition().x), "y": mm(f.GetPosition().y), "rot": f.GetOrientationDegrees(),
        "pad_mid": pad_mid, "mpn": fields.get("MPN", ""), "mfr": fields.get("Manufacturer", ""),
        "lcsc": fields.get("LCSC Part #", ""),
    })
print(json.dumps(rows))
"""


def run(*args):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"failed: {' '.join(map(str, args))}\n{r.stdout}\n{r.stderr}")
    return r


def ref_key(ref):
    m = re.match(r"([A-Za-z_]+)(\d*)", ref)
    return (m.group(1), int(m.group(2) or 0)) if m else (ref, 0)


def assembly(fp):
    if fp["dnp"] and fp["smd"]:
        return "Hand-place"
    if fp["tht"]:
        return "Hand-solder"
    if fp["smd"] and fp["lcsc"]:
        return "JLC SMT"
    return None


def main():
    ap = argparse.ArgumentParser(description="Build the JLCPCB fab package for one board.")
    ap.add_argument("--board", choices=BOARDS, default="brain")
    pcb, out, zip_name = BOARDS[ap.parse_args().board]

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

    fps = json.loads(run(KICAD_PYTHON, "-c", FOOTPRINTS, pcb).stdout)
    parts = [fp for fp in fps if fp["mpn"] and (fp["dnp"] or not fp["no_bom"])]
    problems = []

    groups = {}
    for fp in parts:
        how = assembly(fp)
        if how is None:
            problems.append(f"{fp['ref']}: no assembly class (SMD without an LCSC number?)")
            continue
        key = (fp["value"], fp["footprint"], fp["mpn"], fp["lcsc"], how)
        groups.setdefault(key, []).append(fp)

    order = {"JLC SMT": 0, "Hand-place": 1, "Hand-solder": 2}
    rows = sorted(groups.items(), key=lambda kv: (order[kv[0][4]], ref_key(sorted(f["ref"] for f in kv[1])[0])))
    with open(out / "bom.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Item", "Qty", "References", "Value", "Footprint", "Manufacturer", "MPN", "LCSC Part #",
                    "Assembly"])
        for i, ((value, footprint, mpn, lcsc, how), members) in enumerate(rows, 1):
            refs = sorted((f["ref"] for f in members), key=ref_key)
            w.writerow([i, len(refs), " ".join(refs), value, footprint.split(":")[-1], members[0]["mfr"], mpn, lcsc,
                        how])

    smt = [fp for fp in parts if assembly(fp) == "JLC SMT"]
    with open(out / "jlc_bom.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, mpn, lcsc, how), members in rows:
            if how != "JLC SMT":
                continue
            refs = sorted((f["ref"] for f in members), key=ref_key)
            w.writerow([value, ",".join(refs), footprint.split(":")[-1], lcsc])

    with open(out / "jlc_cpl.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in sorted(smt, key=lambda f: ref_key(f["ref"])):
            bottom = fp["side"] == "B.Cu"
            if fp["pad_mid"]:
                dx, dy = fp["pad_mid"][0] - fp["x"], fp["pad_mid"][1] - fp["y"]
                if (dx * dx + dy * dy) ** 0.5 > 0.25:
                    problems.append(f"{fp['ref']}: anchor is {dx:+.2f}/{dy:+.2f} mm off its pad centre "
                                    f"(the footprint's origin; JLC centres on its own part model, check the preview)")
            w.writerow([fp["ref"], f"{fp['x']:.4f}", f"{-fp['y']:.4f}", "Bottom" if bottom else "Top",
                        f"{jlc_rotation(fp['footprint'], fp['rot'], bottom):.0f}"])
    bottom_refs = sorted((fp["ref"] for fp in smt if fp["side"] == "B.Cu"), key=ref_key)
    offset_refs = sorted((fp["ref"] for fp in smt if jlc_offset(fp["footprint"])), key=ref_key)

    counts = {how: sum(len(m) for k, m in groups.items() if k[4] == how) for how in order}
    lines = sum(1 for k in groups if k[4] == "JLC SMT")
    print(f"gerbers: {len(list(gerbers.iterdir()))} files -> {zip_path.relative_to(ROOT)}")
    print(f"bom.csv: {len(groups)} lines; placements {counts}")
    print(f"jlc_bom.csv: {lines} lines; jlc_cpl.csv: {len(smt)} placements")
    if bottom_refs:
        print(f"bottom side: {len(bottom_refs)} placements; check their rotation in JLC's preview: "
              + " ".join(bottom_refs))
    if offset_refs:
        print("rotation offsets applied (check pin 1 in JLC's preview): " + " ".join(offset_refs))
    for p in problems:
        print("CHECK:", p)


if __name__ == "__main__":
    main()
