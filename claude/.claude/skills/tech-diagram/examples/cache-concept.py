"""Concept illustration + precise data: a Codex-generated picture carries the metaphor, the numbers stay in
code-rendered text so they are exact and editable. The image was made with:

  scripts/imagegen.sh "Editorial flat illustration explaining CPU cache hierarchy as a metaphor: a small desk
  (L1) right next to a worker, a bookshelf (L2/L3) a few steps away, and a distant warehouse (main memory) on
  the horizon. Calm, minimal, lots of white space, off-white background #fafaf9, ink #1d2330 thin line work
  with muted fills, one accent colour orange #e8590c used only on the desk. No text, no letters, no numbers,
  no logos." examples/assets/concept-cache.png --size 1536x1024
"""
import pathlib

HERE = pathlib.Path(__file__).parent


def build(d):
    d.title("Why caches matter: distance is latency", eyebrow="Concept · memory hierarchy",
            subtitle="The CPU works at its desk. Every level further away holds more but costs more trips; "
                     "a miss at one level falls through to the next.")
    img = d.image(HERE / "assets" / "concept-cache.png", w=560, id="art").at(0, 0)
    t = d.table(["level", "metaphor", "size", "latency", "≈ cycles"],
                [["L1d", "the desk", "48 KiB", "~1 ns", "4"],
                 ["L2", "arm's reach", "2 MiB", "~4 ns", "14"],
                 ["L3", "the bookshelf", "36 MiB", "~12 ns", "45"],
                 ["DRAM", "the warehouse", "64 GiB", "~90 ns", "300+"]],
                align=["left", "left", "right", "right", "right"], states={0: "accent"}, id="lat")
    t.right_of(img, gap=40, align="top")
    d.note("A loop that walks an array sequentially hits L1 most of the time: one 64-byte line brings in the "
           "next 15 ints for free. Random access pays the warehouse trip again and again.",
           title="Takeaway", w=t.w).below(t, gap=20, align="left")
    d.footer("Illustration generated with Codex $imagegen; figures are typical for a 2024 desktop CPU.")
