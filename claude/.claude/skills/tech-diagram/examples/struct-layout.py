"""Horizontal memory map at byte granularity: a C struct with alignment padding, a nested struct and the
8-byte words it occupies (x86-64 SysV ABI: sizeof = 32, of which 7 bytes are padding; offsets checked with gcc)."""


def build(d):
    d.title("结构体内存布局：对齐与填充", eyebrow="C · x86-64 SysV ABI",
            subtitle="每个字段按自身大小对齐：len 要落在 4 的倍数、data 要落在 8 的倍数，于是编译器插入 7 字节填充。"
                     "sizeof(struct pkt) = 32，而字段本身只有 25 字节。")
    m = d.memmap([
        dict(name="type", start=0, size=1, sub=["uint8_t"], tone="amber"),
        dict(name="len", start=4, size=4, sub=["uint32_t"]),
        dict(name="seq", start=8, size=8, sub=["uint64_t"]),
        dict(name="ports", start=16, size=4, tone="teal", children=[
            dict(name="sport", start=16, size=2, sub=["u16"]),
            dict(name="dport", start=18, size=2, sub=["u16"]),
        ]),
        dict(name="data", start=24, size=8, sub=["void *"], tone="violet"),
    ], orient="h", title="struct pkt（偏移，字节）", scale="linear", length=820, min_w=40, gap_label="pad",
        addr_fmt=lambda a: f"+{a}", inclusive=False, bounds=(0, 32), id="pkt")
    m.at(0, 0)
    for w in range(4):
        m.overlay(8 * w, 8 * w + 8, f"word {w}", tone="slate", id=f"w{w}")
    m.span(0, 32, "sizeof = 32 B · 一个 64 B 缓存行装得下两个")
    code = d.code("struct pkt {\n    uint8_t  type;\n    uint32_t len;\n    uint64_t seq;\n"
                  "    struct { uint16_t sport, dport; } ports;\n    void    *data;\n};", title="pkt.h", id="src")
    code.below(m, gap=40, align="left")
    d.note("字段按大小从大到小排（seq, data, len, ports, type），7 字节填充全挤到末尾；"
           "再加一个 uint16_t 字段 sizeof 仍是 32（gcc 实测）。", w=320).right_of(code, gap=40, align="top")
