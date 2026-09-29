# Style guide — diagrams that explain

The renderer guarantees the craft (measured text, aligned ports, rounded orthogonal edges, restrained
palette, no overlaps). What it cannot decide is *content*: which facts appear, what is emphasised, how the
reader's eye travels. That is this guide.

## 1. Start from the question

Write down the reader's question and the answer in one sentence before drawing. The **title** names the
topic; the **subtitle** tells the reader what to look at ("a miss falls through to Postgres and back-fills the
cache"). If the answer does not need a picture (a list, a two-column comparison), use a table in prose instead.

## 2. Show the facts, not just the parts

A box that only carries a name is the main symptom of a useless diagram. Every element should carry the
detail that makes the explanation work:

| element | carries |
|---|---|
| service / process | what it is + one technical fact: port, replicas, runtime, protocol (`sub=`) |
| storage | engine + the key/shape of what it stores (`code → url · TTL 24 h`), or real fields (`fields=`) |
| data structure | real cells with real values, indices, pointers — never one box labelled "array" |
| host / device | address, gateway, interface names |
| packet / header | fields with bit widths and concrete values (`d.bits`) |
| edge | *what flows*: verb + payload (`GET code`, `src 203.0.113.5:61001`, `ACK ack=301`) — not "calls" / "uses" |
| step | caption: what happens *and why* ("6 > 5, and 5 has no right child — insert here") |

Use **concrete example values** (keys `cat:7`, `dog:2`; IPs from documentation ranges 192.0.2.0/24,
198.51.100.0/24, 203.0.113.0/24; real port numbers). Abstract placeholders (`k1`, `Service A`) teach nothing.

Pick the **natural representation** of the thing: arrays as cells, structs/rows as records, tables as tables,
headers as bit fields, message exchanges as sequence lanes, hierarchies as trees, code as code. Mixing them
in one picture is good — a hash table (array) with chains (list nodes) and a lookup (card) is three
representations that together explain.

## 3. Hierarchy: not every box is the same

| meaning | treatment |
|---|---|
| the one thing this diagram is about | `kind="focal"` or `state="accent"` — **1–2 per diagram** |
| services, processes, steps | default card, icon optional, `sub` with a fact |
| state: databases, caches, queues, files | `kind="store"` (sunken fill) or a record with `fields` |
| outside your control: users, third parties, the internet | `kind="external"` (dashed) |
| placeholder, future, "would go here" | `kind="ghost"` |
| decision | `shape="diamond"` · graph / tree vertex: `shape="circle"` |
| boundary that matters (trust zone, host, network, process) | `d.group(kind="boundary")`; shared context: `kind="zone"` |

Size follows content — never enlarge a box to look important. Icons: at most one per card, only where they
speed up recognition (world, database, router, lock); never decorative.

## 4. Colour is meaning

- Neutral ink and hairlines for everything by default.
- **States** (theme.json) encode *emphasis and change*: `accent` = the point, `focus` = current,
  `changed/new/removed` = diff between steps, `done` = processed, `dim` = not involved, `error` = broken.
- **Tones** (blue, teal, violet, amber, rose, green, slate) encode *category*: subnet role, layer, owner.
  At most ~3 per diagram, and a tone must mean the same thing everywhere in the picture.
- Never colour for decoration; never more than two emphasised things.

## 5. Layout

- **Reading direction**: requests and data flow left → right; hierarchy, time and layers top → bottom. The
  reader's entry point sits top-left.
- Place with `d.row` / `d.col` / `right_of` / `below` so things line up; equal gaps for equal relations;
  `d.same_width` for a column of cards.
- **Room for labels**: a labelled edge needs a free run of about its label width + 40 px. The check tells you
  when it didn't fit — widen the gap rather than shortening the meaning.
- Order matters? Number the edges (`step=1…`) instead of drawing a separate flowchart.
- Only real boundaries get groups. A legend only for encodings that are not self-evident (dashed = async,
  orange = hot path); put it in `d.legend`, never inside the drawing.
- Notes: 1–2 per diagram, carrying the *insight* ("99% of reads stop at step 3"), not a repeat of labels.
- Budget: ~12 components and ~12 edges. Beyond that, split into an overview and a detail diagram.

## 6. Steps (process diagrams)

- Same layout in every frame — compute positions from the final state; `d.remove()` what doesn't exist yet
  or show it as a `ghost` when its slot is the point.
- Pick the *teaching* steps: the start, each step where something instructive changes, the end. 3–8 frames.
  Drive them from a real simulation so values are right.
- One-sentence caption per step: what happens and why. Pointer names match the code (`i`, `j`, `lo`, `hi`);
  pair an algorithm with `d.code(...)` and highlight the executing line.
- Let the automatic diff show the change; mark the current element `focus`, the invariant region with a
  `span`, finished parts `done`.

## 7. Anti-patterns

| looks like | fix |
|---|---|
| identical boxes with names only | add `sub` facts, use records/arrays/tables, vary kind by meaning |
| arrows labelled "calls", "uses", "data" | label what flows: verb + payload |
| everything orange / rainbow of tones | one focal element, tones only for categories |
| a legend explaining the obvious | drop it; legend only for real encodings |
| 20 boxes, spaghetti edges | split: overview + detail; one idea per diagram |
| step frames where things jump around | lay out the final state once; same ids every step |
| prose in boxes | one line of facts in the box, the explanation in the caption / a note |
| abstract placeholders (A, B, foo) | real names and plausible real values |
| a generated bitmap for a structure/process diagram | code-render it; bitmaps only for concept art |

## 8. Before delivering

1. Report says `0 conflicts`.
2. Open the PNG: can a reader find the focal element in one second and follow the path without a legend?
3. Every box carries a fact; every edge says what flows; numbers are right.
4. Steps: nothing moves between frames except what changes; captions read as a story.
