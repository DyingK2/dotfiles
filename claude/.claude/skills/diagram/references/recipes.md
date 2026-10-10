# Recipes

One entry per kind of topic: the components to use, the layout, and the example to start from.

## Data structures

| topic | build it from | example |
|---|---|---|
| array / buffer / string | `d.array(values, title="a")` + `pointer()` for indices, `span()` for ranges | `partition.py` |
| stack / queue / deque | vertical `array(orient="v")` (stack) or `array(gap=6)` (queue items) + `head`/`tail` pointers | |
| ring buffer | `array` + `pointer(head)`, `pointer(tail)`, `span` for the occupied part; note on wrap-around | |
| linked list | `d.listnode(v)` in a `d.row`, `d.edge(n.next, m)`; last one `next=None`; `head` as a node or text | `hash-table.py` |
| hash table | vertical bucket `array` of `PTR`/`NULL`, chains of `listnode`, a focal lookup card with the hash maths | `hash-table.py` |
| tree / heap / BST | circle `node`s + `d.tree(...)`; edges `arrow="none"` (straight automatically); heap: add the backing `array` below and link index ↔ node with the same `tone` | `bst-insert.py` |
| B-tree | one `array(keys, index=False)` per node, `d.tree`, edges from `node.gap_part(i)` to children | |
| graph | circle nodes placed by hand (or `d.grid`), `route="straight"` edges with weight labels; distances as circle `sub` | |
| struct / object / row | `node(fields=[(name, type/value, chips)])`; pointers between fields: `d.edge(a["next"], b)` | `url-shortener.py` |
| stack frame (a few slots) | vertical `array` with `index=[addresses]`, `labels=[names]`, `span` for frames | `assorted.py` |
| buffer with pointers (sk_buff, ring buffer, gap buffer) | `array(widths=[…])` for the regions, `pointer(i, "data", at="gap")` for pointers into byte boundaries, `span`s for headroom/len/tailroom; struct fields → `d.edge(rec["data"], buf.gap_part(i))` when the pointer's owner must be shown | |
| trie | circle nodes with one-letter titles, edge labels = the letter consumed | |

## Memory layouts

Use `d.memmap` whenever addresses matter. Feed it *real* ranges (`/proc/<pid>/maps`, `readelf -lW`, the linker
`.map`, `Documentation/arch/*/mm.rst`, a datasheet memory map, gdb) — sizes, holes and boundary addresses are
then computed, not typed. Group many mappings of one object into a row and name the pieces in `sub`.

| topic | build it from | example |
|---|---|---|
| process address space | one map `bounds=(0, 1 << 64)` with kernel / non-canonical hole / stack `grow="down"` / mmap / heap `grow="up"` / image; `pointer` for brk, rsp; `span` user / kernel; `zoom` into mmap area and the executable (one row per segment with perms + file offset) | |
| MCU boot / linker script | 4 GiB map (log) → `zoom` Flash and SRAM detail maps; symbols (`_sidata`, `_sdata`, `_ebss`, `_estack`) as `pointer`s; `band(lma, vma, arrow=True)` for the `.data` copy; vector table `array` with edges to `m.addr(...)` | `memory-map.py` |
| dynamic linking (PLT/GOT) | steps: process map + `code` (objdump of `.plt`) + GOT `array`; edges GOT[n] → `m.addr(target)`; the slot's value changes between steps (auto diff) | |
| kernel virtual layout | `mm.rst` regions with `last=`, `gap_label="未用"`, `addr_fmt="{:016x}"`; physical map with `addr_side="right"`; `band`s direct map → all RAM and kernel-text → phys 0..512 MiB | `kernel-vm.py` |
| flash partitions (MCU, internal flash) | vertical map of partitions; the running slot `state="accent"` with `children` (image header / image / TLV / trailer); erase sectors as `overlay`s (one lane), write protection / flash-encryption as overlapping overlays | `flash-partitions.py` |
| flash partition table (ESP-IDF, MTD, A/B rootfs) | `orient="h"` strip from the CSV / DTS offsets, `bounds=(0, size)`; `children` for otadata / env copies; overlays for "what gets flashed" and OTA slots; an edge from the selector (otadata, bootcount) to the booted slot | |
| struct / object layout | `orient="h"`, `scale="linear"`, `addr_fmt=lambda a: f"+{a}"`, `inclusive=False`, `gap_label="pad"`, `bounds=(0, sizeof)`; nested struct as `children`; word / cache-line `overlay`s; the declaration in `d.code`. Check offsets with the compiler (`offsetof`) | `struct-layout.py` |
| file format (ELF / PNG / ZIP) | horizontal map of headers and chunks with offsets; `zoom` a header into `d.bits` | |
| sections → segments, file → memory | horizontal file map above a horizontal memory map, `band` per `LOAD` segment | |
| relocation (U-Boot, kernel decompression) | steps with `kind="ghost"` for where the image will go, band for the copy | |

