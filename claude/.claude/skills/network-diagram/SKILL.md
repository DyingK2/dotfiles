---
name: network-diagram
description: Draw document-quality network topology diagrams (SVG + PNG) from a small YAML description — L3 logical topology with subnets, interface IPs, routes and computed test-traffic paths, or an L2 host view of Linux bridges / taps / VM NICs (Proxmox-aware). Use when the user wants a network, lab, homelab, VM/router or subnet diagram, a topology picture for docs or slides, or to visualise how traffic is routed between hosts.
---

# network-diagram

Topology YAML → laid-out SVG → PNG + automatic layout self-check. Icons are off the shelf (Cisco, unaltered);
the professional look comes from layout rules (see `resources/style-guide.md`).

All paths below are relative to this skill's directory. Scripts carry inline dependencies — run them with
`uv run` from anywhere; no project setup needed.

## Workflow

1. **Write the YAML.** Copy `schema/topology.example.yaml` and edit it; it documents every field.
   Gather facts from the user or their configs (`ip -j addr`, `ip route`, `bridge link`, PVE `qm config`).
   Give every host its `gw` and every router the routes it really has beyond its directly connected
   segments — flow paths are computed from them. Not on Proxmox? Skip `vmid`/`net`/`tap`/`phys-nic`
   (they only feed the L2 view).
2. **Render.**
   ```bash
   uv run scripts/render.py topology.yaml                  # L3 portrait with side panel (docs)
   uv run scripts/render.py topology.yaml --layout lr      # L3 landscape 16:9 (slides / README header)
   uv run scripts/render.py topology.yaml --view l2        # L2 host view: bridges, taps, NICs
   ```
   Output goes next to the YAML: `<stem>-l3.svg`, `<stem>-l3-lr.svg`, `<stem>-l2.svg`, each with a `.png`
   (`-o` to override).
3. **Read the result.** The command prints `0 conflicts` or lists overlaps (exit 1). `warning:` lines flag
   suspicious config — a gateway that is no device's address, a next hop that isn't reachable, a flow whose
   *return* path is broken. These are usually the user's real bug: report them. Then *look at the PNG*
   yourself before handing it over — the check catches collisions, not awkwardness.
4. **Fix at the source.** Model errors (`error: …`) name the bad item: unknown segment, IP outside its CIDR,
   node unreachable from the cloud, missing route for a flow. A missing route is usually a real network bug —
   tell the user rather than papering over it. Shorten over-long labels/notes if the layout reports fallbacks.

## Options

| flag | values | notes |
|---|---|---|
| `--view` | `l3` (default), `l2` | L2 needs `vmid`/`net` or `tap` for meaningful tap names; `phys-nic` externals appear only here |
| `--layout` | `tb` (default), `lr` | L3 direction: portrait with side panel / landscape with bottom legend |
| `--measure` | `browser` (default), `estimate` | `estimate` needs no browser, slightly looser spacing |
| `--no-check` | | skip PNG + self-check |

Diagram text is Chinese or English: `meta.lang: zh|en`, else auto (CJK anywhere in the YAML → zh).

## Choosing a view

- Explaining routing, subnets, gateways, NAT, "why can't A reach B" → **L3** (portrait for docs, `--layout lr`
  for slides).
- Explaining which VM NIC sits on which bridge, taps, physical uplinks → **L2** (`--view l2`).
- Draw both when documenting a lab; never mix layers in one diagram.

## Setup (first run only)

The renderer measures text and checks layout in headless Chromium. If it is missing, the script says so and
prints the command:
```bash
uv run --with playwright playwright install chromium-headless-shell
```
Without a browser: `--measure estimate --no-check` (SVG only, unchecked).

## Limits

- Tree-like topologies draw best. Loops and extra NICs are routed around everything else, but many of them
  add crossings — interface order in the YAML decides which link is the tree link, so list the one that
  should visually group devices first.
- Wide fan-outs stack hosts under their segment automatically; > ~10 segments on one level still makes a wide
  canvas — split into two diagrams if it gets unwieldy.
- Opposite-direction flows on the same links overlap (one flow per diagram reads best).

## Files

- `scripts/render.py` CLI · `model.py` validation + flow tracing · `layout.py` / `layout_lr.py` / `layout_l2.py`
  layouts · `svg_writer.py` · `check.py` self-check (also standalone: `uv run scripts/check.py x.svg`)
  · `measure.py` / `text_metrics.py` text widths · `i18n.py` diagram strings · `icons.py`
- `theme.json` colours, fonts, sizes · `assets/icons/` Cisco icons (+ NOTICE) and fallbacks
- `resources/style-guide.md` full layout rules · `schema/topology.example.yaml` annotated example
