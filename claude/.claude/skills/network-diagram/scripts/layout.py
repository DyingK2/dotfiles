"""Layout: model → list of positioned graphic elements (scene). Rules in resources/style-guide.md.

scene = {"width", "height", "items": [ {z, el, role, owner, group, ...attrs} ], "warnings": [...]}
svg_writer.py is responsible for serializing items to SVG.
"""
from collections import deque

import icons
import route as router
from i18n import T, use
from text_metrics import ASC, DESC, text_box, text_width

AREA_X0, AREA_X1 = 40, 760
DIVIDER_X, PANEL_X, PANEL_W = 775, 790, 280
CANVAS_W = 1100
TOP = 30
ICON = {}  # kind → (width, height); layout() fills this in per theme, preserving icon aspect ratio
BAR_H, CARD_H, CARD_MIN_W = 24, 58, 180
# Look parameters (theme.json "look" block overrides these defaults)
LOOK_DEFAULT = {"seg_h": 26, "seg_rx": 13, "card_h": 56, "card_rx": 12, "card_stroke": "#e5e5ea", "corner": 10,
                "arrow_size": 4.2}
LOOK = dict(LOOK_DEFAULT)
FLOW_OFF = 0  # flow lines run on top of their links
PAD = 4
MAX_SLOT = 380
COMB_IN, COMB_GAP = 40, 14  # comb: spine → card gap, vertical gap between stacked cards
Z = {"link": 1, "flow": 2, "seg": 3, "node": 4, "leader": 5, "annot": 6, "label": 7, "panel": 9}


# ---------------------------------------------------------------- collision registry
class Reg:
    def __init__(self, wall=DIVIDER_X, x_min=AREA_X0 - 20, y_min=TOP - 10):
        self.boxes, self.wall, self.x_min, self.y_min = [], wall, x_min, y_min

    def add(self, box, kind, owner=None):
        self.boxes.append((box, kind, owner))

    def line(self, pts, kind, owner=None, w=1.5):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            self.add((min(x0, x1) - w, min(y0, y1) - w, max(x0, x1) + w, max(y0, y1) + w), kind, owner)

    def free(self, box, pad=PAD, ignore=(), ignore_kinds=()):
        x0, y0, x1, y1 = box
        if x0 < self.x_min or x1 > self.wall - 10 or y0 < self.y_min:
            return False
        for (a0, b0, a1, b1), kind, owner in self.boxes:
            if (kind, owner) in ignore or kind in ignore_kinds:
                continue
            if x0 < a1 + pad and a0 < x1 + pad and y0 < b1 + pad and b0 < y1 + pad:
                return False
        return True


# ---------------------------------------------------------------- structure
def _graph(model):
    nodes = {n["id"]: n for n in model["nodes"] if "l3" in n["views"]}
    segs = {s["id"]: s for s in model["segments"]}
    adj = {("n", i): [] for i in nodes} | {("s", i): [] for i in segs}
    for n in nodes.values():
        for f in n["ifaces"]:
            adj[("n", n["id"])].append(("s", f["seg"]))
            adj[("s", f["seg"])].append(("n", n["id"]))
    root = next((("n", i) for i, n in nodes.items() if n["kind"] == "cloud"), ("n", next(iter(nodes))))
    # BFS by layers; a segment reachable from several devices at the same depth hangs under a router
    # rather than a host (hosts are not transit), otherwise under the first one found
    host = lambda k: k[0] == "n" and nodes[k[1]]["kind"] not in ("router", "cloud")
    layer, parent, children = {root: 0}, {root: None}, {root: []}
    frontier = [root]
    while frontier:
        nxt = []
        for u in frontier:
            for v in adj[u]:
                if v not in layer:
                    layer[v], parent[v] = layer[u] + 1, u
                    nxt.append(v)
                elif layer[v] == layer[u] + 1 and v[0] == "s" and host(parent[v]) and not host(u):
                    parent[v] = u
        for v in nxt:
            children[v] = []
        for v in nxt:
            children[parent[v]].append(v)
        frontier = nxt
    return nodes, segs, adj, root, layer, children


def _seg_text(s):
    cidr = "DHCP" if s["cidr"] == "dhcp" else s["cidr"]
    return f"{s['id']} · {s['label']} · {cidr}"


def _host_lines(n):
    f = n["ifaces"][0] if n["ifaces"] else {}
    ip = f.get("ip") or ""
    return n["label"], (f"{ip} · gw {f['gw_short']}" if f.get("gw_short") else ip)


def _card_w(n, t):
    name, ip = _host_lines(n)
    return max(CARD_MIN_W, 56 + max(text_width(name, t["size"]["name"], bold=True),
                                     text_width(ip, t["size"]["small"])) + 18)


def _elem_h(key, nodes):
    t, i = key
    if t == "s":
        return BAR_H
    k = nodes[i]["kind"]
    return ICON[k][1] if k in ICON else CARD_H


# ---------------------------------------------------------------- main flow
def init(theme):
    """Fill icon sizes and look parameters from theme.json (shared by both layout directions)."""
    global BAR_H, CARD_H
    ICON.clear()
    ICON.update(icons.icon_dims(theme))
    LOOK.clear()
    LOOK.update(LOOK_DEFAULT, **theme.get("look", {}))
    BAR_H, CARD_H = LOOK["seg_h"], LOOK["card_h"]


