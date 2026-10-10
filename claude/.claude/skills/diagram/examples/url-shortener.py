"""System structure: a URL shortener, request path for GET /{code} numbered end to end."""


def build(d):
    d.title("URL shortener · read path", eyebrow="System design",
            subtitle="GET /x7Kp2 → 301 to the long URL. Hot codes are served from Redis; a miss falls "
                     "through to Postgres and back-fills the cache.")
    user = d.node("Browser", sub="GET /x7Kp2", icon="world", kind="external")
    lb = d.node("Load balancer", sub="L7 · TLS · :443", icon="arrows-split")
    api = d.node("Redirect API", sub="stateless × 6 pods", tag="svc", icon="server", kind="focal")
    cache = d.node("Redis", sub="code → url · TTL 24 h", icon="bolt", kind="store")
    db = d.node("urls", tag="postgres", icon="database", kind="store",
                fields=[("code", "char(7)", ["PK"]), ("long_url", "text"), ("created_at", "timestamptz"),
                        ("hits", "bigint")])
    q = d.node("click events", sub="kafka · topic clicks", icon="stack-2", kind="store")
    stats = d.node("Stats worker", sub="batch 1 s → hits += n", icon="refresh", kind="default")

    d.row([user, lb, api], at=(0, 0), gap=96)
    cache.right_of(api, gap=208, align="top").shift(dy=-56)
    db.below(cache, gap=40, align="left")
    d.group([api], label="k8s · app", kind="boundary")
    data = d.group([cache, db], label="data", kind="zone")
    q.below(data, gap=40).align_x(api)
    stats.right_of(q, gap=88, align="center")

    d.edge(user, lb, "HTTPS", step=1)
    d.edge(lb, api, "HTTP/1.1", step=2)
    d.edge(api, cache, "GET code", step=3, state="accent")
    d.edge(api, db["code"], "on miss: SELECT", step=4, style="dashed")
    d.edge(api, q, "click", style="dashed", step=5)
    d.edge(q, stats, "consume")
    d.edge(stats, db["hits"], "UPDATE hits")
    d.note("99% of reads stop at step 3; p99 < 5 ms.", target=cache, w=190).right_of(cache, gap=40)
    d.legend(("node", "focal", "service under discussion"), ("node", "store", "state"),
             ("edge", "dashed", "only on a cache miss / async"), ("edge", "accent", "hot path"))
