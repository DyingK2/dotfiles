"""L2 host view: physical NIC / VM NIC -> tap -> bridge, drawn as buses. Rules in resources/style-guide.md §L2.

A row of device boxes on top (bottom edge labeled net0/net1...), below that each bridge is a thick bus line
that only spans its ports' x range; NIC drop lines land on their bus (dot = connected), and cross unconnected
buses via a hop arc. Output is the same scene shape as layout.layout.
"""
from layout import LOOK_DEFAULT, Reg, _graph
from i18n import T, use
from text_metrics import ASC, DESC, text_box, text_width

M = 32                      # canvas margin
PORT_GAP, BOX_H, BOX_GAP = 64, 92, 36
BUS_GAP, BUS_W, OVERHANG = 60, 6, 40
HOP = 7                     # hop-arc half-height
Z = {"frame": 0, "link": 1, "bus": 2, "dot": 3, "node": 4, "label": 7, "panel": 9}


def _titles(n):
    """Two lines in the device box: VM id / remaining label + OS. phys-nic's second line is the NIC name."""
    if n["kind"] == "phys-nic":
        return n["label"], (n["id"] if n["id"] != n["label"] else "")
    parts = [p.strip() for p in n["label"].split("·")]
    title = f"VM {n['vmid']}" if n.get("vmid") else parts[0]
    rest = [p for p in parts if p != title]
    if n.get("sub"):
        rest.append(n["sub"].split("·")[0].strip())
    return title, " · ".join(rest)


def _ports(n):
    if n["kind"] == "phys-nic":
        return [{"seg": f["seg"], "net": None, "tap": None} for f in n["ifaces"]]
    out = []
    for i, f in enumerate(n["ifaces"]):
        net = f.get("net") or f"net{i}"
        tap = f.get("tap") or (f"tap{n['vmid']}i{net[3:]}" if n.get("vmid") and net.startswith("net") else f["name"])
        out.append({"seg": f["seg"], "net": net, "tap": tap})
    return out


def _crossings(order, port_x, span):
    idx = {s: k for k, s in enumerate(order)}
    return sum(1 for t, xs in port_x.items() for x in xs for s in order[:idx[t]] if span[s][0] <= x <= span[s][1])


def _order_buses(order, port_x, span):
    """Top-to-bottom bus order: start from hop-count order, swap adjacent pairs, keep only swaps that reduce
    hop arcs."""
    order, best = list(order), _crossings(order, port_x, span)
    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            cand = order[:i] + [order[i + 1], order[i]] + order[i + 2:]
            c = _crossings(cand, port_x, span)
            if c < best:
                order, best, improved = cand, c, True
    return order


