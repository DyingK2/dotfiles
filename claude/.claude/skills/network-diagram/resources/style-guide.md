# Layout rules

What the renderer does, so you can predict its output, write YAML that draws well, and extend it without
breaking the look. Code: `scripts/layout.py` (L3 portrait), `layout_lr.py` (L3 landscape), `layout_l2.py`
(L2 host view), `svg_writer.py` (scene → SVG), `check.py` (self-check).

## Principles

- **One layer per diagram.** L3 shows routers, hosts and subnets; switches/bridges collapse into *segment bars*.
  L2 shows bridges, taps and NICs. Never mix them.
- **Troubleshootable.** Every segment shows its CIDR, every link `iface · IP`, every host its gateway,
  every router its key routes (including return routes).
- **Routes and traffic are first-class.** Flows follow the real forwarding path computed from routes.
- **One colour per segment role**, identical on bars, host tiles, buses and the address plan.
- **Restraint.** Hairlines, one accent colour for flows, muted secondary text, aligned columns. No decoration
  that carries no information.

## Pipeline

`model.py` validates the YAML and computes semantics (no coordinates): gateway shorthand (`10.0.2.1` for host
`10.0.2.10` → `.1`), route display text, and each flow's hops `node, seg, node, …` by longest-prefix match
(a host's `gw` counts as its default route). Errors are fatal and name the offending item. Warnings flag
drawable-but-suspicious config: a `gw` that is no device's address on that segment, a route whose next hop is
not an IP on a directly connected segment (`via dhcp` is accepted and ignored for tracing), and a flow whose
return path cannot be traced (skipped when either end is the cloud — replies come back via NAT).

Layouts produce a *scene* (items with coordinates, `data-role`, `data-owner`). Every text and box is placed
through a collision registry: candidates are tried in preference order and the first free one wins. When
nothing fits, spacing grows (and the canvas widens if a label spilled toward the side panel) and the layout
reruns; the lowest-cost run is kept (not the last one).

Text widths: a first pass uses estimates and records every string; `measure.py` measures them all in one
headless-Chromium batch; the second pass uses real widths (`--measure estimate` skips the browser).

## L3 portrait (`layout.py`, default)

- Canvas width 1100: topology area x 40–760, divider at 775, side panel at 790 (280 wide). Height follows
  content. A topology wider than 720 widens the canvas and shifts the panel right.
- **Rows**: devices and segments form a bipartite graph; BFS from the cloud node gives alternating rows
  cloud → segment → router → segment → … A segment reachable from a router and a host at the same depth
  hangs under the router (hosts are not transit). Row gaps: 36 base, 42 when labelled links cross, 66 below a router
  that branches into ≥ 2 segments.
- **Columns**: each leaf of the BFS tree gets a slot (≤ 380 wide, ≥ its own need); parents are centred over
  their children; YAML order is left-to-right order.
- **Segment bars**: capsule, role tint + role ink text `bridge  label  CIDR` (bridge id bold). Width covers
  its children ± 40; trunk bars are capped at 520.
- **Comb**: when the tree is wider than the topology area, every leaf segment with ≥ 2 hosts stacks them
  under the bar, hanging off a spine near the bar's left end (interface name above each stub).
- **Links**: orthogonal with rounded corners. Tree links: straight down when the bar spans the node; otherwise
  a branch leaves the icon's side horizontally and drops onto the bar's centre. **Non-tree links** (loops,
  a host's extra NIC) are routed by `route.py`: A* on a sparse orthogonal grid that keeps 10 px clear of
  icons, cards and other bars, penalises bends and crossings, never runs on top of another link, and ends
  perpendicular on the bar. Their interface label sits next to their own device. Same in landscape.
- **Interface labels** sit beside the vertical run, on the outer side of branches; hosts show only the
  interface name (their IP is on the card).
- Flow captions are clamped to the topology area and wrap at arrows.
- **Device names** right of the icon (name + muted subtitle); **annotations** (routes + notes) are grid-searched
  around the icon, preferring close, right-hand, same-height spots; a dotted leader is drawn only when the box
  ends up > 24 px away.
- **Flows**: path = link into the bar → along the bar's centre line → link out; drawn *under* the bars so they
  visibly pass through segments; blue 1.5 px line + soft halo, rounded arrowhead, drawn on top of the link.
  A muted caption under the topology spells the path out.
- **Side panel**: title block (title, scope, version · date, host, note), legend (only what appears), address plan.
  At least 280 wide; grows to fit the title, note, legend and address-plan columns.

## L3 landscape (`layout_lr.py`, `--layout lr`)

- Columns by hop count left → right; leaves get vertical slots, parents centred. Host cards left-aligned.
- Column gap = max(64, widest interface label + 40), plus room for the branch riser where a router branches.
- Segment bars stand vertically with rotated text.
- Links: one horizontal line when the bar spans the node's height; otherwise out horizontally → vertical riser
  36 px before the bar → into the bar at its mid-height.
- Names centred above icons, subtitles below; annotations prefer the spot under the subtitle (no leader when
  the box is on the device's axis).
- Page: big title + muted view name, subtitle with flow captions and the note, a divider and a one-line legend
  at the bottom, version right-aligned. Canvas ≥ 1280 × 720 with content centred; tall content widens to 16:9.

## L2 host view (`layout_l2.py`, `--view l2`)

- Dashed rounded frame = the hypervisor host, titled `<meta.host> host · Linux kernel network stack`.
- One row of device boxes: physical NICs (`kind: phys-nic`) first, then VMs (`VM <vmid>` + remaining label +
  OS from `sub`). Ports 64 apart along the bottom edge, labelled `net0…` (default: NIC index).
- **Crossing reduction**: routers/multi-NIC boxes by hop count; each single-NIC host sits right after the
  right-most router on its bridge. Bus order starts from hop order and keeps any adjacent swap that removes
  hop arcs.
- One bus per bridge (6 px, rounded, role colour) spanning only its ports ± 40.
- Port drop lines end on their bus with a **dot = attached**; where a drop passes a bus it is not attached to,
  it breaks with a **hop arc**.
- Tap names run vertically beside each drop: `tap<vmid>i<N>` (PVE naming) unless the YAML gives `tap:`.
- Bus name at its left end (right end, then above the bus, when a drop is in the way); caption
  `label · CIDR (· bridged to <nic>)` in a free gap under the bus.
- A physical NIC gets an arrow up out of the frame: to the upstream network (the cloud's label) when it is on
  the cloud's segment, otherwise labelled with its own segment (storage, OOB, …).
- Below the frame: legend (dot, hop arc) and PVE notes (tap naming, firewall bridges fwbr/fwpr/fwln).

## Text language

`meta.lang: zh | en`; when absent, zh if any title/label/note contains CJK, else en. All fixed strings live
in `scripts/i18n.py`.

## Look (`theme.json`)

One look, Apple-like restraint: white canvas; tinted capsule segment bars with role-ink text; white host cards
with hairline border, soft shadow and a role-tinted icon tile; 1.5 px grey links with rounded corners; route
notes in light-grey boxes (monospace); flows as a blue 1.5 px line with a soft halo and a rounded arrowhead;
secondary text muted grey, numbers tabular.

`theme.json` holds the tokens: fonts, sizes, text colours, `line`, `panel`, `roles` (`color` for buses and
swatches, `tint` for bars and tiles, `ink` for bar text; unknown roles use `default`), `annot`, `flow`,
`icons` (kind → `src`, `fallback`, `width`) and `look` (bar/card heights and radii, card border, link corner
radius, arrow size). Class styles are in `svg_writer._style`.

Icons are the official Cisco network topology icons, **used unaltered** (their terms forbid modification):
no recolouring, proportional scaling only. `assets/icons/custom/` holds fallbacks.

## Output contract and self-check

Every element (or its `<g>`) carries `data-role` — `seg`, `link`, `flow`, `icon`, `card`, `label`,
`if-label`, `annot`, `leader`, `panel`, and in L2 `bus`, `dot`, `seg-label`, `frame` — plus
`data-owner=<node or segment id>`. Draw order: background → links → flows → bars → nodes → leaders →
annotations → labels → panel. CSS classes override `fill=` attributes, so per-element text colour uses
`style="fill:…"`.

`check.py` renders the SVG in Chromium and reports: text-text overlap, text-edge (text straddling a box edge),
line-text (links/flows/leaders/buses through text, ignoring parts hidden under later segment bars), line-box,
box-box, text-owner (text on someone else's icon/card), text-divider (diagram text crossing into the side panel), flow-order (flows before all bars), out (outside the
canvas). The side panel is only checked for text overlap and bounds. Exit code 1 on any conflict.
