"""Diagram: factories, placement helpers, page composition (header, step bar, legend, footer)."""
from . import comps, edges, mem
from .core import CJK, Rect, Scene, wrap


class Diagram:
    def __init__(self, theme, fonts):
        self.T, self.F = theme, fonts
        self.els, self.edges = [], []
        self._ids, self._count, self._edge_ids = set(), {}, set()
        self.head = {}
        self.cap = None
        self.legend_items = []
        self.foot = None
        self._routed = False

    # ------------------------------------------------------------------ bookkeeping
    def _uid(self, prefix, id):
        if id is not None:
            id = str(id)
            if id in self._ids:
                raise ValueError(f"duplicate id {id!r}")
        else:
            while True:
                self._count[prefix] = self._count.get(prefix, 0) + 1
                id = f"{prefix}{self._count[prefix]}"
                if id not in self._ids:
                    break
        self._ids.add(id)
        return id

    def _register(self, el):
        self.els.append(el)

    def _unregister(self, el):
        self.els.remove(el)
        self._ids.discard(el.id)

    def tw(self, s, size, font="sans", weight=400, ls=0.0):
        return self.F.width(str(s), size, font, weight, ls)

    # ------------------------------------------------------------------ components
    def node(self, title, **kw):
        """Box / card / record / circle. See comps.Node."""
        return comps.Node(self, title, **kw)

    def array(self, values, **kw):
        return comps.Array(self, values, **kw)

    def listnode(self, value, next=True, prev=False, id=None, **kw):
        """Linked-list node [value | •]. next: True → pointer dot, None → null slash.
        prev: False (default) → singly linked; True / None → doubly linked [• | value | •] with a live / null prev.
        Attach edges to node.next / node.prev (they start at the dot)."""
        cells, widths = [], []
        vw = max(40, self.tw(str(value), 12.5, "mono", 500) + 20)
        if prev is not False:
            cells.append(comps.PTR if prev else comps.NULL)
            widths.append(24)
        cells.append(value)
        widths.append(round(vw / 4 + 0.49) * 4)
        cells.append(comps.PTR if next else comps.NULL)
        widths.append(24)
        return comps.Array(self, cells, index=False, widths=widths, id=id, **kw)

    def table(self, columns, rows, **kw):
        return comps.Table(self, columns, rows, **kw)

    def bits(self, fields, **kw):
        return comps.Bits(self, fields, **kw)

    def code(self, code, **kw):
        return comps.Code(self, code, **kw)

    def note(self, text, target=None, **kw):
        return comps.Note(self, text, target=target, **kw)

    def text(self, text, **kw):
        return comps.Text(self, text, **kw)

    def image(self, path, w, **kw):
        return comps.Image(self, path, w, **kw)

    def memmap(self, regions, **kw):
        """Address space / memory layout: regions stacked by address, gaps, boundary addresses. See mem.MemMap."""
        return mem.MemMap(self, regions, **kw)

    def band(self, src, dst, label=None, **kw):
        """Translucent band mapping one address range onto another (create after placing both ends)."""
        return mem.Band(self, src, dst, label, **kw)

    def zoom(self, src, dst, label=None, **kw):
        """Dashed magnifier from a region to the component that details it."""
        return mem.Band(self, src, dst, label, kind="zoom", **kw)

    def seq(self, actors, messages, **kw):
        return comps.Seq(self, actors, messages, **kw)

    def group(self, members, label=None, **kw):
        g = comps.Group(self, members, label, **kw)
        # groups draw behind everything; keep them before their members in emission order
        self.els.remove(g)
        self.els.insert(0, g)
        return g

    def edge(self, src, dst, label=None, **kw):
        """Connector. style solid|dashed|dotted, state/tone colour, arrow end|start|both|none,
        route auto|straight|hv|vh, via=[(x,y)…], src_side/dst_side, step=n (numbered disc)."""
        e = edges.Edge(self, src, dst, label, **kw)
        self.edges.append(e)
        return e

    # ------------------------------------------------------------------ placement helpers
    def row(self, items, at=(0, 0), gap=48, align="center"):
        """Place items left→right starting at `at` (top-left of the row)."""
        items = [i for i in items if i is not None]
        hmax = max(i.h for i in items)
        x = at[0]
        for it in items:
            l, t, r, b = it.pad_ext
            y = {"top": at[1], "center": at[1] + (hmax - it.h) / 2, "bottom": at[1] + hmax - it.h}[align]
            it.at(x + l, y)
            x += l + it.w + r + gap
        return items

    def col(self, items, at=(0, 0), gap=40, align="center"):
        """Place items top→bottom; align left|center|right relative to the widest item."""
        items = [i for i in items if i is not None]
        wmax = max(i.w for i in items)
        y = at[1]
        for it in items:
            l, t, r, b = it.pad_ext
            x = {"left": at[0], "center": at[0] + (wmax - it.w) / 2, "right": at[0] + wmax - it.w}[align]
            it.at(x, y + t)
            y += t + it.h + b + gap
        return items

    def grid(self, items, cols, at=(0, 0), gap=(48, 40)):
        """Row-major grid with uniform cell size (max item size)."""
        cw = max(i.ext.w if i.placed else i.w + i.pad_ext[0] + i.pad_ext[2] for i in items)
        ch = max(i.h + i.pad_ext[1] + i.pad_ext[3] for i in items)
        for k, it in enumerate(items):
            r, c = divmod(k, cols)
            x = at[0] + c * (cw + gap[0]) + (cw - it.w) / 2
            y = at[1] + r * (ch + gap[1]) + (ch - it.h) / 2
            it.at(x, y)
        return items

    def same_width(self, items, w=None):
        """Give items one width (their max) so a column reads as a column. Call before placing."""
        w = w or max(i.w for i in items)
        for i in items:
            if isinstance(i, comps.Node) and i.fields:
                for p in i.parts.values():
                    p.w = w
            i.w = w
        return items

    def remove(self, *items):
        """Drop elements from the drawing (they keep their position, so a tree laid out with them keeps its
        shape). Use it to reserve slots for things that only appear in later steps."""
        for i in items:
            if i in self.els:
                self._unregister(i)

    def move(self, items, dx=0, dy=0):
        for i in items:
            i.shift(dx, dy)
        return items

    def tree(self, root, children, at=(0, 0), hgap=24, vgap=48, slot=None):
        """Tidy top-down tree. children: {node: [child | None, …]}; None keeps an empty slot so a lone right
        child stays on the right. Lay out the *final* tree once and reuse positions in every step."""
        slot = slot or root.w

        def width(n):
            if n is None:
                return slot
            kids = children.get(n) or []
            if not kids or all(k is None for k in kids):
                return n.w
            return max(n.w, sum(width(k) for k in kids) + hgap * (len(kids) - 1))

        level_h = {}

        def depth_scan(n, dep):
            if n is None:
                return
            level_h[dep] = max(level_h.get(dep, 0), n.h)
            for k in children.get(n) or []:
                depth_scan(k, dep + 1)

        depth_scan(root, 0)
        ys = {0: at[1]}
        for dep in sorted(level_h)[1:]:
            ys[dep] = ys[dep - 1] + level_h[dep - 1] + vgap

        def place(n, left, dep):
            if n is None:
                return
            W = width(n)
            kids = children.get(n) or []
            if kids and not all(k is None for k in kids):
                inner = sum(width(k) for k in kids) + hgap * (len(kids) - 1)
                x = left + (W - inner) / 2
                for k in kids:
                    place(k, x, dep + 1)
                    x += width(k) + hgap
            n.at(left + (W - n.w) / 2, ys[dep] + (level_h[dep] - n.h) / 2)

        place(root, at[0], 0)
        return root

    # ------------------------------------------------------------------ page furniture
    def title(self, title, eyebrow=None, subtitle=None):
        self.head = {"title": title, "eyebrow": eyebrow, "subtitle": subtitle}

    def caption(self, text):
        """Step caption (what happens in this step)."""
        self.cap = text

    def legend(self, *items):
        """Legend entries: (what, value, text) with what in node|edge|state|tone|text, e.g.
        ("edge", "dashed", "async reply"), ("node", "focal", "entry point"), ("state", "changed", "updated")."""
        for it in items:
            if isinstance(it, dict):
                it = (it["what"], it.get("value"), it["text"])
            self.legend_items.append(tuple(it))

    def footer(self, text):
        self.foot = text

    @property
    def lang(self):
        """zh when the title, subtitle or caption contains CJK, else en (drives built-in labels)."""
        texts = [str(v) for v in self.head.values() if v] + ([str(self.cap)] if self.cap else [])
        return "zh" if any(CJK.search(t) for t in texts) else "en"

    def state_label(self, state):
        s = self.T["states"][state]
        return s.get("label_zh", s["label"]) if self.lang == "zh" else s["label"]

    # ------------------------------------------------------------------ build
    def layout(self):
        if self._routed:
            return
        missing = [e.id for e in self.els if not e.placed]
        if missing:
            raise ValueError(f"not placed: {', '.join(missing)} — every component needs .at()/.right_of()/row()…")
        obstacles = []
        for el in self.els:
            for r in el.obstacles():
                obstacles.append((r, el.id))
        edges.plan(self, self.edges, obstacles)
        self._place_captions()
        self._routed = True

    def _place_captions(self):
        """Circle captions with sub_pos="auto": take the side that no edge, box or other text touches."""
        from .core import seg_hits_rect
        segs = [s for e in self.edges for s in zip(e.pts, e.pts[1:])]
        for el in self.els:
            if not getattr(el, "sub_auto", False):
                continue
            others = [o.ext for o in self.els if o is not el and o.solid]
            best = None
            for k, pos in enumerate(comps.Node.SUB_POS):
                r = el.sub_rect(pos).inflate(2)
                cost = k + 100 * sum(1 for a, b in segs if seg_hits_rect(a, b, r)) + 100 * sum(1 for o in others if r.hits(o))
                if best is None or cost < best[0]:
                    best = (cost, pos)
            el.set_sub_pos(best[1])

    def scene(self, diff=None, ghosts=()):
        self.layout()
        S = Scene(self, diff)
        for g in ghosts:
            _ghost(S, g)
        for el in self.els:
            el.emit(S)
        for e in self.edges:
            edges.emit(S, e)
        return S


