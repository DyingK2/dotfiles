# /// script
# requires-python = ">=3.10"
# dependencies = ["fonttools>=4.47", "brotli>=1.1", "pillow>=10", "playwright>=1.40"]
# ///
"""Render a diagram scene script to SVG + PNG and self-check the layout.

usage: uv run scripts/render.py scene.py [-o OUT_DIR] [--no-png] [--no-embed] [--no-diff] [--cols N]

A scene script defines either
    def build(d): ...                      → <stem>.svg / .png
or
    STEPS = [...]                          (any per-step data: dicts, tuples, captions …)
    def build(d, step): ...                → <stem>-01.svg … one page per step + <stem>-steps.svg storyboard
All steps share one canvas; what changed since the previous step is highlighted automatically
(changed → amber, added → green, removed → red dashed ghost) unless the script sets DIFF = False.
Optional module globals: DIFF (bool), COLS (storyboard columns).

Exit status 1 when the self-check finds conflicts.
"""
import argparse
import json
import logging
import math
import pathlib
import runpy
import sys
import warnings

warnings.filterwarnings("ignore", message=".*global interpreter lock.*")  # fontTools on free-threaded Python
logging.getLogger("fontTools").setLevel(logging.ERROR)

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from dgm import Diagram, FontSet
from dgm.check import check
from dgm.core import Rect, Scene, union_all
from dgm.diagram import page
from dgm.svg import document

INSTALL = "uv run --with playwright playwright install chromium-headless-shell"
SUBKEY = (".", "[", "#", "^", "~", ":", "<")


def load_theme():
    return json.loads((ROOT / "theme.json").read_text())


def _child_of(uid, roots):
    return any(len(uid) > len(r) and uid.startswith(r) and uid[len(r)] in SUBKEY for r in roots)


def diff_units(prev, cur):
    """uid → state for the units of `cur` compared with `prev`, plus the removed units to ghost.
    A unit inside a new/removed parent (a field of a new record, a cell of a removed array) is not marked
    separately — the parent carries the change."""
    states, new_roots = {}, []
    for uid in sorted(cur, key=len):
        u = cur[uid]
        if not u["diff"]:
            continue
        if uid not in prev:
            if not _child_of(uid, new_roots):
                states[uid] = "new"
            new_roots.append(uid)
        elif prev[uid]["sig"] != u["sig"]:
            states[uid] = "changed"
    ghosts, gone_roots = [], []
    for uid in sorted(prev, key=len):
        u = prev[uid]
        if uid in cur or not u["diff"]:
            continue
        if not _child_of(uid, gone_roots) and u["shape"] != "none" and not _covered(u, cur):
            ghosts.append(u)
        gone_roots.append(uid)
    return states, ghosts


def _covered(u, cur):
    """A removed unit whose place is now taken by something else needs no ghost (it was replaced)."""
    for c in cur.values():
        if u["shape"] == "path":
            if c["shape"] == "path" and c["pts"] and u["pts"] and all(
                    abs(a - b) < 3 for p, q in ((u["pts"][0], c["pts"][0]), (u["pts"][-1], c["pts"][-1]))
                    for a, b in zip(p, q)):
                return True
        elif u["rect"] is not None and c["rect"] is not None:
            ox, oy = u["rect"].overlap(c["rect"])
            if ox > 0 and oy > 0 and ox * oy > 0.5 * u["rect"].w * u["rect"].h:
                return True
    return False


def browser(svg_path, png_path, scale=2):
    """PNG screenshot + verify every text renders no wider than it was measured."""
    from playwright.sync_api import Error, sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Error as e:
            if "Executable doesn't exist" in str(e):
                print(f"note: Chromium is missing, so no PNG. Install it once with:\n  {INSTALL}", file=sys.stderr)
                return None
            raise
        pg = b.new_page(device_scale_factor=scale)
        pg.goto(pathlib.Path(svg_path).resolve().as_uri())
        w, h = pg.evaluate("() => { const v = document.querySelector('svg').viewBox.baseVal; "
                           "return [v.width, v.height]; }")
        pg.set_viewport_size({"width": int(w + 0.99), "height": int(h + 0.99)})
        pg.evaluate("document.fonts.ready")
        bad = pg.evaluate("""() => [...document.querySelectorAll('text[data-mw]')].map(t => {
              const real = t.getComputedTextLength(), mw = parseFloat(t.dataset.mw);
              return real > mw + 0.75 ? [t.textContent.slice(0, 40), real, mw] : null; }).filter(Boolean)""")
        pg.screenshot(path=str(png_path))  # full_page hangs on SVG documents
        b.close()
    return bad


