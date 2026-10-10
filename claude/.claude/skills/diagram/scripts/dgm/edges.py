"""Edges: side choice, port fan-out, orthogonal routing around obstacles, label placement, emission."""
import heapq
import math

from .core import DIRS, El, Part, Rect, seg_hits_rect, simplify

STUB = 16      # straight run leaving / entering a box
MARGIN = 8     # clearance kept from boxes
BEND = 36      # cost of one bend (in px of detour)


class End:
    """Normalized edge endpoint: an element, a part, or a bare point."""

    def __init__(self, obj):
        self.obj = obj
        if isinstance(obj, (El, Part)):
            self.kind = "part" if isinstance(obj, Part) else "el"
        else:
            self.kind = "pt"

    @property
    def rect(self):
        if self.kind == "pt":
            return Rect(self.obj[0], self.obj[1], 0, 0)
        return self.obj.rect

    @property
    def uid(self):
        return self.obj.uid if self.kind != "pt" else f"({self.obj[0]:.0f},{self.obj[1]:.0f})"

    @property
    def owner(self):
        return self.obj.top_owner if self.kind != "pt" else None

    @property
    def ptr(self):
        return self.kind == "part" and self.obj.ptr

    def shape(self):
        return self.obj.shape() if self.kind != "pt" else "point"

    def sides(self):
        if self.kind == "pt":
            return ["top", "bottom", "left", "right"]
        return self.obj.allowed_sides()

    def penalty(self, side):
        return self.obj.penalty.get(side, 0) if self.kind == "part" else 0

    def offset(self, side):
        return self.obj.offset.get(side, 0) if self.kind == "part" else 0


class Edge:
    prefix = "edge"

    def __init__(self, d, src, dst, label=None, style="solid", state=None, tone=None, arrow="end", src_side=None,
                 dst_side=None, route="auto", via=None, step=None, mono=False, width=None, label_at=None, id=None):
        self.d, self.T = d, d.T
        self.a, self.b = End(src), End(dst)
        self.label = None if label in (None, "") else str(label)
        self.style, self.state, self.tone, self.arrow = style, state, tone, arrow
        self.sa, self.sb = src_side, dst_side
        self.route, self.via, self.step, self.mono = route, via, step, mono
        self.width, self.label_at = width, label_at
        base = id or f"{self.a.uid}->{self.b.uid}"
        self.id = base
        n = 2
        while self.id in d._edge_ids:
            self.id = f"{base}#{n}"
            n += 1
        d._edge_ids.add(self.id)
        self.pts = None
        self.lab = None  # placed label: dict(rect, x, y, badge)
        if self.route == "auto" and "circle" in (self.a.shape(), self.b.shape()):
            self.route = "straight"   # graph / tree vertices: direct lines read best

    uid = property(lambda s: s.id)


# ------------------------------------------------------------------------------------------ geometry helpers

def _pt(r, side, t):
    return r.side(side, t)


def _add(p, d, k):
    return (p[0] + d[0] * k, p[1] + d[1] * k)


def _clip(shape, r, toward):
    """Point where the ray from r's center toward `toward` leaves the shape."""
    cx, cy = r.cx, r.cy
    dx, dy = toward[0] - cx, toward[1] - cy
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    if shape == "point" or r.w == 0:
        return (cx, cy)
    if shape == "circle":
        return (cx + ux * r.w / 2, cy + uy * r.w / 2)
    if shape == "diamond":
        t = 1.0 / (abs(ux) / (r.w / 2) + abs(uy) / (r.h / 2))
        return (cx + ux * t, cy + uy * t)
    tx = (r.w / 2) / abs(ux) if abs(ux) > 1e-9 else 1e9
    ty = (r.h / 2) / abs(uy) if abs(uy) > 1e-9 else 1e9
    t = min(tx, ty)
    return (cx + ux * t, cy + uy * t)


def _segs(pts):
    return list(zip(pts, pts[1:]))


