"""dgm — explanatory technical diagrams rendered straight to SVG (no auto-layout DSL).

Scene scripts get a Diagram `d` and use its factories (d.node, d.array, d.listnode, d.table, d.bits, d.code,
d.note, d.text, d.image, d.seq, d.memmap, d.band, d.zoom, d.group, d.edge) plus placement helpers (.at/.right_of/.below…, d.row,
d.col, d.grid, d.tree). See references/api.md.
"""
from .comps import NULL, PTR  # noqa: F401
from .diagram import Diagram  # noqa: F401
from .fonts import FontSet  # noqa: F401
