"""Data structure: hash table with separate chaining."""
from dgm import NULL, PTR


def build(d):
    d.title("Hash table · separate chaining", eyebrow="Data structure",
            subtitle="put(key): bucket = hash(key) mod 8. Keys that land in the same bucket are chained "
                     "in a singly linked list; lookup walks only that chain.")
    chains = {1: ["cat:7", "dog:2"], 3: ["owl:5"], 6: ["ant:3", "bee:9", "elk:1"]}
    vals = [PTR if i in chains else NULL for i in range(8)]
    b = d.array(vals, orient="v", title="buckets[8]", id="b", states={6: "focus"})
    b.at(0, 0)
    for i, keys in chains.items():
        prev = b[i]
        for k, key in enumerate(keys):
            n = d.listnode(key, next=k < len(keys) - 1, id=f"n{i}{k}")
            n.right_of(prev if k else b, gap=56 if k == 0 else 40, align="center")
            if k == 0:
                n.align_y(b[i])
            d.edge(prev if k == 0 else prev.next, n, id=f"e{i}{k}")
            prev = n
    q = d.node("hash(\"elk\") = 0x3e", sub="0x3e mod 8 = 6", tag="lookup", kind="focal")
    q.left_of(b, gap=64).align_y(b[6])
    d.edge(q, b[6], "index 6", state="accent")
    d.note("Load factor α = 6 keys / 8 buckets = 0.75. Chains stay short while α ≲ 1; beyond that, resize "
           "and rehash.", w=250).below(b, gap=28, align="left")
    d.legend(("node", "focal", "the lookup being traced"), ("state", "focus", "bucket it lands in"))
