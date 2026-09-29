"""Theme icons → inline <symbol> set.

theme.json maps kind → {src, fallback, width}. Icons are used as-is: the Cisco network topology icons may be
used freely but not altered, so no recoloring; internal ids are only prefixed to stay unique once inlined,
and rendering scales them proportionally. assets/icons/custom/ holds hand-drawn fallbacks.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "icons"


def _load(spec):
    for key in ("src", "fallback"):
        p = ICON_DIR / spec.get(key, "")
        if spec.get(key) and p.is_file():
            return p.read_text()
    raise FileNotFoundError(f"icon missing: {spec}")


def to_symbol(svg_text, sym_id):
    svg_text = re.sub(r"<\?xml.*?\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", svg_text, flags=re.S)
    root = re.search(r"<svg\b([^>]*)>(.*)</svg>", svg_text, re.S)
    attrs, inner = root.group(1), root.group(2)
    vb = re.search(r'viewBox="([^"]+)"', attrs).group(1)
    root_style = re.search(r'style="([^"]*)"', attrs)
    inner = re.sub(r'\s+serif:id="[^"]*"', "", inner)
    ids = set(re.findall(r'\bid="([^"]+)"', inner))
    for i in sorted(ids, key=len, reverse=True):  # ids become document-global once inlined
        inner = re.sub(rf'(id="|url\(#|href="#){re.escape(i)}(?=["\)])', rf"\g<1>{sym_id}-{i}", inner)
    inner = "\n".join(line.strip() for line in inner.strip().splitlines() if line.strip())
    g_style = f' style="{root_style.group(1)}"' if root_style else ""
    return f'<symbol id="{sym_id}" viewBox="{vb}" overflow="visible"><g{g_style}>{inner}</g></symbol>'


def viewbox(svg_text):
    vb = re.search(r'<svg\b[^>]*viewBox="([^"]+)"', svg_text, re.S).group(1)
    _, _, w, h = (float(v) for v in vb.replace(",", " ").split())
    return w, h


def icon_dims(theme):
    """{kind: (width, height)}: width from the theme, height from the icon's own aspect ratio (never stretched)."""
    out = {}
    for kind, spec in theme["icons"].items():
        if "width" in spec:
            w, h = viewbox(_load(spec))
            out[kind] = (spec["width"], spec["width"] * h / w)
    return out


def build_symbols(theme):
    return "\n".join(to_symbol(_load(spec), f"ic-{kind}") for kind, spec in theme["icons"].items())
