"""Dynamic programming table: edit distance, showing where one cell's value comes from."""

A, B = "horse", "ros"


def table():
    D = [[0] * (len(B) + 1) for _ in range(len(A) + 1)]
    for i in range(len(A) + 1):
        for j in range(len(B) + 1):
            if i == 0 or j == 0:
                D[i][j] = i + j
            else:
                D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (A[i - 1] != B[j - 1]))
    return D


def build(d):
    D = table()
    i, j = 2, 2                       # the cell being explained: "ho" → "ro"
    d.title("Edit distance: where D[i][j] comes from", eyebrow="Algorithm · dynamic programming",
            subtitle=f"D[i][j] = edits to turn the first i letters of “{A}” into the first j of "
                     f"“{B}”. Each cell looks at three neighbours only.")
    cols = ["", "∅"] + list(B)
    rows = [["∅"] + [str(v) for v in D[0]]] + [[A[r]] + [str(v) for v in D[r + 1]] for r in range(len(A))]
    t = d.table(cols, rows, grid=True, row_header=True, align=["center"] * len(cols), id="D", min_col_w=40,
                states={(i, j + 1): "focus", (i - 1, j): "accent", (i - 1, j + 1): "dim", (i, j): "dim",
                        (len(A), len(B) + 1): "done"})
    t.at(0, 0)
    d.edge(t[i - 1, j], t[i, j + 1], route="center", state="accent")        # diagonal: o == o, free
    d.edge(t[i - 1, j + 1], t[i, j + 1], route="center", style="dashed")    # delete
    d.edge(t[i, j], t[i, j + 1], route="center", style="dashed")            # insert
    code = d.code("""\
if A[i-1] == B[j-1]:
    D[i][j] = D[i-1][j-1]          # match: free
else:
    D[i][j] = 1 + min(D[i-1][j],   # delete
                      D[i][j-1],   # insert
                      D[i-1][j-1]) # replace""", highlight={1: "accent", 2: "accent"}, id="rule")
    code.right_of(t, gap=48, align="top")
    d.note(f"Here A[{i - 1}] = ‘{A[i - 1]}’ equals B[{j - 1}] = ‘{B[j - 1]}’, so D[{i}][{j}] "
           f"copies the diagonal: {D[i - 1][j - 1]}. The answer is the bottom-right cell: {D[-1][-1]}.",
           w=code.w).below(code, gap=20, align="left")
    d.legend(("state", "focus", "cell being computed"), ("state", "accent", "the neighbour it takes"),
             ("edge", "dashed", "neighbours it compares"), ("state", "done", "final answer"))
