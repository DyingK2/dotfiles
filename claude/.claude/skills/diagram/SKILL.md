---
name: tech-diagram
description: Draw explanatory technical diagrams that make a topic click — data structures (arrays, linked lists, hash tables, trees, records), memory layouts / address spaces (process maps, MCU boot & linker sections, flash partitions, struct padding, PLT/GOT, kernel virtual↔physical), algorithm walkthroughs as numbered step-by-step frames with automatic change highlighting, system / architecture diagrams, network concepts (NAT, protocol exchanges, encapsulation), protocol headers (bit fields), sequence diagrams, DP tables, plus optional AI concept illustrations via Codex $imagegen. Renders SVG + PNG directly from a short Python scene (no Mermaid/Graphviz/D2) with measured fonts, orthogonal routing and a layout self-check. Use for 画图/图解/示意图/配图/结构图/内存布局图/流程分步图/算法过程图/架构图/时序图, "diagram this", "illustrate how X works", "draw the steps of Y". For a concrete lab/homelab/VM topology with subnets, IPs and routes, use network-diagram instead.
---

# tech-diagram

A diagram here is a small Python *scene* that places components (cards, records, arrays, tables, bit fields,
code, sequence lanes …) and connects them; `scripts/render.py` measures every string with the real font files,
routes the edges, writes SVG + PNG, and checks the layout. You decide *what* the reader must see and *where*
it goes; the library handles geometry, routing, styling and consistency.

Paths below are relative to this skill's directory. The renderer carries inline dependencies — run it with
`uv run` from anywhere.

## Workflow

1. **Decide what the picture must explain** — one idea per diagram. Name the reader's question ("why does
   lookup only scan one chain?") and the few facts that answer it; those facts must be *visible* in the picture
   (values, addresses, ports, sizes, complexities, states), not only in prose. Pick the form:
   - structure at rest → one diagram; a process / algorithm / protocol exchange → **steps** (see below) or a
     sequence diagram;
   - more than ~12 boxes or two separate ideas → split into two diagrams;
   - a concrete network (real hosts / subnets / interface IPs / routes — lab, homelab, Proxmox VMs) → stop and
     use the `network-diagram` skill instead: it validates the config and computes traffic paths from the
     routes. Network *concepts* (NAT, a handshake, a header, encapsulation) stay here.
   Read `references/style-guide.md` before your first diagram in a session — it is the difference between
   "boxes and arrows" and a diagram that explains. `references/recipes.md` has a recipe per topic.
2. **Write the scene** next to where the output should live (e.g. `docs/diagrams/lru-cache.py`). Start from
   the closest file in `examples/`; the API is in `references/api.md`.
   ```python
   from dgm import PTR, NULL          # the renderer puts dgm on the path

   def build(d):
       d.title("…", eyebrow="Data structure", subtitle="one sentence: what to look at")
       a = d.array([3, 8, 1], title="a").at(0, 0)
       n = d.node("Redis", sub="TTL 24 h", icon="bolt", kind="store").right_of(a, gap=64)
       d.edge(a[1], n, "lookup")
   ```
3. **Render**:
   ```bash
   uv run scripts/render.py path/to/scene.py        # → scene.svg + scene.png (or scene-01… + scene-steps)
   ```
4. **Read the report and fix at the source.** `0 conflicts` or a list such as
   `[text-edge] "on miss: SELECT" <-> <node urls>`. Kinds: text-text, text-edge (text overflowing / straddling
   a box), text-owner (text inside someone else's box), line-text, line-box, line-line, box-box, edge-end
   (arrow not on its target's border), out, text-width. Typical fixes: more `gap` where a labelled edge must fit (a label needs its width + ~40 px of
   free run), move a note, shorten a label, pick `src_side`/`dst_side`. Never ship with conflicts.
5. **Look at the PNG yourself** (Read it) before handing it over. The check catches collisions, not
   awkwardness: is the focal thing obvious in one second? is anything unlabeled that the reader needs? Iterate
   2–3 times if needed; that is normal.
6. **Deliver** the SVG (crisp, fonts embedded, works offline) and/or the PNG (2×). Mention the scene file so
   the diagram can be edited later.

## Steps (processes, algorithms)

Define `STEPS` (any per-step data) and `build(d, step)`. Every step is drawn with the same code, so the layout
stays put; the renderer then

- puts all steps on one shared canvas (same size, same positions),
- highlights what changed since the previous step — changed values amber, added green, removed ones as a red
  dashed ghost — and adds those entries to the legend,
- writes `<stem>-01.svg/png …` and a storyboard `<stem>-steps.svg/png` (header once, panels in a grid).

Rules:
- Give components stable `id=`s (the diff matches by id). Edge labels diff separately from their edge.
- Nothing may move between frames. Compute positions from the *final* state (lay out the final tree, then
  `d.remove()` nodes that do not exist yet); give components whose values change length a fixed `w=`; anchor
  with `.at()` or to something that never changes — not `.below(arr)` when the array's pointers/spans vary.
  The renderer prints `warning: step N: 'x' moved/resized …` when this is violated; fix every one.
- Drive steps from a real simulation of the algorithm, not hand-typed states. Simulation helpers can live in a
  module next to the scene (`from mysim import …` works).
- 3–8 steps, each with a one-sentence `caption` saying what happens and why.
- Explicit states (focus, accent …) override the automatic diff colour. `DIFF = False` turns it off; `COLS`
  overrides the storyboard's column count (default: the one closest to a 4:3 sheet).

## Concept illustrations (optional)

For a metaphor or mood picture that code cannot draw well, generate one with Codex and compose it with
code-rendered labels/tables (`d.image(...)`). Structure, process and data diagrams are *always* code-rendered.
It costs the user's ChatGPT quota and ~1 min: say so and get a yes first. Details and a prompt template:
`references/imagegen.md`.
```bash
scripts/imagegen.sh "<art-directed prompt, no text in image>" out.png --size 1536x1024
```

## Setup

First run downloads the Python deps automatically (`uv`). PNG and the text-width check need headless Chromium;
if missing, the renderer prints: `uv run --with playwright playwright install chromium-headless-shell`.
`--no-png` renders SVG only. Fonts come from the system (Inter, JetBrains Mono, Noto Sans CJK SC preferred;
`fonts:` line in the output says what was found) and are subset-embedded into the SVG.

## CLI

| flag | effect |
|---|---|
| `-o DIR` | output directory (default: next to the scene) |
| `--no-png` | SVG only, no browser |
| `--no-embed` | do not embed font subsets (smaller SVG, depends on viewer fonts) |
| `--no-diff` | steps without automatic change highlighting |
| `--cols N` | storyboard columns |
| several scenes | `render.py examples/*.py` renders all and prints `N/M scenes clean` (regression run) |

## Files

- `scripts/render.py` CLI · `scripts/dgm/` library (`comps.py` components, `mem.py` memory maps + bands, `edges.py` routing + labels,
  `diagram.py` placement + page, `check.py` self-check, `fonts.py` measuring/embedding, `svg.py` writer)
- `scripts/imagegen.sh` Codex image bridge · `theme.json` colours, sizes, states, tones
- `references/` style guide, API, recipes, imagegen · `examples/` one scene per diagram type, with renders
- `assets/icons/` Tabler outline icons (MIT, see NOTICE) — names are the file stems
