"""Components. Each one measures its own text at construction (so its size is known before placement),
exposes addressable parts, and emits drawable items into a Scene."""
import base64
import io
import math
import pathlib

from .core import CJK, El, Part, Rect, union_all, up4, wrap


class _Ptr:
    def __repr__(self):
        return "PTR"


class _Null:
    def __repr__(self):
        return "NULL"


PTR = _Ptr()    # array/list cell holding a pointer: drawn as a dot, edges start from it
NULL = _Null()  # null pointer: drawn as a slash


def _bl(cy, size):
    """Baseline that vertically centers one line of text on cy."""
    return cy + size * 0.35


def _fields(spec):
    """Normalize field rows: str | (name, value[, chips]) | dict(name, value, chips, state, key)."""
    out = []
    for f in spec or []:
        if isinstance(f, str):
            f = {"name": f}
        elif isinstance(f, (tuple, list)):
            f = dict(zip(("name", "value", "chips"), f))
        f = dict(f)
        f.setdefault("value", None)
        f.setdefault("chips", [])
        if isinstance(f["chips"], str):
            f["chips"] = [f["chips"]]
        f.setdefault("key", str(f["name"]))
        f.setdefault("state", None)
        out.append(f)
    return out


# ================================================================================================ Node

class Node(El):
    """A box / card / record / circle / diamond.

    title   main name (sans, semibold).  sub: technical detail line(s) (mono; sans when CJK).
    tag     type chip, e.g. "API", "TABLE", "L3".  icon: name from assets/icons.
    fields  record rows → [(name, value, chips)], each row addressable as node["name"].
    kind    default | focal | store | external | ghost | muted     tone: blue/teal/violet/amber/rose/green/slate
    state   explicit highlight state (focus, accent, changed, new, removed, done, dim, error)
    shape   rect | pill | circle | diamond | cylinder
    badge   small number/letter disc on the top-left corner (step numbers).
    """
    prefix = "node"

    def __init__(self, d, title, sub=None, tag=None, icon=None, fields=None, kind="default", tone=None,
                 state=None, shape="rect", w=None, h=None, min_w=None, align=None, badge=None,
                 sub_pos="auto", tag_upper=True, id=None):
        super().__init__(d, id)
        S = self.T["size"]
        self.title, self.tag, self.icon, self.variant = str(title), tag, icon, kind
        self.tone, self.state, self.shape_kind, self.badge, self.sub_pos = tone, state, shape, badge, sub_pos
        self.tag_upper = tag_upper
        subs = [] if sub is None else ([sub] if isinstance(sub, str) else list(sub))
        self.sub_font = "sans" if any(CJK.search(str(s)) for s in subs) else "mono"
        self.fields = _fields(fields)
        pad = 14
        if shape == "circle":
            tw = d.tw(self.title, S["name"], "sans", 600)
            dia = max(34, math.ceil(tw + 16))
            dia += dia % 2
            self.w = self.h = w or dia
            self.subs = subs
            self.set_sub_pos("right" if sub_pos == "auto" else sub_pos)
            self.sub_auto = sub_pos == "auto" and bool(subs)
            return
        if self.fields:
            self._layout_record(subs, w, min_w)
            return
        # compact card: centered (or left-aligned with an icon)
        self.align = align or ("left" if icon else "center")
        icon_w = 26 if icon else 0
        maxw = (w - 2 * pad - icon_w) if w else None
        tl = wrap(d, self.title, maxw, S["name"], "sans", 600) if maxw else self.title.split("\n")
        sl = []
        for s in subs:
            sl += wrap(d, s, maxw or max(260, max(d.tw(t, S["name"], "sans", 600) for t in tl)), S["mono_small"],
                       self.sub_font)
        self.tl, self.sl = tl, sl
        cw = max([d.tw(t, S["name"], "sans", 600) for t in tl] + [d.tw(s, S["mono_small"], self.sub_font)
                                                                  for s in sl])
        tagw = d.tw(self._tag(), S["tag"], "mono", 500, 0.06) + 10 if tag else 0
        extra = {"pill": 12, "diamond": 0, "cylinder": 0}.get(shape, 0)
        self.w = w or max(min_w or 88, up4(cw + icon_w + 2 * pad + extra), up4(tagw + 16))
        ch = 17 * len(tl) + (3 + 15 * len(sl) if sl else 0)
        if icon:
            ch = max(ch, 20)
        self.pad_t = 28 if tag else 10
        if shape == "cylinder":
            self.pad_t += 8
        self.content_h = ch
        self.h = h or max(40, up4(self.pad_t + ch + 10))
        if shape == "diamond":
            self.w = w or up4(cw * 1.5 + 40)
            self.h = h or max(56, up4(ch * 1.9 + 24))
            self.pad_t = 0
        if badge is not None:
            self.pad_ext = [9, 9, 0, 0]

    def _layout_record(self, subs, w, min_w):
        d, S = self.d, self.T["size"]
        pad = 12
        self.align = "left"
        self.sl = subs
        tw = d.tw(self.title, S["name"], "sans", 600) + (24 if self.icon else 0)
        tagw = d.tw(self._tag(), S["tag"], "mono", 500, 0.06) + 10 + 12 if self.tag else 0
        subw = max([d.tw(s, S["mono_small"], self.sub_font) for s in subs] or [0])
        roww = 0
        for f in self.fields:
            nw = d.tw(str(f["name"]), S["body"], "sans")
            cw = sum(d.tw(str(c).upper(), S["tag"], "mono", 500, 0.06) + 10 + 4 for c in f["chips"])
            vw = d.tw(str(f["value"]), S["mono_small"], "mono") if f["value"] not in (None, "") else 0
            roww = max(roww, nw + (8 + cw if cw else 0) + (20 + vw if vw else 0))
        self.w = w or max(min_w or 140, up4(max(tw + tagw, subw, roww) + 2 * pad))
        self.head_h = 32 + 14 * len(subs)
        self.row_h = 24
        self.h = self.head_h + self.row_h * len(self.fields) + 4
        for i, f in enumerate(self.fields):
            self.parts["." + f["key"]] = Part(self, "." + f["key"], 0, self.head_h + i * self.row_h, self.w,
                                              self.row_h, sides=["left", "right"])
        if self.badge is not None:
            self.pad_ext = [9, 9, 0, 0]

    def __getitem__(self, key):
        return self.part("." + str(key))

    field = __getitem__

    def _tag(self):
        return str(self.tag).upper() if self.tag_upper else str(self.tag)

    # -- circle captions (distance labels, depths, ranks …)
    SUB_POS = ("right", "above", "below", "left")

    def sub_lines(self, pos):
        """[(x, y, anchor, text)] for the circle caption at `pos`, relative to the circle's top-left."""
        n = len(self.subs)
        out = []
        for i, s in enumerate(self.subs):
            if pos == "right":
                out.append((self.w + 5, 9 + i * 14, "start", s))
            elif pos == "left":
                out.append((-5, 9 + i * 14, "end", s))
            elif pos == "above":
                out.append((self.w / 2, -6 - (n - 1 - i) * 14, "middle", s))
            else:
                out.append((self.w / 2, self.h + 14 + i * 14, "middle", s))
        return out

    def sub_rect(self, pos):
        Z = self.T["size"]
        rects = []
        for x, y, anchor, t in self.sub_lines(pos):
            w = self.d.tw(t, Z["mono_small"], self.sub_font, 500)
            x0 = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
            rects.append(Rect(self.x + x0, self.y + y - 9, w, 12))
        return union_all(rects)

    def set_sub_pos(self, pos):
        self.sub_pos = pos
        if not self.subs:
            return
        sw = max(self.d.tw(t, self.T["size"]["mono_small"], self.sub_font, 500) for t in self.subs)
        sh = 14 * len(self.subs)
        side = max(0, sw / 2 - self.w / 2)
        self.pad_ext = {"right": [0, 0, sw + 6, 0], "left": [sw + 6, 0, 0, 0],
                        "above": [side, sh + 4, side, 0], "below": [side, 0, side, sh + 4]}[pos]

    def shape(self):
        return self.shape_kind

    # -- look
    def _look(self, S, st):
        C = self.T["color"]
        stroke, fill, ink, dash, sw = C["stroke"], C["paper"], C["ink"], None, 1.0
        v = self.variant
        if v == "focal":
            a = self.T["states"]["accent"]
            stroke, fill, sw = a["stroke"], a["fill"], 1.5
        elif v == "store":
            fill, stroke = C["sunken"], C["stroke"]
        elif v == "external":
            dash, stroke = "4 3", C["line"]
        elif v == "ghost":
            dash, stroke, fill, ink = "4 3", C["soft"], "none", C["muted"]
        elif v == "muted":
            stroke, ink = C["rule"], C["muted"]
        ts, tf, ti = S.style(None, self.tone)
        if ts:
            stroke, fill = ts, tf
        if st:
            ss, sf, si = S.style(st)
            stroke, fill, sw = ss, sf, 1.5
            if st in ("done", "dim", "removed"):
                ink, sw = si, 1.0
        return stroke, fill, ink, dash, sw

    def emit(self, S):
        C, Z = self.T["color"], self.T["size"]
        r = self.rect
        sig = (self.title, tuple(self.sl if hasattr(self, "sl") else self.subs), self.tag, self.variant, self.tone,
               round(r.x), round(r.y), round(r.w), round(r.h))
        rx = {"pill": r.h / 2, "circle": r.w / 2}.get(self.shape_kind, self.T["look"]["radius"])
        st = S.unit(self.id, sig, r, shape=self.shape_kind, rx=rx, text=self.title, explicit=self.state)
        stroke, fill, ink, dash, sw = self._look(S, st)
        o = self.id
        sk = self.shape_kind
        if sk == "circle":
            S.circle(r.cx, r.cy, r.w / 2, fill=fill, stroke=stroke, sw=sw, role="node", owner=o, dash=dash)
            S.text(r.cx, _bl(r.cy, Z["name"]), self.title, Z["name"], "sans", 600, ink, "middle", owner=o)
            if self.subs:
                sub_ink = S.style(st)[2] if st in ("changed", "new", "removed") else C["muted"]
                for x, y, anchor, t in self.sub_lines(self.sub_pos):
                    S.text(r.x + x, r.y + y, t, Z["mono_small"], self.sub_font, 500, sub_ink, anchor, owner=o)
            return
        # body
        if sk == "diamond":
            pts = [(r.cx, r.y0), (r.x1, r.cy), (r.cx, r.y1), (r.x0, r.cy)]
            S.path(pts, stroke, sw, dash, z=4, role="node", owner=o, corner=3, fill=fill, closed=True)
        elif sk == "cylinder":
            e = 6
            dd = (f"M{r.x0},{r.y0 + e} A{r.w / 2},{e} 0 0 1 {r.x1},{r.y0 + e} L{r.x1},{r.y1 - e} "
                  f"A{r.w / 2},{e} 0 0 1 {r.x0},{r.y1 - e} Z")
            S.raw(dd, fill=fill, stroke=stroke, sw=sw, z=4, role="node", owner=o, bbox=r, dash=dash)
            S.raw(f"M{r.x0},{r.y0 + e} A{r.w / 2},{e} 0 0 0 {r.x1},{r.y0 + e}", stroke=stroke, sw=sw, z=4.1,
                  role="deco", owner=o, bbox=Rect(r.x, r.y, r.w, 2 * e))
        else:
            S.rect(r, rx=rx, fill=fill, stroke=stroke, sw=sw, dash=dash, role="node", owner=o)
        tag_ink = S.style(None, self.tone)[2] or C["muted"]
        if st and st not in ("done", "dim"):
            tag_ink = S.style(st)[2]
        if self.fields:
            self._emit_record(S, r, st, stroke, fill, ink, tag_ink)
        else:
            if self.tag:
                S.chip(r.x + 8, r.y + 8, self.tag, tag_ink, owner=o, upper=self.tag_upper)
            icon_w = 26 if self.icon else 0
            top = r.y + (self.pad_t if sk != "diamond" else 0)
            avail = r.h - (self.pad_t + 10 if sk != "diamond" else 0)
            y0 = top + (avail - self.content_h) / 2
            if self.icon:
                S.icon(self.icon, r.x + 14, y0 + (self.content_h - 18) / 2, 18, ink if ink != C["ink"] else C["ink2"],
                       owner=o)
            if self.align == "left":
                tx, anchor = r.x + 14 + icon_w, "start"
            else:
                tx, anchor = r.cx, "middle"
            y = y0 + 12.5
            for t in self.tl:
                S.text(tx, y, t, Z["name"], "sans", 600, ink, anchor, owner=o)
                y += 17
            y += 3 - 17 + 15 + 0.5
            sub_ink = C["muted"] if ink == C["ink"] else ink
            for s in self.sl:
                S.text(tx, y, s, Z["mono_small"], self.sub_font, 400, sub_ink, anchor, owner=o)
                y += 15
        if self.badge is not None:
            bc = S.style(st)[0] if st and st not in ("done", "dim") else (S.style(None, self.tone)[0] or C["ink"])
            S.circle(r.x0 + 1, r.y0 + 1, 9, fill=bc, stroke=C["paper"], sw=1.5, z=5.5, role="badge", owner=o)
            S.text(r.x0 + 1, _bl(r.y0 + 1, 10), str(self.badge), 10, "mono", 600, C["paper"], "middle", z=5.6,
                   role="badge-text", owner=o)

    def _emit_record(self, S, r, st, stroke, fill, ink, tag_ink):
        C, Z, o = self.T["color"], self.T["size"], self.id
        head = Rect(r.x, r.y, r.w, self.head_h)
        tf = S.style(None, self.tone)[1]
        hf = (S.style(st)[1] if st else None) or tf or C["sunken"]
        rx = self.T["look"]["radius"]
        hd = (f"M{r.x0},{r.y0 + self.head_h} L{r.x0},{r.y0 + rx} Q{r.x0},{r.y0} {r.x0 + rx},{r.y0} "
              f"L{r.x1 - rx},{r.y0} Q{r.x1},{r.y0} {r.x1},{r.y0 + rx} L{r.x1},{r.y0 + self.head_h} Z")
        S.raw(hd, fill=hf, z=4.05, role="deco", owner=o, bbox=head)
        S.path([(r.x0, head.y1), (r.x1, head.y1)], stroke, 1.0, z=4.1, role="rule", owner=o, cap="butt")
        x = r.x + 12
        if self.icon:
            S.icon(self.icon, x, r.y + 7, 18, C["ink2"], owner=o)
            x += 24
        S.text(x, r.y + 21, self.title, Z["name"], "sans", 600, ink, owner=o)
        for i, s in enumerate(self.sl):
            S.text(r.x + 12, r.y + 21 + 15 + i * 14, s, Z["mono_small"], self.sub_font, 400, C["muted"], owner=o)
        if self.tag:
            S.chip(r.x1 - 10, r.y + 9, self.tag, tag_ink, owner=o, anchor="end", upper=self.tag_upper)
        for i, f in enumerate(self.fields):
            pr = self.parts["." + f["key"]].rect
            fst = S.unit(f"{o}.{f['key']}", (f["name"], f["value"], tuple(f["chips"])), pr,
                         text=f"{f['name']} {f['value'] or ''}".strip(), explicit=f["state"])
            fink, vink = ink, C["muted"]
            if fst:
                ss, sf, si = S.style(fst)
                S.rect(pr.inflate(-2, -1.5), rx=3, fill=sf, stroke=ss, sw=1.0, z=4.2, role="row", owner=o)
                if fst in ("done", "dim", "removed"):
                    fink = si
                vink = si
            if i:
                S.path([(r.x0 + 1, pr.y0), (r.x1 - 1, pr.y0)], C["rule"], 1.0, z=4.1, role="rule", owner=o,
                       cap="butt")
            by = _bl(pr.cy, Z["body"])
            S.text(r.x + 12, by, f["name"], Z["body"], "sans", 400, fink, owner=o)
            cx = r.x + 12 + self.d.tw(str(f["name"]), Z["body"], "sans") + 8
            for c in f["chips"]:
                cr = S.chip(cx, pr.cy - 7, c, C["muted"], owner=o)
                cx = cr.x1 + 4
            if f["value"] not in (None, ""):
                S.text(r.x1 - 12, _bl(pr.cy, Z["mono_small"]), f["value"], Z["mono_small"], "mono", 400, vink,
                       "end", owner=o)