def layout(model, theme):
    """Re-layout repeatedly: widen row spacing for rows that don't fit / need a leader line, keep the best
    version (not the last one)."""
    init(theme)
    use(model)
    extra, best = {}, None
    for _ in range(8):
        scene, fails = _layout_once(model, theme, extra)
        q = sum(p for _, p in fails) + 0.05 * scene["height"] + 0.02 * scene["width"]
        if best is None or q < best[0]:
            best = (q, scene, fails)
        if not fails:
            break
        extra = dict(extra)
        if scene["spill"] > 0:  # a fallback label crossed the divider: widen instead of clipping
            extra["w"] = extra.get("w", 0) + scene["spill"] + 12
        for row in {r for r, _ in fails}:
            extra[row] = extra.get(row, 0) + 24
    _, scene, fails = best
    scene["warnings"] += [f"row {r}: annotation/label has no conflict-free spot, used fallback position" for r in sorted({r for r, p in fails if p >= 1000})]
    return scene


def _layout_once(model, t, extra):
    nodes, segs, adj, root, layer, children = _graph(model)
    items, fails = [], []
    S = t["size"]

    par = {c: p for p, cs in children.items() for c in cs}
    is_card = lambda k: k[0] == "n" and nodes[k[1]]["kind"] not in ICON

    # ---- columns (x): leaf slots, parent nodes centered. A leaf segment with several hosts can be drawn as a
    # comb (hosts stacked under the bar, hanging off a spine) — used only when side-by-side is too wide.
    def min_w(k):
        if k in comb:
            return max(text_width(_seg_text(segs[k[1]]), S["seg"], bold=True) + 48,
                       20 + COMB_IN + max(_card_w(nodes[c[1]], t) for c in children[k])) + 40
        if k[0] == "s":
            return text_width(_seg_text(segs[k[1]]), S["seg"], bold=True) + 48 + 40
        n = nodes[k[1]]
        return _card_w(n, t) + 40 if n["kind"] not in ICON else 200

    def measure(k):
        if k in comb:
            width[k] = max(base, min_w(k))
            return width[k]
        own = max(base, min_w(k)) if not children[k] else 0
        width[k] = max(own, sum(measure(c) for c in children[k]), min_w(k))
        return width[k]

    def run():
        leaves = [k for k in layer if k in comb or not children[k] and par.get(k) not in comb]
        return min(MAX_SLOT, (AREA_X1 - AREA_X0) / max(1, len(leaves)))

    comb, width = set(), {}
    base = run()
    total = measure(root)
    if total > AREA_X1 - AREA_X0:
        comb = {k for k in layer if k[0] == "s" and len(children[k]) >= 2
                and all(is_card(c) and not children[c] for c in children[k])}
        if comb:
            width = {}
            base = run()
            total = measure(root)
    stacked = {c: i for k in comb for i, c in enumerate(children[k])}

    # ---- rows (y)
    nrows = max(layer.values()) + 1
    rows = [[k for k, l in layer.items() if l == r] for r in range(nrows)]
    row_h = [max(_elem_h(k, nodes) for k in row) for row in rows]
    for k in comb:
        r = layer[children[k][0]]
        row_h[r] = max(row_h[r], len(children[k]) * (CARD_H + COMB_GAP) - COMB_GAP)
    branchy = set()  # rows with a horizontal branch going down
    row_top, y = [], TOP
    for r in range(nrows):
        row_top.append(y)
        gap = 36
        if r + 1 < nrows:
            labelled = any(k[0] == "n" and nodes[k[1]]["kind"] != "cloud" for k in rows[r] + rows[r + 1])
            if labelled:
                gap = 42
            if any(k[0] == "n" and len([c for c in children[k] if c[0] == "s"]) > 1 for k in rows[r]):
                gap = 66
                branchy.add(r)
        y += row_h[r] + gap + extra.get(r, 0)
    cy = {k: row_top[layer[k]] + row_h[layer[k]] / 2 for k in layer}
    for k in layer:  # cards: top-aligned in their row; stacked ones one under another
        if is_card(k):
            cy[k] = row_top[layer[k]] + CARD_H / 2 + stacked.get(k, 0) * (CARD_H + COMB_GAP)

    cx = {}

    def place(k, x0):
        kids = children[k]
        if not kids or k in comb:
            cx[k] = x0 + width[k] / 2
            return
        inner = sum(width[c] for c in kids)
        x = x0 + (width[k] - inner) / 2
        for c in kids:
            place(c, x)
            x += width[c]
        cx[k] = (cx[kids[0]] + cx[kids[-1]]) / 2

    # widen the canvas when the topology area doesn't fit; shift the side panel right accordingly
    # extra["w"]: more room on the right when labels spilled into the divider on a previous pass
    base = max(0, total - (AREA_X1 - AREA_X0))
    shift = base + extra.get("w", 0)
    place(root, (AREA_X0 + AREA_X1 + base) / 2 - total / 2)
    reg = Reg(DIVIDER_X + shift)

    # ---- segment bars
    bar, spine = {}, {}
    for k in layer:
        if k[0] != "s":
            continue
        s = segs[k[1]]
        tw = text_width(_seg_text(s), S["seg"], bold=True)
        leaf = all(nodes[c[1]]["kind"] not in ICON for c in children[k]) if children[k] else True
        w = max(tw + 48, width[k] * 0.8 if leaf else min(width[k] * 0.7, 520))
        w = min(w, max(width[k] - 20, tw + 48))
        # only span the child nodes (devices hanging down from this segment); parent devices connect via a branch line
        attached = [cx[n] for n in children[k] if n in cx] or [cx[k]]
        x0 = min(cx[k] - w / 2, min(attached) - 40)
        x1 = max(cx[k] + w / 2, max(attached) + 40)
        if k in comb:  # comb: bar across the slot, spine near its left end, cards to the right of the spine
            x0, x1 = cx[k] - width[k] / 2 + 20, cx[k] + width[k] / 2 - 20
            spine[k[1]] = x0 + 20
            for c in children[k]:
                cx[c] = spine[k[1]] + COMB_IN + _card_w(nodes[c[1]], t) / 2
        top = row_top[layer[k]]
        bar[k[1]] = (x0, top, x1, top + BAR_H)
        role = t["roles"].get(s["role"], t["roles"]["default"])
        g = f"seg-{s['id']}"
        items.append(dict(z=Z["seg"], el="rect", role="seg", owner=s["id"], group=g, x=x0, y=top, width=x1 - x0,
                          height=BAR_H, rx=LOOK["seg_rx"], fill=role["tint"]))
        seg_text = dict(z=Z["seg"], el="text", role="seg", owner=s["id"], group=g, x=(x0 + x1) / 2,
                        y=top + BAR_H / 2 + 4.5, anchor="middle", cls="seg", text=_seg_text(s))
        cidr = "DHCP" if s["cidr"] == "dhcp" else s["cidr"]  # split by weight: bridge bold, role light, CIDR
        seg_text["spans"] = [(s["id"], "sgb"), (f"  {s['label']}  ", "sgl"), (cidr, "sgc")]
        seg_text["fill"] = role["ink"]
        items.append(seg_text)
        reg.add(bar[s["id"]], "seg", s["id"])

    # ---- nodes
    shape = {}  # id → ("ellipse", cx, cy, rx, ry) | ("rect", x0, y0, x1, y1)
    for k in layer:
        if k[0] == "n":
            draw_node(items, reg, shape, nodes[k[1]], cx[k], cy[k], t, segs)

    # ---- links (node → segment bar); record geometry for flow lines and labels to use
    # tree edges use the fixed shapes; non-tree edges (loops, extra NICs) are routed around obstacles
    tree = {(p, c) for p, cs in children.items() for c in cs}
    edges = [(("n", n["id"]), f) for n in nodes.values() if ("n", n["id"]) in layer for f in n["ifaces"]]
    is_tree = lambda k, f: (k, ("s", f["seg"])) in tree or (("s", f["seg"]), k) in tree
    edges.sort(key=lambda e: not is_tree(*e))
    bottom = max(b[3] for b, _, _ in reg.boxes)
    links, drawn, routed, combed = {}, [], set(), set()
    for k, f in edges:
        n = nodes[k[1]]
        b = bar[f["seg"]]
        pts, side = _link(shape[n["id"]], b)
        if k in stacked and f["seg"] in spine and par[k] == ("s", f["seg"]):  # comb: stub → spine → bar
            x0_, yc = shape[n["id"]][1], cy[k]
            pts, side = [(x0_, yc), (spine[f["seg"]], yc), (spine[f["seg"]], b[3])], -1
            combed.add((n["id"], f["seg"]))
        elif not is_tree(k, f) and len(pts) > 2:
            r = cross_link(shape[n["id"]], b, n["id"], f["seg"], reg, drawn,
                           (AREA_X0 - 20, TOP - 10, reg.wall - 10, bottom + 60))
            if r:
                (pts, side), _ = r, routed.add((n["id"], f["seg"]))
        links[(n["id"], f["seg"])] = (pts, side, f)
        drawn += router.segments(pts)
        items.append(dict(z=Z["link"], el="path", role="link", owner=n["id"], d=_d(pts), pts=pts, cls="ln"))
        reg.line(pts, "link", n["id"])

    # ---- flow lines (follow the hop-by-hop path, offset to the right-hand side, segments stop at node edges)
    captions = []
    for fl in model["flows"]:
        hops = fl["hops"]
        for i in range(0, len(hops) - 2, 2):
            a, s, b = hops[i]["id"], hops[i + 1]["id"], hops[i + 2]["id"]
            pa, pb = links[(a, s)][0], links[(b, s)][0]
            ym = (bar[s][1] + bar[s][3]) / 2
            pts = _simplify(pa + [(pa[-1][0], ym), (pb[-1][0], ym)] + pb[::-1])
            off = _offset(pts, FLOW_OFF)
            for j in range(len(pts) - 1):  # keep horizontal segments inside the bar on its centerline, no offset
                if abs(pts[j][1] - ym) < 0.01 and abs(pts[j + 1][1] - ym) < 0.01:
                    off[j], off[j + 1] = (off[j][0], ym), (off[j + 1][0], ym)
            pts = _trim(off, 2, 4)
            items.append(dict(z=Z["flow"], el="path", role="flow", owner=fl["from"], d=_d(pts), pts=pts,
                              cls="flowhalo"))  # highlighter-style translucent band
            items.append(dict(z=Z["flow"], el="path", role="flow", owner=fl["from"], d=_d(pts), pts=pts, cls="flow",
                              marker="url(#ar)"))
            reg.line(pts, "flow", fl["from"])
        captions.append(_caption(fl, nodes))

    # ---- device names
    for k in layer:
        if k[0] != "n" or nodes[k[1]]["kind"] not in ICON:
            continue
        n = nodes[k[1]]
        x, yc = cx[k], cy[k]
        r, ry = ICON[n["kind"]][0] / 2, ICON[n["kind"]][1] / 2
        if n["kind"] == "cloud":
            lines = [(n["label"], "tb", S["name"], False, True)]
            cands = [(x + r + 10, yc + 5, "start"), (x - r - 10, yc + 5, "end")]
        else:
            lines = [(n["label"], "tb", S["name"], False, True)] + ([(n["sub"], "ts", S["small"], False, False)]
                                                                    if n.get("sub") else [])
            cands = [(x + r + 12, yc - 6, "start"), (x + r + 12, yc - 27, "start"), (x + r + 12, yc - 40, "start"), (x + r + 12, yc + 22, "start"),
                     (x - r - 12, yc - 6, "end"), (x - r - 12, yc - 27, "end")]
        _place_block(items, reg, lines, cands, "label", n["id"], fails, layer[k])

    # ---- interface labels
    for (nid, sid), (pts, side, f) in links.items():
        n = nodes[nid]
        if n["kind"] == "cloud":
            continue
        ip = f.get("ip")
        text = f["name"] if n["kind"] not in ICON else f"{f['name']} · {'DHCP' if ip == 'dhcp' else ip}"
        if (nid, sid) in combed:  # comb stub: label above (or below) the short horizontal stub
            (xa, yc), (xb, _) = pts[0], pts[1]
            cands = [((xa + xb) / 2, yc - 7, "middle"), ((xa + xb) / 2, yc + 16, "middle")]
            _place_block(items, reg, [(text, "if", S["iface"], False, False)], cands, "if-label", nid, fails,
                         layer[("n", nid)])
            continue
        if (nid, sid) in routed:  # routed link: label beside its first run, next to the device it belongs to
            _label_runs(items, reg, text, pts, S, nid, fails, layer[("n", nid)])
            continue
        (vx, vy0), (_, vy1) = pts[-2], pts[-1]
        lo, hi = sorted((vy0, vy1))
        if n["kind"] in ICON and len(pts) > 2 and hi > shape[nid][2] + shape[nid][4]:  # branch: below the icon
            lo = max(lo, shape[nid][2] + shape[nid][4])
        mid = (lo + hi) / 2 + 4
        order = [side, -side] if side else [-1, 1]
        cands = [(vx + d * 10, mid + dy, "end" if d < 0 else "start") for d in order for dy in (0, -8, 8, -14, 14)]
        cands += [(vx + d * g, mid + dy, "end" if d < 0 else "start") for g in (26, 40) for d in order for dy in (0, -8, 8)]
        _place_block(items, reg, [(text, "if", S["iface"], False, False)], cands, "if-label", nid, fails,
                     layer[("n", nid)])

    # ---- route / policy annotations
    for k in layer:
        if k[0] != "n":
            continue
        n = nodes[k[1]]
        lines = [r["text"] for r in n["routes"]] + n["notes"]
        if not lines or n["kind"] not in ICON:
            continue
        _place_annot(items, reg, n, lines, cx[k], cy[k], (ICON[n["kind"]][0] / 2, ICON[n["kind"]][1] / 2), S, fails, layer[k])

    # ---- bottom captions
    bottom = max(b[3] for b, _, _ in reg.boxes)
    root_x = cx[root]
    y = bottom + 34
    lo, hi = AREA_X0, reg.wall - 10  # captions stay inside the topology area: clamp, wrap at arrows
    for c in captions:
        for line in _wrap(c, S["small"], hi - lo):
            w = text_width(line, S["small"])
            x = min(max(root_x, lo + w / 2), hi - w / 2)
            items.append(dict(z=Z["label"], el="text", role="label", owner="caption", x=x, y=y, anchor="middle",
                              cls="ts", text=line))
            y += 20
    topo_bottom = y

    cols = _plan_cols(model, t)
    pw = _panel_w(model, t, nodes, cols)
    panel_bottom = _panel(items, model, t, nodes, shift, pw, cols)
    height = max(topo_bottom, panel_bottom + 30) + 10
    items.append(dict(z=Z["panel"], el="line", role="panel", owner="divider", group="divider", x1=DIVIDER_X + shift, y1=TOP,
                      x2=DIVIDER_X + shift, y2=height - 30, stroke=t["panel"]["divider"], sw=1.5))
    spill = max(b[2] for b, k, _ in reg.boxes if k != "panel") - (reg.wall - 10)
    return {"width": round(CANVAS_W + shift + pw - PANEL_W), "height": round(height), "items": items, "warnings": [],
            "spill": spill}, fails