def _overlap_len(s, t, tol=4.0):
    """Length over which two axis-aligned segments run on top of each other (within tol)."""
    (a, b), (c, d) = s, t
    if abs(a[1] - b[1]) < 0.01 and abs(c[1] - d[1]) < 0.01 and abs(a[1] - c[1]) < tol:
        lo, hi = max(min(a[0], b[0]), min(c[0], d[0])), min(max(a[0], b[0]), max(c[0], d[0]))
        return max(0.0, hi - lo)
    if abs(a[0] - b[0]) < 0.01 and abs(c[0] - d[0]) < 0.01 and abs(a[0] - c[0]) < tol:
        lo, hi = max(min(a[1], b[1]), min(c[1], d[1])), min(max(a[1], b[1]), max(c[1], d[1]))
        return max(0.0, hi - lo)
    return 0.0


def _crosses(s, t):
    (a, b), (c, d) = s, t
    h1, h2 = abs(a[1] - b[1]) < 0.01, abs(c[1] - d[1]) < 0.01
    if h1 == h2:
        return False
    if not h1:
        (a, b), (c, d) = (c, d), (a, b)
    y = a[1]
    x = c[0]
    return (min(a[0], b[0]) + 0.5 < x < max(a[0], b[0]) - 0.5 and min(c[1], d[1]) + 0.5 < y < max(c[1], d[1]) - 0.5)


# ------------------------------------------------------------------------------------------ routing