# ================================================================================================ Array

class Array(El):
    """A row (or column) of cells: arrays, buffers, stacks, hash buckets, B-tree keys, list nodes.

    values  cell contents; PTR draws a pointer dot (edges start there), NULL a slash, None an empty cell.
    index   True → start.., a list → custom labels (addresses), False → none.
    orient  "h" (default) or "v".   states {i: state}.   title: name drawn left (h) / above (v).
    gap     > 0 separates the cells (queue items, memory blocks).   widths: per-cell widths (list nodes).
    """
    prefix = "arr"

    def __init__(self, d, values, index=True, orient="h", states=None, title=None, gap=0, start=0, font="mono",
                 cell_w=None, cell_h=None, widths=None, labels=None, rounded=4, id=None, tone=None):
        super().__init__(d, id)
        Z = self.T["size"]
        self.values = list(values)
        n = len(self.values)
        self.orient, self.gap, self.font, self.title, self.tone = orient, gap, font, title, tone
        self.states = dict(states or {})
        if index is True:
            self.index = [str(start + i) for i in range(n)]
        elif index:
            self.index = [str(v) for v in index]
        else:
            self.index = None
        self.labels = [("" if v is None else str(v)) for v in labels] if labels else None
        self.rounded = rounded
        self.size = 12.5
        tws = [self._tw(v) for v in self.values]
        cw = cell_w or max(34, up4(max(tws + [0]) + 18))
        self.widths = list(widths) if widths else [cw] * n
        self.ch = cell_h or (32 if orient == "h" else 28)
        self.pointers, self.spans = [], []
        # cell offsets
        self.offs = []
        pos = 0
        for i in range(n):
            self.offs.append(pos)
            pos += (self.widths[i] if orient == "h" else self.ch) + gap
        if orient == "h":
            self.w, self.h = pos - gap, self.ch
        else:
            self.w, self.h = max(self.widths), pos - gap
        # where edges attach: just outside the index / label text instead of through it
        if orient == "h":
            below = (14 if self.index else 0) + (13 if self.labels else 0)
            offset = {"bottom": below + 3} if below else {}
        else:
            offset = {}
            if self.index:
                offset["left"] = max(d.tw(s, Z["index"], "mono") for s in self.index) + 11
            if self.labels:
                offset["right"] = max(d.tw(s, Z["index"], "mono") for s in self.labels) + 11
        for i in range(n):
            if orient == "h":
                sides = ["top", "bottom"] + (["left"] if i == 0 or gap else []) + (["right"] if i == n - 1 or gap
                                                                                   else [])
                rect = (self.offs[i], 0, self.widths[i], self.ch)
            else:
                sides = ["left", "right"] + (["top"] if i == 0 or gap else []) + (["bottom"] if i == n - 1 or gap
                                                                                  else [])
                rect = (0, self.offs[i], self.w, self.ch)
            pen = {k: 40 for k in offset}
            self.parts[f"[{i}]"] = Part(self, f"[{i}]", *rect, sides=sides, ptr=self.values[i] is PTR, penalty=pen,
                                        offset=offset)
        if orient == "h":
            for i in range(n + 1):
                x = self.offs[i] if i < n else self.w
                self.parts[f"<{i}>"] = Part(self, f"<{i}>", x - 0.5, 0, 1, self.ch, sides=["bottom", "top"])
        self._ext()

    def _tw(self, v):
        if v is None or v is PTR or v is NULL:
            return 0
        return self.d.tw(str(v), self.size, self.font, 500)

    def __getitem__(self, i):
        return self.part(f"[{i}]")

    cell = __getitem__

    def gap_part(self, i):
        """Point between cell i-1 and i (0..n) — where a B-tree child pointer leaves."""
        return self.part(f"<{i}>")

    @property
    def next(self):
        """The last pointer cell (list node's next)."""
        for i in range(len(self.values) - 1, -1, -1):
            if self.values[i] is PTR or self.values[i] is NULL:
                return self[i]
        raise KeyError("no pointer cell")

    @property
    def prev(self):
        for i, v in enumerate(self.values):
            if v is PTR or v is NULL:
                return self[i]
        raise KeyError("no pointer cell")

    def pointer(self, i, label, side=None, state=None, at="cell"):
        """A named marker (i, lo, head, top …) with an arrow pointing at cell i — or, with at="gap", at the
        boundary *before* cell i (0..n): byte offsets, buffer pointers like head/data/tail, ring-buffer ends."""
        side = side or ("above" if self.orient == "h" else "right")
        self.pointers.append({"i": i, "label": str(label), "side": side, "state": state, "gap": at == "gap"})
        self._ext()
        return self

    def span(self, i, j, label="", side="below", state=None, tone=None):
        """A bracket over cells i..j with a label (window, partition, sorted part …)."""
        self.spans.append({"i": i, "j": j, "label": str(label), "side": side, "state": state, "tone": tone})
        self._ext()
        return self

    # -- layout of decorations (relative to the array's top-left)
    def _deco(self):
        """Compute pointer and span placement; returns (pointers, spans, pads)."""
        d, Z = self.d, self.T["size"]
        h = self.orient == "h"
        n = len(self.values)
        below0 = self.h + (14 if self.index else 0) + (13 if self.labels else 0)
        left0 = 0
        if not h and self.index:
            left0 = max(d.tw(s, Z["index"], "mono") for s in self.index) + 8
        # pointers on the same cell and side share one arrow: "i, j"
        merged = {}
        for p in self.pointers:
            m = merged.setdefault((p["i"], p["side"], p["gap"]),
                                  {"i": p["i"], "side": p["side"], "gap": p["gap"], "parts": []})
            m["parts"].append((p["label"], p["state"]))
        for m in merged.values():
            m["label"] = ", ".join(lbl for lbl, _ in m["parts"])
        placed_ptrs = []
        for p in sorted(merged.values(), key=lambda p: (p["i"], p["gap"] is False)):
            if not (0 <= p["i"] <= n if p["gap"] else 0 <= p["i"] < n):
                continue
            lw = d.tw(p["label"], Z["label"], "mono", 600)
            if p["gap"]:
                c0 = (self.offs[p["i"]] if p["i"] < n else (self.w if h else self.h)) - (self.gap / 2 if 0 < p["i"] < n
                                                                                       else 0)
            else:
                c0 = self.offs[p["i"]] + (self.widths[p["i"]] / 2 if h else self.ch / 2)
            span = (c0 - lw / 2 - 3, c0 + lw / 2 + 3) if h else (c0 - 8, c0 + 8)
            lvl = 0
            while any(q["side"] == p["side"] and q["lvl"] == lvl and q["span"][0] < span[1] and span[0] < q["span"][1]
                      for q in placed_ptrs):
                lvl += 1
            placed_ptrs.append(dict(p, lvl=lvl, span=span, lw=lw, c=c0))
        placed_spans = []
        for s in self.spans:
            a, b = self.offs[s["i"]], self.offs[s["j"]] + (self.widths[s["j"]] if h else self.ch)
            lvl = 0
            while any(q["side"] == s["side"] and q["lvl"] == lvl and q["a"] < b + 8 and a < q["b"] + 8
                      for q in placed_spans):
                lvl += 1
            placed_spans.append(dict(s, a=a, b=b, lvl=lvl))
        pads = [0, 0, 0, 0]
        if self.title:
            tw = d.tw(self.title, Z["body"], "sans", 600)
            if h:
                pads[0] = tw + 12
            else:
                pads[1] = 20
        if h:
            if self.index or self.labels:
                pads[3] = below0 - self.h + 2
            else:
                pads[3] = 0
        else:
            pads[0] = max(pads[0], left0)
        # vertical arrays stack their right-hand decorations: labels | spans | pointers
        right0 = (max(d.tw(x, Z["index"], "mono") for x in self.labels) + 14) if (not h and self.labels) else 0
        span_x = right0
        if not h:
            pads[2] = right0
            for sp in placed_spans:
                sp["x_off"] = right0 + 8 + sp["lvl"] * 26
                lw = d.tw(sp["label"], Z["small"], "sans", 500) if sp["label"] else 0
                span_x = max(span_x, sp["x_off"] + 6 + lw + 8)
            pads[2] = max(pads[2], span_x)
        for p in placed_ptrs:
            ext = 14 + p["lvl"] * 16 + 14
            if h:
                k = 1 if p["side"] == "above" else 3
                base = 0 if p["side"] == "above" else below0 - self.h
                pads[k] = max(pads[k], base + ext)
                if p["span"][0] < 0:
                    pads[0] = max(pads[0], -p["span"][0])
                if p["span"][1] > self.w:
                    pads[2] = max(pads[2], p["span"][1] - self.w)
            else:
                k = 2 if p["side"] == "right" else 0
                base = span_x if p["side"] == "right" else left0
                p["base"] = base
                pads[k] = max(pads[k], base + 3 + 18 + 4 + p["lw"] + 2)
        for s in placed_spans if h else []:
            k = 3 if s["side"] == "below" else 1
            base = (below0 - self.h) if s["side"] == "below" else (pads[1] if s["side"] == "above" else 0)
            if s["side"] == "above":
                base = max([14 + p["lvl"] * 16 + 14 for p in placed_ptrs if p["side"] == "above"] + [0])
            s["base"] = base
            pads[k] = max(pads[k], base + 8 + s["lvl"] * 26 + 20)
        if self.title and not h:
            pads[1] = max(pads[1], 20)
        return placed_ptrs, placed_spans, pads, below0, left0

    def _ext(self):
        self.pad_ext = self._deco()[2]

    def obstacles(self):
        return [self.ext]

    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        r = self.rect
        h = self.orient == "h"
        ptrs, spans, _, below0, left0 = self._deco()
        n = len(self.values)
        rx = self.rounded
        tone_s, tone_f, tone_i = S.style(None, self.tone)
        base_stroke = tone_s or C["stroke"]
        cells = []
        for i, v in enumerate(self.values):
            pr = self.parts[f"[{i}]"].rect
            txt = "" if v is None else ("•" if v is PTR else ("∅" if v is NULL else str(v)))
            st = S.unit(f"{o}[{i}]", (txt,), pr, rx=2, text=txt, explicit=self.states.get(i))
            cells.append((i, v, pr, st))
        if not self.gap:
            S.rect(r, rx=rx, fill=tone_f or C["paper"], stroke=None, role="node", owner=o)
        for i, v, pr, st in cells:
            if self.gap:
                ss, sf, _ = S.style(st) if st else (None, None, None)
                S.rect(pr, rx=rx, fill=sf or tone_f or C["paper"], stroke=ss or base_stroke, sw=1.5 if st else 1,
                       role="node", owner=o, dash="3 3" if st == "removed" else None)
            elif st:
                ss, sf, _ = S.style(st)
                S.rect(pr.inflate(-1.5), rx=2.5, fill=sf, stroke=ss, sw=1.25, z=4.3, role="cell", owner=o)
        if not self.gap:
            for i in range(1, n):
                if h:
                    x = r.x + self.offs[i]
                    S.path([(x, r.y0), (x, r.y1)], base_stroke, 1, z=4.2, role="rule", owner=o, cap="butt")
                else:
                    y = r.y + self.offs[i]
                    S.path([(r.x0, y), (r.x1, y)], base_stroke, 1, z=4.2, role="rule", owner=o, cap="butt")
            S.rect(r, rx=rx, fill="none", stroke=base_stroke, sw=1, z=4.4, role="frame", owner=o)
        for i, v, pr, st in cells:
            ink = (S.style(st)[2] if st else None) or tone_i or C["ink"]
            if v is PTR:
                S.circle(pr.cx, pr.cy, 3.2, fill=S.style(st)[0] if st else C["ink2"], z=5.5, role="dot", owner=o)
            elif v is NULL:
                S.path([(pr.x0 + 5, pr.y1 - 5), (pr.x1 - 5, pr.y0 + 5)], C["soft"], 1.2, z=4.5, role="slash",
                       owner=o)
            elif v is not None and str(v) != "":
                S.text(pr.cx, _bl(pr.cy, self.size), str(v), self.size, self.font, 500, ink, "middle", owner=o)
        # index + labels
        if self.index:
            for i, s in enumerate(self.index):
                pr = self.parts[f"[{i}]"].rect
                if h:
                    S.text(pr.cx, r.y1 + 13, s, Z["index"], "mono", 400, C["soft"], "middle", owner=o)
                else:
                    S.text(r.x0 - 8, _bl(pr.cy, Z["index"]), s, Z["index"], "mono", 400, C["soft"], "end", owner=o)
        if self.labels:
            for i, s in enumerate(self.labels):
                pr = self.parts[f"[{i}]"].rect
                if s and h:
                    S.text(pr.cx, r.y1 + (14 if self.index else 0) + 12, s, Z["index"], "mono", 400, C["muted"],
                           "middle", owner=o)
                elif s:
                    S.text(r.x1 + 8, _bl(pr.cy, Z["index"]), s, Z["index"], "mono", 400, C["muted"], owner=o)
        if self.title:
            if h:
                S.text(r.x0 - 12, _bl(r.cy, Z["body"]), self.title, Z["body"], "sans", 600, C["ink2"], "end",
                       owner=o)
            else:
                S.text(r.x0, r.y0 - 8, self.title, Z["body"], "sans", 600, C["ink2"], owner=o)
        # pointers
        rank = ["error", "accent", "new", "changed", "removed", "focus", "done", "dim"]
        for p in ptrs:
            sts = [S.unit(f"{o}^{lbl}", (p["i"], p["side"], p["gap"]), None, text=lbl, explicit=pst, shape="none")
                   for lbl, pst in p["parts"]]
            sts = [x for x in sts if x]
            st = min(sts, key=lambda x: rank.index(x) if x in rank else 99) if sts else None
            col = S.style(st or "focus")[0]
            ink = S.style(st or "focus")[2]
            L = 12 + p["lvl"] * 16
            if h:
                cx = r.x + p["c"]
                if p["side"] == "above":
                    tip, tail = (cx, r.y0 - 3), (cx, r.y0 - 3 - L)
                    S.text(cx, tail[1] - 4, p["label"], Z["label"], "mono", 600, ink, "middle", z=6, role="ptr",
                           owner=o)
                    S.path([tail, (cx, tip[1] - 5)], col, 1.25, z=5.8, role="ptr-line", owner=o)
                    S.arrow(tip, (0, 1), col, 6, z=5.9, owner=o)
                else:
                    y0 = r.y0 + below0 + 1
                    tip, tail = (cx, y0), (cx, y0 + L)
                    S.text(cx, tail[1] + 12, p["label"], Z["label"], "mono", 600, ink, "middle", z=6, role="ptr",
                           owner=o)
                    S.path([tail, (cx, tip[1] + 5)], col, 1.25, z=5.8, role="ptr-line", owner=o)
                    S.arrow(tip, (0, -1), col, 6, z=5.9, owner=o)
            else:
                cy = r.y + p["c"]
                if p["side"] == "right":
                    tip, tail = (r.x1 + p["base"] + 3, cy), (r.x1 + p["base"] + 3 + 18, cy)
                    S.text(tail[0] + 4, _bl(cy, Z["label"]), p["label"], Z["label"], "mono", 600, ink, z=6,
                           role="ptr", owner=o)
                    S.path([tail, (tip[0] + 5, cy)], col, 1.25, z=5.8, role="ptr-line", owner=o)
                    S.arrow(tip, (-1, 0), col, 6, z=5.9, owner=o)
                else:
                    x0 = r.x0 - left0 - 3
                    tip, tail = (x0, cy), (x0 - 18, cy)
                    S.text(tail[0] - 4, _bl(cy, Z["label"]), p["label"], Z["label"], "mono", 600, ink, "end", z=6,
                           role="ptr", owner=o)
                    S.path([tail, (tip[0] - 5, cy)], col, 1.25, z=5.8, role="ptr-line", owner=o)
                    S.arrow(tip, (1, 0), col, 6, z=5.9, owner=o)
        # spans
        for s in spans:
            st = S.unit(f"{o}~{s['label'] or s['i']}", (s["i"], s["j"], s["side"]), None, text=s["label"],
                        explicit=s["state"], shape="none", diff=False)
            col, _, ink = S.style(st, s["tone"])
            col, ink = col or C["muted"], ink or C["ink2"]
            a, b = s["a"] + 3, s["b"] - 3
            if h:
                if s["side"] == "below":
                    y = r.y0 + self.h + s["base"] + 8 + s["lvl"] * 26
                    pts = [(r.x + a, y - 5), (r.x + a, y), (r.x + b, y), (r.x + b, y - 5)]
                    ty = y + 14
                else:
                    y = r.y0 - s["base"] - 8 - s["lvl"] * 26
                    pts = [(r.x + a, y + 5), (r.x + a, y), (r.x + b, y), (r.x + b, y + 5)]
                    ty = y - 6
                S.path(pts, col, 1.25, z=5, role="span", owner=o, corner=2)
                if s["label"]:
                    S.text(r.x + (a + b) / 2, ty, s["label"], Z["small"], "sans", 500, ink, "middle", owner=o)
            else:
                x = r.x1 + s["x_off"]
                pts = [(x - 5, r.y + a), (x, r.y + a), (x, r.y + b), (x - 5, r.y + b)]
                S.path(pts, col, 1.25, z=5, role="span", owner=o, corner=2)
                if s["label"]:
                    S.text(x + 6, _bl(r.y + (a + b) / 2, Z["small"]), s["label"], Z["small"], "sans", 500, ink,
                           owner=o)


