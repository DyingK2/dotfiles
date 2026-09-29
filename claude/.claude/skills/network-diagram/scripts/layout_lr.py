"""L3 landscape (left-to-right): Internet at the far left, columns laid out by hop count; segment bars stand
vertical with text rotated 90 deg. For slide decks / README hero images.

Shared with portrait: layering (_graph), node drawing (draw_node), collision registry (Reg), text placement
(_place_block).
Layout: big title + subtitle on top, topology in the middle, a horizontal legend row + version at the bottom;
canvas no smaller than 1280x720.
"""
import layout as L
from layout import Reg, Z, _caption, _card_w, _d, _gap, _graph, _offset, _place_block, _seg_text, _simplify, _trim
from i18n import T, use
from text_metrics import text_width

M = 48
MIN_W, MIN_H = 1280, 720
HEAD, FOOT = 92, 76   # title area / legend area height
BRANCH_IN = 36        # distance from branch drop line to segment bar


def layout(model, t):
    """First lay out at the origin to measure content size, then fix the canvas and re-center the content;
    if it still doesn't fit, widen the gaps step by step and keep the lowest-cost version."""
    L.init(t)
    use(model)
    best = None
    for extra in (0, 16, 32, 48, 72, 96):
        items, fails, box = _layout_once(model, t, extra, 0, 0)
        q = sum(p for _, p in fails) + 0.02 * (box[3] - box[1])
        if best is None or q < best[0]:
            best = (q, extra, box)
        if not fails:
            break
    _, extra, (bx0, by0, bx1, by1) = best
    cw, ch = bx1 - bx0, by1 - by0
    title_w = _title_w(model, t)
    W = max(MIN_W, cw + 2 * M, title_w + 2 * M, *[text_width(x, t["size"]["body"]) + 2 * M for x in _subtitle(model)])
    head = HEAD + 19 * max(0, len(_subtitle(model)) - 1)
    H = max(MIN_H, M + head + ch + 32 + FOOT)
    W = max(W, H * 16 / 9)
    ox = (W - cw) / 2 - bx0
    oy = M + head + (H - M - head - FOOT - 16 - ch) / 2 - by0
    items, fails, _ = _layout_once(model, t, extra, ox, oy)
    _head_foot(items, model, t, W, H)
    warnings = ["annotation/label has no conflict-free spot, used fallback position"] if any(p >= 1000 for _, p in fails) else []
    return {"width": round(W), "height": round(H), "items": items, "warnings": warnings}


def _iface_text(n, f):
    ip = f.get("ip")
    return f["name"] if n["kind"] not in L.ICON else f"{f['name']} · {'DHCP' if ip == 'dhcp' else ip}"


