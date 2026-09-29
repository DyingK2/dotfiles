# API

A scene defines `build(d)` (one diagram) or `STEPS = [...]` + `build(d, step)` (one frame per step).
Optional globals: `DIFF = False` (no automatic change highlighting), `COLS = n` (storyboard columns).
`from dgm import PTR, NULL` for pointer cells. Coordinates are in px, y grows downwards, (0, 0) is arbitrary —
the page is fitted around the content.

Every component is created by a factory on `d`, measures itself immediately (so `.w`/`.h` are known), and
must then be placed. All placement methods return the component, so they chain.

## Placement

| call | effect |
|---|---|
| `c.at(x, y)` / `c.center_at(cx, cy)` | absolute (top-left / center) |
| `c.right_of(o, gap=48, align="center")` | align: center \| top \| bottom |
| `c.left_of(o, gap=48, align=…)` | |
| `c.below(o, gap=40, align="center")` | align: center \| left \| right |
| `c.above(o, gap=40, align=…)` | |
| `c.align_x(o)` / `c.align_y(o)` | center on o's x / y (keeps the other coordinate) |
| `c.shift(dx, dy)` | nudge |
| `d.row(items, at=(x, y), gap=48, align="center")` | left→right; align top\|center\|bottom |
| `d.col(items, at=(x, y), gap=40, align="center")` | top→bottom; align left\|center\|right |
| `d.grid(items, cols, at=(x, y), gap=(48, 40))` | uniform cells |
| `d.tree(root, {node: [child or None, …]}, at, hgap=24, vgap=48)` | tidy tree; `None` keeps an empty slot |
| `d.same_width(items)` | one width for a column of cards (call before placing) |
| `d.move(items, dx, dy)` / `d.remove(*items)` | move several / drop from drawing but keep positions |

`o` may be a component or a part (`arr[3]`, `rec["next"]`). Gaps are measured between *extents* (including
index labels, pointers, captions), alignment between bodies.

## Components

### `d.node(title, **kw)` — card, record, circle, diamond
| kw | meaning |
|---|---|
| `sub` | detail line(s) under the title: str or list. Mono (sans if it contains CJK). Put the facts here: port, type, size, TTL, complexity |
| `tag` | type chip (`"API"`, `"TABLE"`, `"L3"`) |
| `icon` | Tabler icon name (`server database bolt world router lock key cpu cloud user users terminal …`, see `assets/icons/`) |
| `fields` | record rows `[(name, value, chips)]` or dicts `{name, value, chips, state, key}` → `node["name"]` is a part |
| `kind` | `default` \| `focal` (1–2 per diagram) \| `store` \| `external` (dashed) \| `ghost` (placeholder) \| `muted` |
| `tone` | categorical colour: blue teal violet amber rose green slate |
| `state` | highlight: `focus accent changed new removed done dim error` |
| `shape` | `rect` \| `pill` \| `circle` (graph/tree vertex) \| `diamond` (decision) \| `cylinder` |
| `sub_pos` | circles only: where `sub` goes — `auto` (default: the side no edge touches) \| right \| left \| above \| below |
| `badge` | small disc on the top-left corner (step number, letter) |
| `tag_upper` | `False` keeps the tag's case (function names like `skb_clone`) |
| `w`, `h`, `min_w`, `align`, `id` | fixed size / minimum width / text alignment / stable id |

### `d.array(values, **kw)` — arrays, buffers, stacks, buckets, B-tree keys
`index=True|[labels]|False`, `start=0`, `orient="h"|"v"`, `title`, `states={i: state}`, `gap` (>0 separates
cells), `labels=[…]` (second caption row, e.g. addresses), `cell_w`, `cell_h`, `font="mono"`, `tone`,
`widths=[px, …]` (per-cell widths: memory blocks, header/payload segments roughly to scale).
Values: any text; `PTR` draws a pointer dot (edges from it start at the dot), `NULL` a slash, `None` empty.
- `arr[i]` cell part · `arr.gap_part(i)` the boundary before cell i (B-tree child pointers)
- `arr.pointer(i, "lo", side=None, state=None)` named marker with an arrow (h: above/below, v: right/left).
  Several pointers on one cell merge into `"lo, mid"`.
- `arr.pointer(i, "data", at="gap")` points at the **boundary before cell i** (0..n): buffer pointers
  (head/data/tail/end), byte offsets, ring-buffer ends, cursor positions.
- `arr.span(i, j, "window", side="below", tone=None)` bracket over a range.

### `d.listnode(value, next=True, prev=False, id=…)` — `[value | •]`
`next=None` → null slash; `prev=True/None` → doubly linked `[• | value | •]`. Connect `d.edge(n.next, m)`.