class Router:
    def __init__(self, obstacles):
        self.obs = obstacles  # [(rect, owner_uid)]
        self.segs = []        # (segment, terminal point) of already routed edges
        self.key = None       # terminal point of the edge being routed: edges converging on it may merge

    def _blocked(self, a, b, own=(), m=MARGIN):
        """Segment a→b hits an obstacle. Rects of the edge's own endpoints (`own`) are checked only for their
        interior (a stub may start on their border, but a path must never cut through them)."""
        L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 or 1.0
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        a2 = (a[0] + u[0] * 3, a[1] + u[1] * 3) if L > 6 else a
        b2 = (b[0] - u[0] * 3, b[1] - u[1] * 3) if L > 6 else b
        for r, o in self.obs:
            if o in own:
                if L > 6 and seg_hits_rect(a2, b2, r.inflate(1.5)):
                    return True
            elif seg_hits_rect(a, b, r.inflate(m - 0.5)):
                return True
        return False

    def _penalty(self, a, b):
        p = 0.0
        for s, key in self.segs:
            if key is not None and key == self.key:
                continue
            ov = _overlap_len((a, b), s)
            if ov > 1:
                p += 400 + ov * 4
            elif _crosses((a, b), s):
                p += 24
        return p

    def _path_cost(self, pts, own):
        """None if the candidate polyline is blocked, else its cost."""
        cost = 0.0
        for a, b in _segs(pts):
            if self._blocked(a, b, own):
                return None
            cost += abs(a[0] - b[0]) + abs(a[1] - b[1]) + self._penalty(a, b)
        return cost + BEND * (len(pts) - 2)

    def _escape(self, p, d, own):
        """Stub end: STUB beyond p, extended until clear of the owner's own decorations."""
        q = _add(p, d, STUB)
        for _ in range(8):
            hit = [r for r, o in self.obs if o == own and r.inflate(MARGIN - 1).has(q)]
            if not hit:
                break
            r = hit[0]
            if d[0] > 0:
                q = (r.x1 + MARGIN, q[1])
            elif d[0] < 0:
                q = (r.x0 - MARGIN, q[1])
            elif d[1] > 0:
                q = (q[0], r.y1 + MARGIN)
            else:
                q = (q[0], r.y0 - MARGIN)
        return q

    def route(self, p0, d0, p1, d1, own0, own1, need=0):
        """Orthogonal path p0→p1 leaving along d0 and arriving against d1. `need` = label width: prefer a
        candidate with a horizontal run long enough to hold it."""
        self.key = _key(p1)
        q0 = self._escape(p0, d0, own0)
        q1 = self._escape(p1, d1, own1)
        cands = []
        horiz0, horiz1 = d0[0] != 0, d1[0] != 0
        # straight
        if horiz0 and horiz1 and abs(p0[1] - p1[1]) < 0.5 and d0[0] == -d1[0] and (p1[0] - p0[0]) * d0[0] > 0:
            cands.append([p0, p1])
        if not horiz0 and not horiz1 and abs(p0[0] - p1[0]) < 0.5 and d0[1] == -d1[1] and (p1[1] - p0[1]) * d0[1] > 0:
            cands.append([p0, p1])
        # L
        if horiz0 != horiz1:
            c = (p1[0], p0[1]) if horiz0 else (p0[0], p1[1])
            if ((c[0] - p0[0]) * d0[0] + (c[1] - p0[1]) * d0[1] > STUB / 2 and
                    (c[0] - p1[0]) * d1[0] + (c[1] - p1[1]) * d1[1] > STUB / 2):
                cands.append([p0, c, p1])
        # Z (opposite directions) — try a few channel positions
        if horiz0 and horiz1 and d0[0] == -d1[0]:
            for f in (0.5, 0.35, 0.65, 0.2, 0.8):
                x = q0[0] + (q1[0] - q0[0]) * f
                if (x - p0[0]) * d0[0] >= STUB * 0.75 and (x - p1[0]) * d1[0] >= STUB * 0.75:
                    cands.append([p0, (x, p0[1]), (x, p1[1]), p1])
        if not horiz0 and not horiz1 and d0[1] == -d1[1]:
            for f in (0.5, 0.35, 0.65, 0.2, 0.8):
                y = q0[1] + (q1[1] - q0[1]) * f
                if (y - p0[1]) * d0[1] >= STUB * 0.75 and (y - p1[1]) * d1[1] >= STUB * 0.75:
                    cands.append([p0, (p0[0], y), (p1[0], y), p1])
        # U (same direction)
        if d0 == d1:
            if horiz0:
                x = max(q0[0], q1[0]) if d0[0] > 0 else min(q0[0], q1[0])
                cands.append([p0, (x, p0[1]), (x, p1[1]), p1])
            else:
                y = max(q0[1], q1[1]) if d0[1] > 0 else min(q0[1], q1[1])
                cands.append([p0, (p0[0], y), (p1[0], y), p1])
        best, bc, bx = None, None, None
        for c in cands:
            c = simplify(c)
            cost = self._path_cost(c, (own0, own1))
            if cost is None:
                continue
            # extra = what the route pays beyond its own length and bends (overlaps, crossings)
            extra = cost - sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in _segs(c)) - BEND * (len(c) - 2)
            if need:
                hs = [abs(a[0] - b[0]) for a, b in _segs(c) if abs(a[1] - b[1]) < 0.01]
                if hs and max(hs) < need:
                    cost += 160
            if bc is None or cost < bc:
                best, bc, bx = c, cost, extra
        if best is not None and bx < 150:
            return best
        path = self._astar(p0, q0, d0, p1, q1, d1, own0, own1)
        if path is not None:
            return path
        if best is not None:
            return best
        # last resort: Z through the middle, ignoring obstacles
        if horiz0:
            x = (q0[0] + q1[0]) / 2
            return simplify([p0, q0, (x, q0[1]), (x, q1[1]), q1, p1]) if horiz1 else simplify(
                [p0, q0, (q0[0], q1[1]) if not horiz1 else q1, q1, p1])
        y = (q0[1] + q1[1]) / 2
        return simplify([p0, q0, (q0[0], y), (q1[0], y), q1, p1])

    def _astar(self, p0, q0, d0, p1, q1, d1, own0, own1):
        m = MARGIN
        xs, ys = {q0[0], q1[0]}, {q0[1], q1[1]}
        ex, ey = [], []
        for r, _ in self.obs:
            ex += [r.x0 - m, r.x1 + m]
            ey += [r.y0 - m, r.y1 + m]
        xs.update(ex)
        ys.update(ey)
        for arr, out in ((sorted(ex + [q0[0], q1[0]]), xs), (sorted(ey + [q0[1], q1[1]]), ys)):
            for a, b in zip(arr, arr[1:]):
                if b - a > 2 * m + 4:
                    out.add((a + b) / 2)
        lo_x, hi_x = min(q0[0], q1[0]) - 400, max(q0[0], q1[0]) + 400
        lo_y, hi_y = min(q0[1], q1[1]) - 400, max(q0[1], q1[1]) + 400
        xs = sorted(x for x in xs if lo_x <= x <= hi_x)
        ys = sorted(y for y in ys if lo_y <= y <= hi_y)
        ix = {x: i for i, x in enumerate(xs)}
        iy = {y: i for i, y in enumerate(ys)}
        inf = [r.inflate(m - 0.5) for r, _ in self.obs]

        def free_pt(x, y):
            return not any(r.has((x, y)) for r in inf)

        cache = {}

        def step_ok(a, b):
            k = (a, b)
            if k not in cache:
                cache[k] = not any(seg_hits_rect(a, b, r) for r in inf)
            return cache[k]

        start, goal = (ix[q0[0]], iy[q0[1]]), (ix[q1[0]], iy[q1[1]])
        arrive = (-d1[0], -d1[1])
        h = lambda i, j: abs(xs[i] - q1[0]) + abs(ys[j] - q1[1])
        pq = [(h(*start), 0.0, start, d0)]
        seen = {}
        prev = {}
        while pq:
            f, g, (i, j), dr = heapq.heappop(pq)
            if seen.get(((i, j), dr), 1e18) <= g:
                continue
            seen[((i, j), dr)] = g
            if (i, j) == goal:
                # rebuild
                node = ((i, j), dr)
                pts = []
                while node in prev:
                    pts.append((xs[node[0][0]], ys[node[0][1]]))
                    node = prev[node]
                pts.append(q0)
                pts.reverse()
                return simplify([p0] + pts + [p1])
            for nd in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if nd == (-dr[0], -dr[1]):
                    continue
                ni, nj = i + nd[0], j + nd[1]
                if not (0 <= ni < len(xs) and 0 <= nj < len(ys)):
                    continue
                a, b = (xs[i], ys[j]), (xs[ni], ys[nj])
                if (ni, nj) != goal and not free_pt(*b):
                    continue
                if not step_ok(a, b):
                    continue
                ng = g + abs(a[0] - b[0]) + abs(a[1] - b[1]) + (BEND if nd != dr else 0) + self._penalty(a, b)
                if (ni, nj) == goal and nd != arrive:
                    ng += BEND
                key = ((ni, nj), nd)
                if seen.get(key, 1e18) <= ng:
                    continue
                prev[key] = ((i, j), dr)
                heapq.heappush(pq, (ng + h(ni, nj), ng, (ni, nj), nd))
        return None