## Algorithms (steps)

1. Write the algorithm as a simulation that records a dict per interesting moment:
   `dict(a=list(a), i=i, j=j, line=5, caption="…")`.
2. `STEPS = simulate(input)`; `build(d, s)` draws `s`.
3. Pointers named like the code variables; `d.code(CODE, highlight=s["line"])` beside the data; `span` for the
   invariant (sorted prefix, window, partition); `state="done"` for finished elements.
4. The diff highlights swapped/updated cells automatically.

Examples: `partition.py` (array + code), `bst-insert.py` (tree, fixed positions, ghost slot).
Sorting, two pointers, sliding window, binary search, BFS/DFS (tree/graph + queue/stack array beside it),
Dijkstra (graph + distance table), union-find (forest + parent array), LRU (hash map + doubly linked list).

## Dynamic programming

`d.table(cols, rows, grid=True, row_header=True)` with the recurrence in `d.code`; mark the cell being
computed `focus`, the dependency it takes `accent`, others `dim`; `route="center"` edges between neighbouring
cells. Steps if you fill the table progressively. Example: `edit-distance.py`.

## Systems / architecture

- Left → right along the request; `step=1…` on the edges of the path the diagram is about; that path
  `state="accent"`, side paths `style="dashed"`.
- Cards with icon + `sub` fact; storage as `kind="store"` records with the fields that matter;
  `d.group(kind="boundary")` for clusters/VPCs/trust zones, `zone` for "the data tier".
- One note with the key number or insight. Example: `url-shortener.py`.
- Variants: read vs write path as two diagrams; failure mode as steps (`state="error"` on the failing part,
  ghost for what is lost).

## Networks

| topic | build it from | example |
|---|---|---|
| small topology / NAT / routing | device cards with addresses in `sub`, router as a record with interfaces as `fields`, edges to interfaces (`r["wan0"]`), LAN in a `zone` group, tables for NAT/routing/ARP state | `nat.py` |
| protocol exchange | `d.seq` with seq/ack numbers in labels, state notes, dividers per phase, `numbered=True` | `tcp-handshake.py` |
| packet / header format | `d.bits(fields, width=32)` with a real packet's values, flags explained in a `table` | `tcp-header.py` |
| encapsulation | `d.bits` per layer stacked with `d.col`, or an `array` of header+payload cells whose widths follow the byte counts | |
| lab / homelab L3/L2 topology with routes | use the `network-diagram` skill (YAML → routed topology with flows) | |

## State machines

Pill nodes (`shape="pill"`) for states, the start state `focal`, a `ghost` for "no state", edge labels =
`event / action`. Lay out the happy path on a line, error transitions `dashed` below it.

## Concept pictures

Metaphors, "what it feels like", hero images: `scripts/imagegen.sh` → `d.image(...)` beside a table or notes
with the exact numbers. See `imagegen.md`; example `cache-concept.py`.