def _ghost(S, u):
    """Draw where a removed unit used to be (dashed, red, faded)."""
    col = S.T["states"]["removed"]["stroke"]
    ink = S.T["states"]["removed"]["ink"]
    if u["shape"] == "path" and u["pts"]:
        S.path(u["pts"], col, 1.25, "4 4", z=2, role="ghost", owner="ghost", opacity=0.55)
        return
    r = u["rect"]
    if r is None:
        return
    if u["shape"] == "circle":
        S.circle(r.cx, r.cy, r.w / 2, fill=S.T["states"]["removed"]["fill"], stroke=col, sw=1.2, z=2, role="ghost",
                 owner="ghost", dash="4 3")
    else:
        S.rect(r, rx=u["rx"] or 4, fill=S.T["states"]["removed"]["fill"], stroke=col, sw=1.2, dash="4 3", z=2,
               role="ghost", owner="ghost")
    if u["text"]:
        size = 12
        t = u["text"]
        while size > 8 and S.d.tw(t, size, "mono", 500) > r.w - 6:
            size -= 0.5
        S.text(r.cx, r.cy + size * 0.35, t, size, "mono", 500, ink, "middle", z=2.1, role="ghost-text",
               owner="ghost", deco="line-through", opacity=0.8)


# ====================================================================================== page composition