# ------------------------------------------------------------------------------------------ planning

def _choose_sides(e):
    ra, rb = e.a.rect, e.b.rect
    sa_opts = [e.sa] if e.sa else e.a.sides()
    sb_opts = [e.sb] if e.sb else e.b.sides()
    best, bc = None, None
    for sa in sa_opts:
        for sb in sb_opts:
            pa, pb = ra.side(sa), rb.side(sb)
            da, db = DIRS[sa], DIRS[sb]
            qa, qb = _add(pa, da, STUB), _add(pb, db, STUB)
            cost = abs(qa[0] - qb[0]) + abs(qa[1] - qb[1])
            v = (pb[0] - pa[0], pb[1] - pa[1])
            if da[0] * v[0] + da[1] * v[1] <= 0:
                cost += 300
            if db[0] * -v[0] + db[1] * -v[1] <= 0:
                cost += 300
            if da == (-db[0], -db[1]):
                gap = (v[0] * da[0] + v[1] * da[1])
                if gap < 2 * STUB:
                    cost += 150
                aligned = abs((pa[1] - pb[1]) if da[0] else (pa[0] - pb[0])) < 1
                cost += 0 if aligned else 2 * 30
            elif da == db:
                cost += 120
            else:
                cost += 30
            cost += e.a.penalty(sa) + e.b.penalty(sb)
            if best is None or cost < bc:
                best, bc = (sa, sb), cost
    return best