# ================================================================================================ Table

class Table(El):
    """A real table: header row + body rows. Cells t[r, c], rows t.row(r) are addressable.

    states {r: state} for rows, {(r, c): state} for cells.  mono: column indexes drawn in mono (default: columns
    whose values look like numbers/addresses).  grid: vertical rules too (DP tables, matrices).
    row_header: first column bold (matrix row labels)."""
    prefix = "table"

    def __init__(self, d, columns, rows, title=None, states=None, mono=None, align=None, grid=False,
                 row_header=False, id=None, tone=None, min_col_w=None):
        super().__init__(d, id)
        Z = self.T["size"]
        self.columns = [str(c) for c in columns] if columns else None
        self.rows = [["" if v is None else str(v) for v in row] for row in rows]
        ncol = max([len(self.columns or [])] + [len(r) for r in self.rows])
        for r in self.rows:
            r += [""] * (ncol - len(r))
        self.ncol, self.title, self.grid, self.row_header, self.tone = ncol, title, grid, row_header, tone
        self.states = dict(states or {})
        import re as _re
        tech = _re.compile(r"^[\s\d.,:/xX#%+\-–→←*()a-fA-F_]*$")
        if mono is None:
            mono = [c for c in range(ncol) if all(tech.match(r[c] or "0") and r[c] != "" or r[c] == ""
                                                  for r in self.rows) and any(r[c] for r in self.rows)]
        self.mono = set(mono)
        self.align = align or ["left"] * ncol
        self.pad = 10
        cw = []
        for c in range(ncol):
            f = "mono" if c in self.mono else "sans"
            sz = Z["mono"] if f == "mono" else Z["body"]
            wid = [d.tw(r[c], sz, f, 600 if (row_header and c == 0) else 400) for r in self.rows]
            if self.columns:
                wid.append(d.tw(self.columns[c] if c < len(self.columns) else "", Z["small"], "sans", 600))
            cw.append(max(min_col_w or 28, up4(max(wid + [0]) + 2 * self.pad)))
        self.cw = cw
        self.head_h = 26 if self.columns else 0
        self.row_h = 32 if grid else 24   # grids (DP tables, matrices) get near-square cells
        self.w = sum(cw)
        self.h = self.head_h + self.row_h * len(self.rows)
        self.pad_ext = [0, 20 if title else 0, 0, 0]
        x = 0
        self.cx0 = []
        for c in range(ncol):
            self.cx0.append(x)
            x += cw[c]
        for ri in range(len(self.rows)):
            y = self.head_h + ri * self.row_h
            self.parts[f"[{ri}]"] = Part(self, f"[{ri}]", 0, y, self.w, self.row_h, sides=["left", "right"])
            for c in range(ncol):
                self.parts[f"[{ri},{c}]"] = Part(self, f"[{ri},{c}]", self.cx0[c], y, cw[c], self.row_h)
        for c in range(ncol):
            self.parts[f"[h,{c}]"] = Part(self, f"[h,{c}]", self.cx0[c], 0, cw[c], self.head_h or self.row_h,
                                          sides=["top"])

    def __getitem__(self, key):
        if isinstance(key, tuple):
            return self.part(f"[{key[0]},{key[1]}]")
        return self.part(f"[{key}]")

    def row(self, r):
        return self.part(f"[{r}]")

    def col(self, c):
        """Header cell of column c (attach from above)."""
        return self.part(f"[h,{c}]")

    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        r = self.rect
        rx = self.T["look"]["radius"]
        ts, tf, ti = S.style(None, self.tone)
        stroke = ts or C["stroke"]
        S.rect(r, rx=rx, fill=C["paper"], stroke=None, role="node", owner=o)
        if self.columns:
            hd = (f"M{r.x0},{r.y0 + self.head_h} L{r.x0},{r.y0 + rx} Q{r.x0},{r.y0} {r.x0 + rx},{r.y0} "
                  f"L{r.x1 - rx},{r.y0} Q{r.x1},{r.y0} {r.x1},{r.y0 + rx} L{r.x1},{r.y0 + self.head_h} Z")
            S.raw(hd, fill=tf or C["sunken"], z=4.05, role="deco", owner=o, bbox=Rect(r.x, r.y, r.w, self.head_h))
            for c, name in enumerate(self.columns):
                x = self._tx(r, c)
                S.text(x, _bl(r.y + self.head_h / 2, Z["small"]), name, Z["small"], "sans", 600, ti or C["ink2"],
                       self._anchor(c), owner=o)
        if self.title:
            S.text(r.x0, r.y0 - 8, self.title, Z["body"], "sans", 600, C["ink2"], owner=o)
        for ri, row in enumerate(self.rows):
            y = r.y + self.head_h + ri * self.row_h
            rst = S.unit(f"{o}[{ri}]", tuple(row), self.parts[f"[{ri}]"].rect, text=" ".join(row),
                         explicit=self.states.get(ri), diff=False)
            if rst:
                ss, sf, _ = S.style(rst)
                S.rect(Rect(r.x + 1.5, y + 1.5, r.w - 3, self.row_h - 3), rx=3, fill=sf, stroke=ss, sw=1.0, z=4.2,
                       role="row", owner=o)
            if ri or self.columns:
                S.path([(r.x0 + 0.5, y), (r.x1 - 0.5, y)], stroke if (ri == 0 and self.columns) else C["rule"], 1,
                       z=4.15, role="rule", owner=o, cap="butt")
            for c, val in enumerate(row):
                pr = self.parts[f"[{ri},{c}]"].rect
                cst = S.unit(f"{o}[{ri},{c}]", (val,), pr, text=val, explicit=self.states.get((ri, c)))
                if cst and not rst:
                    ss, sf, _ = S.style(cst)
                    S.rect(pr.inflate(-2), rx=3, fill=sf, stroke=ss, sw=1.0, z=4.25, role="cell", owner=o)
                st = cst or rst
                ink = (S.style(st)[2] if st else None) or C["ink"]
                f = "mono" if c in self.mono else "sans"
                sz = Z["mono"] if f == "mono" else Z["body"]
                wgt = 600 if (self.row_header and c == 0) else 400
                if val:
                    S.text(self._tx(r, c), _bl(pr.cy, sz), val, sz, f, wgt, ink, self._anchor(c), owner=o)
        if self.grid:
            for c in range(1, self.ncol):
                x = r.x + self.cx0[c]
                S.path([(x, r.y0 + 0.5), (x, r.y1 - 0.5)], C["rule"], 1, z=4.15, role="rule", owner=o, cap="butt")
        S.rect(r, rx=rx, fill="none", stroke=stroke, sw=1, z=4.4, role="frame", owner=o)

    def _anchor(self, c):
        return {"left": "start", "right": "end", "center": "middle"}[self.align[c]]

    def _tx(self, r, c):
        a = self.align[c]
        x0 = r.x + self.cx0[c]
        return x0 + self.pad if a == "left" else (x0 + self.cw[c] - self.pad if a == "right" else x0 + self.cw[c] / 2)


