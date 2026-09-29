"""Orthogonal router for non-tree links (loops, extra NICs): A* on a sparse grid around obstacles.

The grid holds every coordinate that matters exactly (exit points, obstacle edges ± clearance, existing
link lines) plus uniform samples, so results are exact orthogonal polylines. Cost = length + a penalty per
bend + a penalty per crossing of an existing link; running along an existing link or through an obstacle is
not allowed. The path ends perpendicular to the target bar's long axis, on its edge, away from its ends.
"""
import heapq
from bisect import bisect_left, bisect_right

SAMPLE = 14     # uniform grid spacing
CLEAR = 10      # clearance kept around obstacles
BEND = 40
CROSS = 60
END_IN = 16     # stay this far from the bar's rounded ends


def route(exits, bar, obstacles, lines, bounds, own=None):
    """exits: [(x, y, dx, dy)] points on the node outline with outward unit direction.
    bar: (x0, y0, x1, y1) target segment bar (horizontal if wider than tall).
    obstacles: boxes to keep clear of (padded here by CLEAR); lines: existing orthogonal segments
    [((x0, y0), (x1, y1))]; bounds: (x0, y0, x1, y1) search area. Returns [(x, y)…] or None."""
    bx0, by0, bx1, by1 = bar
    horiz = bx1 - bx0 >= by1 - by0
    boxes = [(a - CLEAR, b - CLEAR, c + CLEAR, d + CLEAR) for a, b, c, d in obstacles] + [bar] + ([own] if own else [])
    X0, Y0, X1, Y1 = bounds

    xs = {round(X0 + i * SAMPLE, 1) for i in range(int((X1 - X0) / SAMPLE) + 1)}
    ys = {round(Y0 + i * SAMPLE, 1) for i in range(int((Y1 - Y0) / SAMPLE) + 1)}
    for a, b, c, d in boxes:
        xs |= {a, c}
        ys |= {b, d}
    for x, y, _, _ in exits:
        xs.add(x)
        ys.add(y)
    for (a, b), (c, d) in lines:
        (xs if a == c else ys).add(a if a == c else b)
    xs |= {bx0, bx1}
    ys |= {by0, by1}
    xs = sorted(v for v in xs if X0 <= v <= X1)
    ys = sorted(v for v in ys if Y0 <= v <= Y1)
    xi = {v: i for i, v in enumerate(xs)}
    yi = {v: i for i, v in enumerate(ys)}
    nx, ny = len(xs), len(ys)

    blocked = bytearray(nx * ny)  # grid point strictly inside a box
    for a, b, c, d in boxes:
        for i in range(bisect_right(xs, a), bisect_left(xs, c)):
            for j in range(bisect_right(ys, b), bisect_left(ys, d)):
                blocked[i * ny + j] = 1
    vline = bytearray(nx * ny)    # grid point lies on an existing vertical / horizontal link
    hline = bytearray(nx * ny)
    for (a, b), (c, d) in lines:
        if a == c and a in xi:
            i = xi[a]
            for j in range(bisect_left(ys, min(b, d)), bisect_right(ys, max(b, d))):
                vline[i * ny + j] = 1
        elif b == d and b in yi:
            j = yi[b]
            for i in range(bisect_left(xs, min(a, c)), bisect_right(xs, max(a, c))):
                hline[i * ny + j] = 1

    def goal(i, j, di, dj):
        x, y = xs[i], ys[j]
        if horiz:
            return (dj == 1 and y == by0 or dj == -1 and y == by1) and bx0 + END_IN <= x <= bx1 - END_IN
        return (di == 1 and x == bx0 or di == -1 and x == bx1) and by0 + END_IN <= y <= by1 - END_IN

    def h(i, j):
        x, y = xs[i], ys[j]
        return max(bx0 - x, 0, x - bx1) + max(by0 - y, 0, y - by1)

    heap, best, prev = [], {}, {}
    for x, y, dx, dy in exits:
        if x in xi and y in yi:
            s = (xi[x], yi[y], int(dx), int(dy))
            best[s] = 0
            prev[s] = None
            heapq.heappush(heap, (h(s[0], s[1]), 0, s))
    while heap:
        _, g, s = heapq.heappop(heap)
        if g > best.get(s, 1e18):
            continue
        i, j, di, dj = s
        if goal(i, j, di, dj):
            return _path(s, prev, xs, ys)
        turns = ((di, dj),) if prev[s] is None else ((di, dj), (dj, di), (-dj, -di))  # leave exits straight
        for ndi, ndj in turns:  # straight, or turn left/right
            ni, nj = i + ndi, j + ndj
            if not (0 <= ni < nx and 0 <= nj < ny):
                continue
            k = ni * ny + nj
            if blocked[k] and not goal(ni, nj, ndi, ndj):
                continue
            along, across = (hline, vline) if ndj == 0 else (vline, hline)
            if along[k] and along[i * ny + j]:
                continue  # never run on top of an existing link
            cost = g + abs(xs[ni] - xs[i]) + abs(ys[nj] - ys[j])
            cost += BEND if (ndi, ndj) != (di, dj) else 0
            cost += CROSS if across[k] else 0
            t = (ni, nj, ndi, ndj)
            if cost < best.get(t, 1e18):
                best[t], prev[t] = cost, s
                heapq.heappush(heap, (cost + h(ni, nj), cost, t))
    return None


def _path(s, prev, xs, ys):
    pts = []
    while s is not None:
        pts.append((xs[s[0]], ys[s[1]]))
        s = prev[s]
    pts.reverse()
    out = [pts[0]]  # keep only the corners
    for a, b in zip(pts[1:], pts[2:] + [None]):
        if b is None or not (out[-1][0] == a[0] == b[0] or out[-1][1] == a[1] == b[1]):
            out.append(a)
    return out


def exits(shape):
    """Exit points of a node outline: icon (ellipse) → 4 side midpoints + 4 off-centre; card (rect) → top/bottom at
    three positions and both side midpoints."""
    if shape[0] == "ellipse":
        _, x, y, rx, ry = shape
        out = [(x, y - ry, 0, -1), (x, y + ry, 0, 1), (x - rx, y, -1, 0), (x + rx, y, 1, 0)]
        for k in (-0.5, 0.5):  # off-centre exits on top/bottom, for when the middle ones are taken
            out += [(x + k * rx, y - 0.87 * ry, 0, -1), (x + k * rx, y + 0.87 * ry, 0, 1)]
        return out
    _, a, b, c, d = shape
    xm, ym = (a + c) / 2, (b + d) / 2
    out = [(a, ym, -1, 0), (c, ym, 1, 0)]
    for x in (a + 24, xm, c - 24):
        out += [(x, b, 0, -1), (x, d, 0, 1)]
    return out


def segments(pts):
    return list(zip(pts, pts[1:]))