def _layout_once(model, t, extra, ox, oy):
    nodes, segs, adj, root, layer, children = _graph(model)
    ICON, LOOK, S = L.ICON, L.LOOK, t["size"]
    items, fails = [], []
    reg = Reg(wall=1e9, x_min=-1e9, y_min=-1e9)
    ncol = max(layer.values()) + 1
    cols = [[k for k, l in layer.items() if l == c] for c in range(ncol)]
    seg_mono = False

    def ext_w(k):
        if k[0] == "s":
            return L.BAR_H
        n = nodes[k[1]]
        return ICON[n["kind"]][0] if n["kind"] in ICON else _card_w(n, t)

    # ---- columns (x): column gap sized by the interface-label width within that gap
    parent = {c: k for k in layer for c in children[k]}
    gap = []
    for c in range(ncol - 1):
        lw, branchy = 0, False
        for k in cols[c] + cols[c + 1]:
            if k[0] != "n" or nodes[k[1]]["kind"] == "cloud":
                continue
            n = nodes[k[1]]
            for f in n["ifaces"]:
                if layer.get(("s", f["seg"])) in (c, c + 1):
                    lw = max(lw, text_width(_iface_text(n, f), S["iface"], mono=seg_mono))
            if layer[k] == c and len([x for x in children[k] if x[0] == "s"]) > 1:
                branchy = True
        g = max(64, lw + 40) if not branchy else lw + BRANCH_IN + 44
        gap.append(g + extra)
    colw = [max(ext_w(k) for k in col) for col in cols]
    left, x = [], ox
    for c in range(ncol):
        left.append(x)
        x += colw[c] + (gap[c] if c < ncol - 1 else 0)
    cx = {}
    for k in layer:
        c = layer[k]
        card = k[0] == "n" and nodes[k[1]]["kind"] not in ICON
        cx[k] = left[c] + ext_w(k) / 2 if card else left[c] + colw[c] / 2  # left-align host cards

    # ---- rows (y): leaves get their own slot, parent nodes are centered
    def min_h(k):
        if k[0] == "s":
            return text_width(_seg_text(segs[k[1]]), S["seg"], mono=seg_mono, bold=True) + 64
        n = nodes[k[1]]
        if n["kind"] not in ICON:
            return L.CARD_H + 28 + extra / 2
        ann = len(n["routes"]) + len(n["notes"])
        return ICON[n["kind"]][1] + 70 + (14 + 19 * ann + 20 if ann else 0) + extra

    height = {}

    def measure(k):
        height[k] = max(sum(measure(c) for c in children[k]), min_h(k))
        return height[k]

    measure(root)
    cy = {}

    def place(k, y0):
        kids = children[k]
        if not kids:
            cy[k] = y0 + height[k] / 2
            return
        inner = sum(height[c] for c in kids)
        y = y0 + (height[k] - inner) / 2
        for c in kids:
            place(c, y)
            y += height[c]
        cy[k] = (cy[kids[0]] + cy[kids[-1]]) / 2

    place(root, oy)

    # ---- segment bars (vertical)
    bar = {}
    for k in layer:
        if k[0] != "s":
            continue
        s = segs[k[1]]
        tw = text_width(_seg_text(s), S["seg"], mono=seg_mono, bold=True)
        attached = [cy[c] for c in children[k]] or [cy[k]]
        y0 = min(cy[k] - (tw + 48) / 2, min(attached) - 40)
        y1 = max(cy[k] + (tw + 48) / 2, max(attached) + 40)
        bx = cx[k] - L.BAR_H / 2
        bar[s["id"]] = (bx, y0, bx + L.BAR_H, y1)
        role = t["roles"].get(s["role"], t["roles"]["default"])
        g = f"seg-{s['id']}"
        items.append(dict(z=Z["seg"], el="rect", role="seg", owner=s["id"], group=g, x=bx, y=y0, width=L.BAR_H,
                          height=y1 - y0, rx=LOOK["seg_rx"], fill=role["tint"]))
        tx, ty = cx[k] + 4.5, (y0 + y1) / 2
        st = dict(z=Z["seg"], el="text", role="seg", owner=s["id"], group=g, x=tx, y=ty, anchor="middle", cls="seg",
                  transform=f"rotate(-90 {tx:.1f} {ty:.1f})", text=_seg_text(s))
        cidr = "DHCP" if s["cidr"] == "dhcp" else s["cidr"]
        st["spans"] = [(s["id"], "sgb"), (f"  {s['label']}  ", "sgl"), (cidr, "sgc")]
        st["fill"] = role["ink"]
        items.append(st)
        reg.add(bar[s["id"]], "seg", s["id"])

    # ---- nodes
    shape = {}
    for k in layer:
        if k[0] == "n":
            L.draw_node(items, reg, shape, nodes[k[1]], cx[k], cy[k], t, segs)

    # ---- links
    # tree edges use the fixed shapes; non-tree edges (loops, extra NICs) are routed around obstacles
    tree = {(p, c) for p, cs in children.items() for c in cs}
    edges = [(("n", n["id"]), f) for n in nodes.values() if ("n", n["id"]) in layer for f in n["ifaces"]]
    is_tree = lambda k, f: (k, ("s", f["seg"])) in tree or (("s", f["seg"]), k) in tree
    edges.sort(key=lambda e: not is_tree(*e))
    ext = [b for b, _, _ in reg.boxes]
    bounds = (min(b[0] for b in ext) - 80, min(b[1] for b in ext) - 80, max(b[2] for b in ext) + 80,
              max(b[3] for b in ext) + 80)
    links, drawn, routed = {}, [], set()
    for k, f in edges:
        n = nodes[k[1]]
        pts, side = _link(shape[n["id"]], bar[f["seg"]])
        if not is_tree(k, f) and len(pts) > 2:
            r = L.cross_link(shape[n["id"]], bar[f["seg"]], n["id"], f["seg"], reg, drawn, bounds)
            if r:
                (pts, side), _ = r, routed.add((n["id"], f["seg"]))
        links[(n["id"], f["seg"])] = (pts, side, f)
        drawn += list(zip(pts, pts[1:]))
        items.append(dict(z=Z["link"], el="path", role="link", owner=n["id"], d=_d(pts), pts=pts, cls="ln"))
        reg.line(pts, "link", n["id"])

    # ---- flow lines: follow the path, run along the bar's centerline when crossing a segment bar
    captions = []
    for fl in model["flows"]:
        hops = fl["hops"]
        for i in range(0, len(hops) - 2, 2):
            a, s, b = hops[i]["id"], hops[i + 1]["id"], hops[i + 2]["id"]
            pa, pb = links[(a, s)][0], links[(b, s)][0]
            xm = (bar[s][0] + bar[s][2]) / 2
            pts = _simplify(pa + [(xm, pa[-1][1]), (xm, pb[-1][1])] + pb[::-1])
            off = _offset(pts, L.FLOW_OFF)
            for j in range(len(pts) - 1):
                if abs(pts[j][0] - xm) < 0.01 and abs(pts[j + 1][0] - xm) < 0.01:
                    off[j], off[j + 1] = (xm, off[j][1]), (xm, off[j + 1][1])
            pts = _trim(off, 2, 4)
            items.append(dict(z=Z["flow"], el="path", role="flow", owner=fl["from"], d=_d(pts), pts=pts,
                              cls="flowhalo"))
            items.append(dict(z=Z["flow"], el="path", role="flow", owner=fl["from"], d=_d(pts), pts=pts, cls="flow",
                              marker="url(#ar)"))
            reg.line(pts, "flow", fl["from"])
        captions.append(_caption(fl, nodes))

    # ---- device name (centered above the icon) and subtitle (below)
    for k in layer:
        if k[0] != "n" or nodes[k[1]]["kind"] not in ICON:
            continue
        n = nodes[k[1]]
        x, yc = cx[k], cy[k]
        rx, ry = ICON[n["kind"]][0] / 2, ICON[n["kind"]][1] / 2
        name = [(n["label"], "tb", S["name"], False, True)]
        if n["kind"] == "cloud":
            cands = [(x, yc + ry + 20, "middle"), (x, yc - ry - 10, "middle"), (x + rx + 10, yc + 5, "start")]
            _place_block(items, reg, name, cands, "label", n["id"], fails, 0)
            continue
        cands = [(x, yc - ry - 12, "middle"), (x, yc - ry - 26, "middle"), (x + rx + 10, yc - ry - 4, "start"),
                 (x - rx - 10, yc - ry - 4, "end")]
        _place_block(items, reg, name, cands, "label", n["id"], fails, 0)
        if n.get("sub"):
            sub = [(n["sub"], "ts", S["small"], False, False)]
            cands = [(x, yc + ry + 20, "middle"), (x, yc + ry + 34, "middle"), (x - rx - 10, yc + ry + 6, "end")]
            _place_block(items, reg, sub, cands, "label", n["id"], fails, 0)

    # ---- interface labels: above the line when straight; beside the drop line when branching
    for (nid, sid), (pts, side, f) in links.items():
        n = nodes[nid]
        if n["kind"] == "cloud":
            continue
        text = _iface_text(n, f)
        line = [(text, "if", S["iface"], seg_mono, False)]
        if (nid, sid) in routed:  # routed link: label beside its first runs, next to its device
            L._label_runs(items, reg, text, pts, S, nid, fails, 0)
            continue
        if side == 0:
            (xa, y), (xb, _) = pts[0], pts[1]
            mx = (xa + xb) / 2
            cands = [(mx + dx, y + dy, "middle") for dy in (-9, 19) for dx in (0, -10, 10, -20, 20)]
        else:
            (xv, ya), (_, yb) = pts[1], pts[2]
            mid = (ya + yb) / 2 + 4
            cands = [(xv + d * 9, mid + dy, "end" if d < 0 else "start") for d in (-1, 1)
                     for dy in (0, -10, 10, -20, 20, -30, 30)]
        _place_block(items, reg, line, cands, "if-label", nid, fails, 0)

    # ---- route / policy annotations (prefer directly below the icon)
    for k in layer:
        if k[0] != "n":
            continue
        n = nodes[k[1]]
        lines = [r["text"] for r in n["routes"]] + n["notes"]
        if lines and n["kind"] in ICON:
            _annot(items, reg, n, lines, cx[k], cy[k], (ICON[n["kind"]][0] / 2, ICON[n["kind"]][1] / 2), S, fails)

    for c in captions:  # write caption text into the subtitle
        items.append(dict(z=0, el="caption", text=c))
    box = (min(b[0] for b, _, _ in reg.boxes), min(b[1] for b, _, _ in reg.boxes),
           max(b[2] for b, _, _ in reg.boxes), max(b[3] for b, _, _ in reg.boxes))
    return items, fails, box


