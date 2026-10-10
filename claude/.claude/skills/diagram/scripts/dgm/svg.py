"""Items (page coordinates) → SVG text."""
import pathlib
import re
from html import escape

ICONS = pathlib.Path(__file__).resolve().parents[2] / "assets" / "icons"


def _n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def rounded(pts, r, closed=False):
    """Polyline → path with quadratic rounded corners (radius capped at half of each adjacent segment)."""
    if len(pts) < 2:
        return ""
    if r <= 0 or len(pts) < 3:
        d = "M" + " L".join(f"{_n(p[0])},{_n(p[1])}" for p in pts)
        return d + (" Z" if closed else "")
    P = list(pts)
    n = len(P)
    rng = range(n) if closed else range(1, n - 1)
    corners = {}
    for i in rng:
        a, b, c = P[i - 1], P[i], P[(i + 1) % n]
        l1 = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        l2 = ((c[0] - b[0]) ** 2 + (c[1] - b[1]) ** 2) ** 0.5
        if l1 < 1e-6 or l2 < 1e-6:
            continue
        k = min(r, l1 / 2, l2 / 2)
        u = ((b[0] - a[0]) / l1, (b[1] - a[1]) / l1)
        v = ((c[0] - b[0]) / l2, (c[1] - b[1]) / l2)
        corners[i] = ((b[0] - u[0] * k, b[1] - u[1] * k), b, (b[0] + v[0] * k, b[1] + v[1] * k))
    f = lambda p: f"{_n(round(p[0], 2))},{_n(round(p[1], 2))}"
    if closed and 0 in corners:
        d = f"M{f(corners[0][2])}"
        order = list(range(1, n)) + [0]
    else:
        d = f"M{f(P[0])}"
        order = range(1, n)
    for i in order:
        if i in corners:
            p, q, s = corners[i]
            d += f" L{f(p)} Q{f(q)} {f(s)}"
        else:
            d += f" L{f(P[i])}"
    return d + (" Z" if closed else "")


_icon_cache = {}


def icon_symbol(name):
    if name in _icon_cache:
        return _icon_cache[name]
    p = ICONS / f"{name}.svg"
    if not p.exists():
        raise ValueError(f"unknown icon {name!r}; available: {', '.join(sorted(x.stem for x in ICONS.glob('*.svg')))}")
    src = re.sub(r"<!--.*?-->", "", p.read_text(), flags=re.S)
    body = re.search(r"<svg[^>]*>(.*)</svg>", src, re.S).group(1)
    body = re.sub(r'<path stroke="none" d="M0 0h24v24H0z" fill="none"\s*/>', "", body)
    body = " ".join(body.split())
    sym = (f'<symbol id="i-{name}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
           f'stroke-linecap="round" stroke-linejoin="round">{body}</symbol>')
    _icon_cache[name] = sym
    return sym


def _attrs(pairs):
    return " ".join(f'{k}="{escape(_n(v)) if not isinstance(v, str) else escape(v)}"' for k, v in pairs
                    if v is not None)


def _tag(it):
    out = []
    if it.get("role"):
        out.append(("data-role", it["role"]))
    if it.get("owner"):
        out.append(("data-owner", str(it["owner"])))
    return out