def draw_node(items, reg, shape, n, x, yc, t, segs):
    """Draw one node (icon or host card), registering its collision box and shape."""
    if n["kind"] in ICON:
        iw, ih = ICON[n["kind"]]
        shape[n["id"]] = ("ellipse", x, yc, iw / 2, ih / 2)
        items.append(dict(z=Z["node"], el="use", role="icon", owner=n["id"], href=f"#ic-{n['kind']}",
                          x=x - iw / 2, y=yc - ih / 2, width=iw, height=ih))
        reg.add((x - iw / 2, yc - ih / 2, x + iw / 2, yc + ih / 2), "icon", n["id"])
    else:
        w = _card_w(n, t)
        x0, y0 = x - w / 2, yc - CARD_H / 2
        seg0 = n["ifaces"][0]["seg"] if n["ifaces"] else None
        role = t["roles"].get(segs[seg0]["role"] if seg0 else "default", t["roles"]["default"])
        name, ip = _host_lines(n)
        g = f"card-{n['id']}"
        ty = y0 + (CARD_H - 32) / 2  # white card, hairline + shadow, rounded icon tile in the segment's tint
        items += [
            dict(z=Z["node"], el="rect", role="card", owner=n["id"], group=g, x=x0, y=y0, width=w, height=CARD_H,
                 rx=LOOK["card_rx"], fill="#ffffff", stroke=LOOK["card_stroke"], sw=1, filter="url(#shadow)"),
            dict(z=Z["node"], el="rect", role="card", owner=n["id"], group=g, x=x0 + 12, y=ty, width=32, height=32,
                 rx=8, fill=role["tint"]),
            dict(z=Z["node"], el="use", role="card", owner=n["id"], group=g, href="#ic-host",
                 x=x0 + 18, y=ty + 6, width=20, height=20),
            dict(z=Z["node"], el="text", role="card", owner=n["id"], group=g, x=x0 + 56, y=y0 + CARD_H / 2 - 3,
                 cls="tb", text=name),
            dict(z=Z["node"], el="text", role="card", owner=n["id"], group=g, x=x0 + 56, y=y0 + CARD_H / 2 + 14,
                 cls="ip", text=ip),
        ]
        shape[n["id"]] = ("rect", x0, y0, x0 + w, y0 + CARD_H)
        reg.add((x0, y0, x0 + w, y0 + CARD_H), "card", n["id"])


