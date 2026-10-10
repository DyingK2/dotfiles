"""Protocol fields: the TCP header, 32 bits per row, with the values of a real SYN+ACK."""


def build(d):
    d.title("TCP header", eyebrow="Network · RFC 9293",
            subtitle="20 bytes without options. Values are from the SYN+ACK of a handshake; the flags that "
                     "are set are highlighted.")
    hdr = d.bits([
        ("Source port", 16, "443"), ("Destination port", 16, "51514"),
        ("Sequence number", 32, "300"),
        ("Acknowledgment number", 32, "101"),
        ("Offset", 4, "5 (×4 B)"), ("Rsv", 4, "0"),
        ("C", 1, "0"), ("E", 1, "0"), ("U", 1, "0"), dict(name="A", bits=1, value="1", state="accent"),
        ("P", 1, "0"), ("R", 1, "0"), dict(name="S", bits=1, value="1", state="accent"), ("F", 1, "0"),
        ("Window", 16, "65535"),
        ("Checksum", 16, "0x5a3c"), ("Urgent pointer", 16, "0"),
    ], width=32, bit_w=22, title="bits  0 … 31", id="tcp").at(0, 0)
    flags = d.table(["flag", "meaning"], [["S  SYN", "synchronize sequence numbers"],
                                          ["A  ACK", "acknowledgment field is valid"],
                                          ["F  FIN", "sender has finished sending"],
                                          ["R  RST", "reset the connection"]],
                    id="flags", mono=[0], states={0: "accent", 1: "accent"})
    flags.right_of(hdr, gap=56, align="top")
    d.note("Offset counts 32-bit words: 5 × 4 = 20 bytes, i.e. no options.", w=230) \
        .below(flags, gap=24, align="left")
    d.legend(("state", "accent", "flag set in this segment"))
