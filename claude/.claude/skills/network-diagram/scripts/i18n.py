"""Text drawn on the diagram, in Chinese and English.

The language comes from `meta.lang` (zh | en); when absent it is zh if any title/label/note in the YAML
contains CJK characters, otherwise en. Layouts call `use(model)` once, then `T(key, **fields)`.
"""
import re

STR = {
    "zh": {
        "title": "网络拓扑", "view_l3": "L3 逻辑拓扑", "view_l2": "L2 宿主机视图",
        "scope": "范围：VM {a} – {b}", "version": "版本：{v}", "host": "宿主：{h}",
        "legend": "图例", "plan": "地址规划", "col_seg": "网段", "col_bridge": "标识", "col_use": "用途",
        "lg_router": "三层设备（路由器）", "lg_host": "终端主机", "lg_seg": "三层网段（bridge / VLAN）",
        "lg_if": "接口名 · 地址", "lg_annot": "路由 / 策略注释", "lg_flow": "测试流量路径",
        "lr_router": "路由器", "lr_seg": "三层网段", "lr_annot": "路由 / 策略", "lr_flow": "测试流量",
        "flow": "测试流量 {src} → {dst}{tag}：{path}", "flow_tag": "（{label}）", "forwards": "{r} 转发",
        "sep": "；",
        "upstream": "上游网络", "bridged": "桥接 {nic}", "host_frame": "{host} 宿主机", "kernel": "Linux 内核网络栈",
        "l2_sub": "bridge / tap 映射", "lg_dot": "端口挂在该 bridge 上", "lg_hop": "跨越弧：仅交叉，不相连",
        "note_tap": "tap<VMID>i<N>：PVE 为 VM 的第 N 块虚拟网卡在宿主机上创建的 tap 设备，作为 bridge 端口",
        "note_fw": "启用 PVE 防火墙时，tap 与 vmbr 之间会多出 fwbr / fwpr / fwln 一层 · 可用 bridge link 核对",
    },
    "en": {
        "title": "Network topology", "view_l3": "L3 logical topology", "view_l2": "L2 host view",
        "scope": "Scope: VM {a} – {b}", "version": "Version: {v}", "host": "Host: {h}",
        "legend": "Legend", "plan": "Address plan", "col_seg": "Subnet", "col_bridge": "ID", "col_use": "Name",
        "lg_router": "L3 device (router)", "lg_host": "End host", "lg_seg": "L3 segment (bridge / VLAN)",
        "lg_if": "Interface · address", "lg_annot": "Routes / policy", "lg_flow": "Test traffic path",
        "lr_router": "Router", "lr_seg": "L3 segment", "lr_annot": "Routes / policy", "lr_flow": "Test traffic",
        "flow": "Test traffic {src} → {dst}{tag}: {path}", "flow_tag": " ({label})", "forwards": "{r}",
        "sep": "; ",
        "upstream": "Upstream", "bridged": "bridged to {nic}", "host_frame": "{host} host",
        "kernel": "Linux kernel network stack",
        "l2_sub": "bridge / tap mapping", "lg_dot": "Port attached to this bridge",
        "lg_hop": "Hop arc: crossing, not connected",
        "note_tap": "tap<VMID>i<N>: tap device PVE creates on the host for NIC N of a VM; it is the bridge port",
        "note_fw": "With the PVE firewall on, fwbr / fwpr / fwln sit between tap and vmbr · verify with bridge link",
    },
}
LANG = ["zh"]
CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿]")


def detect(raw):
    """Language of a raw topology dict: meta.lang if set, else zh when any human-readable text has CJK."""
    meta = raw.get("meta") or {}
    if meta.get("lang") in STR:
        return meta["lang"]
    texts = [str(v) for v in meta.values()]
    for group in ("segments", "external", "devices"):
        for item in raw.get(group) or []:
            texts += [str(item.get(k, "")) for k in ("label", "sub")] + [str(n) for n in item.get("notes", [])]
    texts += [str(f.get("label", "")) for f in raw.get("flows") or []]
    return "zh" if any(CJK.search(t) for t in texts) else "en"


def use(model):
    LANG[0] = model["meta"].get("lang", "zh")


def T(key, **kw):
    return STR[LANG[0]][key].format(**kw)