# ---------------------------------------------------------------- geometry helpers
def _link(shape, b):
    """Node → segment bar orthogonal polyline (from node edge to bar edge), and the interface label's outward
    direction (-1 left / 1 right / 0 straight)."""
    x0, y0, x1, y1 = b
    if shape[0] == "ellipse":
        _, x, y, r, ry = shape
        top, bot = y - ry, y + ry
    else:
        _, a0, top, a1, bot = shape
        x, y, r = (a0 + a1) / 2, (top + bot) / 2, (a1 - a0) / 2
    below = y0 > y
    edge_node, edge_bar = (bot, y0) if below else (top, y1)
    if x0 + 14 <= x <= x1 - 14:
        return [(x, edge_node), (x, edge_bar)], 0
    ax = (x0 + x1) / 2
    side = -1 if ax < x else 1
    return [(x + side * r, y), (ax, y), (ax, edge_bar)], side


def _label_runs(items, reg, text, pts, S, nid, fails, row):
    """Interface label for a routed link: beside its first runs (nearest the device it belongs to first);
    vertical runs get side placements, horizontal runs above/below."""
    cands = []
    for a, b in list(zip(pts, pts[1:]))[:3]:
        if abs(a[0] - b[0]) < 0.01:
            if abs(a[1] - b[1]) < 24:
                continue
            x, mid = a[0], (a[1] + b[1]) / 2 + 4
            cands += [(x + d * g, mid + dy, "end" if d < 0 else "start") for g in (10, 26) for d in (-1, 1)
                      for dy in (0, -10, 10, -20, 20)]
        else:
            if abs(a[0] - b[0]) < 60:
                continue
            w, sgn = text_width(text, S["iface"]), 1 if b[0] > a[0] else -1
            x = a[0] + sgn * min(abs(b[0] - a[0]) / 2, w / 2 + 24)  # near the device end of the run
            cands += [(x + sgn * dx, a[1] + dy, "middle") for dy in (-9, 19) for dx in (0, 20, 40, 80)]
    if not cands:  # all runs short: fall back to beside the last one
        (x, y0), (_, y1) = pts[-2], pts[-1]
        cands = [(x + d * 10, (y0 + y1) / 2 + 4, "end" if d < 0 else "start") for d in (-1, 1)]
    _place_block(items, reg, [(text, "if", S["iface"], False, False)], cands, "if-label", nid, fails, row)