def page(d, S, box, step=None, header=True, legend=True, footer=True, cap_lines=None, min_w=0):
    """Lay out header / step bar / content / legend. Returns (items in page coordinates, W, H, info) with
    info = {offset: content translation, top: y where content starts, bottom: y after content}.

    box      content bounding box to reserve (union over steps so every step has the same geometry)
    step     (k, n, caption) or None
    """
    T, C, Z = d.T, d.T["color"], d.T["size"]
    M = T["look"]["margin"]
    P = Scene(d)  # page furniture
    content_w = box.w
    W_inner = max(content_w, min_w)
    head = d.head if header else {}
    y = M
    sub_lines = []
    if head:
        tw = d.tw(head.get("title") or "", Z["title"], "sans", 650)
        W_inner = max(W_inner, min(tw, 900))
        if head.get("subtitle"):
            sub_lines = wrap(d, head["subtitle"], max(W_inner, 600), Z["subtitle"], "sans")
            W_inner = max(W_inner, max(d.tw(l, Z["subtitle"], "sans") for l in sub_lines))
    cap_ls = []
    if step:
        chip = f"STEP {step[0]} / {step[1]}"
        cw = d.tw(chip, 9.5, "mono", 600, 0.08) + 14
        if step[2]:
            cap_ls = wrap(d, step[2], max(W_inner - cw - 12, 360), Z["caption"], "sans", 500)
            W_inner = max(W_inner, cw + 12 + max(d.tw(l, Z["caption"], "sans", 500) for l in cap_ls))
    legend_rows = _legend_layout(d, W_inner) if (legend and d.legend_items) else []
    W = W_inner + 2 * M
    if head:
        if head.get("eyebrow"):
            P.text(M, y + 10, str(head["eyebrow"]).upper(), Z["eyebrow"], "mono", 500, C["muted"], ls=0.12,
                   role="head")
            y += 22
        if head.get("title"):
            P.text(M, y + 19, head["title"], Z["title"], "sans", 650, C["ink"], role="head")
            y += 28
        for l in sub_lines:
            P.text(M, y + 13, l, Z["subtitle"], "sans", 400, C["muted"], role="head")
            y += 19
        y += 18
    if step:
        chip = f"STEP {step[0]} / {step[1]}"
        cw = d.tw(chip, 9.5, "mono", 600, 0.08) + 14
        P.rect(Rect(M, y, cw, 20), rx=10, fill=C["ink"], role="step-chip")
        P.text(M + 7, y + 13.5, chip, 9.5, "mono", 600, C["paper"], ls=0.08, role="step-chip")
        for i, l in enumerate(cap_ls):
            P.text(M + cw + 10, y + 14.5 + i * 19, l, Z["caption"], "sans", 500, C["ink"], role="step-caption")
        nl = max(len(cap_ls), cap_lines or 0, 1)
        y += 20 + (nl - 1) * 19 + 20
    ox = M + (W_inner - content_w) / 2 - box.x
    oy = y - box.y
    info = {"offset": (ox, oy), "top": y, "bottom": y + box.h}
    y += box.h + 24
    info["legend"] = y if legend_rows else None
    if legend_rows:
        P.path([(M, y), (W - M, y)], C["rule"], 1, z=1, role="legend-rule", cap="butt", corner=0)
        y += 14
        P.text(M, y + 9, "图例" if d.lang == "zh" else "LEGEND", 9 if d.lang != "zh" else 10, "mono", 500,
               C["soft"], ls=0.14, role="legend")
        y += 18
        for row in legend_rows:
            for (x, it, tw) in row:
                _legend_item(P, d, M + x, y, it)
            y += 22
        y += 2
    if d.foot and footer:
        P.text(M, y + 10, d.foot, 10.5, "sans", 400, C["soft"], role="footer")
        y += 20
    H = y + M - 12
    items = [_shift(it, ox, oy) for it in S.items] + P.items
    return items, W, H, info


