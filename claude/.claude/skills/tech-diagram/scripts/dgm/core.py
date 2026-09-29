"""Geometry, the scene (flat list of drawable items), element base class and placement helpers."""
import math
import re

CJK = re.compile(r"[⺀-鿿豈-﫿＀-￯　-〿]")


class Rect:
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    x0 = property(lambda s: s.x)
    y0 = property(lambda s: s.y)
    x1 = property(lambda s: s.x + s.w)
    y1 = property(lambda s: s.y + s.h)
    cx = property(lambda s: s.x + s.w / 2)
    cy = property(lambda s: s.y + s.h / 2)

    def inflate(self, m, my=None):
        my = m if my is None else my
        return Rect(self.x - m, self.y - my, self.w + 2 * m, self.h + 2 * my)

    def shift(self, dx, dy):
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def union(self, o):
        if o is None:
            return self
        x0, y0 = min(self.x0, o.x0), min(self.y0, o.y0)
        return Rect(x0, y0, max(self.x1, o.x1) - x0, max(self.y1, o.y1) - y0)

    def overlap(self, o):
        return (min(self.x1, o.x1) - max(self.x0, o.x0), min(self.y1, o.y1) - max(self.y0, o.y0))

    def hits(self, o, tol=0.0):
        ox, oy = self.overlap(o)
        return ox > tol and oy > tol

    def contains(self, o, tol=0.5):
        return (o.x0 >= self.x0 - tol and o.y0 >= self.y0 - tol and o.x1 <= self.x1 + tol
                and o.y1 <= self.y1 + tol)

    def has(self, p, pad=0.0):
        return self.x0 + pad < p[0] < self.x1 - pad and self.y0 + pad < p[1] < self.y1 - pad

    def side(self, side, t=0.5):
        if side == "top":
            return (self.x + self.w * t, self.y0)
        if side == "bottom":
            return (self.x + self.w * t, self.y1)
        if side == "left":
            return (self.x0, self.y + self.h * t)
        return (self.x1, self.y + self.h * t)

    def __repr__(self):
        return f"Rect({self.x:.1f},{self.y:.1f},{self.w:.1f},{self.h:.1f})"


def union_all(rects):
    out = None
    for r in rects:
        if r is not None:
            out = r if out is None else out.union(r)
    return out


def up4(v, g=4):
    return math.ceil(v / g - 1e-9) * g


DIRS = {"top": (0, -1), "bottom": (0, 1), "left": (-1, 0), "right": (1, 0)}


def seg_hits_rect(a, b, r, pad=0.0):
    """Does segment a→b pass through the interior of rect r (shrunk by pad)? Liang–Barsky."""
    x0, y0, x1, y1 = r.x0 + pad, r.y0 + pad, r.x1 - pad, r.y1 - pad
    if x1 <= x0 or y1 <= y0:
        return False
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q <= 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 >= t1:
                return False
    return t1 - t0 > 1e-6


def simplify(pts):
    """Drop duplicate and collinear points of an orthogonal/straight polyline."""
    out = []
    for p in pts:
        p = (round(p[0], 2), round(p[1], 2))
        if out and abs(out[-1][0] - p[0]) < 0.01 and abs(out[-1][1] - p[1]) < 0.01:
            continue
        out.append(p)
        while len(out) >= 3:
            (ax, ay), (bx, by), (cx, cy) = out[-3:]
            if abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) < 0.01:
                out.pop(-2)
            else:
                break
    return out


NO_START = set("，。、；：！？）》」』】,.;:!?)]}%")   # never begin a wrapped line with these
NO_END = set("（《「『【([{")                            # never end one with these


