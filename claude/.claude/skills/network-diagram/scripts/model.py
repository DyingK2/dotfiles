# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""topology.yaml → normalized model (model.json).

Semantics only: validation, route display text, gateway shorthand, hop-by-hop flow paths. No coordinates.
usage: uv run scripts/model.py topology.yaml [-o model.json]
"""
import argparse
import ipaddress
import json
import pathlib
import sys
from collections import deque

import yaml

from i18n import detect

L2_ONLY_KINDS = {"phys-nic"}


class ModelError(Exception):
    pass


def gw_short(ip, gw):
    """Keep only the octets where the gateway differs from the host IP: 10.0.2.10 / 10.0.2.1 → '.1'."""
    a, b = ip.split("."), gw.split(".")
    same = 0
    while same < 3 and a[same] == b[same]:
        same += 1
    return gw if same == 0 else "." + ".".join(b[same:])


def _net(cidr):
    return None if cidr in (None, "dhcp") else ipaddress.ip_network(cidr)


def _iface(i, segs, owner):
    if i["seg"] not in segs:
        raise ModelError(f"{owner}: iface {i.get('name')} references unknown segment {i['seg']}")
    ip = i.get("ip")
    if ip and ip != "dhcp":
        ip = str(ip).split("/")[0]  # tolerate "10.0.1.1/24"
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise ModelError(f"{owner}: iface {i.get('name')} has invalid ip {i.get('ip')!r}") from None
    net = segs[i["seg"]]["net"]
    if ip and ip != "dhcp" and net and ipaddress.ip_address(ip) not in net:
        raise ModelError(f"{owner}: {ip} is not inside segment {i['seg']} ({net})")
    out = {"name": i.get("name"), "seg": i["seg"], "ip": ip, "net": i.get("net"), "tap": i.get("tap")}
    if i.get("gw"):
        out["gw"] = i["gw"]
        out["gw_short"] = gw_short(ip, i["gw"])
    return out


def _route(r):
    dst, _, via = r.partition(" via ")
    dst, via = dst.strip(), via.strip()
    return {"prefix": dst, "via": via, "text": f"{dst} → {via}"}


def _prefix(p):
    return ipaddress.ip_network("0.0.0.0/0" if p == "default" else p)


def build_model(raw):
    segs = {}
    for s in raw.get("segments", []):
        segs[s["id"]] = {"id": s["id"], "cidr": s["cidr"], "role": s["role"],
                         "label": s.get("label", s["role"]), "net": _net(s["cidr"])}

    nodes = []
    for e in raw.get("external", []):
        kind = e["kind"]
        if e.get("seg") and e["seg"] not in segs:
            raise ModelError(f"{e['id']}: references unknown segment {e['seg']}")
        nodes.append({"id": e["id"], "kind": kind, "label": e.get("label", e["id"]), "sub": e.get("sub"),
                      "vmid": None, "ifaces": [{"name": None, "seg": e["seg"], "ip": None}] if e.get("seg") else [],
                      "routes": [], "notes": [],
                      "views": ["l2"] if kind in L2_ONLY_KINDS else ["l2", "l3"]})
    for d in raw.get("devices", []):
        nodes.append({"id": d["id"], "kind": d["kind"], "label": d.get("label", d["id"]), "sub": d.get("sub"),
                      "vmid": d.get("vmid"),
                      "ifaces": [_iface(i, segs, d["id"]) for i in d.get("ifaces", [])],
                      "routes": [_route(r) for r in d.get("routes", [])],
                      "notes": list(d.get("notes", [])),
                      "views": ["l2", "l3"]})
    by_id = {n["id"]: n for n in nodes}
    if len(by_id) != len(nodes):
        raise ModelError("duplicate node id")

    _check_reachable(nodes, segs)
    flows = [dict(f, hops=_trace(f, by_id, segs)) for f in raw.get("flows", [])]
    warnings = _lint(nodes, segs)
    for f in flows:  # replies need a path too: a broken return path is the classic "ping times out"
        if "cloud" in (by_id[f["from"]]["kind"], by_id[f["to"]]["kind"]):
            continue  # replies from the Internet come back via NAT/upstream, not traceable here
        try:
            _trace({"from": f["to"], "to": f["from"]}, by_id, segs)
        except ModelError as e:
            warnings.append(f"return path broken — {e}")

    seg_out = [{k: v for k, v in s.items() if k != "net"} for s in segs.values()]
    meta = {k: str(v) for k, v in (raw.get("meta") or {}).items()}
    meta["lang"] = detect(raw)  # YAML parses dates into date objects
    return {"meta": meta, "segments": seg_out, "nodes": nodes, "flows": flows, "warnings": warnings}


def _lint(nodes, segs):
    """Suspicious but drawable config: gateways and next hops that point at no device."""
    out = []
    addrs = {}  # seg → {ip: node id}
    for n in nodes:
        for i in n["ifaces"]:
            if i["ip"] and i["ip"] != "dhcp":
                addrs.setdefault(i["seg"], {})[i["ip"]] = n["id"]
    for n in nodes:
        for i in n["ifaces"]:
            if i.get("gw") and i["gw"] not in addrs.get(i["seg"], {}):
                out.append(f"{n['id']}: gateway {i['gw']} is not the address of any device on {i['seg']}")
        for r in n["routes"]:
            if r["via"] == "dhcp":
                continue
            try:
                ipaddress.ip_address(r["via"])
            except ValueError:
                out.append(f"{n['id']}: route '{r['text']}' — next hop must be an IP (omit routes learned via "
                           f"DHCP on the uplink, or write 'via dhcp')")
                continue
            if not any(r["via"] in addrs.get(i["seg"], {}) for i in n["ifaces"]):
                out.append(f"{n['id']}: route '{r['text']}' — next hop {r['via']} is not a device on a directly "
                           f"connected segment")
    return out


def _check_reachable(nodes, segs):
    l3 = [n for n in nodes if "l3" in n["views"]]
    roots = [n for n in l3 if n["kind"] == "cloud"] or l3[:1]
    seen, q = set(), deque(("n", r["id"]) for r in roots)
    seg_nodes = {}
    for n in l3:
        for i in n["ifaces"]:
            seg_nodes.setdefault(i["seg"], []).append(n)
    by_id = {n["id"]: n for n in l3}
    while q:
        t, x = q.popleft()
        if (t, x) in seen:
            continue
        seen.add((t, x))
        if t == "n":
            q.extend(("s", i["seg"]) for i in by_id[x]["ifaces"])
        else:
            q.extend(("n", n["id"]) for n in seg_nodes.get(x, []))
    lost = [n["id"] for n in l3 if ("n", n["id"]) not in seen]
    if lost:
        raise ModelError(f"not reachable from the Internet/root: {', '.join(lost)}")


def _addr(node):
    for i in node["ifaces"]:
        if i["ip"] and i["ip"] != "dhcp":
            return ipaddress.ip_address(i["ip"])
    return None


def _owner_of(ip, by_id):
    for n in by_id.values():
        for i in n["ifaces"]:
            if i["ip"] == ip:
                return n, i
    return None, None


def _trace(flow, by_id, segs):
    src, dst = by_id.get(flow["from"]), by_id.get(flow["to"])
    if not src or not dst:
        raise ModelError(f"flow endpoint not found: {flow['from']} → {flow['to']}")
    dst_ip = _addr(dst)
    dst_segs = {i["seg"] for i in dst["ifaces"]}
    hops = [{"type": "node", "id": src["id"]}]
    cur, via_if = src, None
    for _ in range(32):
        shared = [i for i in cur["ifaces"] if i["seg"] in dst_segs]
        if shared:
            if via_if is not None:
                hops[-1]["out_if"] = shared[0]["name"]
            hops.append({"type": "seg", "id": shared[0]["seg"]})
            hops.append({"type": "node", "id": dst["id"]})
            return hops
        nh = _next_hop(cur, dst_ip)
        if not nh:
            raise ModelError(f"flow {flow['from']} → {flow['to']}: {cur['id']} has no route to the destination")
        nxt, nxt_if = _owner_of(nh, by_id)
        if not nxt:
            raise ModelError(f"flow {flow['from']} → {flow['to']}: next hop {nh} belongs to no device")
        out = next(i for i in cur["ifaces"] if i["seg"] == nxt_if["seg"])
        if via_if is not None:
            hops[-1]["out_if"] = out["name"]
        hops.append({"type": "seg", "id": nxt_if["seg"]})
        hops.append({"type": "node", "id": nxt["id"], "in_if": nxt_if["name"]})
        cur, via_if = nxt, nxt_if
    raise ModelError(f"flow {flow['from']} → {flow['to']}: routing loop")


def _next_hop(node, dst_ip):
    """Longest-prefix match: static routes + gw on host interfaces (treated as the default route)."""
    table = [(_prefix(r["prefix"]), r["via"]) for r in node["routes"] if r["via"] != "dhcp"]
    table += [(_prefix("default"), i["gw"]) for i in node["ifaces"] if i.get("gw")]
    cands = [(p, via) for p, via in table if dst_ip is None and p.prefixlen == 0 or dst_ip is not None and dst_ip in p]
    if not cands:
        return None
    return max(cands, key=lambda c: c[0].prefixlen)[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    try:
        m = build_model(yaml.safe_load(pathlib.Path(a.yaml).read_text()))
    except ModelError as e:
        sys.exit(f"error: {e}")
    s = json.dumps(m, ensure_ascii=False, indent=2)
    pathlib.Path(a.out).write_text(s) if a.out else print(s)


if __name__ == "__main__":
    main()
