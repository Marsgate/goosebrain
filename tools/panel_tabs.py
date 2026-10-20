"""KiKit tabs plugin for the brain panel: mouse-bite tabs at fixed spots on the top and bottom edges.

KiKit's own tab layouts space tabs evenly, which would put them under J1, J4, J3, SW1 or SW2, the parts that overhang
the top and bottom edges so their ports sit flush with the case wall. This plugin places them only where nothing
overhangs, no MLCC sits at the edge, and the stitching vias along the edge are clear of the holes (the mouse bites sit
on the rail side of the edge, see tools/panel.json).

arg: "top=<x>,<x>...;bottom=<x>,...;width=<mm>". Each x is mm from the board's left (west) edge.
Used by tools/fab.py --panel via tools/panel.json.
"""

from kikit.annotations import TabAnnotation
from kikit.common import fromMm
from kikit.plugin import TabsPlugin


class EdgeTabs(TabsPlugin):
    def buildTabAnnotations(self, panel):
        opts = dict(part.split("=", 1) for part in self.userArg.split(";") if part)
        width = fromMm(float(opts.get("width", "3")))
        for s in panel.substrates:
            minx, miny, maxx, maxy = s.bounds()
            for side, y, direction in (("top", miny, (0, 1)), ("bottom", maxy, (0, -1))):
                for x in filter(None, opts.get(side, "").split(",")):
                    origin = (minx + fromMm(float(x)), y)
                    s.annotations.append(TabAnnotation(None, origin, direction, width))
