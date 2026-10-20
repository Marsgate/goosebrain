"""Crop/label the comparison renders. usage: compose.py SCRATCH OUTDIR"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
S, O = sys.argv[1], sys.argv[2]
T = S + "/try/"
FONT = "/System/Library/Fonts/Helvetica.ttc"
f_big, f_small = ImageFont.truetype(FONT, 40), ImageFont.truetype(FONT, 28)

def trim(im):  # kicad-cli leaves a black strip on the right
    a = np.asarray(im.convert("RGB")).sum(axis=2)
    cols = np.where(a.max(axis=0) > 30)[0]
    return im.convert("RGB").crop((0, 0, cols.max() + 1, im.height))

def label(im, title, sub=""):
    d = ImageDraw.Draw(im)
    d.text((30, 24), title, font=f_big, fill=(25, 25, 40))
    if sub:
        d.text((30, 74), sub, font=f_small, fill=(45, 45, 70))
    return im

# side section, cropped round the case
im = trim(Image.open(T + "side_tall.png")); a = np.asarray(im).astype(int)
bg = a[:, :20].mean(axis=1, keepdims=True); rows = np.where(np.abs(a - bg).sum(axis=2).max(axis=1) > 60)[0]
c, h = (rows.min() + rows.max()) // 2, max(rows.max() - rows.min() + 200, 600)
im.crop((0, max(0, c - h // 2), im.width, min(im.height, c + h // 2))).save(O + "/8_clear_side.png")

OLD = ("Old kitbot brain", "PBB + ESP32 + 3x DRV8833 + buck, 109 x 56 x 25 mm case")
NEW = ("New goosebrain", "68 x 32 mm board, 72 x 35 x 15.6 mm case, flush ports")

# robot, old vs new, same camera
for src_old, src_new, name in [("old_robot.png", O + "/1_on_robot.png", "9_robot_old_vs_new.png"),
                               ("old_closeup.png", O + "/2_on_robot_closeup.png", "10_closeup_old_vs_new.png")]:
    a, b = trim(Image.open(T + src_old)), trim(Image.open(src_new))
    out = Image.new("RGB", (a.width + b.width + 12, a.height), (20, 20, 30))
    out.paste(label(a, *OLD), (0, 0)); out.paste(label(b, *NEW), (a.width + 12, 0))
    out.save(O + "/" + name)

# brains alone, same scale: iso / top / side rows
rows = []
for v in ["iso", "top", "side"]:
    a, b = trim(Image.open(T + f"brain_old_{v}.png")), trim(Image.open(T + f"closed_{v}.png"))
    if v == "side":  # thin strip: crop vertically
        a, b = a.crop((0, 130, a.width, 560)), b.crop((0, 130, b.width, 560))
    r = Image.new("RGB", (a.width + b.width + 12, a.height), (20, 20, 30))
    r.paste(a, (0, 0)); r.paste(b, (a.width + 12, 0)); rows.append(r)
W = rows[0].width
out = Image.new("RGB", (W, sum(r.height for r in rows) + 12 * (len(rows) - 1)), (20, 20, 30))
y = 0
for r in rows:
    out.paste(r, (0, y)); y += r.height + 12
half = rows[0].width // 2
label(out.crop((0, 0, half, rows[0].height)), *OLD)
d = ImageDraw.Draw(out)
for x, (t, s) in [(0, OLD), (half + 6, NEW)]:
    d.text((x + 30, 24), t, font=f_big, fill=(25, 25, 40)); d.text((x + 30, 74), s, font=f_small, fill=(45, 45, 70))
d.text((30, rows[0].height + 24), "Front (same scale)", font=f_small, fill=(45, 45, 70))
d.text((30, rows[0].height + rows[1].height + 36), "Side (same scale)", font=f_small, fill=(45, 45, 70))
out.save(O + "/0_brain_old_vs_new.png")