def element(it):
    el = it["el"]
    common = []
    if it.get("opacity") is not None:
        common.append(("opacity", it["opacity"]))
    if el == "rect":
        a = [("x", it["x"]), ("y", it["y"]), ("width", it["w"]), ("height", it["h"])]
        if it.get("rx"):
            a.append(("rx", it["rx"]))
        a.append(("fill", it.get("fill") or "none"))
        if it.get("stroke"):
            a += [("stroke", it["stroke"]), ("stroke-width", it.get("sw", 1))]
            if it.get("dash"):
                a.append(("stroke-dasharray", it["dash"]))
        return f"<rect {_attrs(a + common + _tag(it))}/>"
    if el == "circle":
        a = [("cx", it["cx"]), ("cy", it["cy"]), ("r", it["r"]), ("fill", it.get("fill") or "none")]
        if it.get("stroke"):
            a += [("stroke", it["stroke"]), ("stroke-width", it.get("sw", 1))]
            if it.get("dash"):
                a.append(("stroke-dasharray", it["dash"]))
        return f"<circle {_attrs(a + common + _tag(it))}/>"
    if el == "path":
        d = rounded(it["pts"], it.get("corner") or 0, it.get("closed", False))
        a = [("d", d), ("fill", it.get("fill") or "none"), ("stroke", it["stroke"]), ("stroke-width", it["sw"])]
        if it.get("dash"):
            a.append(("stroke-dasharray", it["dash"]))
        cap = it.get("cap", "round")
        a += [("stroke-linecap", cap), ("stroke-linejoin", "round")]
        return f"<path {_attrs(a + common + _tag(it))}/>"
    if el == "raw":
        a = [("d", it["d"]), ("fill", it.get("fill") or "none")]
        if it.get("stroke"):
            a += [("stroke", it["stroke"]), ("stroke-width", it.get("sw", 1)), ("stroke-linejoin", "round")]
            if it.get("dash"):
                a.append(("stroke-dasharray", it["dash"]))
        if it.get("tx") or it.get("ty"):
            a.append(("transform", f"translate({_n(round(it.get('tx', 0), 2))},{_n(round(it.get('ty', 0), 2))})"))
        return f"<path {_attrs(a + common + _tag(it))}/>"
    if el == "text":
        cls = "m" if it["font"] == "mono" else "s"
        a = [("x", round(it["x"], 2)), ("y", round(it["y"], 2)), ("class", cls), ("font-size", it["size"])]
        if it["weight"] != 400:
            a.append(("font-weight", it["weight"]))
        a.append(("fill", it["fill"]))
        if it["anchor"] != "start":
            a.append(("text-anchor", it["anchor"]))
        if it.get("ls"):
            a.append(("letter-spacing", round(it["ls"] * it["size"], 3)))
        if it.get("deco"):
            a.append(("text-decoration", it["deco"]))
        a.append(("data-mw", round(it["w"], 2)))
        return f"<text {_attrs(a + common + _tag(it))}>{escape(it['s'])}</text>"
    if el == "icon":
        a = [("href", f"#i-{it['name']}"), ("x", it["x"]), ("y", it["y"]), ("width", it["size"]),
             ("height", it["size"]), ("style", f"color:{it['color']}")]
        return f"<use {_attrs(a + _tag(it))}/>"
    if el == "image":
        clip = ""
        a = [("href", it["href"]), ("x", it["x"]), ("y", it["y"]), ("width", it["w"]), ("height", it["h"]),
             ("preserveAspectRatio", "xMidYMid slice")]
        if it.get("rx"):
            cid = f"clip-{abs(hash((it['x'], it['y'], it['w']))) % 10 ** 8}"
            clip = (f'<clipPath id="{cid}"><rect x="{_n(it["x"])}" y="{_n(it["y"])}" width="{_n(it["w"])}" '
                    f'height="{_n(it["h"])}" rx="{_n(it["rx"])}"/></clipPath>')
            a.append(("clip-path", f"url(#{cid})"))
        return clip + f"<image {_attrs(a + _tag(it))}/>"
    raise ValueError(el)


def document(pages, W, H, T, fonts, embed=True, title=None):
    """pages: list of (items, dx, dy). One SVG with shared defs."""
    icons = sorted({it["name"] for items, _, _ in pages for it in items if it["el"] == "icon"})
    body = []
    for items, dx, dy in pages:
        if dx or dy:
            body.append(f'<g transform="translate({_n(dx)},{_n(dy)})">')
        for it in sorted(items, key=lambda i: i["z"]):
            body.append(element(it))
        if dx or dy:
            body.append("</g>")
    faces = fonts.css_faces() if embed else ""
    css = (f"{faces}\n.s{{font-family:{fonts.stack('sans', embed)};}}\n"
           f".m{{font-family:{fonts.stack('mono', embed)};}}\n"
           "text{text-rendering:geometricPrecision;font-kerning:none;font-variant-ligatures:none;font-feature-settings:'kern' 0,'liga' 0,'calt' 0;"
           "white-space:pre;}")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(W)} {_n(H)}" width="{_n(W)}" '
           f'height="{_n(H)}">']
    if title:
        out.append(f"<title>{escape(title)}</title>")
    out.append("<defs>")
    out.append(f"<style>\n{css}\n</style>")
    for n in icons:
        out.append(icon_symbol(n))
    out.append("</defs>")
    out.append(f'<rect width="{_n(W)}" height="{_n(H)}" fill="{T["color"]["paper"]}"/>')
    out += body
    out.append("</svg>")
    return "\n".join(out) + "\n"
