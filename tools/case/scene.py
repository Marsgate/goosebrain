"""Write a scene board: the goosebrain board plus a footprint carrying extra models.

usage: scene.py OUT.kicad_pcb [--bare] MODEL[@opacity][@dx,dy,dz] ...
  MODEL is a STEP path relative to this script's folder.
  --bare keeps only the board outline (no parts/copper), for scenes where the
  board should be hidden inside another model.
"""
import sys, uuid, shutil, os

SRC = "/Volumes/code/goosebrain/kicad/thegoose"
S = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
out = args.pop(0)
bare = "--bare" in args
args = [a for a in args if a != "--bare"]

def model(spec):
    p = spec.split("@")
    op = p[1] if len(p) > 1 and p[1] else "1"
    off = p[2].replace(",", " ") if len(p) > 2 else "0 0 0"
    return f'''		(model "{S}/{p[0]}"
			(opacity {op})
			(offset (xyz {off}))
			(scale (xyz 1 1 1))
			(rotate (xyz 0 0 0))
		)
'''

fp = f'''	(footprint "scene:case"
		(layer "F.Cu")
		(uuid "{uuid.uuid4()}")
		(at 99.925 99.925)
		(property "Reference" "SCENE1" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uuid.uuid4()}")
			(effects (font (size 1 1) (thickness 0.15))))
		(property "Value" "case" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uuid.uuid4()}")
			(effects (font (size 1 1) (thickness 0.15))))
		(attr board_only exclude_from_pos_files exclude_from_bom)
{"".join(model(a) for a in args)}	)
'''

def top_level(txt):
    """Split '(kicad_pcb ...)' into its top-level child blocks."""
    i, depth, start, blocks = txt.index("(", 1), 0, None, []
    while i < len(txt) - 1:
        ch = txt[i]
        if ch == '"':
            i += 1
            while txt[i] != '"':
                i += 2 if txt[i] == "\\" else 1
        elif ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                blocks.append(txt[start:i + 1])
        i += 1
    return blocks

txt = open(SRC + ".kicad_pcb").read().rstrip()
if bare:
    keep = ("version", "generator", "general", "paper", "title_block", "layers", "setup", "net", "embedded_fonts")
    blocks = []
    for b in top_level(txt):
        head = b[1:].split(None, 1)[0].rstrip(")")
        if head in keep or (head.startswith("gr_") and '"Edge.Cuts"' in b):
            blocks.append(b)
    txt = "(kicad_pcb\n\t" + "\n\t".join(blocks) + "\n)"
open(out, "w").write(txt[:-1] + fp + ")\n")
shutil.copy(SRC + ".kicad_pro", out.replace(".kicad_pcb", ".kicad_pro"))