def plan(d, edges, obstacles):
    """Route every edge in creation order; then place labels."""
    ortho = [e for e in edges if e.route not in ("straight", "center")]
    for e in ortho:
        if e.via:
            continue
        e.sa_, e.sb_ = _choose_sides(e)
    # fan-out: group endpoints per (uid, side)
    groups = {}
    for e in ortho:
        if e.via:
            continue
        for which, end, side, other in (("a", e.a, e.sa_, e.b), ("b", e.b, e.sb_, e.a)):
            if end.kind == "pt" or (which == "a" and end.ptr) or end.shape() in ("circle", "diamond"):
                continue
            groups.setdefault((end.uid, side), []).append((e, which, other))
    e_t = {}
    for (uid, side), lst in groups.items():
        horiz = side in ("top", "bottom")
        r = (lst[0][0].a if lst[0][1] == "a" else lst[0][0].b).rect
        L = r.w if horiz else r.h
        lst.sort(key=lambda it: (it[2].rect.cx if horiz else it[2].rect.cy))
        n = len(lst)
        if n == 1:
            e_t[(id(lst[0][0]), lst[0][1])] = 0.5
            continue
        sp = min(24.0, (L * 0.8) / (n - 1))
        if sp < 6:
            # too narrow to fan (a byte boundary, a thin part): the edges converge on the one point
            for e, which, _ in lst:
                e_t[(id(e), which)] = 0.5
            continue
        for k, (e, which, _) in enumerate(lst):
            off = (k - (n - 1) / 2) * sp
            e_t[(id(e), which)] = 0.5 + off / L
    single = {k for k, v in groups.items() if len(v) == 1}
    R = Router(obstacles)
    for e in edges:
        if e.route == "center":
            e.pts = _center(e)
            continue
        if e.route == "straight":
            e.pts = _straight(e, edges)
            R.segs += [(sg, None) for sg in _segs(e.pts)] if len(e.pts) and _is_ortho(e.pts) else []
            continue
        if e.via:
            e.pts = _via(e)
            R.segs += [(sg, None) for sg in _segs(e.pts)]
            continue
        ra, rb = e.a.rect, e.b.rect
        ta = e_t.get((id(e), "a"), 0.5)
        tb = e_t.get((id(e), "b"), 0.5)
        pa, pb = _pt(ra, e.sa_, ta), _pt(rb, e.sb_, tb)
        da, db = DIRS[e.sa_], DIRS[e.sb_]
        # align single ports across facing sides so the edge is one straight line
        if ((e.a.uid, e.sa_) in single or e.a.ptr) and (e.b.uid, e.sb_) in single and da == (-db[0], -db[1]) \
                and e.a.shape() == "rect" and e.b.shape() == "rect":
            if da[0]:
                lo, hi = max(ra.y0, rb.y0) + 6, min(ra.y1, rb.y1) - 6
                if lo <= hi:
                    y = min(max(ra.cy, lo), hi) if not e.a.ptr else ra.cy
                    if lo <= y <= hi:
                        pa, pb = (pa[0], y), (pb[0], y)
            else:
                lo, hi = max(ra.x0, rb.x0) + 6, min(ra.x1, rb.x1) - 6
                if lo <= hi:
                    x = min(max(ra.cx, lo), hi) if not e.a.ptr else ra.cx
                    if lo <= x <= hi:
                        pa, pb = (x, pa[1]), (x, pb[1])
        if not e.a.ptr:
            pa = _add(pa, da, e.a.offset(e.sa_))
        pb = _add(pb, db, e.b.offset(e.sb_))
        own_a = e.a.owner.uid if e.a.owner else None
        own_b = e.b.owner.uid if e.b.owner else None
        if e.a.ptr:
            pa = _pt(ra, e.sa_, 0.5)
        if e.route in ("hv", "vh"):
            c = (pb[0], pa[1]) if e.route == "hv" else (pa[0], pb[1])
            pts = simplify([pa, c, pb])
        else:
            need = _label_size(d, e)[0] + 16 if e.label else 0
            pts = R.route(pa, da, pb, db, own_a, own_b, need)
        if e.a.ptr:
            pts = simplify([(ra.cx, ra.cy)] + pts)
        e.pts = pts
        R.segs += [(sg, _key(pts[-1])) for sg in _segs(pts)]
    _place_labels(d, edges, obstacles)


