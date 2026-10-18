"""Build the fab package for kicad/thegoose.kicad_pcb into build/fab/.

Writes:
- gerbers/: Gerbers for all 6 copper layers, mask, paste, silk and outline, plus Excellon drill files (PTH and NPTH)
- thegoose-gerbers.zip: the gerbers/ folder, ready to upload to JLCPCB
- bom.csv: the full BOM, every purchased part, grouped, with MPN, manufacturer, LCSC number and how it's assembled
- jlc_bom.csv / jlc_cpl.csv: JLC's PCBA BOM and placement files, machine-placed SMD parts only

Assembly classes:
- "JLC SMT": SMD with an LCSC number and not DNP. These go in the JLC files.
- "Hand-solder": through-hole connectors and the switch, soldered after the boards arrive.
- "Hand-place": SMD parts marked DNP (L3, bought from Digi-Key and placed by hand).

Coordinates use the same absolute frame as the Gerbers (X right, Y up, mm), so JLC lines them up without an offset.
Rotations are KiCad's. Check each part's orientation in JLC's placement preview before paying.

Usage: .venv/bin/python tools/fab.py
"""

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
PCB = ROOT / "kicad/thegoose.kicad_pcb"
OUT = ROOT / "build/fab"

LAYERS = ("F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,"
          "F.Mask,B.Mask,Edge.Cuts")

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
    gerbers = OUT / "gerbers"
    gerbers.mkdir(parents=True, exist_ok=True)
    for old in gerbers.iterdir():
        old.unlink()

    run(KICAD_CLI, "pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask", "--check-zones",
        "-o", gerbers, PCB)
    run(KICAD_CLI, "pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm",
        "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2", "-o", gerbers, PCB)
    zip_path = OUT / "thegoose-gerbers.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gerbers.iterdir()):
            z.write(f, f.name)

    fps = json.loads(run(KICAD_PYTHON, "-c", FOOTPRINTS, PCB).stdout)
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
    with open(OUT / "bom.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Item", "Qty", "References", "Value", "Footprint", "Manufacturer", "MPN", "LCSC Part #",
                    "Assembly"])
        for i, ((value, footprint, mpn, lcsc, how), members) in enumerate(rows, 1):
            refs = sorted((f["ref"] for f in members), key=ref_key)
            w.writerow([i, len(refs), " ".join(refs), value, footprint.split(":")[-1], members[0]["mfr"], mpn, lcsc,
                        how])

    smt = [fp for fp in parts if assembly(fp) == "JLC SMT"]
    with open(OUT / "jlc_bom.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, mpn, lcsc, how), members in rows:
            if how != "JLC SMT":
                continue
            refs = sorted((f["ref"] for f in members), key=ref_key)
            w.writerow([value, ",".join(refs), footprint.split(":")[-1], lcsc])

    with open(OUT / "jlc_cpl.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in sorted(smt, key=lambda f: ref_key(f["ref"])):
            if fp["side"] != "F.Cu":
                problems.append(f"{fp['ref']}: on {fp['side']}; Economic PCBA is top side only")
            if fp["pad_mid"]:
                dx, dy = fp["pad_mid"][0] - fp["x"], fp["pad_mid"][1] - fp["y"]
                if (dx * dx + dy * dy) ** 0.5 > 0.25:
                    problems.append(f"{fp['ref']}: anchor is {dx:+.2f}/{dy:+.2f} mm off its pad centre")
            w.writerow([fp["ref"], f"{fp['x']:.4f}", f"{-fp['y']:.4f}", "Top", f"{fp['rot'] % 360:.0f}"])

    counts = {how: sum(len(m) for k, m in groups.items() if k[4] == how) for how in order}
    lines = sum(1 for k in groups if k[4] == "JLC SMT")
    print(f"gerbers: {len(list(gerbers.iterdir()))} files -> {zip_path.relative_to(ROOT)}")
    print(f"bom.csv: {len(groups)} lines; placements {counts}")
    print(f"jlc_bom.csv: {lines} lines; jlc_cpl.csv: {len(smt)} placements")
    for p in problems:
        print("CHECK:", p)


if __name__ == "__main__":
    main()