def cross_link(shape, b, nid, sid, reg, drawn, bounds):
    """Route a non-tree link around icons, cards and other bars; returns (pts, side) or None."""
    own = shape[1:] if shape[0] == "rect" else (shape[1] - shape[3], shape[2] - shape[4], shape[1] + shape[3],
                                                   shape[2] + shape[4])
    obstacles = [bx for bx, kind, o in reg.boxes if kind in ("icon", "card", "seg") and o not in (nid, sid)]
    used = {p for seg in drawn for p in seg}  # exits already taken by this node's other links
    free = [e for e in router.exits(shape) if (e[0], e[1]) not in used]
    pts = router.route(free, b, obstacles, drawn, bounds, own)
    if not pts:
        return None
    return pts, (-1 if pts[-1][0] < pts[0][0] else 1)


def _simplify(pts):
    out = []
    for p in pts:
        if out and abs(p[0] - out[-1][0]) < 0.01 and abs(p[1] - out[-1][1]) < 0.01:
            continue
        out.append(p)
    res = [out[0]]
    for i in range(1, len(out) - 1):
        a, b, c = res[-1], out[i], out[i + 1]
        if (abs(a[0] - b[0]) < 0.01 and abs(b[0] - c[0]) < 0.01) or (abs(a[1] - b[1]) < 0.01 and abs(b[1] - c[1]) < 0.01):
            continue
        res.append(b)
    res.append(out[-1])
    return res


