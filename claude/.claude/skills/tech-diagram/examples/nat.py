"""Network topology: source NAT on a home router, with the translation table that makes replies find
their way back."""


def build(d):
    d.title("Source NAT (masquerade)", eyebrow="Network · topology",
            subtitle="Two LAN hosts share one public address. The router rewrites the source of outgoing "
                     "packets and remembers the mapping; the reply is matched against that table.")
    a = d.node("laptop", sub=["192.168.1.20", "gw 192.168.1.1"], icon="device-laptop", id="a")
    b = d.node("phone", sub=["192.168.1.31", "gw 192.168.1.1"], icon="device-mobile", id="b")
    r = d.node("home router", tag="NAT", icon="router", kind="focal", id="r",
               fields=[("lan0", "192.168.1.1/24"), ("wan0", "203.0.113.5"), ("rule", "masquerade -o wan0")])
    web = d.node("example.com", sub="93.184.216.34:443", icon="world", kind="external", id="web")
    d.col([a, b], at=(0, 0), gap=32, align="left")
    r.right_of(a, gap=150).align_y(d.group([a, b], label="LAN 192.168.1.0/24", kind="zone", id="lan"))
    web.right_of(r, gap=190, align="top")
    d.edge(a, r["lan0"], "src .20:51514")
    d.edge(b, r["lan0"], "src .31:40022")
    d.edge(r["wan0"], web, "src 203.0.113.5:61001", state="accent")
    t = d.table(["inside", "outside", "remote"],
                [["192.168.1.20:51514", "203.0.113.5:61001", "93.184.216.34:443"],
                 ["192.168.1.31:40022", "203.0.113.5:61002", "93.184.216.34:443"]],
                title="conntrack / NAT table", id="nat", states={0: "accent"})
    t.below(r, gap=48, align="left")
    d.edge(r["rule"], t.row(0), style="dotted", arrow="end", src_side="left", dst_side="left")
    d.note("Reply to 203.0.113.5:61001 → table row 1 → rewritten to 192.168.1.20:51514.", target=t.row(0),
           w=210).right_of(t, gap=32, align="top")
    d.legend(("node", "focal", "does the translation"), ("edge", "accent", "packet after rewrite"),
             ("group", "zone", "private network"))
