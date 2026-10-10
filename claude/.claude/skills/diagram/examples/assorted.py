"""Gallery / regression scene: weighted graph, B-tree, stack frame, state machine in one picture."""


def build(d):
    d.title("Assorted structures", eyebrow="Gallery",
            subtitle="A weighted graph with tentative distances, a B-tree with child pointers leaving from key "
                     "gaps, a stack frame with addresses, and a state machine.")
    # weighted graph (Dijkstra mid-run): circles → straight edges; captions pick a free side automatically
    pos = {"A": (0, 60), "B": (120, 0), "C": (120, 130), "D": (250, 60)}
    dist = {"A": 0, "B": 3, "C": 1, "D": "∞"}
    n = {k: d.node(k, shape="circle", sub=f"d={dist[k]}", id=k,
                   state="focus" if k == "B" else ("done" if k in "AC" else None)).at(*pos[k]) for k in pos}
    for a, b, w in [("A", "B", 4), ("A", "C", 1), ("C", "B", 2), ("B", "D", 5), ("C", "D", 8)]:
        d.edge(n[a], n[b], str(w), state="accent" if (a, b) == ("C", "B") else None)
    # B-tree: one array per node, children hang off the gaps between keys
    root = d.array(["17", "35"], index=False, id="bt")
    kids = [d.array(k, index=False, id=f"bt{i}") for i, k in enumerate([["3", "9"], ["20", "28", "31"],
                                                                         ["40", "52"]])]
    d.tree(root, {root: kids}, at=(380, 0), hgap=24, vgap=48)
    for i, k in enumerate(kids):
        d.edge(root.gap_part(i), k)
    # stack frame: vertical array, addresses as index, register names as labels, a span for the frame
    mem = d.array(["ret addr", "saved rbp", "x = 7", "buf[0..7]", ""], orient="v", title="stack", id="mem",
                  index=["0x7ffc40", "0x7ffc38", "0x7ffc30", "0x7ffc28", "0x7ffc20"],
                  labels=["", "← rbp", "", "", "← rsp"])
    mem.span(0, 2, "frame of f()")
    mem.below(n["C"], gap=60, align="left")
    # state machine: pills, events / actions on the edges
    s = [d.node(t, shape="pill", kind="focal" if t == "CLOSED" else "default", id=t)
         for t in ["CLOSED", "SYN_SENT", "ESTABLISHED"]]
    d.row(s, at=(380, 220), gap=110)
    d.edge(s[0], s[1], "connect / SYN")
    d.edge(s[1], s[2], "SYN+ACK / ACK")
    d.edge(s[1], s[0], "timeout", style="dashed")
    d.legend(("state", "focus", "being relaxed"), ("state", "done", "settled"), ("edge", "accent", "shorter path found"))
