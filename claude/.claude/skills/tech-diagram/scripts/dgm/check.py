"""Layout self-check on the final item list (page coordinates) — exact, because text widths are the real font
advances. Every conflict names both parties so the fix is obvious.

  text-text   two texts overlap
  text-edge   a text straddles a box border (overflowing its node, or half on a neighbour)
  text-owner  a text sits inside a box it does not belong to
  line-text   an edge / leader / pointer runs through a text
  line-box    an edge runs through a box that is not one of its endpoints
  line-line   two edges run on top of each other
  box-box     two components overlap
  edge-end    an edge does not start / end on its component's border (e.g. fanned off a thin target)
  out         something extends past the canvas
"""
from .core import seg_hits_rect

LINE_ROLES = {"edge", "leader", "ptr-line", "msg", "span", "band", "grow"}
TEXT_SKIP_EDGE = {"badge-text", "ghost-text"}


def _name(it):
    if it["el"] == "text":
        return f'"{it["s"][:32]}"'
    return f"<{it.get('role') or it['el']} {it.get('owner') or ''}>".replace(" >", ">")


def _segs(pts):
    return list(zip(pts, pts[1:]))


def check(items, W, H, d, offset=(0, 0)):
    """items: final page items; d: the Diagram (for component rects, shifted by offset)."""
    hits = []
    add = lambda kind, a, b: hits.append((kind, a, b))
    ox, oy = offset
    texts = [it for it in items if it["el"] == "text" and it.get("s", "").strip()]
    boxes = []   # (rect, id, name)
    for el in d.els:
        if el.solid:
            r = el.rect.shift(ox, oy)
            boxes.append((r, el.id, f"<{el.prefix} {el.id}>", el.shape()))
    groups = [(el.rect.shift(ox, oy), el.id) for el in d.els if el.prefix == "group"]
    lines = [it for it in items if it["el"] == "path" and it.get("role") in LINE_ROLES]

    # text-text
    for i in range(len(texts)):
        a = texts[i]["bbox"]
        for j in range(i + 1, len(texts)):
            b = texts[j]["bbox"]
            ov = a.overlap(b)
            if ov[0] > 1.5 and ov[1] > 1.5:
                add("text-text", _name(texts[i]), _name(texts[j]))
    # text vs boxes
    for t in texts:
        if t.get("role") in TEXT_SKIP_EDGE:
            continue
        tb = t["bbox"].inflate(-0.5)
        for r, bid, bname, shape in boxes:
            ov = tb.overlap(r)
            if ov[0] <= 1 or ov[1] <= 1:
                continue
            owner = str(t.get("owner") or "")
            mine = owner == bid or owner.startswith(bid + ".")
            if not r.contains(tb, tol=0.5):
                add("text-edge", _name(t), bname)
            elif not mine:
                add("text-owner", _name(t), bname)
        for r, gid in groups:
            ov = tb.overlap(r)
            if ov[0] > 1 and ov[1] > 1 and not r.contains(tb, tol=0.5):
                add("text-edge", _name(t), f"<group {gid}>")
    # lines
    ends = {}
    for e in d.edges:
        ends[e.id] = {x for x in (e.a.owner.uid if e.a.owner else None, e.b.owner.uid if e.b.owner else None) if x}
    for el in d.els:
        if el.prefix == "note" and getattr(el, "target", None) is not None and hasattr(el.target, "top_owner"):
            ends[el.id] = {el.id, el.target.top_owner.uid}
        if el.prefix == "band":
            ends[el.id] = {el.id, el.src.top_owner.uid, el.dst.top_owner.uid}
    for ln in lines:
        owner = str(ln.get("owner") or "")
        segs = _segs(ln["pts"])
        own_eps = ends.get(owner, {owner})
        for t in texts:
            if ln.get("role") == "msg" and t.get("role") in ("label", "badge-text") and str(t.get("owner")) == owner:
                continue
            if t.get("role") in ("badge-text",) and str(t.get("owner")) == owner:
                continue
            tb = t["bbox"].inflate(-1)
            if any(seg_hits_rect(a, b, tb) for a, b in segs):
                add("line-text", _name(ln), _name(t))
        if ln.get("role") in ("edge", "leader", "band"):
            for r, bid, bname, shape in boxes:
                if bid in own_eps:
                    continue
                inner = r.inflate(-2)
                if any(seg_hits_rect(a, b, inner) for a, b in segs):
                    add("line-box", _name(ln), bname)
    edge_lines = [ln for ln in lines if ln.get("role") == "edge"]
    for i in range(len(edge_lines)):
        for j in range(i + 1, len(edge_lines)):
            A, B = edge_lines[i], edge_lines[j]
            if A.get("owner") == B.get("owner"):
                continue
            if max(abs(A["pts"][-1][0] - B["pts"][-1][0]), abs(A["pts"][-1][1] - B["pts"][-1][1])) < 10:
                continue  # converging on one point (arrow bases differ by the arrow cut): a deliberate merge
            if any(_overlap(s, t) > 4 for s in _segs(A["pts"]) for t in _segs(B["pts"])):
                add("line-line", _name(A), _name(B))
    # edge-end: endpoints sit on the border of their element (parts may attach a little outside, past labels)
    for e in d.edges:
        if not e.pts or e.route in ("straight", "center") or e.via:
            continue
        for end, p in ((e.a, e.pts[0]), (e.b, e.pts[-1])):
            if end.kind == "pt" or (end is e.a and end.ptr):
                continue
            r = end.rect
            off = max(end.obj.offset.values(), default=0) if end.kind == "part" else 0
            dx = max(r.x0 - p[0], 0, p[0] - r.x1)
            dy = max(r.y0 - p[1], 0, p[1] - r.y1)
            inside = r.x0 + 1 < p[0] < r.x1 - 1 and r.y0 + 1 < p[1] < r.y1 - 1
            if inside or (dx * dx + dy * dy) ** 0.5 > off + 1.5:
                add("edge-end", f"<edge {e.id}>", f"<{end.uid}>")
    # box-box
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ov = boxes[i][0].overlap(boxes[j][0])
            if ov[0] > 1 and ov[1] > 1:
                add("box-box", boxes[i][2], boxes[j][2])
    # out of canvas
    for it in items:
        b = it.get("bbox")
        if b is None:
            continue
        if b.x0 < -0.5 or b.y0 < -0.5 or b.x1 > W + 0.5 or b.y1 > H + 0.5:
            add("out", _name(it), "canvas")
    # de-duplicate
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _overlap(s, t, tol=3.0):
    (a, b), (c, d) = s, t
    if abs(a[1] - b[1]) < 0.01 and abs(c[1] - d[1]) < 0.01 and abs(a[1] - c[1]) < tol:
        return min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0]))
    if abs(a[0] - b[0]) < 0.01 and abs(c[0] - d[0]) < 0.01 and abs(a[0] - c[0]) < tol:
        return min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1]))
    return 0.0