def report(tag, hits, bad):
    for kind, a, b in hits:
        print(f"  [{kind}] {a}  <->  {b}")
    for s, real, mw in bad or []:
        print(f"  [text-width] \"{s}\" renders {real:.1f}px but was measured {mw:.1f}px (font fallback?)")
    n = len(hits) + len(bad or [])
    print(f"{tag}: {n} conflict(s)" if n else f"{tag}: 0 conflicts")
    return n


def main():
    ap = argparse.ArgumentParser(description="scene.py → SVG + PNG with layout self-check")
    ap.add_argument("scene", nargs="+", help="scene script(s); several → a regression run over all of them")
    ap.add_argument("-o", "--out", help="output directory (default: next to the scene)")
    ap.add_argument("--no-png", action="store_true", help="skip the browser (no PNG, no text-width check)")
    ap.add_argument("--no-embed", action="store_true", help="do not embed font subsets (smaller, less exact SVG)")
    ap.add_argument("--no-diff", action="store_true", help="steps: no automatic change highlighting")
    ap.add_argument("--cols", type=int, help="storyboard columns (default: 2 when panels are narrow)")
    ap.add_argument("--scale", type=float, default=2, help="PNG pixel ratio (default 2)")
    a = ap.parse_args()
    failed = 0
    for scene in a.scene:
        try:
            failed += render_scene(pathlib.Path(scene).resolve(), a) > 0
        except Exception as e:  # keep going in a multi-scene run, but say exactly what broke
            if len(a.scene) == 1:
                raise
            print(f"{scene}: error: {type(e).__name__}: {e}")
            failed += 1
    if len(a.scene) > 1:
        print(f"{len(a.scene) - failed}/{len(a.scene)} scenes clean")
    sys.exit(1 if failed else 0)


def render_scene(src, a):
    """Render one scene script; returns the number of conflicts."""
    out = pathlib.Path(a.out).resolve() if a.out else src.parent
    out.mkdir(parents=True, exist_ok=True)
    T = load_theme()
    F = FontSet(T["fonts"])
    if str(src.parent) not in sys.path:
        sys.path.insert(0, str(src.parent))  # scenes may import helpers (simulations, data) next to them
    mod = runpy.run_path(str(src), run_name="__scene__")
    build = mod.get("build")
    if build is None:
        raise SystemExit(f"error: {src.name} defines no build(d) / build(d, step)")
    steps = mod.get("STEPS")
    embed = not a.no_embed
    total, outputs = 0, []

    if not steps:
        d = Diagram(T, F)
        build(d)
        S = d.scene()
        items, W, H, info = page(d, S, S.bbox())
        hits = check(items, W, H, d, info["offset"])
        p = out / f"{src.stem}.svg"
        p.write_text(document([(items, 0, 0)], W, H, T, F, embed, d.head.get("title")))
        outputs.append(p)
        bad = None if a.no_png else browser(p, p.with_suffix(".png"), a.scale)
        total += report(p.name, hits, bad)
    else:
        ds = []
        for st in steps:
            d = Diagram(T, F)
            build(d, st)
            if d.cap is None and isinstance(st, dict) and st.get("caption"):
                d.cap = st["caption"]
            d.layout()
            ds.append(d)
        drift_warnings(ds)
        diff_on = mod.get("DIFF", True) and not a.no_diff
        scenes, prev = [], None
        for d in ds:
            units = d.scene().units
            states, ghosts = diff_units(prev, units) if (diff_on and prev is not None) else ({}, [])
            prev = units
            S = d.scene(states, ghosts)
            scenes.append(S)
            used = S.applied | ({"removed"} if ghosts else set())
            for s in ("changed", "new", "removed"):
                if s in used and not any(it[:2] == ("state", s) for it in d.legend_items):
                    d.legend(("state", s, d.state_label(s)))
        # one legend (union over steps) and one content box → every page has identical geometry
        legend = []
        for d in ds:
            legend += [it for it in d.legend_items if it not in legend]
        for d in ds:
            d.legend_items = list(legend)
        box = union_all(S.bbox() for S in scenes)
        n = len(ds)
        M = T["look"]["margin"]
        # pass 1 finds the widest page and the most caption lines; pass 2 lays every page out with both, so the
        # content sits at exactly the same place on every page
        pages = [page(d, S, box, step=(k + 1, n, d.cap)) for k, (d, S) in enumerate(zip(ds, scenes))]
        min_w = max(p[1] for p in pages) - 2 * M
        pages = [page(d, S, box, step=(k + 1, n, d.cap), min_w=min_w) for k, (d, S) in enumerate(zip(ds, scenes))]
        cap_lines = max(_cap_lines(p) for p in pages)
        pages = [page(d, S, box, step=(k + 1, n, d.cap), cap_lines=cap_lines, min_w=min_w)
                 for k, (d, S) in enumerate(zip(ds, scenes))]
        W = max(p[1] for p in pages)
        H = max(p[2] for p in pages)
        for k, ((items, _, _, info), d) in enumerate(zip(pages, ds)):
            hits = check(items, W, H, d, info["offset"])
            p = out / f"{src.stem}-{k + 1:02d}.svg"
            p.write_text(document([(items, 0, 0)], W, H, T, F, embed, d.head.get("title")))
            outputs.append(p)
            bad = None if a.no_png else browser(p, p.with_suffix(".png"), a.scale)
            total += report(p.name, hits, bad)
        p = out / (f"{src.stem}.svg" if src.stem.endswith("-steps") else f"{src.stem}-steps.svg")
        p.write_text(storyboard(ds, scenes, box, T, F, embed, a.cols or mod.get("COLS"), cap_lines, min_w))
        outputs.append(p)
        if not a.no_png:
            browser(p, p.with_suffix(".png"), a.scale)
    print("fonts: " + F.report())
    for p in outputs:
        print(f"SVG: {p}" + ("" if a.no_png else f"  PNG: {p.with_suffix('.png')}"))
    return total