def _link(shape, b):
    """Node -> vertical segment bar: a single horizontal line when at the same height; otherwise horizontal out
    -> vertical to the bar's midpoint height -> horizontal in (two bends)."""
    x0, y0, x1, y1 = b
    if shape[0] == "ellipse":
        _, x, y, r, _ = shape
    else:
        _, a0, top, a1, bot = shape
        x, y, r = (a0 + a1) / 2, (top + bot) / 2, (a1 - a0) / 2
    right = x0 > x
    en, eb = (x + r, x0) if right else (x - r, x1)
    if y0 + 14 <= y <= y1 - 14:
        return [(en, y), (eb, y)], 0
    bm = (y0 + y1) / 2
    xv = eb - BRANCH_IN if right else eb + BRANCH_IN
    return [(en, y), (xv, y), (xv, bm), (eb, bm)], (-1 if bm < y else 1)


def _annot(items, reg, n, lines, x, y, r, S, fails):
    """Distance is measured against the whole "icon + its own name/subtitle" block: sitting right under the
    subtitle also counts as close, so no leader line is needed."""
    w = max(text_width(s, S["route"], mono=True) for s in lines) + 20
    h = 14 + 19 * len(lines)
    own = [b for b, k, o in reg.boxes if o == n["id"] and k in ("icon", "label")]
    anchor = (min(b[0] for b in own), min(b[1] for b in own), max(b[2] for b in own), max(b[3] for b in own))

    def dist(b):
        dx = max(b[0] - anchor[2], anchor[0] - b[2], 0)
        dy = max(b[1] - anchor[3], anchor[1] - b[3], 0)
        return (dx * dx + dy * dy) ** 0.5

    best = None
    ys = [anchor[3] + 8 + 6 * j for j in range(30)] + [anchor[1] - 8 - h - 6 * j for j in range(30)]
    for bx in [x - w / 2 + 8 * i for i in range(-24, 25)]:
        for by in ys:
            b = (bx, by, bx + w, by + h)
            score = dist(b) + 0.3 * abs(bx + w / 2 - x) + (25 if by < y else 0)
            if best and score >= best[0]:
                continue
            if reg.free(b, pad=6):
                best = (score, b)
    if best is None:
        fails.append((0, 1000))
        box = (x - w / 2, anchor[3] + 30, x + w / 2, anchor[3] + 30 + h)
    else:
        box = best[1]
        if dist(box) > 40:
            fails.append((0, dist(box)))
    g = f"annot-{n['id']}"
    items.append(dict(z=Z["annot"], el="rect", role="annot", owner=n["id"], group=g, x=box[0], y=box[1], width=w,
                      height=h, rx=6, cls="rbox"))
    for i, s in enumerate(lines):
        items.append(dict(z=Z["annot"], el="text", role="annot", owner=n["id"], group=g, x=box[0] + 10,
                          y=box[1] + 21 + 19 * i, cls="rt", text=s))
    reg.add(box, "annot", n["id"])
    if dist(box) > 24 and not box[0] < x < box[2]:  # same axis directly above/below reads as attached, no leader
        lead = L._leader(box, x, y, r)
        if lead:
            items.append(dict(z=Z["leader"], el="path", role="leader", owner=n["id"], d=_d(lead), cls="lead"))
            reg.line(lead, "leader", n["id"])