### `d.table(columns, rows, **kw)`
`title`, `states={r: state, (r, c): state}`, `mono=[cols]` (default: columns that look numeric/addresses),
`align=["left"|"right"|"center", …]`, `grid=True` (vertical rules + square-ish cells for DP tables/matrices),
`row_header=True`, `min_col_w`, `tone`. Parts: `t[r, c]`, `t.row(r)` (attach left/right), `t.col(c)` (header).

### `d.bits(fields, width=32, **kw)` — header / register layouts
`fields=[(name, bits[, value])]` or dicts with `state`/`tone`; rows wrap every `width` bits; `bit_w` (px per
bit, auto), `title`, `ruler=True`, `offsets=True` (byte offset per row), `msb_first`. Part: `b["Flags"]`.
One-bit fields need one-letter names (`S`, `A`) plus a table/legend explaining them.

### `d.code(text, highlight=None, title=None, lineno=True, start=1)`
Monospace panel; `highlight` = line, list of lines, or `{line: state}`. Comments (`#`, `//`, `--`) muted.
Part: `code.line(n)`.

### `d.memmap(regions, **kw)` — memory layout / address space / partitions / struct layout
Regions laid along an address axis, holes between them inserted and hatched automatically, the start address
printed at every boundary, sizes computed. Vertical (default: high addresses on top) or `orient="h"`
(low offsets on the left — byte layouts, partition strips, file formats). Region = dict (or `(name, start, end)`):

| key | meaning |
|---|---|
| `name`, `sub` | title and detail line(s) (what lives there: sections, perms of each mapping, who uses it) |
| `start` + `end` \| `size` \| `last` | address range (`end` exclusive, `last` inclusive — as kernel docs list them). Omit on every region for a symbolic stack (list order, no addresses) |
| `children` | list of regions *inside* this one (slot → header / image / TLV / trailer, struct → sub-struct, slab page → objects); drawn inline under a header line, holes between them hatched; `gap_label` on the parent names those holes. Nest as deep as needed; keys are global |
| `perm` | chip like `r-x` · `tone` category (code/data/heap …) · `state` emphasis (`accent` for the point) |
| `kind` | `default` \| `free` (hatched hole) \| `reserved` (sunken grey) \| `ghost` (dashed, "not there yet") |
| `grow` | `"down"` / `"up"` in *address* terms: stack grows down, heap up — arrows into the neighbouring hole |
| `len` (alias `h`) | fixed length along the axis (else from `scale`) · `key` (default `name`) · `addr=False` hides its start address |

Map kwargs: `title`, `orient="v"|"h"`, `scale="log"|"linear"|"equal"` (log: length ∝ log size so 4 KiB and
64 TiB fit on one page; holes capped by `gap_h=(22, 40)` / `gap_w=(44, 90)`), vertical `w`, `min_h`, `max_h`;
horizontal `min_w`, `max_w`, `cell_h`; `length` (total for `linear`), `high` (`top|bottom` for v, `right|left` for
h), `addr_side` (`left|right` for v, `bottom|top` for h), `addr_fmt` (format string like `"{:016x}"` or callable,
e.g. `lambda a: f"+{a}"` for offsets; default `0x` + 8/16 digits), `inclusive=True` (last boundary shows end-1;
`False` for offsets/sizes), `gaps=True`, `gap_label="unmapped"` (`""` → size only; `"pad"` for structs),
`bounds=(lo, hi)` (holes down to `lo` / up to `hi`: `(0, 1 << 64)` for a whole 64-bit space), `sizes=True`.
Nested boundaries print lighter and are dropped where they would collide.
- `m["heap"]` region part (any depth) · `m.addr(a)` part at one address · `m.range(a0, a1)` part over a
  sub-range — edge / band / note targets (`d.edge(got[3], m.addr(0x7ffff7c83d00), "puts")`).
- `m.pointer(target, "brk", at="mid"|"start"|"end", side=None, state=None)` — target = address or region key
  (`start` = its low-address edge). Close pointers get elbow leaders (v) or stack in levels (h); the same spot
  merges into `"_edata, _sbss"`.
- `m.overlay(a, b, "S5 · 128K", tone="blue", tint=False)` — a range that may **overlap** other ranges or cut
  across regions: erase sectors, MPU / write-protect regions, aliases, RELRO, cache lines, 8-byte words, "what
  esptool flashes". Drawn as a labelled bar in a lane beside the body; overlapping bars get further lanes (first
  added = innermost, so add the regular grid — sectors, words — before the exceptions). `tint=True` also shades
  the range across the body.
- `m.span(a, b=None, "user space\n128 TiB", side=None)` — bracket over regions a..b (keys) or addresses.
- Order from the body outward on each side: addresses → pointers → overlay lanes → spans. Decorations default
  to the side without addresses.