def _dir(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = abs(dx) + abs(dy)
    return dx / L, dy / L


def _offset(pts, off):
    """Shift an orthogonal polyline by off, to the right-hand side of its direction of travel."""
    ns = [(-d[1], d[0]) for d in (_dir(a, b) for a, b in zip(pts, pts[1:]))]
    out = [(pts[0][0] + off * ns[0][0], pts[0][1] + off * ns[0][1])]
    for i in range(1, len(pts) - 1):
        n0, n1 = ns[i - 1], ns[i]
        out.append((pts[i][0] + off * (n0[0] + n1[0]), pts[i][1] + off * (n0[1] + n1[1])))
    out.append((pts[-1][0] + off * ns[-1][0], pts[-1][1] + off * ns[-1][1]))
    return out


def _trim(pts, s0, s1):
    pts = list(pts)
    d = _dir(pts[0], pts[1])
    pts[0] = (pts[0][0] + d[0] * s0, pts[0][1] + d[1] * s0)
    d = _dir(pts[-2], pts[-1])
    pts[-1] = (pts[-1][0] - d[0] * s1, pts[-1][1] - d[1] * s1)
    return pts


def _d(pts):
    (x, y), rest = pts[0], pts[1:]
    s = f"M{x:.1f},{y:.1f}"
    for (px, py), (qx, qy) in zip(pts, rest):
        if abs(py - qy) < 0.01:
            s += f" H{qx:.1f}"
        elif abs(px - qx) < 0.01:
            s += f" V{qy:.1f}"
        else:
            s += f" L{qx:.1f},{qy:.1f}"
    return s.replace(".0", "")


# ---------------------------------------------------------------- placement
def _block_boxes(lines, x, y, anchor, lh=18):
    """lines: [(text, cls, size, mono, bold)]; y is the first line's baseline, line height 18."""
    out = []
    for i, (s, cls, size, mono, bold) in enumerate(lines):
        out.append((s, cls, x, y + lh * i, text_box(x, y + lh * i, s, size, anchor, mono, bold)))
    return out


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _place_block(items, reg, lines, cands, role, owner, fails, row, lh=18):
    chosen = None
    for x, y, anchor in cands:
        bl = _block_boxes(lines, x, y, anchor, lh)
        if reg.free(_union([b[4] for b in bl])):
            chosen = (bl, anchor)
            break
    if not chosen:
        fails.append((row, 1000))
        x, y, anchor = cands[0]
        chosen = (_block_boxes(lines, x, y, anchor, lh), anchor)
    bl, anchor = chosen
    for s, cls, x, y, box in bl:
        it = dict(z=Z["label"], el="text", role=role, owner=owner, x=x, y=y, anchor=anchor, cls=cls, text=s)
        if role == "if-label":  # interface name muted, address regular
            name, _, ip = s.partition(" · ")
            it["spans"] = [(name, "ifn")] + ([(f"  {ip}", "ifa")] if ip else [])
        items.append(it)
        reg.add(box, role, owner)


def _place_annot(items, reg, n, lines, x, y, r, S, fails, row):
    w = max(text_width(s, S["route"], mono=True) for s in lines) + 20
    h = 14 + 19 * len(lines)
    box = _search_annot(reg, x, y, r, w, h)
    if box and _gap(box, x, y, r) > 24:
        fails.append((row, _gap(box, x, y, r)))  # fits but needs a leader line: soft cost, retry with more spacing
    if box is None:
        fails.append((row, 1000))
        box = (x - r[0] - 16 - w, y + r[1] + 8, x - r[0] - 16, y + r[1] + 8 + h)
    g = f"annot-{n['id']}"
    items.append(dict(z=Z["annot"], el="rect", role="annot", owner=n["id"], group=g, x=box[0], y=box[1], width=w,
                      height=h, rx=4, cls="rbox"))
    for i, s in enumerate(lines):
        items.append(dict(z=Z["annot"], el="text", role="annot", owner=n["id"], group=g, x=box[0] + 10,
                          y=box[1] + 21 + 19 * i, cls="rt", text=s))
    reg.add(box, "annot", n["id"])
    lead = _leader(box, x, y, r)
    if lead:
        items.append(dict(z=Z["leader"], el="path", role="leader", owner=n["id"], d=_d(lead), cls="lead"))
        reg.line(lead, "leader", n["id"])


def _gap(box, x, y, r):
    """Distance from the annotation box to the icon's bounding box."""
    x0, y0, x1, y1 = box
    rx, ry = r
    dx = max(x0 - (x + rx), (x - rx) - x1, 0)
    dy = max(y0 - (y + ry), (y - ry) - y1, 0)
    return (dx * dx + dy * dy) ** 0.5


def _search_annot(reg, x, y, r, w, h):
    """Grid-search around the icon for a conflict-free spot, scored by "distance + preference": prefer close to
    the icon, then to the right, then level with the icon."""
    best = None
    xs = [x + r[0] + 12 + 8 * i for i in range(40)] + [x - r[0] - 12 - w - 8 * i for i in range(40)] + \
         [x - w / 2 + 8 * i for i in range(-12, 13)]
    ys = [y - h / 2 + 6 * j for j in range(-30, 31)]
    for bx in xs:
        for by in ys:
            b = (bx, by, bx + w, by + h)
            d = _gap(b, x, y, r)
            if d < 8:
                continue
            score = d + (10 if bx + w / 2 < x else 0) + 0.15 * abs(by + h / 2 - y)
            if best and score >= best[0]:
                continue
            if reg.free(b, pad=6):
                best = (score, b)
    return best[1] if best else None


def _leader(box, x, y, r):
    """When the annotation box is > 24px from the icon, draw a straight line from the box's nearest point to
    the icon center, pointing to the icon edge (ellipse approximation)."""
    if _gap(box, x, y, r) <= 24:
        return None
    x0, y0, x1, y1 = box
    px, py = min(max(x, x0), x1), min(max(y, y0), y1)
    dx, dy = px - x, py - y
    rx, ry = r[0] + 3, r[1] + 3
    k = 1 / ((dx / rx) ** 2 + (dy / ry) ** 2) ** 0.5
    return [(px, py), (x + dx * k, y + dy * k)]


def _wrap(text, size, width):
    """Greedy wrap at " → " so each line fits width (continuation lines start with the arrow)."""
    parts = text.split(" → ")
    lines = [parts[0]]
    for p in parts[1:]:
        if text_width(f"{lines[-1]} → {p}", size) <= width:
            lines[-1] += f" → {p}"
        else:
            lines.append(f"→ {p}")
    return lines


def _short(n):
    parts = [p.strip() for p in n["label"].split("·")]
    return parts[min(1, len(parts) - 1)] if n["kind"] not in ICON else parts[0]


def _caption(fl, nodes):
    hops = fl["hops"]
    src, dst = nodes[hops[0]["id"]], nodes[hops[-1]["id"]]
    mid = []
    for h in hops[1:-1]:
        mid.append(h["id"] if h["type"] == "seg" else T("forwards", r=_short(nodes[h["id"]])))
    tag = T("flow_tag", label=fl["label"]) if fl.get("label") else ""
    return T("flow", src=_short(src), dst=_short(dst), tag=tag, path=" → ".join(mid))


# ---------------------------------------------------------------- right-hand side panel
def _plan_cols(model, t):
    """Address-plan column widths from their contents (subnet incl. swatch, id, name)."""
    S, segs = t["size"], model["segments"]
    w1 = 10 + max([text_width("DHCP" if s["cidr"] == "dhcp" else s["cidr"], S["iface"]) for s in segs]
                  + [text_width(T("col_seg"), S["small"])])
    w2 = max([text_width(s["id"], S["iface"]) for s in segs] + [text_width(T("col_bridge"), S["small"])])
    w3 = max([text_width(s["label"], S["body"]) for s in segs] + [text_width(T("col_use"), S["small"])])
    return max(w1 + 20, 130), max(w2 + 16, 64), w3


def _panel_w(model, t, nodes, cols):
    """Side panel width: at least PANEL_W, wider when the title, notes, legend or address plan need it."""
    S, meta = t["size"], model["meta"]
    need = [text_width(meta.get("title", T("title")), S["title"], bold=True),
            text_width(meta.get("note", ""), S["small"]), sum(cols),
            60 + max(text_width(T(k), S["body"]) for k in ("lg_router", "lg_host", "lg_seg", "lg_annot", "lg_flow"))]
    return max(PANEL_W, max(need) + 32)


def _panel(items, model, t, nodes, shift=0, w=PANEL_W, cols=(130, 64, 0)):
    S, meta = t["size"], model["meta"]
    x = PANEL_X + shift
    tx = x + 16

    def P(**kw):
        items.append(dict(z=Z["panel"], role="panel", owner=kw.pop("owner", "panel"), group="panel", **kw))

    # title bar
    y = TOP
    vmids = sorted(n["vmid"] for n in nodes.values() if n.get("vmid"))
    rows = []
    if vmids:
        rows.append(T("scope", a=vmids[0], b=vmids[-1]))
    if meta.get("version") or meta.get("date"):
        rows.append(T("version", v=" · ".join(str(v) for v in (meta.get("version"), meta.get("date")) if v)))
    if meta.get("host"):
        rows.append(T("host", h=meta["host"]))
    title = meta.get("title", T("title"))
    tw = text_width(title, S["title"], bold=True)
    wrap = tw + 8 + text_width(T("view_l3"), S["title"] - 3) > w - 32  # long (e.g. English) titles: view name on the next line
    dy = 20 if wrap else 0
    h = 62 + dy + 20 * len(rows) + (18 if meta.get("note") else 0) - 8
    P(el="rect", x=x, y=y, width=w, height=h, rx=6, cls="box")
    P(el="text", x=tx, y=y + 30, cls="tb", fs=S["title"], text=title)  # gray view name beside it or below
    P(el="text", x=tx if wrap else tx + tw + 8, y=y + 30 + dy, cls="ts", fs=S["title"] - 3, text=T("view_l3"))
    P(el="line", x1=tx, y1=y + 42 + dy, x2=x + w - 16, y2=y + 42 + dy, stroke=t["panel"]["divider"], sw=1)
    yy = y + 64 + dy
    for s in rows:
        P(el="text", x=tx, y=yy, cls="t", text=s)
        yy += 20
    if meta.get("note"):
        P(el="text", x=tx, y=yy - 2, cls="ts", text=meta["note"])
    y += h + 16

    # legend (only list the element kinds that actually appear)
    kinds = {n["kind"] for n in nodes.values()}
    has_annot = any(n["routes"] or n["notes"] for n in nodes.values())
    entries = []
    if "router" in kinds:
        entries.append(("router", T("lg_router")))
    if kinds - {"router", "cloud"}:
        entries.append(("host", T("lg_host")))
    entries.append(("seg", T("lg_seg")))
    entries.append(("if", T("lg_if")))
    if has_annot:
        entries.append(("annot", T("lg_annot")))
    if model["flows"]:
        entries.append(("flow", T("lg_flow")))
    h = 46 + 38 * len(entries) - 8
    P(el="rect", x=x, y=y, width=w, height=h, rx=6, cls="box")
    P(el="text", x=tx, y=y + 26, cls="tb", text=T("legend"))
    yy = y + 38
    ix, lx = x + 18, x + 76  # left column: swatches; right column: labels, both left-aligned
    for kind, label in entries:
        cy_ = yy + 15
        c = ix + 22  # centerline of the swatch column (width 44): all samples centered within the column
        if kind == "router":
            P(el="use", href="#ic-router", x=c - 16, y=cy_ - 16, width=32, height=32)
        elif kind == "host":
            P(el="rect", x=c - 12, y=cy_ - 12, width=24, height=24, rx=6, fill=t["roles"]["client"]["tint"])
            P(el="use", href="#ic-host", x=c - 8, y=cy_ - 8, width=16, height=16)
        elif kind == "seg":
            tr = t["roles"]["transit"]
            P(el="rect", x=c - 16, y=cy_ - 7, width=32, height=14, rx=7,
              fill=tr["color"])
        elif kind == "if":
            P(el="text", x=c, y=cy_ + 4, anchor="middle", cls="if", text="eth0 · IP")
        elif kind == "annot":
            P(el="rect", x=c - 16, y=cy_ - 10, width=32, height=20, rx=5, fill=t["canvas"]["bg"],
              stroke=t["panel"]["divider"], sw=1)  # annotations share the panel's fill: sample gets a border
        elif kind == "flow":
            P(el="line", x1=c - 14, y1=cy_, x2=c + 14, y2=cy_, cls="flowhalo")
            P(el="line", x1=c - 14, y1=cy_, x2=c + 12, y2=cy_, cls="flow", marker="url(#ar)")
        P(el="text", x=lx, y=cy_ + 5, cls="t", text=label)
        yy += 38
    y += h + 16

    # address plan
    segs = model["segments"]
    h = 70 + 25 * len(segs)
    P(el="rect", x=x, y=y, width=w, height=h, rx=6, cls="box")
    P(el="text", x=tx, y=y + 26, cls="tb", text=T("plan"))
    c1 = tx
    c2 = c1 + cols[0]
    c3 = c2 + cols[1]
    for cx_, s in ((c1, T("col_seg")), (c2, T("col_bridge")), (c3, T("col_use"))):
        P(el="text", x=cx_, y=y + 52, cls="ts", text=s)
    P(el="line", x1=tx, y1=y + 60, x2=x + w - 16, y2=y + 60, stroke=t["panel"]["divider"], sw=1)
    yy = y + 70
    for s in segs:
        color = t["roles"].get(s["role"], t["roles"]["default"])["color"]
        P(el="rect", x=c1, y=yy, width=4, height=16, fill=color)
        P(el="text", x=c1 + 10, y=yy + 13, cls="if", text="DHCP" if s["cidr"] == "dhcp" else s["cidr"])
        P(el="text", x=c2, y=yy + 13, cls="if", text=s["id"])
        P(el="text", x=c3, y=yy + 13, cls="t", text=s["label"])
        yy += 25
    return y + h