def layout(model, t):
    look = dict(LOOK_DEFAULT, **t.get("look", {}))
    use(model)
    S, meta = t["size"], model["meta"]
    items, fails = [], []
    nodes_l3, segs_by_id, _, _, layer, _ = _graph(model)
    segs = {s["id"]: s for s in model["segments"]}

    # ---- order: bridges by hop distance from Internet; physical NICs first, VMs by their layer
    seg_order = sorted(segs, key=lambda i: (layer.get(("s", i), 1e9), list(segs).index(i)))
    rank = {s: k for k, s in enumerate(seg_order)}
    boxes_n = [n for n in model["nodes"] if "l2" in n["views"] and n["kind"] != "cloud" and n["ifaces"]]
    boxes_n.sort(key=lambda n: (n["kind"] != "phys-nic", layer.get(("n", n["id"]), -1) if n["kind"] != "phys-nic"
                                else min(rank[f["seg"]] for f in n["ifaces"])))
    cloud = next((n for n in model["nodes"] if n["kind"] == "cloud"), None)

    # ---- geometry (x is laid out starting from 0 first, then shifted as a whole at the end)
    def place(order):
        boxes, x = [], 0.0
        for n in order:
            title, sub = _titles(n)
            ports = _ports(n)
            mono_sub = n["kind"] == "phys-nic"
            tw = max(text_width(title, S["name"], bold=True), text_width(sub, S["small"]) if sub else 0)
            w = max(tw + 40, len(ports) * PORT_GAP + 20, 112)
            for i, p in enumerate(ports):
                p["x"] = x + w / 2 + (i - (len(ports) - 1) / 2) * PORT_GAP
            boxes.append({"n": n, "x0": x, "w": w, "title": title, "sub": sub, "ports": ports, "mono": mono_sub})
            x += w + BOX_GAP
        return boxes

    # single-NIC hosts follow right after the rightmost router/multi-NIC device on their bridge, keeping bus
    # lines short and crossings few
    leaf = lambda n: n["kind"] not in ("phys-nic", "router") and len(n["ifaces"]) == 1
    core = [n for n in boxes_n if not leaf(n)]
    after = {}
    for n in boxes_n:
        if leaf(n):
            seg = n["ifaces"][0]["seg"]
            k = max([i for i, c in enumerate(core) if any(f["seg"] == seg for f in c["ifaces"])], default=len(core) - 1)
            after.setdefault(k, []).append(n)
    order = []
    for i, c in enumerate(core):
        order += [c] + sorted(after.get(i, []), key=lambda n: rank[n["ifaces"][0]["seg"]])
    boxes = place(order)
    port_x = {}
    for b in boxes:
        for p in b["ports"]:
            port_x.setdefault(p["seg"], []).append(p["x"])
    span = {s: (min(port_x[s]) - OVERHANG, max(port_x[s]) + OVERHANG) for s in port_x}
    buses = _order_buses([s for s in seg_order if s in port_x], port_x, span)
    name_w = {s: text_width(s, S["name"] - 0.5, bold=True) for s in buses}
    min_x = min([0] + [span[s][0] - 12 - name_w[s] for s in buses])
    dx = M + 24 - min_x
    for b in boxes:
        b["x0"] += dx
        for p in b["ports"]:
            p["x"] += dx
    span = {s: (a + dx, c + dx) for s, (a, c) in span.items()}

    # ---- y
    has_up = any(b["n"]["kind"] == "phys-nic" for b in boxes)
    FT = M + (78 if has_up else 58)          # top of host box
    BT = FT + 46                              # top of device box
    BB = BT + BOX_H
    taps = [p["tap"] for b in boxes for p in b["ports"] if p["tap"]]
    tap_len = max([text_width(s, S["iface"]) for s in taps] or [0])
    y0 = BB + 16 + tap_len + 30
    bus_y = {s: y0 + k * BUS_GAP for k, s in enumerate(buses)}
    reg = Reg(wall=1e9, x_min=-1e9, y_min=-1e9)

    # ---- device boxes
    for b in boxes:
        n, x0, w = b["n"], b["x0"], b["w"]
        g, cx = f"box-{n['id']}", x0 + w / 2
        phys = n["kind"] == "phys-nic"
        fill = t["roles"]["uplink"]["tint"] if phys else "#ffffff"
        items.append(dict(z=Z["node"], el="rect", role="card", owner=n["id"], group=g, x=x0, y=BT, width=w, height=BOX_H,
                          rx=look["card_rx"], fill=fill, stroke=look["card_stroke"], sw=1,
                          filter=None if phys else "url(#shadow)"))
        ty = BT + (40 if phys else 30)
        items.append(dict(z=Z["node"], el="text", role="card", owner=n["id"], group=g, x=cx, y=ty, anchor="middle",
                          cls="tb", text=b["title"]))
        if b["sub"]:
            items.append(dict(z=Z["node"], el="text", role="card", owner=n["id"], group=g, x=cx, y=ty + 19,
                              anchor="middle", cls="if" if b["mono"] else "ts", text=b["sub"]))
        for p in b["ports"]:
            if p["net"]:
                items.append(dict(z=Z["node"], el="text", role="card", owner=n["id"], group=g, x=p["x"], y=BB - 12,
                                  anchor="middle", cls="ifk", text=p["net"]))
        reg.add((x0, BT, x0 + w, BB), "card", n["id"])

    # ---- bus
    for s in buses:
        x0, x1 = span[s]
        y = bus_y[s]
        role = t["roles"].get(segs[s]["role"], t["roles"]["default"])
        items.append(dict(z=Z["bus"], el="line", role="bus", owner=s, x1=x0, y1=y, x2=x1, y2=y, stroke=role["color"],
                          sw=BUS_W, cap="round"))
        reg.add((x0 - BUS_W / 2, y - BUS_W / 2, x1 + BUS_W / 2, y + BUS_W / 2), "bus", s)

    # ---- drop lines (port -> bus); draw an arc when crossing an unconnected bus
    ring = t["panel"]["fill"]
    for b in boxes:
        nid = b["n"]["id"]
        for p in b["ports"]:
            px, yt = p["x"], bus_y[p["seg"]]
            cross = sorted(bus_y[s] for s in buses if s != p["seg"] and bus_y[s] < yt and span[s][0] <= px <= span[s][1])
            d = f"M{px:.1f},{BB}"
            for yc in cross:
                d += f" V{yc - HOP:.1f} C{px + HOP * 1.3:.1f},{yc - HOP:.1f} {px + HOP * 1.3:.1f},{yc + HOP:.1f} {px:.1f},{yc + HOP:.1f}"
            d += f" V{yt:.1f}"
            items.append(dict(z=Z["link"], el="path", role="link", owner=nid, d=d, cls="ln"))
            reg.line([(px, BB), (px, yt)], "link", nid)
            items.append(dict(z=Z["dot"], el="circle", role="dot", owner=nid, cx=px, cy=yt, r=4.5,
                              fill=t["text"]["title"], stroke=ring, sw=1.5))
            if p["tap"]:  # tap name written vertically to the left of the drop line, right under the device box
                size = S["iface"]
                w = text_width(p["tap"], size)
                bx = px - 7
                box = (bx - ASC * size, BB + 10, bx + DESC * size, BB + 10 + w)
                items.append(dict(z=Z["label"], el="text", role="if-label", owner=nid, x=bx, y=BB + 10,
                                  anchor="end", cls="if", transform=f"rotate(-90 {bx:.1f} {BB + 10})", text=p["tap"]))
                reg.add(box, "if-label", nid)

    # ---- uplink (physical NIC -> upstream network)
    for b in boxes:
        if b["n"]["kind"] != "phys-nic":
            continue
        px = b["x0"] + b["w"] / 2
        tip = FT - 16
        items.append(dict(z=Z["link"], el="path", role="link", owner=b["n"]["id"], d=f"M{px:.1f},{BT} V{tip}", cls="ln",
                          marker="url(#al)"))
        segs_of = {f["seg"] for f in b["n"]["ifaces"]}
        if cloud and cloud["ifaces"] and cloud["ifaces"][0]["seg"] in segs_of:  # this NIC is the uplink
            up = f"{T('upstream')} / {cloud['label']}"
        else:  # another physical network (storage, OOB, …): name it after its segment
            up = " / ".join(segs[s]["label"] for s in sorted(segs_of))
        items.append(dict(z=Z["label"], el="text", role="label", owner=b["n"]["id"], x=px + 10, y=tip + 5, cls="ts",
                          text=up))
        reg.line([(px, BT), (px, tip)], "link", b["n"]["id"])
        reg.add(text_box(px + 10, tip + 5, up, S["small"]), "label", b["n"]["id"])

    # ---- bus name (left end, right end if it doesn't fit) and caption (below the bus, in gaps between drop
    # lines)
    phys_on = {p["seg"]: b["n"]["id"] for b in boxes if b["n"]["kind"] == "phys-nic" for p in b["ports"]}
    for s in buses:
        x0, x1 = span[s]
        y = bus_y[s]
        fs = S["name"] - 0.5
        name_c = [(x0 - 12, y + 4.5, "end"), (x1 + 12, y + 4.5, "start")]
        name_c += [(bx, y - 10, "start") for bx in range(int(x0), int(x1 - name_w[s]), 6)]  # fallback: above bus
        for bx, by, anchor in name_c:
            box = text_box(bx, by, s, fs, anchor, bold=True)
            if reg.free(box, pad=3):
                break
        else:
            fails.append(s)
            bx, by, anchor = name_c[0]
            box = text_box(bx, by, s, fs, anchor, bold=True)
        items.append(dict(z=Z["label"], el="text", role="seg-label", owner=s, x=bx, y=by, anchor=anchor, cls="tb",
                          fs=fs, text=s))
        reg.add(box, "seg-label", s)

        sg = segs[s]
        cap = [sg["label"], "DHCP" if sg["cidr"] == "dhcp" else sg["cidr"]]
        if s in phys_on:
            cap.append(T("bridged", nic=phys_on[s]))
        cap = " · ".join(cap)
        w = text_width(cap, S["small"])
        cands = [(cx, y + 21) for cx in range(int(x0), int(max(x0, x1 - w)) + 1, 6)]
        cands += [(cx, y - 11) for cx in range(int(x0), int(max(x0, x1 - w)) + 1, 6)]
        cands += [(x1 + 12 + (name_w[s] + 10 if anchor == "start" else 0), y + 4.5)]
        for cx, cy in cands:
            box = text_box(cx, cy, cap, S["small"])
            if reg.free(box, pad=3):
                break
        else:
            fails.append(s)
            cx, cy = cands[0]
            box = text_box(cx, cy, cap, S["small"])
        items.append(dict(z=Z["label"], el="text", role="seg-label", owner=s, x=cx, y=cy, cls="ts", text=cap))
        reg.add(box, "seg-label", s)

    # ---- host box
    right = max(b[2] for b, _, _ in reg.boxes) + 28
    FB = (max(bus_y.values()) if buses else BB) + 46
    FX = M
    items.append(dict(z=Z["frame"], el="rect", role="frame", owner="host", x=FX, y=FT, width=right - FX, height=FB - FT,
                      rx=16, fill=ring, stroke=t["panel"]["divider"], sw=1.2,
                      dash="5 4"))
    host = T("host_frame", host=meta.get("host", "")).strip()
    hw = text_width(host, S["name"], bold=True)
    tw = hw + 8 + text_width(T("kernel"), S["small"])
    for hx in range(int(FX + 20), int(right), 8):  # box title top-left; shift right if an uplink arrow crosses
        if reg.free((hx, FT + 28 - ASC * S["name"], hx + tw, FT + 28 + DESC * S["name"]), pad=8):
            break
    items.append(dict(z=Z["label"], el="text", role="label", owner="host", x=hx, y=FT + 28, cls="tb", text=host))
    items.append(dict(z=Z["label"], el="text", role="label", owner="host", x=hx + hw + 8, y=FT + 28, cls="ts",
                      text=T("kernel")))

    # ---- title
    title = meta.get("title", T("title"))
    items.append(dict(z=Z["panel"], el="text", role="panel", owner="title", x=M, y=M + 18, cls="tb", fs=S["title"] + 3,
                      text=title))
    items.append(dict(z=Z["panel"], el="text", role="panel", owner="title",
                      x=M + text_width(title, S["title"] + 3, bold=True) + 10, y=M + 18, cls="ts", fs=S["title"],
                      text=T("view_l2")))
    sub = T("l2_sub") + (f" · {meta['note']}" if meta.get("note") else "")
    items.append(dict(z=Z["panel"], el="text", role="panel", owner="title", x=M, y=M + 42, cls="ts", text=sub))

    # ---- legend and notes (below the box)
    y = FB + 32
    P = lambda **kw: items.append(dict(z=Z["panel"], role="panel", owner="legend", group="legend", **kw))
    P(el="circle", cx=M + 8, cy=y - 4, r=4.5, fill=t["text"]["title"], stroke=ring, sw=1.5)
    P(el="text", x=M + 22, y=y, cls="t", text=T("lg_dot"))
    ax = M + 36 + text_width(T("lg_dot"), S["body"]) + 36
    P(el="line", x1=ax - 12, y1=y - 4, x2=ax + 12, y2=y - 4, stroke=t["roles"]["uplink"]["color"], sw=BUS_W, cap="round")
    P(el="path", d=f"M{ax:.1f},{y - 18} V{y - 4 - HOP} C{ax + HOP * 1.3:.1f},{y - 4 - HOP} {ax + HOP * 1.3:.1f},"
                   f"{y - 4 + HOP} {ax:.1f},{y - 4 + HOP} V{y + 10}", cls="ln")
    P(el="text", x=ax + 24, y=y, cls="t", text=T("lg_hop"))
    notes = []
    if any(b["n"].get("vmid") for b in boxes):
        notes.append(T("note_tap"))
        notes.append(T("note_fw"))
    yy = y + 30
    for s in notes:
        P(el="text", x=M, y=yy, cls="ts", text=s)
        yy += 20
    width = max(right + M, M * 2 + text_width(title, S["title"] + 3, bold=True) + 10 + text_width(T("view_l2"), S["title"]),
                *[M * 2 + text_width(s, S["small"]) for s in notes + [sub]])
    if width > right + M:  # if the notes are wider than the box, stretch the box to match, keep alignment
        for it in items:
            if it["role"] == "frame":
                it["width"] = width - 2 * M
    warnings = [f"bridge {s}: label has no conflict-free spot" for s in dict.fromkeys(fails)]
    return {"width": round(width), "height": round(yy - 20 + M + 4), "items": items, "warnings": warnings}