def _key(p):
    return (round(p[0]), round(p[1]))


def _is_ortho(pts):
    return all(abs(a[0] - b[0]) < 0.01 or abs(a[1] - b[1]) < 0.01 for a, b in _segs(pts))


def _via(e):
    pts = [e.a.rect.side(e.sa, 0.5) if e.sa else None]
    via = list(e.via)
    first = pts[0] or _clip(e.a.shape(), e.a.rect, via[0])
    if pts[0] is None and e.a.shape() == "rect":
        # leave perpendicular: pick the side facing the first via point
        r = e.a.rect
        p = via[0]
        if r.x0 <= p[0] <= r.x1:
            first = (p[0], r.y1 if p[1] > r.cy else r.y0)
        elif r.y0 <= p[1] <= r.y1:
            first = (r.x1 if p[0] > r.cx else r.x0, p[1])
    rb = e.b.rect
    last_hint = via[-1]
    if e.sb:
        last = rb.side(e.sb, 0.5)
    elif e.b.shape() == "rect" and rb.x0 <= last_hint[0] <= rb.x1:
        last = (last_hint[0], rb.y0 if last_hint[1] < rb.cy else rb.y1)
    elif e.b.shape() == "rect" and rb.y0 <= last_hint[1] <= rb.y1:
        last = (rb.x0 if last_hint[0] < rb.cx else rb.x1, last_hint[1])
    else:
        last = _clip(e.b.shape(), rb, last_hint)
    raw = [first] + via + [last]
    out = [raw[0]]
    for p in raw[1:]:
        a = out[-1]
        if abs(a[0] - p[0]) > 0.01 and abs(a[1] - p[1]) > 0.01:
            out.append((p[0], a[1]))
        out.append(p)
    if e.a.ptr:
        out = [(e.a.rect.cx, e.a.rect.cy)] + out
    return simplify(out)


def _center(e):
    """Short arrow from center to center, trimmed at both ends: dependencies between neighbouring table / grid
    cells, which share a border so a border-to-border line would have no length."""
    ca, cb = (e.a.rect.cx, e.a.rect.cy), (e.b.rect.cx, e.b.rect.cy)
    dx, dy = cb[0] - ca[0], cb[1] - ca[1]
    L = math.hypot(dx, dy) or 1
    k = min(7 + 5 * abs(dx) / L, L / 3)   # clear the cell's text: wider sideways than up/down
    return [(ca[0] + dx / L * k, ca[1] + dy / L * k), (cb[0] - dx / L * k, cb[1] - dy / L * k)]


def _straight(e, edges):
    ra, rb = e.a.rect, e.b.rect
    ca, cb = (ra.cx, ra.cy), (rb.cx, rb.cy)
    if e.via:
        pts = [_clip(e.a.shape(), ra, e.via[0])] + list(e.via) + [_clip(e.b.shape(), rb, e.via[-1])]
        return pts
    off = 0.0
    for o in edges:
        if o is not e and o.route == "straight" and o.a.uid == e.b.uid and o.b.uid == e.a.uid:
            off = 5.0
    dx, dy = cb[0] - ca[0], cb[1] - ca[1]
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L * off, dx / L * off
    ca2, cb2 = (ca[0] + nx, ca[1] + ny), (cb[0] + nx, cb[1] + ny)
    p0 = _clip(e.a.shape(), ra, cb2)
    p1 = _clip(e.b.shape(), rb, ca2)
    return [(p0[0] + nx, p0[1] + ny), (p1[0] + nx, p1[1] + ny)]