def _legend_layout(d, maxw):
    rows, row, x = [], [], 0
    for it in d.legend_items:
        tw = d.tw(it[2], 11, "sans") + 40
        if row and x + tw > maxw:
            rows.append(row)
            row, x = [], 0
        row.append((x, it, tw))
        x += tw + 28
    if row:
        rows.append(row)
    return rows


def _legend_item(P, d, x, y, it):
    C, T = d.T["color"], d.T
    what, val, text = it
    cy = y + 7
    if what == "edge":
        dash = {"dashed": "5 4", "dotted": "1.5 3.5"}.get(val)
        col = C["edge"]
        if val in T["states"]:
            col = T["states"][val]["stroke"]
        elif val in T["tones"]:
            col = T["tones"][val]["stroke"]
        P.path([(x, cy), (x + 22, cy)], col, 1.5 if val in T["states"] else 1.25, dash, z=2, role="legend",
               corner=0)
        P.arrow((x + 28, cy), (1, 0), col, 7, z=2.1, role="legend")
    elif what in ("state", "tone", "node"):
        stroke, fill, dash = C["stroke"], C["paper"], None
        src = T["states"].get(val) if what == "state" else (T["tones"].get(val) if what == "tone" else None)
        if what == "node":
            if val == "focal":
                src = T["states"]["accent"]
            elif val == "store":
                fill = C["sunken"]
            elif val in ("external", "ghost"):
                dash = "4 3"
        if val == "removed":
            dash = "4 3"
        if src:
            stroke, fill = src["stroke"], src["fill"]
        P.rect(Rect(x + 3, cy - 7, 22, 14), rx=3, fill=fill, stroke=stroke, sw=1.25, dash=dash, z=2, role="legend")
    elif what == "group":
        P.rect(Rect(x + 3, cy - 7, 22, 14), rx=4, fill="none" if val == "boundary" else C["zone"],
               stroke=C["line"] if val == "boundary" else C["rule"], dash="4 3" if val == "boundary" else None, z=2,
               role="legend")
    P.text(x + 36, cy + 4, text, 11, "sans", 400, C["ink2"], z=2, role="legend")


def _shift(it, dx, dy):
    it = dict(it)
    for kx, ky in (("x", "y"), ("cx", "cy")):
        if kx in it:
            it[kx] += dx
            it[ky] += dy
    if "pts" in it:
        it["pts"] = [(p[0] + dx, p[1] + dy) for p in it["pts"]]
    if it["el"] == "raw":
        it["tx"] = it.get("tx", 0) + dx
        it["ty"] = it.get("ty", 0) + dy
    if it.get("bbox") is not None:
        it["bbox"] = it["bbox"].shift(dx, dy)
    return it
