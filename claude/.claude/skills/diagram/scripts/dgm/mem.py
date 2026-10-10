"""Memory maps: address-driven stacks of regions (process / kernel / MCU address spaces, flash partitions, ELF
sections, struct and file layouts) plus bands that map one address range onto another (LMA → VMA, virtual →
physical, file offset → mapping, zoom into a region).

A map is a tree of regions laid along a *main axis* (addresses): vertical (orient="v", high addresses on top)
or horizontal (orient="h", low offsets on the left). Regions may nest (`children=`), holes are inserted and
hatched automatically, and overlapping ranges (MPU regions, aliases, RELRO, cache lines) go into lanes beside
the body."""
import math

from .core import El, Part, Rect, seg_hits_rect, up4

UNITS = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"]
OPP = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


def _bl(cy, size):
    return cy + size * 0.35


def human(n):
    """Byte count → '4 KiB', '1.5 MiB', '~128 TiB' (tilde when the shown value is rounded)."""
    if n is None:
        return ""
    v, i = float(n), 0
    while v >= 1024 and i < len(UNITS) - 1:
        v /= 1024
        i += 1
    s = f"{v:.0f}" if v >= 100 else (f"{v:.1f}" if v >= 10 else f"{v:.2f}")
    s = s.rstrip("0").rstrip(".") if "." in s else s
    approx = abs(float(s) - v) > v * 1e-3
    return f"{'~' if approx else ''}{s} {UNITS[i]}"


def _region(spec, i):
    if isinstance(spec, (tuple, list)):
        spec = dict(zip(("name", "start", "end"), spec))
    r = dict(spec)
    r.setdefault("name", "")
    r.setdefault("start", None)
    if r.get("end") is None:
        if r.get("last") is not None:
            r["end"] = r["last"] + 1
        elif r.get("size") is not None and r["start"] is not None:
            r["end"] = r["start"] + r["size"]
        else:
            r["end"] = None
    for k, v in (("sub", None), ("kind", "default"), ("tone", None), ("state", None), ("perm", None),
                 ("grow", None), ("h", None), ("len", None), ("addr", True), ("size_label", True), ("free", False),
                 ("children", None), ("gap_label", "")):
        r.setdefault(k, v)
    r["len"] = r["len"] or r["h"]
    r.setdefault("key", r["name"] or f"#{i}")
    if isinstance(r["sub"], str):
        r["sub"] = r["sub"].split("\n")
    r["sub"] = list(r["sub"] or [])
    return r


def _overlaps(a0, a1, b0, b1, gap=0):
    return a0 < b1 + gap and b0 < a1 + gap


