"""Move kitbot modules into the brain case's model frame.

usage: robot.py OUT.step MODULE.step ...   (modules from /Volumes/code/CAD/OnShape/modules/)

The case stands where the old PBB stack was (robot X 20.4-45.7, Y 66.8-176,
Z 78-133.8 mm): floor against X 45.7, lid facing -X, USB wall up, XT30 down.
This transform puts robot X 45.7 at model Z -5.4 and the old case centre at
model (34.125, -16.025). For a case whose floor is elsewhere, add a model
offset in the scene (scene.py MODEL@@dx,dy,dz).
"""
import sys
from OCP.gp import gp_Trsf
from build123d import import_step, export_step, Compound, Location

MOD = "/Volumes/code/CAD/OnShape/modules/"
t = gp_Trsf()
t.SetValues(0, -1, 0, 155.525,
            0, 0, 1, -122.025,
            -1, 0, 0, 40.3)
loc = Location(t)
parts = []
for name in sys.argv[2:]:
    parts.append(import_step(MOD + name).moved(loc))
    print(name, "ok", flush=True)
export_step(Compound(children=parts, label="kitbot"), sys.argv[1])