def wrap(d, text, maxw, size, font="sans", weight=400):
    """Greedy line wrap. Latin breaks at spaces, CJK between any two characters; '\n' forces a break."""
    lines = []
    for para in str(text).split("\n"):
        tokens = re.findall(r"[⺀-鿿豈-﫿＀-￯　-〿]|[^\s⺀-鿿豈-﫿"
                            r"＀-￯　-〿]+|\s+", para)
        cur = ""
        for tok in tokens:
            trial = cur + tok
            if cur and d.tw(trial.rstrip(), size, font, weight) > maxw and not tok.isspace() \
                    and tok not in NO_START:
                head = cur.rstrip()
                carry = ""
                while len(head) > 1 and head[-1] in NO_END:   # an opening bracket moves to the next line
                    carry, head = head[-1] + carry, head[:-1]
                lines.append(head.rstrip())
                cur = carry + tok.lstrip()
            else:
                cur = trial
        lines.append(cur.rstrip())
    return lines or [""]


# ---------------------------------------------------------------------------------------------- scene

class Scene:
    """Flat list of drawable items in content coordinates. Every item keeps what the SVG writer needs plus a
    `bbox` / `pts` for the self-check. Components ask `unit()` for the state of each diffable piece."""

    def __init__(self, d, diff=None):
        self.d = d
        self.T = d.T
        self.items = []
        self.units = {}
        self.diff = diff or {}
        self.applied = set()   # diff states that actually got drawn (explicit states win over them)

    # -- state of a diffable unit (a node, a cell, a field row, an edge …)
    def unit(self, uid, sig, rect=None, shape="rect", rx=0, text=None, pts=None, explicit=None, diff=True):
        self.units[uid] = {"sig": sig, "rect": rect, "shape": shape, "rx": rx, "text": text, "pts": pts,
                           "diff": diff}
        if explicit:
            return explicit
        st = self.diff.get(uid) if diff else None
        if st:
            self.applied.add(st)
        return st

    def style(self, state=None, tone=None):
        """(stroke, fill, ink) for a state or tone; None entries mean 'use the default'."""
        if state and state in self.T["states"]:
            s = self.T["states"][state]
            return s["stroke"], s["fill"], s["ink"]
        if tone and tone in self.T["tones"]:
            s = self.T["tones"][tone]
            return s["stroke"], s["fill"], s["ink"]
        return None, None, None

    def _add(self, it):
        self.items.append(it)
        return it

    def rect(self, r, rx=0, fill="none", stroke=None, sw=1.0, dash=None, z=4, role="deco", owner=None,
             opacity=None, uid=None):
        return self._add({"el": "rect", "x": r.x, "y": r.y, "w": r.w, "h": r.h, "rx": rx, "fill": fill,
                          "stroke": stroke, "sw": sw, "dash": dash, "z": z, "role": role, "owner": owner,
                          "opacity": opacity, "bbox": r, "uid": uid})

    def text(self, x, y, s, size, font="sans", weight=400, fill=None, anchor="start", ls=0.0, z=5,
             role="text", owner=None, deco=None, opacity=None):
        s = str(s)
        w = self.d.tw(s, size, font, weight, ls)
        x0 = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
        asc = 0.86 if CJK.search(s) else 0.76
        bbox = Rect(x0, y - asc * size, w, (asc + 0.22) * size)
        return self._add({"el": "text", "x": x, "y": y, "s": s, "size": size, "font": font, "weight": weight,
                          "fill": fill or self.T["color"]["ink"], "anchor": anchor, "ls": ls, "z": z,
                          "role": role, "owner": owner, "bbox": bbox, "w": w, "deco": deco, "opacity": opacity})

    def path(self, pts, stroke, sw=1.25, dash=None, z=3, role="edge", owner=None, corner=None, fill="none",
             opacity=None, cap="round", closed=False):
        corner = self.T["look"]["corner"] if corner is None else corner
        return self._add({"el": "path", "pts": list(pts), "stroke": stroke, "sw": sw, "dash": dash, "z": z,
                          "role": role, "owner": owner, "corner": corner, "fill": fill, "opacity": opacity,
                          "cap": cap, "closed": closed,
                          "bbox": union_all(Rect(p[0], p[1], 0, 0) for p in pts)})

    def raw(self, d, fill="none", stroke=None, sw=1.0, z=4, role="deco", owner=None, bbox=None, dash=None,
            opacity=None):
        return self._add({"el": "raw", "d": d, "fill": fill, "stroke": stroke, "sw": sw, "z": z, "role": role,
                          "owner": owner, "bbox": bbox, "dash": dash, "opacity": opacity})

    def circle(self, cx, cy, r, fill="none", stroke=None, sw=1.0, z=4, role="deco", owner=None, dash=None):
        return self._add({"el": "circle", "cx": cx, "cy": cy, "r": r, "fill": fill, "stroke": stroke, "sw": sw,
                          "z": z, "role": role, "owner": owner, "dash": dash,
                          "bbox": Rect(cx - r, cy - r, 2 * r, 2 * r)})

    def icon(self, name, x, y, size, color, z=5, owner=None):
        return self._add({"el": "icon", "name": name, "x": x, "y": y, "size": size, "color": color, "z": z,
                          "role": "icon", "owner": owner, "bbox": Rect(x, y, size, size)})

    def image(self, href, r, rx=0, z=4, owner=None):
        return self._add({"el": "image", "href": href, "x": r.x, "y": r.y, "w": r.w, "h": r.h, "rx": rx, "z": z,
                          "role": "image", "owner": owner, "bbox": r})

    def chip(self, x, y, s, color, z=5, owner=None, anchor="start", fill="none", upper=True):
        """Small rectangular type tag (mono caps). (x, y) = top-left (or top-right with anchor='end')."""
        T = self.T
        size = T["size"]["tag"]
        s = str(s).upper() if upper else str(s)
        w = self.d.tw(s, size, "mono", 500, 0.06) + 10
        x0 = x - w if anchor == "end" else x
        r = Rect(x0, y, w, 14)
        self.rect(r, rx=2, fill=fill, stroke=color, sw=0.8, z=z, role="chip", owner=owner, opacity=None)
        self.text(x0 + 5, y + 10, s, size, "mono", 500, fill=color, ls=0.06, z=z + 0.1, role="chip-text",
                  owner=owner)
        return r

    def arrow(self, tip, direction, color, size=None, z=3.5, owner=None, role="arrow"):
        """Rounded solid arrowhead with its tip at `tip`, pointing along unit vector `direction`."""
        L = size or self.T["look"]["arrow"]
        ux, uy = direction
        px, py = -uy, ux
        hw = L * 0.42
        bx, by = tip[0] - ux * L, tip[1] - uy * L
        a = (bx + px * hw, by + py * hw)
        b = (bx - px * hw, by - py * hw)
        f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")
        d = (f"M{f(tip[0])},{f(tip[1])} L{f(a[0])},{f(a[1])} "
             f"Q{f(bx + ux * L * 0.18)},{f(by + uy * L * 0.18)} {f(b[0])},{f(b[1])} Z")
        bb = union_all(Rect(p[0], p[1], 0, 0) for p in (tip, a, b))
        return self.raw(d, fill=color, stroke=color, sw=0.9, z=z, role=role, owner=owner, bbox=bb)

    def bbox(self):
        return union_all(it["bbox"] for it in self.items if it.get("bbox") is not None)