class MemMap(El):
    """Address space / memory layout. See references/api.md → d.memmap."""
    prefix = "mem"
    NAME, SUB, ADDR = 12, 10.5, 9.5
    INSET = 8          # nested stack: inset from the parent's border

    def __init__(self, d, regions, title=None, orient="v", w=None, scale="log", min_h=26, max_h=110, min_w=56,
                 max_w=200, length=None, height=None, cell_h=None, gap_h=(22, 40), gap_w=(44, 90), high=None,
                 addr_side=None, addr_fmt=None, inclusive=True, gaps=True, gap_label="unmapped", sizes=True,
                 bounds=None, id=None):
        super().__init__(d, id)
        self.v = orient == "v"
        self.high = high or ("top" if self.v else "right")
        self.desc = self.high in ("top", "left")          # screen order along the main axis = descending address
        self.addr_side = addr_side or ("left" if self.v else "bottom")
        self.free_side = OPP[self.addr_side]
        self.title, self.inclusive, self.sizes = title, inclusive, sizes
        self.gaps, self.gap_label, self.scale = gaps, gap_label, scale
        self.min_len, self.max_len = (min_h, max_h) if self.v else (min_w, max_w)
        self.gap_len = gap_h if self.v else gap_w
        self.length = length or height
        self.addressed = None
        self.index = {}
        self.rows = self._tree(regions, bounds, 0)
        if addr_fmt is None:
            top = max((r["end"] for r in self.rows), default=0) if self.addressed else 0
            addr_fmt = f"0x{{:0{8 if top <= 1 << 32 else 16}x}}"
        self.fmt = addr_fmt if callable(addr_fmt) else addr_fmt.format
        every = list(self.index.values())
        real = [r["size"] for r in every if not r["free"] and r["size"]]
        self._lo, self._hi = (math.log2(min(real)), math.log2(max(real))) if real else (0, 0)
        self._total = sum(r["size"] for r in self.rows if r["size"]) or 1
        for r in every:
            self._measure(r)
        if self.v:
            self.w = w or max(160, up4(max((r["need_x"] for r in self.rows), default=0)))
            self.h = self._lay_v(self.rows, 0, 0, self.w)
        else:
            for r in self.rows:
                self._len_h(r)
            self._addr_room_h()
            self.h = max([cell_h or 0] + [r["need_x"] for r in self.rows])
            self.w = self._lay_h(self.rows, 0, 0, self.h, None)
        self._addresses()
        self._parts()
        self.pointers, self.spans, self.overlays = [], [], []
        self._ext()

    # ------------------------------------------------------------------ region tree
    def _tree(self, specs, bounds, depth, parent=None):
        rows = [_region(r, i) for i, r in enumerate(specs)]
        addressed = all(r["start"] is not None and r["end"] is not None for r in rows)
        if not addressed and any(r["start"] is not None for r in rows):
            raise ValueError("memmap: give every region start + end/size/last, or none of them")
        if self.addressed is None:
            self.addressed = addressed
        elif addressed != self.addressed:
            raise ValueError("memmap: nested regions need addresses exactly when the map has them")
        if addressed:
            rows.sort(key=lambda r: r["start"])
            for a, b in zip(rows, rows[1:]):
                if b["start"] < a["end"]:
                    raise ValueError(f"memmap regions overlap: {a['key']!r} ends {a['end']:#x} > "
                                     f"{b['key']!r} starts {b['start']:#x} — overlapping ranges go in m.overlay()")
            if parent is not None:
                for r in rows:
                    if r["start"] < parent["start"] or r["end"] > parent["end"]:
                        raise ValueError(f"memmap: {r['key']!r} lies outside its parent {parent['key']!r}")
            if self.gaps:
                label = self.gap_label if parent is None else parent["gap_label"]
                gap = lambda s, e: _region({"name": label or "", "start": s, "end": e, "kind": "free", "free": True,
                                            "key": f"gap@{s:x}" + (f"/{depth}" if depth else "")}, 0)
                out = []
                if bounds and rows and bounds[0] < rows[0]["start"]:
                    out.append(gap(bounds[0], rows[0]["start"]))
                for r in rows:
                    if out and r["start"] > out[-1]["end"]:
                        out.append(gap(out[-1]["end"], r["start"]))
                    out.append(r)
                if bounds and out and bounds[1] > out[-1]["end"]:
                    out.append(gap(out[-1]["end"], bounds[1]))
                rows = out
        for r in rows:
            r["depth"] = depth
            r["size"] = (r["end"] - r["start"]) if addressed else None
            r["kids"] = self._tree(r["children"], (r["start"], r["end"]) if addressed else None, depth + 1, r) \
                if r["children"] else []
            if r["key"] in self.index:
                raise ValueError(f"memmap: duplicate region key {r['key']!r} — give one of them key=")
            self.index[r["key"]] = r
        if addressed and self.desc:
            rows.reverse()
        return rows

    def _scaled(self, r):
        lo, hi = self.min_len, self.max_len
        size = r["size"]
        if not size or self.scale == "equal":
            v = lo
        elif self.scale == "linear":
            v = size / self._total * (self.length or (400 if self.v else 800))
        elif self._hi - self._lo < 1e-9:
            v = (lo + hi) / 2
        else:
            v = lo + (math.log2(size) - self._lo) / (self._hi - self._lo) * (hi - lo)
        if r["free"] or r["kind"] == "free":
            v = min(max(v * 0.5, self.gap_len[0]), self.gap_len[1])
        return v

    # ------------------------------------------------------------------ measuring
    def _meta_w(self, r):
        tw, Z = self.d.tw, self.T["size"]
        chip = (tw(str(r["perm"]), Z["tag"], "mono", 500, 0.06) + 10) if r["perm"] else 0
        size = tw(r["size_txt"], self.SUB, "mono") if r["size_txt"] else 0
        return chip + (6 if chip and size else 0) + size

    def _measure(self, r):
        tw, Z = self.d.tw, self.T["size"]
        r["size_txt"] = human(r["size"]) if (self.sizes and self.addressed and r["size_label"]) else ""
        name_w = tw(r["name"], self.NAME, "sans", 600)
        sub_w = max((tw(s, self.SUB, "mono") for s in r["sub"]), default=0)
        meta = self._meta_w(r)
        if r["kind"] == "free":
            r["free_txt"] = " · ".join(x for x in (r["name"], r["size_txt"]) if x)
            one = tw(r["free_txt"], Z["small"], "sans", 500)
            if self.v:
                r["need_x"], r["min_m"] = one + 24, 20
            else:
                two = max(tw(r["name"], Z["small"], "sans", 500), tw(r["size_txt"], Z["small"], "sans", 500))
                r["min_m"], r["need_x"] = two + 14, 48
            return
        if self.v:
            head = max(20 + name_w + (14 + meta if meta else 0), sub_w + 20)
            if r["kids"]:
                r["head"] = 24 + 13 * len(r["sub"])
                r["need_x"] = max(head, max(k["need_x"] for k in r["kids"]) + 2 * self.INSET)
            else:
                r["need_x"] = head
                r["min_m"] = max(self.min_len, 26 + 13 * len(r["sub"]))
        else:
            if r["kids"]:
                r["head"] = 24 + 13 * len(r["sub"])
                r["head_w"] = max(name_w + (12 + meta if meta else 0), sub_w) + 16
                r["need_x"] = r["head"] + max(k["need_x"] for k in r["kids"]) + self.INSET
            else:
                lines = 1 + (1 if meta else 0) + len(r["sub"])
                r["min_m"] = max(name_w, meta, sub_w) + 16
                r["need_x"] = 20 + 14 + 13 * (lines - 1)

    # ------------------------------------------------------------------ layout
    def _lay_v(self, rows, x, y, w):
        y0 = y
        for r in rows:
            if r["kids"]:
                inner = self._lay_v(r["kids"], x + self.INSET, y + r["head"], w - 2 * self.INSET)
                h = r["head"] + inner + self.INSET
            else:
                h = round(max(r["len"] or self._scaled(r), r["min_m"]))
            r["box"] = Rect(x, y, w, h)
            y += h
        return y - y0

    def _len_h(self, r):
        if r["kids"]:
            for k in r["kids"]:
                self._len_h(k)
            r["m"] = max(r["head_w"], sum(k["m"] for k in r["kids"]) + 2 * self.INSET)
        else:
            r["m"] = round(max(r["len"] or self._scaled(r), r["min_m"]))
        return r["m"]

    def _addr_room_h(self):
        """Horizontal maps print boundary addresses side by side: widen top-level cells so neighbours fit."""
        if not self.addressed:
            return
        tw = lambda a: self.d.tw(self.fmt(a), self.ADDR, "mono")
        rows = self.rows
        for k, r in enumerate(rows):
            lo = tw(r["start"]) if r["addr"] else 0
            nb = rows[k - 1] if self.desc else (rows[k + 1] if k + 1 < len(rows) else None)
            if self.desc and k == 0:
                nb = None
            hi = tw(nb["start"]) if nb is not None else tw(r["end"] - 1 if self.inclusive else r["end"])
            r["m"] = max(r["m"], round((lo + hi) / 2 + 10))

    def _lay_h(self, rows, x, y, h, avail):
        total = sum(r["m"] for r in rows)
        extra = (avail - total) if (avail and avail > total) else 0
        x0 = x
        for r in rows:
            w = r["m"] + (extra * r["m"] / total if total else 0)
            r["box"] = Rect(x, y, w, h)
            if r["kids"]:
                self._lay_h(r["kids"], x + self.INSET, y + r["head"], h - r["head"] - self.INSET, w - 2 * self.INSET)
            x += w
        return x - x0

    def _lohi(self, box):
        """(low-address edge, high-address edge) of a box along the main axis."""
        a, b = (box.y0, box.y1) if self.v else (box.x0, box.x1)
        return (b, a) if self.desc else (a, b)

    def _addresses(self):
        """Every boundary shows the start of the region on its high-address side; nested boundaries are
        lighter and dropped where they would collide with a label already there."""
        self.addrs = []
        if not self.addressed:
            return
        cand = []

        def walk(rows):
            for r in rows:
                if r["addr"]:
                    cand.append((self._lohi(r["box"])[0], self.fmt(r["start"]), r["depth"]))
                if r["kids"]:
                    walk(r["kids"])
        walk(self.rows)
        ext = self.rows[0] if self.desc else self.rows[-1]
        cand.append((self._lohi(ext["box"])[1], self.fmt(ext["end"] - 1 if self.inclusive else ext["end"]), 0))
        tw = lambda s: self.d.tw(s, self.ADDR, "mono")
        for pos, s, depth in sorted(cand, key=lambda c: c[2]):
            clash = False
            for q, t, _ in self.addrs:
                if depth and t == s:
                    clash = True
                elif self.v:
                    clash = clash or (depth and abs(q - pos) < 12)
                else:
                    clash = clash or (depth and _overlaps(pos - tw(s) / 2, pos + tw(s) / 2, q - tw(t) / 2,
                                                          q + tw(t) / 2, 6))
            if not clash:
                self.addrs.append((pos, s, depth))
        self.addr_w = max((tw(s) for _, s, _ in self.addrs), default=0)

    def _addr_off(self):
        if not self.addrs:
            return 0
        return self.addr_w + 12 if self.v else 22

    def _parts(self):
        off = {self.addr_side: self._addr_off()} if self.addrs else {}
        for r in self.index.values():
            b = r["box"]
            if self.v:
                sides = ["left", "right"] + (["top"] if b.y0 < 0.5 else []) + (["bottom"] if b.y1 > self.h - 0.5 else [])
                geo = (0, b.y0, self.w, b.h)
            else:
                sides = ["top", "bottom"] + (["left"] if b.x0 < 0.5 else []) + (["right"] if b.x1 > self.w - 0.5 else [])
                geo = (b.x0, 0, b.w, self.h)
            self.parts[f"[{r['key']}]"] = Part(self, f"[{r['key']}]", *geo, sides=sides,
                                               penalty={s: 40 for s in off}, offset=off)

    # ------------------------------------------------------------------ addressing
    def __getitem__(self, key):
        return self.part(f"[{key}]")

    def row(self, key):
        if key not in self.index:
            raise KeyError(f"memmap '{self.id}' has no region {key!r}; regions: {', '.join(self.index)}")
        return self.index[key]

    def pos_of(self, addr):
        """Main-axis offset (y for vertical, x for horizontal maps) of an address; linear inside a region."""
        if not self.addressed:
            raise ValueError("memmap without addresses: refer to regions by key")

        def find(rows):
            for r in rows:
                if r["start"] <= addr <= r["end"]:
                    if r["kids"]:
                        p = find(r["kids"])
                        if p is not None:
                            return p
                    lo, hi = self._lohi(r["box"])
                    return lo + (hi - lo) * (addr - r["start"]) / max(r["end"] - r["start"], 1)
            return None
        p = find(self.rows)
        if p is None:
            raise ValueError(f"address {addr:#x} is outside memmap '{self.id}'")
        return p

    y_of = pos_of

    def _mr(self, t, at="all"):
        """Target → main-axis interval: region key → its extent (or one edge / the middle); address → a point."""
        if isinstance(t, str):
            lo, hi = self._lohi(self.row(t)["box"])
            return {"mid": ((lo + hi) / 2,) * 2, "start": (lo, lo), "end": (hi, hi), "all": (lo, hi)}[at]
        p = self.pos_of(t)
        return p, p

    def _interval(self, a, b):
        m = self._mr(a) + self._mr(b if b is not None else a)
        return min(m), max(m)

    def _thin(self, key, m0, m1):
        if key not in self.parts:
            off = {self.addr_side: self._addr_off()} if self.addrs else {}
            geo = (0, m0, self.w, max(m1 - m0, 1)) if self.v else (m0, 0, max(m1 - m0, 1), self.h)
            sides = ["left", "right"] if self.v else ["top", "bottom"]
            self.parts[key] = Part(self, key, *geo, sides=sides, offset=off)
        return self.parts[key]

    def addr(self, a):
        """Part at one address (edge target / source: 'GOT[3] points here')."""
        p = self.pos_of(a)
        return self._thin(f"@{a:x}", p - 0.5, p + 0.5)

    def range(self, a0, a1):
        """Part covering addresses a0..a1 (bands and edges into a sub-range of a region)."""
        m0, m1 = sorted((self.pos_of(a0), self.pos_of(a1)))
        return self._thin(f"@{a0:x}-{a1:x}", m0, m1)

    # ------------------------------------------------------------------ decorations
    def pointer(self, target, label, side=None, state=None, at="mid"):
        """Named marker with an arrow at an address (int) or a region (key; at = mid | start | end, where
        start = the region's low-address edge): brk, rsp, _sdata, _estack, PAGE_OFFSET …"""
        self.pointers.append({"m": self._mr(target, at)[0], "label": str(label), "side": side or self.free_side,
                              "state": state})
        self._ext()
        return self

    def span(self, a, b=None, label="", side=None, state=None, tone=None):
        """Bracket over regions a..b (keys, inclusive, any order) or addresses a..b: 'user space', 'segment 1'."""
        m0, m1 = self._interval(a, b)
        self.spans.append({"m0": m0, "m1": m1, "label": str(label), "side": side or self.free_side, "state": state,
                           "tone": tone})
        self._ext()
        return self

    def overlay(self, a, b=None, label="", tone="blue", state=None, side=None, tint=False, id=None):
        """A range that may overlap others (MPU region, alias, RELRO, cache line, 'mapped by TLB entry 3'):
        drawn as a labelled bar in a lane beside the body; overlapping bars get separate lanes. a..b are
        addresses (b exclusive) or region keys. tint=True also shades that range across the body."""
        m0, m1 = self._interval(a, b)
        self.overlays.append({"m0": m0, "m1": m1, "label": str(label), "tone": tone, "state": state,
                              "side": side or self.free_side, "tint": tint, "id": id or str(label)})
        self._ext()
        return self

    def _deco(self):
        return self._deco_v() if self.v else self._deco_h()

    def _deco_v(self):
        d, Z = self.d, self.T["size"]
        base = {"left": 0, "right": 0}
        if self.addrs:
            base[self.addr_side] = self.addr_w + 12
        merged = {}
        for p in self.pointers:
            m = merged.setdefault((round(p["m"], 1), p["side"]), {"m": p["m"], "side": p["side"], "parts": []})
            m["parts"].append((p["label"], p["state"]))
        ptrs = sorted(merged.values(), key=lambda p: p["m"])
        ext = dict(base)
        for side in ("left", "right"):
            last = None
            mine = [p for p in ptrs if p["side"] == side]
            for p in mine:
                p["label"] = ", ".join(l for l, _ in p["parts"])
                p["lw"] = d.tw(p["label"], Z["label"], "mono", 600)
                p["lm"] = p["m"] if last is None else max(p["m"], last + 14)
                last = p["lm"]
            if mine:   # a cluster pushed past its targets: center it on them instead of hanging below
                over = mine[-1]["lm"] - mine[-1]["m"]
                if over > 0:
                    shift = min(over / 2, min(p["lm"] - p["m"] for p in mine) + over / 2)
                    for p in mine:
                        p["lm"] -= shift
                    for a, b in zip(mine, mine[1:]):
                        b["lm"] = max(b["lm"], a["lm"] + 14)
            bend = any(abs(p["lm"] - p["m"]) > 0.5 for p in mine)
            for p in mine:
                p["tip"] = base[side] + 3
                p["tail"] = base[side] + 3 + (30 if bend else 18)
                ext[side] = max(ext[side], p["tail"] + 4 + p["lw"] + 2)
        lanes = self._lanes(lambda o: d.tw(o["label"], Z["small"], "sans", 500) + 14, gap=-0.5)
        for side in ("left", "right"):
            mine = [o for o in lanes if o["side"] == side]
            x = ext[side] + 6
            for lvl in range(max([o["lvl"] for o in mine], default=-1) + 1):
                ls = [o for o in mine if o["lvl"] == lvl]
                width = max(o["need"] for o in ls)
                for o in ls:
                    o["off"], o["thick"] = x, width
                x += width + 4
                ext[side] = x
        spans = self._span_levels(lambda s: 0)
        for side in ("left", "right"):
            x = ext[side] + (8 if ext[side] else 6)
            for lvl in range(max([s["lvl"] for s in spans if s["side"] == side], default=-1) + 1):
                ss = [s for s in spans if s["side"] == side and s["lvl"] == lvl]
                for s in ss:
                    s["off"] = x
                x += 6 + max(s["lw"] for s in ss) + 14
                ext[side] = x - 8
        top = 24 if self.title else (7 if self.addrs else 0)
        top = max([top] + [7 - p["lm"] for p in ptrs])
        bottom = max([7 if self.addrs else 0] + [p["lm"] + 7 - self.h for p in ptrs])
        return ptrs, lanes, spans, [ext["left"], top, ext["right"], bottom]

    def _lanes(self, need, gap):
        lanes = []
        for o in self.overlays:   # first come, innermost lane: add the regular grid (sectors) before exceptions
            lvl = 0
            while any(q["side"] == o["side"] and q["lvl"] == lvl and _overlaps(q["m0"], q["m1"], o["m0"], o["m1"], gap)
                      for q in lanes):
                lvl += 1
            lanes.append(dict(o, lvl=lvl, need=need(o)))
        return lanes

    def _span_levels(self, extra):
        d, Z = self.d, self.T["size"]
        spans = []
        for s in self.spans:
            lines = s["label"].split("\n") if s["label"] else []
            lw = max((d.tw(l, Z["small"], "sans", 500) for l in lines), default=0)
            a, b = s["m0"], s["m1"]
            if not self.v:   # horizontal: the label sits under the bracket and may be wider than it
                c = (a + b) / 2
                a, b = min(a, c - lw / 2 - 4), max(b, c + lw / 2 + 4)
            lvl = 0
            while any(q["side"] == s["side"] and q["lvl"] == lvl and _overlaps(q["a"], q["b"], a, b, -1) for q in spans):
                lvl += 1
            spans.append(dict(s, lvl=lvl, lines=lines, lw=lw, a=a, b=b))
        return spans

    def _deco_h(self):
        d, Z = self.d, self.T["size"]
        base = {"top": 0, "bottom": 0}
        if self.addrs:
            base[self.addr_side] = 20
        ext = dict(base)
        lo_x, hi_x = 0.0, float(self.w)       # horizontal overflow of labels
        tw = lambda s: d.tw(s, self.ADDR, "mono")
        for pos, s, _ in self.addrs:
            lo_x, hi_x = min(lo_x, pos - tw(s) / 2), max(hi_x, pos + tw(s) / 2)
        merged = {}
        for p in self.pointers:
            m = merged.setdefault((round(p["m"], 1), p["side"]), {"m": p["m"], "side": p["side"], "parts": []})
            m["parts"].append((p["label"], p["state"]))
        ptrs = sorted(merged.values(), key=lambda p: p["m"])
        placed = []
        for p in ptrs:
            p["label"] = ", ".join(l for l, _ in p["parts"])
            p["lw"] = d.tw(p["label"], Z["label"], "mono", 600)
            a, b = p["m"] - p["lw"] / 2 - 3, p["m"] + p["lw"] / 2 + 3
            lvl = 0
            while any(q["side"] == p["side"] and q["lvl"] == lvl and _overlaps(q["a"], q["b"], a, b) for q in placed):
                lvl += 1
            p.update(lvl=lvl, a=a, b=b, tip=base[p["side"]] + 3, L=12 + lvl * 16)
            placed.append(p)
            ext[p["side"]] = max(ext[p["side"]], p["tip"] + p["L"] + 4 + 12)
            lo_x, hi_x = min(lo_x, a), max(hi_x, b)
        lanes = self._lanes(lambda o: 18, gap=-0.5)
        for side in ("top", "bottom"):
            mine = [o for o in lanes if o["side"] == side]
            y = ext[side] + 6
            for lvl in range(max([o["lvl"] for o in mine], default=-1) + 1):
                for o in (q for q in mine if q["lvl"] == lvl):
                    o["off"], o["thick"] = y, 18
                    lw = d.tw(o["label"], Z["small"], "sans", 500)
                    o["inside"] = lw + 12 <= o["m1"] - o["m0"]
                    if not o["inside"]:
                        hi_x = max(hi_x, o["m1"] + 6 + lw)
                y += 18 + 4
                ext[side] = y
        spans = self._span_levels(lambda s: 0)
        for side in ("top", "bottom"):
            mine = [s for s in spans if s["side"] == side]
            start = ext[side] + (8 if ext[side] else 6)
            for s in mine:
                s["off"] = start + s["lvl"] * (10 + 15 * max(1, len(s["lines"])))
                ext[side] = max(ext[side], s["off"] + 8 + 15 * len(s["lines"]))
                lo_x, hi_x = min(lo_x, s["a"]), max(hi_x, s["b"])
        top = ext["top"] + (24 if self.title else 0)
        return ptrs, lanes, spans, [max(0, -lo_x), max(top, 7 if self.addrs else 0), max(0, hi_x - self.w),
                                    max(ext["bottom"], 7 if self.addrs else 0)]

    def _ext(self):
        self.pad_ext = self._deco()[3]

    # ------------------------------------------------------------------ drawing
    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        r = self.rect
        ptrs, lanes, spans, _ = self._deco()
        self._draw_stack(S, self.rows, r, top=True)
        # overlay tints sit over the fills, under the text
        for ov in lanes:
            if ov["tint"]:
                _, f, _ = S.style(ov["state"], ov["tone"])
                box = Rect(r.x, r.y + ov["m0"], r.w, ov["m1"] - ov["m0"]) if self.v else \
                    Rect(r.x + ov["m0"], r.y, ov["m1"] - ov["m0"], r.h)
                S.rect(box, fill=f, z=4.25, role="tint", owner=o, opacity=0.55)
        self._draw_addrs(S, r)
        if self.title:
            y = r.y0 - (14 if self.v else self.pad_ext[1] - 10)
            S.text(r.x0, y, self.title, Z["body"], "sans", 600, C["ink2"], owner=o)
        (self._draw_deco_v if self.v else self._draw_deco_h)(S, r, ptrs, lanes, spans)

    def _abs(self, r, box):
        return Rect(r.x + box.x, r.y + box.y, box.w, box.h)

    def _draw_stack(self, S, rows, r, top=False):
        C, Z, o = self.T["color"], self.T["size"], self.id
        stroke = C["stroke"]
        boxes = [self._abs(r, x["box"]) for x in rows]
        cont = Rect(min(b.x0 for b in boxes), min(b.y0 for b in boxes), 0, 0)
        cont = Rect(cont.x, cont.y, max(b.x1 for b in boxes) - cont.x, max(b.y1 for b in boxes) - cont.y)
        for k, (row, rr) in enumerate(zip(rows, boxes)):
            sig = (row["name"], tuple(row["sub"]), row["start"], row["end"], row["kind"], row["perm"])
            st = S.unit(f"{o}[{row['key']}]", sig, rr, rx=2, text=row["name"], explicit=row["state"],
                        diff=not row["free"])
            ts, tf, ti = S.style(None, row["tone"])
            fill = {"free": C["paper"], "reserved": C["sunken"], "ghost": C["paper"]}.get(row["kind"], tf or C["paper"])
            if st:
                fill = S.style(st)[1]
            S.rect(rr, fill=fill, role="node", owner=o)
            if row["kind"] == "free":
                self._hatch(S, rr, C["rule"])
            if st:
                S.rect(rr.inflate(-1.5), rx=2.5, fill="none", stroke=S.style(st)[0], sw=1.25, z=4.3, role="cell",
                       owner=o, dash="3 3" if st == "removed" else None)
            elif row["kind"] == "ghost":
                S.rect(rr.inflate(-3), rx=2, fill="none", stroke=C["line"], dash="4 3", z=4.3, role="cell", owner=o)
            if k:
                p = [(cont.x0, rr.y0), (cont.x1, rr.y0)] if self.v else [(rr.x0, cont.y0), (rr.x0, cont.y1)]
                S.path(p, stroke, 1, z=4.2, role="rule", owner=o, cap="butt", corner=0)
            ink = (S.style(st)[2] if st else None) or ti or C["ink"]
            if row["kind"] == "ghost" and not st:
                ink = C["soft"]
            self._draw_text(S, row, rr, ink, ti)
            if row["kids"]:
                self._draw_stack(S, row["kids"], r)
        S.rect(cont, rx=2, fill="none", stroke=stroke, sw=1, z=4.4, role="frame", owner=o)
        # growth arrows (stack grows down, heap up): short arrows out of the region's moving edge
        into = {}
        for k, row in enumerate(rows):
            if row["grow"]:
                into.setdefault(k + self._grow_dir(row), []).append(k)
        for k, (row, rr) in enumerate(zip(rows, boxes)):
            if not row["grow"]:
                continue
            sgn = self._grow_dir(row)
            col = S.style(row["state"], row["tone"])[0] or C["edge"]
            shared = len(into.get(k + sgn, [])) > 1
            fr = ((0.08, 0.92) if sgn > 0 else (0.17, 0.83)) if shared else (0.12, 0.88)
            if not self.v:
                fr = ((0.22, 0.78) if sgn > 0 else (0.36, 0.64)) if shared else (0.28, 0.72)
            for f in fr:
                if self.v:
                    ye, x = (rr.y1 if sgn > 0 else rr.y0), rr.x + rr.w * f
                    S.path([(x, ye + sgn * 2), (x, ye + sgn * 11)], col, 1.25, z=5.8, role="grow", owner=o)
                    S.arrow((x, ye + sgn * 16), (0, sgn), col, 6, z=5.9, owner=o)
                else:
                    xe, y = (rr.x1 if sgn > 0 else rr.x0), rr.y + rr.h * f
                    S.path([(xe + sgn * 2, y), (xe + sgn * 11, y)], col, 1.25, z=5.8, role="grow", owner=o)
                    S.arrow((xe + sgn * 16, y), (sgn, 0), col, 6, z=5.9, owner=o)

    def _grow_dir(self, row):
        """+1 when growth moves toward the next row in screen order."""
        toward_low = row["grow"] == "down"
        return 1 if toward_low == self.desc else -1

    def _draw_text(self, S, row, rr, ink, ti):
        C, Z, o = self.T["color"], self.T["size"], self.id
        tw = self.d.tw
        if row["kind"] == "free":
            if not row["free_txt"]:
                return
            one = tw(row["free_txt"], Z["small"], "sans", 500)
            if self.v or one + 12 <= rr.w:
                S.rect(Rect(rr.cx - one / 2 - 5, rr.cy - 7.5, one + 10, 15), rx=3, fill=C["paper"], z=4.5, role="deco",
                       owner=o)
                S.text(rr.cx, _bl(rr.cy, Z["small"]), row["free_txt"], Z["small"], "sans", 500, C["muted"], "middle",
                       owner=o)
            else:
                lines = [x for x in (row["name"], row["size_txt"]) if x]
                wmax = max(tw(x, Z["small"], "sans", 500) for x in lines)
                hh = 15 * len(lines)
                S.rect(Rect(rr.cx - wmax / 2 - 4, rr.cy - hh / 2 - 1, wmax + 8, hh + 2), rx=3, fill=C["paper"],
                       z=4.5, role="deco", owner=o)
                for i, x in enumerate(lines):
                    S.text(rr.cx, _bl(rr.cy + (i - (len(lines) - 1) / 2) * 15, Z["small"]), x, Z["small"], "sans",
                           500, C["muted"], "middle", owner=o)
            return
        header = bool(row["kids"])
        if self.v or header:
            # name (+ subs) left, size and perm chip right; a parent keeps this as its header line
            n = 1 + len(row["sub"])
            if header:
                base = rr.y0 + 17
            else:
                base = rr.cy - (14 + 13 * (n - 1)) / 2 + 11
            x0 = rr.x0 + (8 if not self.v else 10)
            S.text(x0, base, row["name"], self.NAME, "sans", 600, ink, owner=o)
            for i, s in enumerate(row["sub"]):
                S.text(x0, base + 14 + 13 * i, s, self.SUB, "mono", 400, C["muted"], owner=o)
            x = rr.x1 - (8 if not self.v else 10)
            if row["size_txt"]:
                S.text(x, base, row["size_txt"], self.SUB, "mono", 400, C["soft"], "end", owner=o)
                x -= tw(row["size_txt"], self.SUB, "mono") + 6
            if row["perm"]:
                S.chip(x, base - 10.5, row["perm"], ti or C["muted"], anchor="end", owner=o, upper=False)
            return
        # horizontal leaf: centered stack — name / perm + size / subs
        meta = self._meta_w(row)
        n = 1 + (1 if meta else 0) + len(row["sub"])
        y = rr.cy - (14 + 13 * (n - 1)) / 2 + 11
        S.text(rr.cx, y, row["name"], self.NAME, "sans", 600, ink, "middle", owner=o)
        step = 14
        if meta:
            y += step
            step = 13
            x = rr.cx - meta / 2
            if row["perm"]:
                S.chip(x, y - 10.5, row["perm"], ti or C["muted"], owner=o, upper=False)
                x += tw(str(row["perm"]), Z["tag"], "mono", 500, 0.06) + 10 + 6
            if row["size_txt"]:
                S.text(x, y, row["size_txt"], self.SUB, "mono", 400, C["soft"], owner=o)
        for s in row["sub"]:
            y += step
            step = 13
            S.text(rr.cx, y, s, self.SUB, "mono", 400, C["muted"], "middle", owner=o)

    def _draw_addrs(self, S, r):
        C, o = self.T["color"], self.id
        stroke = C["stroke"]
        for pos, s, depth in self.addrs:
            col = C["muted"] if depth == 0 else C["soft"]
            if self.v:
                left = self.addr_side == "left"
                yy, xe = r.y + pos, (r.x0 if left else r.x1)
                S.path([(xe, yy), (xe + (-5 if left else 5), yy)], stroke, 1, z=4.4, role="tick", owner=o, cap="butt",
                       corner=0)
                S.text(xe + (-9 if left else 9), _bl(yy, self.ADDR), s, self.ADDR, "mono", 400, col,
                       "end" if left else "start", owner=o)
            else:
                below = self.addr_side == "bottom"
                xx, ye = r.x + pos, (r.y1 if below else r.y0)
                S.path([(xx, ye), (xx, ye + (5 if below else -5))], stroke, 1, z=4.4, role="tick", owner=o,
                       cap="butt", corner=0)
                S.text(xx, ye + 16 if below else ye - 8, s, self.ADDR, "mono", 400, col, "middle", owner=o)

    def _ptr_state(self, S, p):
        rank = ["error", "accent", "new", "changed", "removed", "focus", "done", "dim"]
        sts = [S.unit(f"{self.id}^{lbl}", (round(p["m"], 1), p["side"]), None, text=lbl, explicit=pst, shape="none")
               for lbl, pst in p["parts"]]
        sts = [x for x in sts if x]
        return min(sts, key=lambda x: rank.index(x) if x in rank else 99) if sts else None

    def _lane_style(self, S, ov):
        st = S.unit(f"{self.id}~{ov['id']}", (round(ov["m0"], 1), round(ov["m1"], 1)), None, text=ov["label"],
                    explicit=ov["state"], shape="none")
        s, f, i = S.style(st, ov["tone"])
        C = self.T["color"]
        return s or C["stroke"], f or C["sunken"], i or C["ink2"]

    def _draw_deco_v(self, S, r, ptrs, lanes, spans):
        C, Z, o = self.T["color"], self.T["size"], self.id
        for p in ptrs:
            col, _, ink = S.style(self._ptr_state(S, p) or "focus")
            sgn = 1 if p["side"] == "right" else -1
            xe = r.x1 if sgn > 0 else r.x0
            tip = (xe + sgn * p["tip"], r.y + p["m"])
            tail_x = xe + sgn * p["tail"]
            ly = r.y + p["lm"]
            if abs(ly - tip[1]) > 0.5:
                kx = xe + sgn * (p["tip"] + 14)
                pts = [(tail_x, ly), (kx, ly), (kx, tip[1]), (tip[0] + sgn * 5, tip[1])]
            else:
                pts = [(tail_x, ly), (tip[0] + sgn * 5, tip[1])]
            S.path(pts, col, 1.25, z=5.8, role="ptr-line", owner=o, corner=4)
            S.arrow(tip, (-sgn, 0), col, 6, z=5.9, owner=o)
            S.text(tail_x + sgn * 4, _bl(ly, Z["label"]), p["label"], Z["label"], "mono", 600, ink,
                   "start" if sgn > 0 else "end", z=6, role="ptr", owner=o)
        for ov in lanes:
            s, f, i = self._lane_style(S, ov)
            sgn = 1 if ov["side"] == "right" else -1
            xe = r.x1 if sgn > 0 else r.x0
            x0 = xe + sgn * ov["off"] - (ov["thick"] if sgn < 0 else 0)
            bar = Rect(x0, r.y + ov["m0"] + 1, ov["thick"], ov["m1"] - ov["m0"] - 2)
            S.rect(bar, rx=3, fill=f, stroke=s, sw=1, z=4.6, role="lane", owner=o)
            S.text(bar.cx, _bl(bar.cy, Z["small"]), ov["label"], Z["small"], "sans", 500, i, "middle", z=4.7,
                   owner=o)
        for sp in spans:
            col, _, ink = S.style(sp["state"], sp["tone"])
            col, ink = col or C["muted"], ink or C["ink2"]
            sgn = 1 if sp["side"] == "right" else -1
            xe = r.x1 if sgn > 0 else r.x0
            x = xe + sgn * sp["off"]
            a, b = r.y + sp["m0"] + 2, r.y + sp["m1"] - 2
            S.path([(x - sgn * 5, a), (x, a), (x, b), (x - sgn * 5, b)], col, 1.25, z=5, role="span", owner=o, corner=2)
            n = len(sp["lines"])
            for i, l in enumerate(sp["lines"]):
                cy = (a + b) / 2 + (i - (n - 1) / 2) * 15
                S.text(x + sgn * 6, _bl(cy, Z["small"]), l, Z["small"], "sans", 500, ink, "start" if sgn > 0 else "end",
                       owner=o)

    def _draw_deco_h(self, S, r, ptrs, lanes, spans):
        C, Z, o = self.T["color"], self.T["size"], self.id
        for p in ptrs:
            col, _, ink = S.style(self._ptr_state(S, p) or "focus")
            sgn = 1 if p["side"] == "bottom" else -1
            ye = r.y1 if sgn > 0 else r.y0
            x = r.x + p["m"]
            tip, tail = (x, ye + sgn * p["tip"]), (x, ye + sgn * (p["tip"] + p["L"]))
            S.path([tail, (x, tip[1] + sgn * 5)], col, 1.25, z=5.8, role="ptr-line", owner=o)
            S.arrow(tip, (0, -sgn), col, 6, z=5.9, owner=o)
            S.text(x, tail[1] + (12 if sgn > 0 else -4), p["label"], Z["label"], "mono", 600, ink, "middle", z=6,
                   role="ptr", owner=o)
        for ov in lanes:
            s, f, i = self._lane_style(S, ov)
            sgn = 1 if ov["side"] == "bottom" else -1
            ye = r.y1 if sgn > 0 else r.y0
            y0 = ye + sgn * ov["off"] - (ov["thick"] if sgn < 0 else 0)
            bar = Rect(r.x + ov["m0"] + 1, y0, ov["m1"] - ov["m0"] - 2, ov["thick"])
            S.rect(bar, rx=3, fill=f, stroke=s, sw=1, z=4.6, role="lane", owner=o)
            if ov["inside"]:
                S.text(bar.cx, _bl(bar.cy, Z["small"]), ov["label"], Z["small"], "sans", 500, i, "middle", z=4.7,
                       owner=o)
            else:
                S.text(bar.x1 + 6, _bl(bar.cy, Z["small"]), ov["label"], Z["small"], "sans", 500, i, z=4.7, owner=o)
        for sp in spans:
            col, _, ink = S.style(sp["state"], sp["tone"])
            col, ink = col or C["muted"], ink or C["ink2"]
            sgn = 1 if sp["side"] == "bottom" else -1
            ye = r.y1 if sgn > 0 else r.y0
            y = ye + sgn * sp["off"]
            a, b = r.x + sp["m0"] + 2, r.x + sp["m1"] - 2
            S.path([(a, y - sgn * 5), (a, y), (b, y), (b, y - sgn * 5)], col, 1.25, z=5, role="span", owner=o, corner=2)
            for i, l in enumerate(sp["lines"]):
                ty = y + 14 + 15 * i if sgn > 0 else y - 6 - 15 * (len(sp["lines"]) - 1 - i)
                S.text((a + b) / 2, ty, l, Z["small"], "sans", 500, ink, "middle", owner=o)

    @staticmethod
    def _hatch(S, r, color, step=7):
        """45° hatching clipped to r (unmapped / free memory)."""
        segs = []
        t = -r.h
        while t < r.w:
            s0 = max(0.0, -t / r.h) if r.h else 0
            s1 = min(1.0, (r.w - t) / r.h) if r.h else 0
            if s1 > s0:
                ax, ay = r.x0 + t + s0 * r.h, r.y1 - s0 * r.h
                bx, by = r.x0 + t + s1 * r.h, r.y1 - s1 * r.h
                segs.append(f"M{ax:.1f},{ay:.1f} L{bx:.1f},{by:.1f}")
            t += step
        if segs:
            S.raw(" ".join(segs), stroke=color, sw=1, z=4.1, role="hatch", bbox=r)