# ================================================================================================ Bits

class Bits(El):
    """Bit-level field layout (packet headers, register/PTE formats, instruction encodings).

    fields [(name, bits[, value])] or dicts with state/tone; rows wrap every `width` bits.
    ruler: bit numbers on top.  offsets: byte offset of each row on the left."""
    prefix = "bits"

    def __init__(self, d, fields, width=32, bit_w=None, title=None, ruler=True, offsets=True, states=None,
                 msb_first=False, id=None):
        super().__init__(d, id)
        Z = self.T["size"]
        fs = []
        for f in fields:
            if isinstance(f, (tuple, list)):
                f = dict(zip(("name", "bits", "value"), f))
            f = dict(f)
            f.setdefault("value", None)
            f.setdefault("state", (states or {}).get(f["name"]))
            f.setdefault("tone", None)
            fs.append(f)
        self.fields, self.width, self.title, self.ruler, self.offsets = fs, width, title, ruler, offsets
        self.msb_first = msb_first
        need = 10
        for f in fs:
            need = max(need, (d.tw(str(f["name"]), Z["small"], "sans", 500) + 10) / min(f["bits"], width))
        self.bit_w = bit_w or min(28, max(14, math.ceil(need / 2) * 2))
        self.has_val = any(f["value"] not in (None, "") for f in fs)
        self.row_h = 40 if self.has_val else 30
        total = sum(f["bits"] for f in fs)
        self.nrows = math.ceil(total / width)
        self.w = self.bit_w * width
        self.h = self.row_h * self.nrows
        # segments
        self.segs = []
        pos = 0
        for fi, f in enumerate(fs):
            left = f["bits"]
            first = True
            while left > 0:
                row, col = divmod(pos, width)
                n = min(left, width - col)
                self.segs.append({"f": fi, "row": row, "col": col, "n": n, "first": first})
                if first:
                    self.parts[str(f["name"])] = Part(self, str(f["name"]), col * self.bit_w, row * self.row_h,
                                                      n * self.bit_w, self.row_h)
                first = False
                pos += n
                left -= n
        offw = d.tw(str((self.nrows - 1) * width // 8), Z["index"], "mono") + 10 if offsets else 0
        self.pad_ext = [offw, (16 if ruler else 0) + (20 if title else 0), 0, 0]

    def __getitem__(self, name):
        return self.part(str(name))

    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        r = self.rect
        bw = self.bit_w
        if self.title:
            S.text(r.x0, r.y0 - (16 if self.ruler else 0) - 8, self.title, Z["body"], "sans", 600, C["ink2"], owner=o)
        if self.ruler:
            step = 1 if bw >= 16 else (4 if bw >= 8 else 8)
            for b in range(0, self.width, step):
                label = str(self.width - 1 - b) if self.msb_first else str(b)
                S.text(r.x + b * bw + bw / 2, r.y0 - 5, label, 8.5, "mono", 400, C["soft"], "middle", owner=o)
        if self.offsets:
            for row in range(self.nrows):
                S.text(r.x0 - 8, _bl(r.y + row * self.row_h + self.row_h / 2, Z["index"]),
                       str(row * self.width // 8), Z["index"], "mono", 400, C["soft"], "end", owner=o)
        S.rect(Rect(r.x, r.y, r.w, self.row_h * self.nrows), rx=3, fill=C["paper"], role="node", owner=o)
        for sg in self.segs:
            f = self.fields[sg["f"]]
            sr = Rect(r.x + sg["col"] * bw, r.y + sg["row"] * self.row_h, sg["n"] * bw, self.row_h)
            st = S.unit(f"{o}.{f['name']}#{sg['row']}", (f["name"], f["value"], f["bits"]), sr, text=str(f["name"]),
                        explicit=f["state"])
            ss, sf, si = S.style(st, f["tone"])
            S.rect(sr, rx=0, fill=sf or C["paper"], stroke=None, z=4.1, role="cell", owner=o)
            name = str(f["name"]) if sg["first"] else f"{f['name']} (cont.)"
            size = Z["small"]
            while size > 8.5 and self.d.tw(name, size, "sans", 500) > sr.w - 6:
                size -= 0.5
            cy = sr.cy - (7 if self.has_val else 0)
            S.text(sr.cx, _bl(cy, size), name, size, "sans", 500,
                   (si or C["ink"]) if sg["first"] else C["muted"], "middle", owner=o)
            if self.has_val and f["value"] not in (None, "") and sg["first"]:
                vs = Z["mono_small"]
                while vs > 8 and self.d.tw(str(f["value"]), vs, "mono") > sr.w - 6:
                    vs -= 0.5
                S.text(sr.cx, _bl(sr.cy + 9, vs), str(f["value"]), vs, "mono", 400, si or C["muted"], "middle",
                       owner=o)
            if ss:
                S.rect(sr.inflate(-1.5), rx=2, fill="none", stroke=ss, sw=1.25, z=4.6, role="cell-hi", owner=o)
        # grid: field boundaries + row lines + outer frame
        for sg in self.segs:
            x = r.x + sg["col"] * bw
            if sg["col"]:
                y0 = r.y + sg["row"] * self.row_h
                S.path([(x, y0), (x, y0 + self.row_h)], C["stroke"], 1, z=4.3, role="rule", owner=o, cap="butt")
        for row in range(1, self.nrows):
            y = r.y + row * self.row_h
            S.path([(r.x0, y), (r.x1, y)], C["stroke"], 1, z=4.3, role="rule", owner=o, cap="butt")
        # bit ticks along the top edge
        for b in range(1, self.width):
            x = r.x + b * bw
            tall = b % 8 == 0
            S.path([(x, r.y0), (x, r.y0 + (4 if tall else 2.5))], C["stroke"], 1, z=4.35, role="tick", owner=o,
                   cap="butt")
        S.rect(Rect(r.x, r.y, r.w, self.row_h * self.nrows), rx=3, fill="none", stroke=C["stroke"], z=4.4,
               role="frame", owner=o)


# ================================================================================================ Code

class Code(El):
    """Code / pseudo-code panel with line numbers; highlight {line: state} (1-based) marks the current line."""
    prefix = "code"

    def __init__(self, d, code, highlight=None, title=None, lineno=True, start=1, w=None, id=None):
        super().__init__(d, id)
        self.lines = str(code).strip("\n").expandtabs(4).split("\n")
        if isinstance(highlight, int):
            highlight = {highlight: "focus"}
        elif isinstance(highlight, (list, tuple, set)):
            highlight = {i: "focus" for i in highlight}
        self.hl = dict(highlight or {})
        self.title, self.lineno, self.start = title, lineno, start
        self.size, self.lh = 11.5, 19
        self.gut = (d.tw(str(start + len(self.lines)), 10, "mono") + 16) if lineno else 12
        lw = max(d.tw(self._nb(l), self.size, "mono") for l in self.lines)
        self.w = w or up4(self.gut + lw + 16)
        self.h = len(self.lines) * self.lh + 16
        self.pad_ext = [0, 20 if title else 0, 0, 0]
        for i in range(len(self.lines)):
            self.parts[str(start + i)] = Part(self, str(start + i), 0, 8 + i * self.lh, self.w, self.lh,
                                              sides=["left", "right"])

    @staticmethod
    def _nb(s):
        return s.replace(" ", " ")

    def line(self, n):
        return self.part(str(n))

    __getitem__ = line

    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        r = self.rect
        S.rect(r, rx=self.T["look"]["radius"], fill=C["sunken"], stroke=C["rule"], role="node", owner=o)
        if self.title:
            S.text(r.x0, r.y0 - 8, self.title, Z["body"], "sans", 600, C["ink2"], owner=o)
        for i, line in enumerate(self.lines):
            n = self.start + i
            y = r.y + 8 + i * self.lh
            st = S.unit(f"{o}:{n}", (line,), None, explicit=self.hl.get(n), diff=False, shape="none")
            ink = C["ink"]
            if st:
                ss, sf, si = S.style(st)
                S.rect(Rect(r.x + 1, y, r.w - 2, self.lh), fill=sf, z=4.1, role="row", owner=o)
                S.rect(Rect(r.x + 1, y, 3, self.lh), fill=ss, z=4.2, role="row", owner=o)
            if self.lineno:
                S.text(r.x + self.gut - 10, _bl(y + self.lh / 2, 10), str(n), 10, "mono", 400,
                       C["soft"] if not st else S.style(st)[2], "end", owner=o)
            code, comment = _split_comment(line)
            x = r.x + self.gut
            if code.strip():
                S.text(x, _bl(y + self.lh / 2, self.size), self._nb(code.rstrip()), self.size, "mono",
                       500 if st else 400, ink, owner=o)
            if comment:
                cx = x + self.d.tw(self._nb(code), self.size, "mono", 500 if st else 400)
                S.text(cx, _bl(y + self.lh / 2, self.size), self._nb(comment), self.size, "mono", 400, C["muted"],
                       owner=o)


def _split_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#" or line.startswith("//", i) or line.startswith("--", i) and (i == 0 or line[i - 1] == " "):
            return line[:i], line[i:]
    return line, ""


# ================================================================================================ Note

class Note(El):
    """Editorial callout: wrapped text in a quiet box, optionally with a dotted leader to a target."""
    prefix = "note"

    def __init__(self, d, text, target=None, w=220, title=None, state=None, tone=None, id=None):
        super().__init__(d, id)
        Z = self.T["size"]
        self.target, self.title, self.state, self.tone = target, title, state, tone
        self.lines = wrap(d, text, w - 20, Z["small"], "sans")
        tw = max(d.tw(l, Z["small"], "sans") for l in self.lines)
        if title:
            tw = max(tw, d.tw(title, Z["small"], "sans", 600))
        self.w = up4(w if len(self.lines) > 1 else min(w, tw + 20))
        self.h = up4(len(self.lines) * 16 + (17 if title else 0) + 14)

    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        r = self.rect
        ss, sf, si = S.style(self.state, self.tone)
        S.rect(r, rx=self.T["look"]["radius"], fill=sf or C["note"], stroke=ss or C["note_rule"], role="note",
               owner=o)
        y = r.y + 7 + 11.5
        if self.title:
            S.text(r.x + 10, y, self.title, Z["small"], "sans", 600, si or C["ink"], owner=o)
            y += 17
        for l in self.lines:
            S.text(r.x + 10, y, l, Z["small"], "sans", 400, C["ink2"], owner=o)
            y += 16
        if self.target is not None:
            t = self.target.rect if hasattr(self.target, "rect") else Rect(self.target[0], self.target[1], 0, 0)
            # nearest points: note side facing the target → target boundary
            nx = min(max(t.cx, r.x0), r.x1)
            ny = min(max(t.cy, r.y0), r.y1)
            tx = min(max(nx, t.x0), t.x1)
            ty = min(max(ny, t.y0), t.y1)
            dx, dy = tx - nx, ty - ny
            if abs(dx) < 1 and abs(dy) < 1:
                return
            col = ss or C["soft"]
            S.path([(nx, ny), (tx, ty)], col, 1.2, dash="1 3", z=6.5, role="leader", owner=o, corner=0)
            S.circle(tx, ty, 2.2, fill=col, z=6.6, role="leader-dot", owner=o)


# ================================================================================================ Text

class Text(El):
    """Free text (section labels, axis captions, annotations). Wraps when w is given."""
    prefix = "text"
    solid = False

    def __init__(self, d, text, size=None, font="sans", weight=400, color=None, w=None, anchor="start", id=None,
                 lh=None, state=None):
        super().__init__(d, id)
        self.size = size or self.T["size"]["body"]
        self.font, self.weight, self.color, self.anchor = font, weight, color, anchor
        if state and not color:
            self.color = self.T["states"][state]["ink"]
        self.lines = wrap(d, text, w, self.size, font, weight) if w else str(text).split("\n")
        self.lh = lh or round(self.size * 1.4)
        self.w = max(d.tw(l, self.size, font, weight) for l in self.lines)
        self.h = self.lh * (len(self.lines) - 1) + self.size * 1.0

    def emit(self, S):
        r = self.rect
        x = {"start": r.x0, "middle": r.cx, "end": r.x1}[self.anchor]
        for i, l in enumerate(self.lines):
            S.text(x, r.y + self.size * 0.78 + i * self.lh, l, self.size, self.font, self.weight,
                   self.color or self.T["color"]["ink2"], self.anchor, z=7, owner=self.id)


# ================================================================================================ Image

class Image(El):
    """Raster image (e.g. a Codex-generated concept illustration), embedded as a data URI."""
    prefix = "img"

    def __init__(self, d, path, w, h=None, rx=6, border=True, id=None, max_px=None):
        super().__init__(d, id)
        from PIL import Image as PImage
        p = pathlib.Path(path)
        im = PImage.open(p)
        iw, ih = im.size
        self.w = w
        self.h = h or round(w * ih / iw)
        target = int((max_px or 2) * w)
        if iw > target:
            im = im.resize((target, round(target * ih / iw)), PImage.LANCZOS)
        buf = io.BytesIO()
        if im.mode in ("RGBA", "LA", "P") and "A" in im.getbands():
            im.save(buf, "PNG", optimize=True)
            mime = "image/png"
        else:
            im.convert("RGB").save(buf, "JPEG", quality=86, optimize=True)
            mime = "image/jpeg"
        self.href = f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}"
        self.rx, self.border = rx, border

    def emit(self, S):
        r = self.rect
        S.image(self.href, r, rx=self.rx, owner=self.id)
        if self.border:
            S.rect(r, rx=self.rx, fill="none", stroke=self.T["color"]["rule"], z=4.5, role="frame", owner=self.id)


# ================================================================================================ Group

class Group(El):
    """Container drawn behind its members: zone (tinted), boundary (dashed: trust zone, host, VPC) or box.
    Create it after its members are placed; it wraps their current extents."""
    prefix = "group"
    solid = False

    def __init__(self, d, members, label=None, kind="zone", tone=None, pad=16, id=None, state=None, upper=True):
        super().__init__(d, id)
        label = None if label is None else (str(label).upper() if upper else str(label))
        self.members, self.label, self.variant, self.tone, self.state = list(members), label, kind, tone, state
        box = union_all(m.ext for m in self.members)
        if box is None:
            raise ValueError("group needs placed members")
        top = pad + (18 if label else 0)
        self.x, self.y = box.x - pad, box.y - top
        self.w, self.h = box.w + 2 * pad, box.h + top + pad
        Z = self.T["size"]
        self.label_w = d.tw(label, Z["tag"] + 0.5, "mono", 500, 0.1) if label else 0

    def label_rect(self):
        return Rect(self.x + 10, self.y + 6, self.label_w + 4, 14) if self.label else None

    def obstacles(self):
        lr = self.label_rect()
        return [lr] if lr else []

    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        r = self.rect
        st = S.unit(self.id, (self.label, len(self.members)), None, explicit=self.state, diff=False, shape="none")
        ss, sf, si = S.style(st, self.tone)
        if self.variant == "boundary":
            S.rect(r, rx=10, fill="none", stroke=ss or C["line"], sw=1.1, dash="5 4", z=1, role="group", owner=o)
        elif self.variant == "box":
            S.rect(r, rx=10, fill=C["paper"], stroke=ss or C["stroke"], z=1, role="group", owner=o)
        else:
            S.rect(r, rx=10, fill=sf or C["zone"], stroke=ss or C["rule"], z=1, role="group", owner=o,
                   opacity=None)
        if self.label:
            S.text(r.x + 12, r.y + 17, self.label, Z["tag"] + 0.5, "mono", 500, si or C["muted"],
                   ls=0.1, z=1.5, role="group-label", owner=o)


# ================================================================================================ Sequence

class Seq(El):
    """Sequence diagram: actors across the top, lifelines, messages top-to-bottom.

    actors   [key | (key, title) | (key, title, sub) | dict(key, title, sub, tag, tone, icon)]
    messages (a, b, label) | (a, b, label, opts) | dict(src, dst, label, dashed, state) |
             {"note": text, "over": key or [k1, k2]} | {"divider": text} | {"gap": px}
    numbered adds a step disc to every message label."""
    prefix = "seq"

    def __init__(self, d, actors, messages, numbered=False, row_h=34, min_gap=48, id=None):
        super().__init__(d, id)
        Z = self.T["size"]
        self.actors = []
        for a in actors:
            if isinstance(a, str):
                a = {"key": a}
            elif isinstance(a, (tuple, list)):
                a = dict(zip(("key", "title", "sub"), a))
            a = dict(a)
            a.setdefault("title", a["key"])
            self.actors.append(a)
        keys = [a["key"] for a in self.actors]
        self.col = {k: i for i, k in enumerate(keys)}
        self.nodes = []
        for a in self.actors:
            n = Node(d, a["title"], sub=a.get("sub"), tag=a.get("tag"), tone=a.get("tone"), icon=a.get("icon"),
                     kind=a.get("kind", "default"), id=f"{self.id}.{a['key']}", min_w=96)
            d._unregister(n)
            self.nodes.append(n)
        self.rows = []
        for m in messages:
            if isinstance(m, dict) and ("note" in m or "divider" in m or "gap" in m):
                self.rows.append(dict(m))
                continue
            if isinstance(m, (tuple, list)):
                mm = dict(zip(("src", "dst", "label"), m[:3]))
                if len(m) > 3:
                    mm.update(m[3])
                m = mm
            m = dict(m)
            m.setdefault("label", "")
            self.rows.append(m)
        self.numbered, self.row_h = numbered, row_h
        n = len(self.actors)
        # column gaps from actor widths and message labels
        gaps = [max(min_gap, (self.nodes[i].w + self.nodes[i + 1].w) / 2 + 32) for i in range(n - 1)]
        for m in self.rows:
            if "src" not in m:
                continue
            i, j = sorted((self.col[m["src"]], self.col[m["dst"]]))
            lw = d.tw(str(m["label"]), Z["label"], "sans", 500) + (22 if numbered else 0) + 28
            if i == j:
                j = min(i + 1, n - 1)
                lw += 30
                if i == j:
                    continue
            need = lw - sum(gaps[i:j])
            if need > 0:
                for k in range(i, j):
                    gaps[k] += need / (j - i)
        self.xs = [self.nodes[0].w / 2]
        for g in gaps:
            self.xs.append(self.xs[-1] + g)
        self.head_h = max(nd.h for nd in self.nodes)
        # rows
        y = self.head_h + 24
        self.ys = []
        for m in self.rows:
            if "gap" in m:
                self.ys.append(y)
                y += m["gap"]
            elif "divider" in m:
                self.ys.append(y + 6)
                y += 30
            elif "note" in m:
                over = m["over"] if isinstance(m["over"], (list, tuple)) else [m["over"]]
                xs = [self.xs[self.col[k]] for k in over]
                nw = max(140, max(xs) - min(xs) + 60, min(280, d.tw(m["note"], Z["small"], "sans") + 20))
                m["_lines"] = wrap(d, m["note"], nw - 20, Z["small"], "sans")
                m["_w"] = max(nw, max(d.tw(l, Z["small"], "sans") for l in m["_lines"]) + 20)
                hh = len(m["_lines"]) * 16 + 12
                self.ys.append(y)
                y += hh + 12
            else:
                if m["src"] == m["dst"]:
                    self.ys.append(y + 10)
                    y += self.row_h + 18
                else:
                    self.ys.append(y + 10)
                    y += self.row_h
        lo, hi = 0.0, self.xs[-1] + self.nodes[-1].w / 2   # extent relative to the first actor box's left
        for m in self.rows:
            if "note" in m:
                over = m["over"] if isinstance(m["over"], (list, tuple)) else [m["over"]]
                xs = [self.xs[self.col[k]] for k in over]
                c = (min(xs) + max(xs)) / 2
                lo = min(lo, c - m["_w"] / 2)
                hi = max(hi, c + m["_w"] / 2)
            elif "src" in m and m["src"] == m["dst"]:
                x = self.xs[self.col[m["src"]]]
                hi = max(hi, x + 38 + d.tw(str(m["label"]), Z["label"], "sans", 500) + (22 if numbered else 0))
        self.xs = [x - lo for x in self.xs]
        self.w = hi - lo
        self.h = y + 4
        for k, i in self.col.items():
            nd = self.nodes[i]
            self.parts["." + k] = Part(self, "." + k, self.xs[i] - nd.w / 2, 0, nd.w, nd.h)

    def actor(self, key):
        return self.part("." + key)

    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        r = self.rect
        for i, nd in enumerate(self.nodes):
            nd.x, nd.y = r.x + self.xs[i] - nd.w / 2, r.y + (self.head_h - nd.h) / 2
            x = r.x + self.xs[i]
            S.path([(x, r.y + self.head_h / 2 + nd.h / 2), (x, r.y1)], C["line"], 1, dash="3 4", z=2, role="lifeline",
                   owner=o, cap="butt")
            nd.emit(S)
        num = 0
        for k, m in enumerate(self.rows):
            y = r.y + self.ys[k]
            if "gap" in m:
                continue
            if "divider" in m:
                S.path([(r.x0, y), (r.x1, y)], C["rule"], 1, dash="4 4", z=2.5, role="divider", owner=o, cap="butt")
                tw = self.d.tw(str(m["divider"]).upper(), Z["tag"] + 0.5, "mono", 500, 0.1)
                S.rect(Rect(r.cx - tw / 2 - 8, y - 9, tw + 16, 18), rx=9, fill=C["paper"], stroke=C["rule"], z=2.6,
                       role="chip", owner=o)
                S.text(r.cx, _bl(y, Z["tag"] + 0.5), str(m["divider"]).upper(), Z["tag"] + 0.5, "mono", 500,
                       C["muted"], "middle", ls=0.1, z=2.7, owner=o)
                continue
            if "note" in m:
                over = m["over"] if isinstance(m["over"], (list, tuple)) else [m["over"]]
                xs = [r.x + self.xs[self.col[kk]] for kk in over]
                c = (min(xs) + max(xs)) / 2
                hh = len(m["_lines"]) * 16 + 12
                nr = Rect(c - m["_w"] / 2, y, m["_w"], hh)
                st = S.unit(f"{o}#n{k}", (m["note"],), nr, text=m["note"], explicit=m.get("state"))
                ss, sf, si = S.style(st)
                S.rect(nr, rx=6, fill=sf or C["note"], stroke=ss or C["note_rule"], z=4, role="note", owner=o)
                for li, l in enumerate(m["_lines"]):
                    S.text(nr.x + 10, nr.y + 6 + 11.5 + li * 16, l, Z["small"], "sans", 400, si or C["ink2"],
                           owner=o)
                continue
            num += 1
            a, b = self.col[m["src"]], self.col[m["dst"]]
            xa, xb = r.x + self.xs[a], r.x + self.xs[b]
            st = S.unit(f"{o}#m{k}", (m["src"], m["dst"], m["label"]), Rect(min(xa, xb), y - 20, abs(xb - xa) or 40, 24),
                        text=m["label"], explicit=m.get("state"), shape="none")
            col = S.style(st)[0] if st else C["edge"]
            ink = S.style(st)[2] if st else C["ink2"]
            dash = "5 4" if m.get("dashed") else None
            sw = 1.5 if st else 1.25
            label = str(m["label"])
            if a == b:
                pts = [(xa, y - 6), (xa + 30, y - 6), (xa + 30, y + 12), (xa + 4, y + 12)]
                S.path(pts, col, sw, dash, z=3, role="msg", owner=o, corner=6)
                S.arrow((xa + 1, y + 12), (-1, 0), col, owner=o, z=3.1)
                lx, anchor = xa + 38, "start"
                ly = _bl(y + 3, Z["label"])
            else:
                dirx = 1 if xb > xa else -1
                S.path([(xa, y), (xb - dirx * 6, y)], col, sw, dash, z=3, role="msg", owner=o)
                S.arrow((xb - dirx * 1, y), (dirx, 0), col, owner=o, z=3.1)
                lx, anchor = (xa + xb) / 2, "middle"
                ly = y - 7
            if self.numbered:
                tw = self.d.tw(label, Z["label"], "sans", 500)
                bx = lx - tw / 2 - 11 if anchor == "middle" else lx + 8
                if anchor == "middle":
                    lx += 11
                else:
                    lx += 22
                S.circle(bx, ly - 4, 8, fill=col if st else C["ink"], z=5.5, role="badge", owner=o)
                S.text(bx, _bl(ly - 4, 9.5), str(num), 9.5, "mono", 600, C["paper"], "middle", z=5.6,
                       role="badge-text", owner=o)
            if label:
                S.text(lx, ly, label, Z["label"], "sans", 500, ink, anchor, z=5, role="label", owner=o)