# ---------------------------------------------------------------------------------------------- elements

class Part:
    """An addressable piece of a component (array cell, record field, table cell, code line …) that edges and
    notes can attach to. Geometry is stored relative to the owner so moving the owner moves the part."""

    def __init__(self, owner, key, dx, dy, w, h, sides=None, ptr=False, penalty=None, offset=None):
        self.owner, self.key = owner, key
        self.dx, self.dy, self.w, self.h = dx, dy, w, h
        self.sides = sides
        self.ptr = ptr
        self.penalty = penalty or {}   # side → extra routing cost (discourage, don't forbid)
        self.offset = offset or {}     # side → attach this far outside the part (clear of index labels)

    @property
    def rect(self):
        return Rect(self.owner.x + self.dx, self.owner.y + self.dy, self.w, self.h)

    @property
    def uid(self):
        return f"{self.owner.id}{self.key}"

    @property
    def top_owner(self):
        return self.owner.top_owner

    def allowed_sides(self):
        if self.sides:
            return self.sides
        o, r = self.owner.rect, self.rect
        s = [n for n, ok in (("top", abs(r.y0 - o.y0) < 1), ("bottom", abs(r.y1 - o.y1) < 1),
                             ("left", abs(r.x0 - o.x0) < 1), ("right", abs(r.x1 - o.x1) < 1)) if ok]
        return s or ["top", "bottom", "left", "right"]

    def shape(self):
        return "rect"


