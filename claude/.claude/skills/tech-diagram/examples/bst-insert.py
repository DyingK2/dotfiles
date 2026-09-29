"""Algorithm process with a tree: inserting 6 into a BST, with Chinese text.
Positions come from laying out the FINAL tree once, so nothing moves between steps."""

KEYS = [8, 3, 10, 1, 5, 14, 4]   # existing tree, in insertion order
NEW = 6

STEPS = [
    dict(path=[8], cmp="6 < 8，向左", caption="从根开始：6 < 8，进入左子树。"),
    dict(path=[8, 3], cmp="6 > 3，向右", caption="6 > 3，进入 3 的右子树。"),
    dict(path=[8, 3, 5], cmp="6 > 5，向右", caption="6 > 5，而 5 的右孩子为空——这就是插入位置。",
         slot=True),
    dict(path=[8, 3, 5, 6], cmp="挂到 5.right", caption="新建节点 6，挂为 5 的右孩子。比较了 3 次，等于树高。",
         inserted=True),
]


def shape(keys):
    """BST children map for the given insertion order: {key: [left, right]}."""
    kids = {}
    root = keys[0]
    for k in keys[1:]:
        cur = root
        while True:
            side = 0 if k < cur else 1
            nxt = kids.setdefault(cur, [None, None])[side]
            if nxt is None:
                kids[cur][side] = k
                break
            cur = nxt
    return root, kids


def build(d, s):
    d.title("二叉搜索树：插入 6", eyebrow="Algorithm · BST",
            subtitle="每一步只和一个节点比较：小于往左，大于往右，走到空位就插入。")
    root, kids = shape(KEYS + [NEW])        # final shape → fixed positions for every step
    present = set(KEYS) | ({NEW} if s.get("inserted") else set())
    nodes = {}
    for k in KEYS + [NEW]:
        st = None
        if k == s["path"][-1]:
            st = "focus"
        elif k in s["path"]:
            st = "done"
        ghost = k == NEW and s.get("slot")
        nodes[k] = d.node("?" if ghost else str(k), shape="circle", id=f"k{k}", state=st,
                          kind="ghost" if ghost else "default",
                          sub=s["cmp"] if k == s["path"][-1] else None, sub_pos="right")
    children = {nodes[p]: [nodes[c] if c is not None else None for c in cs] for p, cs in kids.items()}
    d.tree(nodes[root], children, at=(0, 0), hgap=28, vgap=44)
    for k in KEYS + [NEW]:
        if k not in present and not (k == NEW and s.get("slot")):
            d.remove(nodes[k])                 # keeps its slot in the layout, not drawn
    for p, cs in kids.items():
        for c in cs:
            if c is not None and c in present and p in present:
                on_path = p in s["path"] and c in s["path"]
                d.edge(nodes[p], nodes[c], arrow="none", state="focus" if on_path else None, id=f"{p}-{c}")
            elif c == NEW and s.get("slot"):
                d.edge(nodes[p], nodes[c], arrow="none", style="dashed", id=f"{p}-{c}?")
    d.legend(("state", "focus", "当前比较的节点"), ("state", "done", "已走过的路径"))
