"""Algorithm process: Lomuto partition, one page per interesting step (steps come from a real simulation)."""

CODE = """\
pivot = a[hi]
i = lo
for j in range(lo, hi):
    if a[j] < pivot:
        a[i], a[j] = a[j], a[i]
        i += 1
a[i], a[hi] = a[hi], a[i]   # pivot lands"""


def simulate(a):
    a = list(a)
    lo, hi = 0, len(a) - 1
    pivot, i = a[hi], lo
    steps = [dict(a=list(a), i=i, j=None, line=2, caption=f"Pivot = a[hi] = {pivot}. "
                                                               "i marks where the next small element goes.")]
    for j in range(lo, hi):
        if a[j] < pivot:
            a[i], a[j] = a[j], a[i]
            i += 1
            steps.append(dict(a=list(a), i=i, j=j, line=5,
                              caption=f"a[{j}] = {a[i - 1]} < {pivot}: swap it into slot {i - 1}, then i → {i}."))
    a[i], a[hi] = a[hi], a[i]
    steps.append(dict(a=list(a), i=i, j=None, line=7, done=True,
                      caption=f"Loop over. Swap the pivot into slot {i}: everything left of it is smaller, "
                              "everything right of it is not."))
    return steps


STEPS = simulate([7, 2, 9, 4, 3, 8, 5])


def build(d, s):
    d.title("Lomuto partition", eyebrow="Algorithm · quicksort",
            subtitle="Partition a[lo..hi] around the last element. One left-to-right scan; i grows the "
                     "“smaller than pivot” prefix.")
    hi = len(s["a"]) - 1
    states = {hi: "accent"} if not s.get("done") else {s["i"]: "accent"}
    arr = d.array(s["a"], id="a", title="a", states=states).at(0, 0)
    arr.pointer(s["i"], "i")
    if s["j"] is not None:
        arr.pointer(s["j"], "j")
    if s["i"] > 0:
        arr.span(0, s["i"] - 1, "< pivot", tone="teal")
    d.code(CODE, highlight=s["line"], id="code").right_of(arr, gap=56, align="top")
    d.legend(("state", "accent", "pivot"), ("tone", "teal", "partitioned prefix: a[lo..i-1] < pivot"))