class El:
    prefix = "el"
    solid = True      # an obstacle for edges and a box for the overlap check
    shape_kind = "rect"

    def __init__(self, d, id=None):
        self.d = d
        self.T = d.T
        self.id = d._uid(self.prefix, id)
        self.x = self.y = None
        self.w = self.h = 0
        self.pad_ext = [0, 0, 0, 0]  # decorations outside the body: left, top, right, bottom
        self.parts = {}
        d._register(self)

    # -- geometry
    @property
    def placed(self):
        return self.x is not None

    @property
    def rect(self):
        self._need()
        return Rect(self.x, self.y, self.w, self.h)

    @property
    def ext(self):
        l, t, r, b = self.pad_ext
        return Rect(self.x - l, self.y - t, self.w + l + r, self.h + t + b)

    cx = property(lambda s: s.rect.cx)
    cy = property(lambda s: s.rect.cy)
    top_owner = property(lambda s: s)
    uid = property(lambda s: s.id)

    def _need(self):
        if self.x is None:
            raise ValueError(f"{self.prefix} '{self.id}' is not placed yet — call .at()/.right_of()/… first")

    def allowed_sides(self):
        return ["top", "bottom", "left", "right"]

    def shape(self):
        return self.shape_kind

    def obstacles(self):
        """Rects edges must avoid."""
        return [self.ext]

    def part(self, key):
        if key not in self.parts:
            raise KeyError(f"{self.prefix} '{self.id}' has no part {key!r}; parts: {', '.join(map(str, self.parts))}")
        return self.parts[key]

    # -- placement (all return self)
    def at(self, x, y):
        """Place the body's top-left corner."""
        self.x, self.y = float(x), float(y)
        return self

    def center_at(self, cx, cy):
        return self.at(cx - self.w / 2, cy - self.h / 2)

    def _rel(self, other, where, gap, align):
        o = other.rect if isinstance(other, (El, Part)) else other
        oe = other.ext if isinstance(other, El) else o
        l, t, r, b = self.pad_ext
        if where in ("right", "left"):
            x = oe.x1 + gap + l if where == "right" else oe.x0 - gap - r - self.w
            y = {"center": o.cy - self.h / 2, "top": o.y0, "bottom": o.y1 - self.h}[align or "center"]
        else:
            y = oe.y1 + gap + t if where == "below" else oe.y0 - gap - b - self.h
            x = {"center": o.cx - self.w / 2, "left": o.x0, "right": o.x1 - self.w}[align or "center"]
        return self.at(x, y)

    def right_of(self, other, gap=48, align="center"):
        return self._rel(other, "right", gap, align)

    def left_of(self, other, gap=48, align="center"):
        return self._rel(other, "left", gap, align)

    def below(self, other, gap=40, align="center"):
        return self._rel(other, "below", gap, align)

    def above(self, other, gap=40, align="center"):
        return self._rel(other, "above", gap, align)

    def align_x(self, other):
        """Center horizontally on another element (keeps y)."""
        o = other.rect
        self.x = o.cx - self.w / 2
        return self

    def align_y(self, other):
        o = other.rect
        self.y = o.cy - self.h / 2
        return self

    def shift(self, dx=0, dy=0):
        self._need()
        self.x += dx
        self.y += dy
        return self

    def emit(self, S):  # pragma: no cover - abstract
        raise NotImplementedError