### `d.band(src, dst, label=None, tone="blue", arrow=False, label_at=0.5)` / `d.zoom(src, dst)`
Translucent band from one range to another: LMA → VMA copy, virtual → physical, file offset → mapping.
src/dst: region parts, `m.range(...)`, or a whole component; place both ends first (the band is computed at
render time, leaves outside the maps' decorations, and its label finds a free spot inside or beside it).
Vertical maps are entered from the left/right, horizontal maps from the top/bottom — so stack horizontal maps
(file layout above, memory below) and put vertical maps side by side; a band cannot loop back to a vertical map
in the same column (use an edge there). `zoom` is the dashed grey magnifier from a region to the component
that details it (another memmap, an array of GOT entries, a vector table …).

### `d.seq(actors, messages, numbered=False, row_h=34)` — sequence diagram (self-laid-out)
actors: `key` \| `(key, title, sub)` \| dict with `tag tone icon kind`. messages: `(a, b, label)` \|
`(a, b, label, {"dashed": True, "state": "accent"})` \| `{"note": text, "over": key or [k1, k2]}` \|
`{"divider": "close"}` \| `{"gap": 12}`. Self-messages (`a == b`) loop to the right. Place it with `.at()`.

### `d.note(text, target=None, w=220, title=None, state=None, tone=None)`
Quiet callout; with `target` (component/part) a dotted leader ends on the target's nearest border.

### `d.text(text, size=None, font="sans", weight=400, color=None, w=None, anchor="start", state=None)`
Free text (section labels, axis captions). `w` wraps; `state` colours it like that state's ink. Keep free text
≥ 12 px away from edges — closer, and the router treats the corridor as blocked.

### `d.image(path, w, h=None, rx=6, border=True)`
Raster image embedded as data URI (downscaled to 2× display size). For Codex concept art.

### `d.group(members, label=None, kind="zone"|"boundary"|"box", tone=None, pad=16, upper=True)`
Container behind its members — create it **after** placing them. `zone` tinted, `boundary` dashed (trust
zone, host, VPC, process), `box` white. Groups can be placement anchors (`x.below(group)`).

## Edges

`d.edge(src, dst, label=None, **kw)` — src/dst: component, part, or a point `(x, y)`. A point lands the
arrow exactly where you want it, e.g. two arrows into one cell at different x:
`d.edge(rec["data"], (buf[2].rect.x0 + 10, buf[2].rect.y0), dst_side="top")`.

| kw | meaning |
|---|---|
| `style` | `solid` \| `dashed` (async, return, optional) \| `dotted` (reference, weak link) |
| `state` / `tone` | colour: `accent` for the path the diagram is about, `focus` for the current step … |
| `arrow` | `end` \| `start` \| `both` \| `none` |
| `route` | `auto` (orthogonal, avoids boxes; circles default to straight) \| `straight` \| `center` (short arrow between neighbouring cells of a grid) \| `hv` \| `vh` (forced L) |
| `src_side`, `dst_side` | force `top bottom left right` |
| `via` | `[(x, y), …]` waypoints (orthogonalised) |
| `step` | number disc in front of the label (request order) |
| `mono`, `width`, `label_at` (0–1 along the path), `id` | |

Ports fan out automatically when several edges share a side (not on targets narrower than ~16 px, such as
`gap_part`s: there the edges converge on one point and share the last run); single opposite ports are aligned
so the edge is straight. Record fields attach only on their left/right sides — when an arrow must leave
downward, use a card with `sub` lines instead of `fields`. Labels sit beside their line (never on it), clear of boxes and other labels; if there is no room
the check reports it — add space.

## Page

`d.title(title, eyebrow=None, subtitle=None)` · `d.caption(text)` (step caption; or a `"caption"` key in the
step dict) · `d.legend((what, value, text), …)` with what = `node` (focal/store/external/ghost) \| `edge`
(dashed/dotted/state/tone) \| `state` \| `tone` \| `group` (zone/boundary) · `d.footer(text)` (source, notes).
Built-in labels switch to Chinese when the title/subtitle/caption contains CJK.

## States and tones (theme.json)

| state | use |
|---|---|
| `focus` (blue) | the current element: pointer target, node being visited |
| `accent` (orange) | the one thing the diagram is about; 1–2 per diagram |
| `changed` / `new` / `removed` | set automatically between steps; set by hand to mark a diff in a single diagram |
| `done` (grey fill) | processed / finalized / already visited |
| `dim` | present but not involved |
| `error` | failure, violated invariant |

Tones are categorical (group membership, subnet role, layer), never emphasis. Max ~3 tones per diagram.