def drift_warnings(ds):
    """Steps promise a still layout. Report components that move or change size between frames — usually a
    width that follows its values (fix with w=) or a .below()/.right_of() anchored on something that changes."""
    prev = None
    for k, d in enumerate(ds):
        cur = {el.id: el.rect for el in d.els if el.placed and el.solid}  # free text may follow what it labels
        if prev:
            for id_, r in cur.items():
                q = prev.get(id_)
                if q is None:
                    continue
                if abs(q.x - r.x) > 0.5 or abs(q.y - r.y) > 0.5:
                    print(f"warning: step {k + 1}: '{id_}' moved by ({r.x - q.x:+.0f}, {r.y - q.y:+.0f}) px since "
                          f"step {k} — anchor it to something fixed (.at / a fixed neighbour)", file=sys.stderr)
                elif abs(q.w - r.w) > 0.5 or abs(q.h - r.h) > 0.5:
                    print(f"warning: step {k + 1}: '{id_}' resized {q.w:.0f}×{q.h:.0f} → {r.w:.0f}×{r.h:.0f} — "
                          f"give it a fixed w=/h= so the frame stays still", file=sys.stderr)
        prev = cur


def _cap_lines(pg):
    return sum(1 for it in pg[0] if it.get("role") == "step-caption") or 1


def storyboard(ds, scenes, box, T, F, embed, cols, cap_lines, min_w):
    """All steps on one sheet: header once, one framed panel per step, legend once."""
    C, M = T["color"], T["look"]["margin"]
    n = len(ds)
    I, G = 14, 16  # frame inset inside a panel page, gap between frames
    panels = []
    for k, (d, S) in enumerate(zip(ds, scenes)):
        panels.append(page(d, S, box, step=(k + 1, n, d.cap), header=False, legend=False, footer=False,
                           cap_lines=cap_lines, min_w=min_w))
    pw = max(p[1] for p in panels)
    ph = max(p[2] for p in panels)
    if not cols:
        # the column count whose sheet is closest to a 4:3 landscape page (at most 3 columns)
        cols = min(range(1, min(n, 3) + 1),
                   key=lambda c: abs(math.log((c * pw) / (math.ceil(n / c) * ph) / (4 / 3))))
    cols = max(1, min(cols, n))
    rows = (n + cols - 1) // cols
    fw, fh = pw - 2 * I, ph - 2 * I          # frame size
    inner = cols * fw + (cols - 1) * G       # sheet content width
    d0, dl = ds[0], ds[-1]
    hdr = page(d0, Scene(d0), Rect(0, 0, inner, 0), header=True, legend=False, footer=False)
    top = hdr[3]["top"]
    saved = dl.head
    dl.head = {}
    leg = page(dl, Scene(dl), Rect(0, 0, inner, 0), header=False, legend=True, footer=True)
    dl.head = saved
    W = max(inner + 2 * M, hdr[1], leg[1])
    frames_bottom = top + rows * fh + (rows - 1) * G
    leg_dy = frames_bottom - leg[3]["top"] + 4
    H = leg_dy + leg[2]
    out = [(hdr[0], 0, 0)]
    for k, (items, w, h, info) in enumerate(panels):
        r, c = divmod(k, cols)
        x = M + c * (fw + G) - I
        y = top + r * (fh + G) - I
        frame = {"el": "rect", "x": I + 0.5, "y": I + 0.5, "w": fw - 1, "h": fh - 1, "rx": 10, "fill": C["paper"],
                 "stroke": C["rule"], "sw": 1, "z": -1, "role": "panel", "owner": None, "bbox": None}
        out.append(([frame] + items, x, y))
    out.append((leg[0], 0, leg_dy))
    return document(out, W, H, T, F, embed, d0.head.get("title"))


if __name__ == "__main__":
    main()