def _subtitle(model):
    nodes = {n["id"]: n for n in model["nodes"]}
    return [_caption(fl, nodes) for fl in model["flows"]] + ([model["meta"]["note"]] if model["meta"].get("note") else [])


def _title_w(model, t):
    S = t["size"]
    title = model["meta"].get("title", T("title"))
    return text_width(title, S["title"] + 7, bold=True) + 12 + text_width(T("view_l3"), S["title"] + 2)


def _head_foot(items, model, t, W, H):
    """Top: title + subtitle (flow captions, notes); bottom: divider line + horizontal legend + version."""
    S, meta = t["size"], model["meta"]
    captions = [it["text"] for it in items if it["el"] == "caption"]
    items[:] = [it for it in items if it["el"] != "caption"]

    def P(**kw):
        items.append(dict(z=Z["panel"], role="panel", owner=kw.pop("owner", "legend"), group=kw.pop("group", "legend"),
                          **kw))

    title = meta.get("title", T("title"))
    P(el="text", x=M, y=M + 22, cls="tb", fs=S["title"] + 7, text=title, owner="title", group="title")
    P(el="text", x=M + text_width(title, S["title"] + 7, bold=True) + 12, y=M + 22, cls="ts", fs=S["title"] + 2,
      text=T("view_l3"), owner="title", group="title")
    for i, line in enumerate(_subtitle(model)):  # one flow caption per line, then the note
        P(el="text", x=M, y=M + 50 + 19 * i, cls="ts", fs=S["body"], text=line, owner="title", group="title")

    fy = H - FOOT
    P(el="line", x1=M, y1=fy, x2=W - M, y2=fy, stroke=t["panel"]["divider"], sw=1)
    cy = fy + FOOT / 2
    x = M
    kinds = {n["kind"] for n in model["nodes"] if "l3" in n["views"]}
    entries = []
    if "router" in kinds:
        entries.append(("router", T("lr_router")))
    if kinds - {"router", "cloud"}:
        entries.append(("host", T("lg_host")))
    entries.append(("seg", T("lr_seg")))
    if any(n["routes"] or n["notes"] for n in model["nodes"]):
        entries.append(("annot", T("lr_annot")))
    if model["flows"]:
        entries.append(("flow", T("lr_flow")))
    for kind, label in entries:
        if kind == "router":
            P(el="use", href="#ic-router", x=x, y=cy - 14, width=28, height=28)
        elif kind == "host":
            cl = t["roles"]["client"]
            P(el="rect", x=x + 2, y=cy - 12, width=24, height=24, rx=6,
              fill=cl["tint"])
            P(el="use", href="#ic-host", x=x + 6, y=cy - 8, width=16, height=16)
        elif kind == "seg":
            P(el="rect", x=x + 8, y=cy - 13, width=12, height=26, rx=6, fill=t["roles"]["transit"]["color"])
        elif kind == "annot":
            P(el="rect", x=x, y=cy - 10, width=28, height=20, rx=5, fill=t["annot"]["fill"], stroke=t["panel"]["divider"], sw=1)
        elif kind == "flow":
            P(el="line", x1=x, y1=cy, x2=x + 28, y2=cy, cls="flowhalo")
            P(el="line", x1=x, y1=cy, x2=x + 26, y2=cy, cls="flow", marker="url(#ar)")
        P(el="text", x=x + 38, y=cy + 4.5, cls="t", text=label)
        x += 38 + text_width(label, S["body"]) + 36
    ver = " · ".join(str(v) for v in (meta.get("version"), meta.get("date")) if v)
    if ver:
        P(el="text", x=W - M, y=cy + 4.5, anchor="end", cls="ts", text=ver)