class Band(El):
    """Translucent band from one address range to another: a mapping (LMA → VMA copy, virtual → physical,
    file segment → VMA) or, with kind="zoom", a dashed magnifier from a region to a detail component.
    Vertical maps are entered from the left/right, horizontal maps from the top/bottom."""
    prefix = "band"
    solid = False
    NORMAL = {"left": (1, 0), "right": (-1, 0), "top": (0, 1), "bottom": (0, -1)}

    def __init__(self, d, src, dst, label=None, kind="map", tone=None, state=None, arrow=False, label_at=0.5,
                 id=None):
        super().__init__(d, id)
        self.src, self.dst, self.label, self.kind = src, dst, label, kind
        self.tone, self.state, self.arrow, self.label_at = tone, state, arrow, label_at
        self.x = self.y = 0.0

    def obstacles(self):
        return []

    @staticmethod
    def _end(obj, other):
        """Side of obj facing `other` and the (body, outside-decorations) point pairs of that side."""
        top = obj.top_owner
        body, ext, oc = obj.rect, top.ext, other.rect
        dx, dy = oc.cx - body.cx, oc.cy - body.cy
        if isinstance(top, MemMap):
            horiz = top.v
        else:
            horiz = abs(dx) >= abs(dy)
        if horiz:
            side = "right" if dx > 0 else "left"
            xb, xo = (body.x1, ext.x1) if side == "right" else (body.x0, ext.x0)
            pairs = [((xb, body.y0), (xo, body.y0)), ((xb, body.y1), (xo, body.y1))]
        else:
            side = "bottom" if dy > 0 else "top"
            yb, yo = (body.y1, ext.y1) if side == "bottom" else (body.y0, ext.y0)
            pairs = [((body.x0, yb), (body.x0, yo)), ((body.x1, yb), (body.x1, yo))]
        return side, pairs

    def geometry(self):
        sa, A = self._end(self.src, self.dst)
        sb, B = self._end(self.dst, self.src)
        (a0, a1), (b0, b1) = A, B
        if _cross(a0[1], b0[1], a1[1], b1[1]):
            b0, b1 = b1, b0
        return sa, sb, a0, a1, b0, b1

    def lines(self):
        _, _, a0, a1, b0, b1 = self.geometry()
        return (a0[1], b0[1]), (a1[1], b1[1])

    def _label_spot(self, wmax, hh):
        """First spot along the band (preferring label_at) where the label sits inside the band, or beside it,
        without touching any band line or component."""
        (p0, q0), (p1, q1) = mine = self.lines()
        segs = [sg for el in self.d.els if isinstance(el, Band) for sg in el.lines()]
        boxes = [el.ext for el in self.d.els if el.solid and el.placed]
        ok = lambda r: not any(seg_hits_rect(p, q, r) for p, q in segs) and not any(r.hits(bx) for bx in boxes)
        lerp = lambda a, b, t: (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        ts = sorted({round(t / 20, 2) for t in range(3, 18)} | {self.label_at}, key=lambda t: abs(t - self.label_at))
        fallback = None
        for t in ts:
            e0, e1 = lerp(p0, q0, t), lerp(p1, q1, t)
            for v in (0.5, 0.3, 0.7, 0.15, 0.85):
                cx, cy = lerp(e0, e1, v)
                spots = [(cx - wmax / 2, cy)]
                if v == 0.5:
                    # beside a thin band: past where its edges cross the label's rows (or columns)
                    xs, ys = [], []
                    for p, q in mine:
                        for yy in (cy - hh / 2 - 3, cy + hh / 2 + 3):
                            if abs(q[1] - p[1]) > 1e-6:
                                u = min(max((yy - p[1]) / (q[1] - p[1]), 0), 1)
                                xs.append(p[0] + (q[0] - p[0]) * u)
                        for xx in (cx - wmax / 2 - 5, cx + wmax / 2 + 5):
                            if abs(q[0] - p[0]) > 1e-6:
                                u = min(max((xx - p[0]) / (q[0] - p[0]), 0), 1)
                                ys.append(p[1] + (q[1] - p[1]) * u)
                    spots += [(max(xs + [cx]) + 10, cy), (min(xs + [cx]) - 10 - wmax, cy),
                              (cx - wmax / 2, max(ys + [cy]) + hh / 2 + 8), (cx - wmax / 2, min(ys + [cy]) - hh / 2 - 8)]
                for x0, y in spots:
                    r = Rect(x0 - 5, y - hh / 2 - 3, wmax + 10, hh + 6)
                    if ok(r):
                        return x0, y
                    fallback = fallback or (x0, y)
        return fallback

    def emit(self, S):
        C, Z, o = self.T["color"], self.T["size"], self.id
        sa, sb, a0, a1, b0, b1 = self.geometry()
        st = S.unit(o, (self.src.uid, self.dst.uid, self.label), None, text=self.label, explicit=self.state,
                    shape="none")
        if self.kind == "zoom":
            stroke, fill, ink, dash, op = C["line"], C["zone"], C["muted"], "4 3", 1
        else:
            ss, sf, si = S.style(st, self.tone or "blue")
            stroke, fill, ink, dash, op = ss, sf, si, None, 0.75
        poly = [a0[0], a0[1], b0[1], b0[0], b1[0], b1[1], a1[1], a1[0]]
        S.path(poly, "none", 0, z=2, role="band-fill", owner=o, corner=0, fill=fill, opacity=op, closed=True)
        for p, q in self.lines():
            S.path([p, q], stroke, 1, dash=dash, z=3, role="band", owner=o, corner=0, cap="butt")
        if self.arrow:
            tip = ((b0[1][0] + b1[1][0]) / 2, (b0[1][1] + b1[1][1]) / 2)
            S.arrow(tip, self.NORMAL[sb], stroke, 7, z=3.5, owner=o)
        if self.label:
            lines = str(self.label).split("\n")
            wmax = max(self.d.tw(l, Z["small"], "sans", 500) for l in lines)
            hh = 15 * len(lines)
            x0, y = self._label_spot(wmax, hh)
            S.rect(Rect(x0 - 5, y - hh / 2 - 1, wmax + 10, hh + 2), rx=3, fill=C["paper"], z=6.8, role="deco",
                   owner=o, opacity=0.92)
            for i, l in enumerate(lines):
                cy = y + (i - (len(lines) - 1) / 2) * 15
                S.text(x0, _bl(cy, Z["small"]), l, Z["small"], "sans", 500, ink or C["ink2"], z=6.9, owner=o,
                       role="label")


def _cross(a, b, c, d):
    """Do segments a–b and c–d properly intersect?"""
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    return orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0