# ------------------------------------------------------------------------------------------ labels

def _label_size(d, e):
    Z = d.T["size"]
    font = "mono" if e.mono else "sans"
    size = Z["mono_small"] if e.mono else Z["label"]
    w = d.tw(e.label, size, font, 500) if e.label else 0
    bw = 20 if e.step is not None else 0
    if not e.label:
        return bw - 4, 16, font, size
    return w + bw + 6, 16, font, size


def _place_labels(d, edges, obstacles):
    """Put each label beside its own line, clear of boxes, other labels, other lines and group borders.
    Candidates slide along every segment; the cheapest one wins."""
    placed = []
    all_segs = [(e, s) for e in edges for s in _segs(e.pts or [])]
    obs = [r for r, _ in obstacles]
    borders = [el.rect for el in d.els if el.prefix == "group"]
    for e in edges:
        if not e.label and e.step is None:
            continue
        w, h, font, size = _label_size(d, e)
        segs = _segs(e.pts)
        if e.label is None:
            # badge only: sits on the line, in the middle of the longest segment
            a, b = max(segs, key=lambda s: math.dist(*s))
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            e.lab = {"rect": Rect(m[0] - 9, m[1] - 9, 18, 18), "badge_only": True, "font": font, "size": size}
            placed.append(e.lab["rect"])
            continue
        total = sum(math.dist(*s) for s in segs)
        target = (e.label_at if e.label_at is not None else 0.5) * total
        cands = []  # (rect, distance from the preferred spot along the path)
        acc = 0.0
        for a, b in segs:
            L = math.dist(a, b)
            if L < 1:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            horiz, vert = abs(uy) < 0.01, abs(ux) < 0.01
            along = w if horiz else h
            lo, hi = along / 2 + 6, L - along / 2 - 6
            ts = [L / 2] if hi <= lo else [lo + (hi - lo) * k / max(1, int((hi - lo) / 10)) for k in
                                           range(int((hi - lo) / 10) + 1)]
            for t in ts:
                p = (a[0] + ux * t, a[1] + uy * t)
                if horiz:
                    opts = [Rect(p[0] - w / 2, p[1] - 7 - h, w, h), Rect(p[0] - w / 2, p[1] + 7, w, h)]
                elif vert:
                    opts = [Rect(p[0] + 9, p[1] - h / 2, w, h), Rect(p[0] - 9 - w, p[1] - h / 2, w, h)]
                else:
                    nx, ny = -uy, ux
                    off = 6 + abs(nx) * w / 2 + abs(ny) * h / 2
                    opts = [Rect(p[0] + nx * off * sg - w / 2, p[1] + ny * off * sg - h / 2, w, h) for sg in (1, -1)]
                for k, r in enumerate(opts):
                    cands.append((r, abs(acc + t - target) + k * 4, "h" if horiz else ("v" if vert else "")))
            acc += L
        best, bs = None, None
        for r, dist, host in cands:
            rr = r.inflate(3)
            score = dist * (1.0 if e.label_at is not None else 0.15)   # an explicit label_at is a strong wish
            # squeezed between this line and a parallel neighbour → ambiguous; prefer the outer side
            for oe, (a, b) in all_segs:
                if oe is e:
                    continue
                if host == "h" and abs(a[1] - b[1]) < 0.01 and r.y0 - 14 < a[1] < r.y1 + 14 \
                        and min(a[0], b[0]) < r.x1 and max(a[0], b[0]) > r.x0:
                    score += 60
                elif host == "v" and abs(a[0] - b[0]) < 0.01 and r.x0 - 14 < a[0] < r.x1 + 14 \
                        and min(a[1], b[1]) < r.y1 and max(a[1], b[1]) > r.y0:
                    score += 60
            score += sum(400 for o in obs if rr.hits(o))
            score += sum(400 for o in placed if rr.hits(o))
            score += sum(150 for g in borders if rr.hits(g) and not g.contains(rr))
            for oe, (a, b) in all_segs:
                if seg_hits_rect(a, b, r.inflate(1)):
                    score += 150 if oe is not e else 250
            if best is None or score < bs:
                best, bs = r, score
        e.lab = {"rect": best, "font": font, "size": size, "badge_only": False}
        placed.append(best)


