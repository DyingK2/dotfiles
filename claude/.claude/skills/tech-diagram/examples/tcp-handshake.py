"""Network: TCP three-way handshake and teardown as a sequence diagram, with seq/ack numbers and states."""


def build(d):
    d.title("TCP connection lifecycle", eyebrow="Network · transport",
            subtitle="Every SYN and FIN consumes one sequence number, so each ACK is the peer's seq + 1. "
                     "States in the notes are the endpoints' TCP states after the message.")
    d.seq(
        actors=[("c", "Client", "10.0.0.7:51514"), ("s", "Server", "93.184.216.34:443")],
        messages=[
            {"divider": "open"},
            ("c", "s", "SYN  seq=100"),
            {"note": "client: SYN_SENT", "over": "c"},
            ("s", "c", "SYN+ACK  seq=300 ack=101"),
            {"note": "server: SYN_RCVD", "over": "s"},
            ("c", "s", "ACK  seq=101 ack=301", {"state": "accent"}),
            {"note": "both: ESTABLISHED — data can flow", "over": ["c", "s"]},
            {"divider": "close"},
            ("c", "s", "FIN  seq=101"),
            ("s", "c", "ACK  ack=102", {"dashed": True}),
            ("s", "c", "FIN  seq=301"),
            ("c", "s", "ACK  ack=302", {"dashed": True}),
            {"note": "client waits 2×MSL in TIME_WAIT before the port is reusable", "over": "c"},
        ],
        numbered=True, id="tcp",
    ).at(0, 0)
    d.legend(("edge", "accent", "handshake completes here"), ("edge", "dashed", "pure ACK"))
