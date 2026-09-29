"""scene (layout.py output) → SVG string."""
from html import escape

ATTR = {"x": "x", "y": "y", "width": "width", "height": "height", "rx": "rx", "fill": "fill", "stroke": "stroke",
        "sw": "stroke-width", "x1": "x1", "y1": "y1", "x2": "x2", "y2": "y2", "d": "d", "href": "href",
        "anchor": "text-anchor", "cls": "class", "marker": "marker-end", "fs": "font-size", "filter": "filter",
        "cx": "cx", "cy": "cy", "r": "r", "transform": "transform", "dash": "stroke-dasharray", "cap": "stroke-linecap"}


def _style(t):
    f, S, c = t["fonts"], t["size"], t["text"]
    tnum = "font-variant-numeric: tabular-nums; font-feature-settings: 'tnum' 1, 'cv11' 1;"
    round_ = "stroke-linecap:round; stroke-linejoin:round;"
    return f"""
      .t  {{ fill:{c['body']}; font-size:{S['body']}px; letter-spacing:-0.005em; }}
      .tb {{ fill:{c['title']}; font-size:{S['name']}px; font-weight:600; letter-spacing:-0.01em; }}
      .ts {{ fill:{c['muted']}; font-size:{S['small']}px; }}
      .ip {{ fill:{c['muted']}; font-size:{S['small']}px; {tnum} }}
      .if {{ fill:{c['iface']}; font-size:{S['iface']}px; {tnum} }}
      .ifn{{ fill:{c['iface']}; font-weight:400; }}
      .ifk{{ fill:{c['muted']}; font-size:{S['iface'] - 1}px; }}
      .rt {{ fill:{t['annot']['text']}; font-size:{S['route']}px; font-family:{f['mono']}; }}
      .seg{{ fill:{c['title']}; font-size:{S['seg']}px; font-weight:500; letter-spacing:0.01em; {tnum} }}
      .sgb{{ font-weight:650; }} .sgl{{ font-weight:450; fill-opacity:0.78; }} .sgc{{ font-weight:500; }}
      .ln {{ fill:none; stroke:{t['line']}; stroke-width:1.5; {round_} }}
      .box{{ fill:{t['panel']['fill']}; }}
      .rbox{{ fill:{t['annot']['fill']}; }}
      .lead{{ fill:none; stroke:{t['annot']['leader']}; stroke-width:1.2; stroke-dasharray:1 3; stroke-linecap:round; }}
      .flow{{ fill:none; stroke:{t['flow']}; stroke-width:1.5; {round_} }}
      .flowhalo{{ fill:none; stroke:{t['flow']}; stroke-width:6; stroke-opacity:0.16; {round_} }}"""


def _num(v):
    return f"{v:.1f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def _el(it):
    attrs = []
    if "pts" in it and CORNER[0]:
        it = dict(it, d=_rounded(it["pts"], CORNER[0]))
    for k, name in ATTR.items():
        if k in it and it[k] is not None:
            v = it[k]
            attrs.append(f'{name}="{escape(_num(v)) if not isinstance(v, str) else escape(v)}"')
    if it["el"] == "text":  # class overrides fill=/font-size=; use style to recolor or resize text individually
        st = ([f'fill:{it["fill"]}'] if "fill" in it else []) + ([f'font-size:{it["fs"]}px'] if "fs" in it else [])
        attrs = [a for a in attrs if not a.startswith(("fill=", "font-size="))]
        if st:
            attrs.append(f'style="{"; ".join(st)}"')
    if it["el"] == "line" and "stroke" in it and "sw" not in it:
        attrs.append('stroke-width="1"')
    a = " ".join(attrs)
    if it["el"] == "text":
        if it.get("spans"):
            body = "".join(f'<tspan class="{c}">{escape(x).replace("  ", "&#160; ")}</tspan>' for x, c in it["spans"])
            return f"<text {a}>{body}</text>"
        return f"<text {a}>{escape(it['text'])}</text>"
    return f"<{it['el']} {a}/>"


CORNER = [0]


def _rounded(pts, r):
    """Orthogonal polyline → rounded path (each corner uses a quadratic bezier; radius capped at half the
    adjacent segment length)."""
    f = lambda v: f"{v:.1f}".rstrip("0").rstrip(".")
    d = f"M{f(pts[0][0])},{f(pts[0][1])}"
    for i in range(1, len(pts) - 1):
        (ax, ay), (bx, by), (cx, cy) = pts[i - 1], pts[i], pts[i + 1]
        l1, l2 = abs(bx - ax) + abs(by - ay), abs(cx - bx) + abs(cy - by)
        k = min(r, l1 / 2, l2 / 2)
        ux, uy = (bx - ax) / l1, (by - ay) / l1
        vx, vy = (cx - bx) / l2, (cy - by) / l2
        d += f" L{f(bx - ux * k)},{f(by - uy * k)} Q{f(bx)},{f(by)} {f(bx + vx * k)},{f(by + vy * k)}"
    return d + f" L{f(pts[-1][0])},{f(pts[-1][1])}"


def _tag(it):
    s = f' data-role="{it["role"]}"' if it.get("role") else ""
    return s + (f' data-owner="{escape(it["owner"])}"' if it.get("owner") else "")


def render(scene, theme, symbols):
    t = theme
    look = t.get("look", {})
    CORNER[0] = look.get("corner", 0)
    W, H = scene["width"], scene["height"]
    # rounded solid triangle: same visual language as round-capped lines
    arrow = f'<path d="M2.2,1.3 Q1,0.7 1,2 L1,8 Q1,9.3 2.2,8.7 L8.8,5.7 Q10,5 8.8,4.3 Z" fill="{t["flow"]}"/>'
    msize = look.get("arrow_size", 6)
    shadow = ('    <filter id="shadow" x="-10%" y="-20%" width="120%" height="170%">'
              '<feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#000" flood-opacity="0.06"/>'
              '<feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000" flood-opacity="0.06"/></filter>')
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="{escape(t["fonts"]["sans"])}">',
           "  <defs>",
           f'    <marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="{msize}" markerHeight="{msize}" '
           f'orient="auto-start-reverse">{arrow}</marker>',
           f'    <marker id="al" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="{msize + 1}" '
           f'markerHeight="{msize + 1}" orient="auto-start-reverse">{arrow.replace(t["flow"], t["line"])}</marker>',
           shadow,
           "    " + symbols.replace("\n", "\n    "),
           f"    <style>{_style(t)}\n    </style>",
           "  </defs>",
           f'  <rect width="{W}" height="{H}" fill="{t["canvas"]["bg"]}"/>']
    items = sorted(scene["items"], key=lambda i: i["z"])  # stable sort, keeps generation order within a layer
    open_group = None
    for it in items:
        g = it.get("group")
        if g != open_group:
            if open_group:
                out.append("  </g>")
            if g:
                out.append(f"  <g{_tag(it)}>")
            open_group = g
        if g:
            out.append("    " + _el(it))
        else:
            out.append("  " + _add_tag(_el(it), it))
    if open_group:
        out.append("  </g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _add_tag(s, it):
    i = s.index(" ")
    return s[:i] + _tag(it) + s[i:]