# ------------------------------------------------------------------------------------------ emission

def emit(S, e):
    T, C = S.T, S.T["color"]
    st = S.unit(e.id, (e.a.uid, e.b.uid, e.style), None, shape="path", pts=e.pts, text=e.label,
                explicit=e.state)
    col, _, ink = S.style(st, e.tone)
    col = col or C["edge"]
    ink = ink or C["ink2"]
    sw = e.width or (1.75 if st in ("accent", "focus", "changed", "new", "error") else T["look"]["edge_w"])
    dash = {"dashed": "5 4", "dotted": "1.5 3.5"}.get(e.style)
    if st == "removed":
        dash = "4 4"
    pts = list(e.pts)
    L = T["look"]["arrow"] + (1 if sw > 1.5 else 0)
    ends = []
    if e.arrow in ("end", "both") and len(pts) >= 2:
        ends.append(("end", pts[-1], pts[-2]))
    if e.arrow in ("start", "both") and len(pts) >= 2:
        ends.append(("start", pts[0], pts[1]))
    draw = list(pts)
    for which, tip, prev in ends:
        dx, dy = tip[0] - prev[0], tip[1] - prev[1]
        n = math.hypot(dx, dy) or 1
        u = (dx / n, dy / n)
        cut = (tip[0] - u[0] * (L - 1.5), tip[1] - u[1] * (L - 1.5))
        if which == "end":
            draw[-1] = cut
        else:
            draw[0] = cut
        S.arrow(tip, u, col, L, z=5.7 if e.route == "center" else 3.5, owner=e.id)
    corner = 0 if e.route in ("straight", "center") else None
    z = 5.6 if e.route == "center" else 3     # center arrows live inside cells, so above them
    S.path(draw, col, sw, dash, z=z, role="edge", owner=e.id, corner=corner)
    if e.a.ptr and len(pts) >= 2:
        # the stub inside the pointer cell is drawn above the cell so the line visibly starts at the dot
        S.path(pts[:2], col, sw, None, z=5.4, role="edge-stub", owner=e.id, corner=0)
    if e.lab:
        r = e.lab["rect"]
        if e.lab["badge_only"]:
            S.circle(r.cx, r.cy, 8, fill=col if st else C["ink"], stroke=C["paper"], sw=1.5, z=6, role="badge",
                     owner=e.id)
            S.text(r.cx, r.cy + 3.3, str(e.step), 9.5, "mono", 600, C["paper"], "middle", z=6.1, role="badge-text",
                   owner=e.id)
            return
        # the label diffs on its own: new text → the label is highlighted, not the whole edge
        lst = S.unit(e.id + "#label", (e.label,), None, shape="none", text=e.label)
        lfill, link = C["paper"], ink
        if lst and not st:
            _, lfill, link = S.style(lst)
        S.rect(r.inflate(2, 1), rx=3, fill=lfill, z=5.9, role="label-mask", owner=e.id)
        x = r.x0
        if e.step is not None:
            S.circle(x + 8, r.cy, 8, fill=col if st else C["ink"], z=6, role="badge", owner=e.id)
            S.text(x + 8, r.cy + 3.3, str(e.step), 9.5, "mono", 600, C["paper"], "middle", z=6.1, role="badge-text",
                   owner=e.id)
            x += 20
        S.text(x + 3, r.cy + e.lab["size"] * 0.35, e.label, e.lab["size"], e.lab["font"], 500, link, z=6.1,
               role="label", owner=e.id)
