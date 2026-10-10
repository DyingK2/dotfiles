# Examples

One scene per kind of diagram; each render is the quality bar. Re-render all (regression run):

```bash
uv run scripts/render.py examples/*.py      # → "N/N scenes clean"
```

| scene | shows | components |
|---|---|---|
| `hash-table.py` | data structure: buckets + chains + a traced lookup | vertical `array` with `PTR`/`NULL`, `listnode`, focal card, note |
| `partition.py` | algorithm steps (Lomuto partition), driven by a simulation | `array` + `pointer` + `span`, `code` with highlighted line, automatic diff |
| `bst-insert.py` | tree steps with fixed positions, ghost slot, Chinese text | circle nodes, `d.tree`, `d.remove`, straight edges |
| `edit-distance.py` | DP table: where one cell comes from | `table(grid=True)`, `route="center"` edges, `code` |
| `url-shortener.py` | system architecture, numbered request path | icon cards, record with fields, groups, `step=` edges, note |
| `nat.py` | network topology + NAT table | router record with interface parts, zone group, table, dotted reference edge |
| `tcp-handshake.py` | protocol exchange | `d.seq` with notes, dividers, numbered messages |
| `tcp-header.py` | packet header layout | `d.bits` with values and highlighted flags, table |
| `cache-concept.py` | Codex concept illustration + exact data | `d.image`, table, note, footer (prompt in the docstring) |
| `memory-map.py` | memory layout: MCU boot, LMA → VMA, vector table | `memmap` (log scale, holes, `pointer`, `grow`), `zoom`, `band`, edges to `m.addr()` |
| `kernel-vm.py` | 64-bit kernel VA layout (mm.rst) mapped onto physical RAM | `memmap` with `last=`, `bounds`, many holes, left `span`s, two crossing `band`s, `addr_side="right"` |
| `flash-partitions.py` | MCUboot A/B on STM32 internal flash | nested regions (`children`), erase sectors + write protection as overlapping `overlay` lanes, span |
| `struct-layout.py` | C struct padding at byte level | `memmap(orient="h", scale="linear")`, offsets, nested struct, word overlays, `code` |
| `assorted.py` | graph, B-tree, stack frame, state machine | circle captions (`sub_pos="auto"`), `gap_part`, vertical array labels/span, pills |
