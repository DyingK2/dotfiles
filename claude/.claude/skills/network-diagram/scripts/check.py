# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "playwright>=1.40"]
# ///
"""SVG → PNG render + layout conflict check (extended from netdiag-handoff/tools/render_check.py).

Checks:
  text-text     text bounding boxes overlap each other
  text-edge     text partially overlaps a rectangle edge
  line-text     a link/flow/leader line crosses text (parts hidden by a later opaque shape don't count)
  line-box      a line crosses an annotation box, host card or router icon it doesn't belong to
  text-divider  diagram text crosses into the side panel
  box-box       annotation box/segment bar/card/icon overlap each other
  text-owner    text lands on someone else's icon/card
  flow-order    flow lines must be drawn before all segment bars (i.e. below them)
  out           any visible element extends past the canvas
Side panel (inside data-role=panel) only runs text-text / text-edge / out.

usage: uv run scripts/check.py diagram.svg [out.png] [--json report.json]
"""
import argparse
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

from measure import launch

JS = r"""
() => {
  const svg = document.querySelector('svg');
  const vb = svg.viewBox.baseVal;
  const R = el => { const r = el.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; };
  const role = el => { const h = el.closest('[data-role]'); return h ? h.dataset.role : ''; };
  const owner = el => { const h = el.closest('[data-owner]'); return h ? h.dataset.owner : ''; };
  const inPanel = el => !!el.closest('[data-role=panel]');
  const inDefs = el => !!el.closest('defs, symbol, marker');
  const name = el => el.tagName === 'text' ? `"${el.textContent.trim().slice(0, 30)}"`
      : `<${el.tagName} ${role(el) || '?'}${owner(el) ? ' ' + owner(el) : ''}>`;
  const ov = (p, q) => [Math.min(p.x + p.w, q.x + q.w) - Math.max(p.x, q.x),
                        Math.min(p.y + p.h, q.y + q.h) - Math.max(p.y, q.y)];
  const inside = (p, q, t = 1) => p.x >= q.x - t && p.y >= q.y - t && p.x + p.w <= q.x + q.w + t && p.y + p.h <= q.y + q.h + t;
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  const hits = [];
  const add = (type, a, b) => hits.push({type, a: name(a), b: typeof b === 'string' ? b : name(b)});

  const all = [...svg.querySelectorAll('text, rect, path, line, use, circle, ellipse, polygon')]
      .filter(el => !inDefs(el));
  const texts = all.filter(el => el.tagName === 'text').map(el => ({el, r: R(el)})).filter(t => t.r.w > 0);
  const bg = r => r.w >= vb.width - 1 && r.h >= vb.height - 1;
  const rects = all.filter(el => el.tagName === 'rect').map(el => ({el, r: R(el)})).filter(o => o.r.w > 0 && !bg(o.r));

  // text-text
  for (let a = 0; a < texts.length; a++) for (let b = a + 1; b < texts.length; b++) {
    const [ox, oy] = ov(texts[a].r, texts[b].r);
    if (ox > 2 && oy > 2) add('text-text', texts[a].el, texts[b].el);
  }
  // text-edge
  for (const t of texts) for (const o of rects) {
    const [ox, oy] = ov(t.r, o.r);
    if (ox > 2 && oy > 2 && !inside(t.r, o.r)) add('text-edge', t.el, o.el);
  }

  const diagram = el => !inPanel(el);
  const boxes = all.filter(el => diagram(el) && ['annot', 'seg', 'card', 'icon'].includes(role(el))
      && (el.tagName === 'rect' || el.tagName === 'use')).map(el => ({el, r: R(el), role: role(el), owner: owner(el)}));
  // Segment bars and line-hugging labels are legitimate occluders (a flow line "crossing" a segment, or a
  // label sitting on its own line); a line hidden behind an annotation box/card still counts as a conflict
  const occluders = all.filter(el => diagram(el) && el.tagName === 'rect' && role(el) === 'seg')
      .map(el => ({el, r: R(el)}));

  // Lines: sample points (screen coordinates)
  const lines = all.filter(el => diagram(el) && ['link', 'flow', 'leader', 'bus'].includes(role(el))
      && (el.tagName === 'path' || el.tagName === 'line'));
  const samples = el => {
    const m = el.getScreenCTM(), pts = [], L = el.getTotalLength();
    for (let s = 0; s <= L; s += 2) {
      const p = el.getPointAtLength(s);
      pts.push({x: m.a * p.x + m.c * p.y + m.e, y: m.b * p.x + m.d * p.y + m.f});
    }
    return pts;
  };
  const inR = (p, r, pad) => p.x > r.x + pad && p.x < r.x + r.w - pad && p.y > r.y + pad && p.y < r.y + r.h - pad;
  const hidden = (line, p) => occluders.some(o => before(line, o.el) && inR(p, o.r, 0));
  for (const ln of lines) {
    const pts = samples(ln);
    for (const t of texts.filter(t => diagram(t.el))) {
      if (pts.some(p => inR(p, t.r, 1) && !hidden(ln, p))) add('line-text', ln, t.el);
    }
    for (const b of boxes.filter(b => ['annot', 'card', 'icon'].includes(b.role))) {
      if (b.role === 'icon' && b.owner === owner(ln)) continue;  // a link leaves its own icon
      if (role(ln) === 'leader' && b.owner === owner(ln)) continue;
      if (pts.some(p => inR(p, b.r, 2) && !hidden(ln, p))) add('line-box', ln, b.el);
    }
  }
  // box-box
  for (let a = 0; a < boxes.length; a++) for (let b = a + 1; b < boxes.length; b++) {
    if (boxes[a].owner && boxes[a].owner === boxes[b].owner) continue;  // a card and its own icon
    const [ox, oy] = ov(boxes[a].r, boxes[b].r);
    if (ox > 1 && oy > 1) add('box-box', boxes[a].el, boxes[b].el);
  }
  // text-owner
  for (const t of texts.filter(t => diagram(t.el))) for (const b of boxes.filter(b => ['icon', 'card'].includes(b.role))) {
    if (b.owner && b.owner === owner(t.el)) continue;
    const [ox, oy] = ov(t.r, b.r);
    if (ox > 1 && oy > 1) add('text-owner', t.el, b.el);
  }
  // text-divider: diagram text crossing the side-panel divider line
  const divider = all.find(el => owner(el) === 'divider' && el.tagName === 'line');
  if (divider) {
    const dx = R(divider).x;
    for (const t of texts.filter(t => diagram(t.el))) if (t.r.x < dx && t.r.x + t.r.w > dx - 1) add('text-divider', t.el, 'divider');
  }
  // flow-order
  const segs = all.filter(el => role(el) === 'seg' && el.tagName === 'rect');
  for (const f of all.filter(el => role(el) === 'flow' && el.tagName !== 'text'))
    for (const s of segs) if (!before(f, s)) add('flow-order', f, s);
  // out
  for (const el of all) {
    const r = R(el);
    if (r.w === 0 && r.h === 0) continue;
    if (r.x < -0.5 || r.y < -0.5 || r.x + r.w > vb.width + 0.5 || r.y + r.h > vb.height + 0.5) add('out', el, 'canvas');
  }
  return {w: vb.width, h: vb.height, hits};
}
"""


def check(svg_path, png_path=None):
    src = pathlib.Path(svg_path).resolve()
    png = png_path or str(src.with_suffix(".png"))
    with sync_playwright() as p:
        b = launch(p)
        pg = b.new_page()
        pg.goto(src.as_uri())
        w, h = pg.evaluate("() => { const v = document.querySelector('svg').viewBox.baseVal; return [v.width, v.height]; }")
        pg.set_viewport_size({"width": int(w), "height": int(h)})
        r = pg.evaluate(JS)
        pg.screenshot(path=png)
        b.close()
    r["png"] = png
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("png", nargs="?")
    ap.add_argument("--json")
    a = ap.parse_args()
    r = check(a.svg, a.png)
    print(f"PNG: {r['png']}")
    for h in r["hits"]:
        print(f"  [{h['type']}] {h['a']}  <->  {h['b']}")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"{len(r['hits'])} conflict(s)" if r["hits"] else "0 conflicts")
    sys.exit(1 if r["hits"] else 0)


if __name__ == "__main__":
    main()
