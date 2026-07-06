#!/usr/bin/env python3
"""waybar custom/tailscale reader — tailnet 连通哨兵 pill.

waybar runs this on an interval. Read `tailscale status --json`, boil the
tailnet state down to up / down and emit one JSON pill:

  up   : backend Running AND self reports Online → quiet, normal color.
  down : backend Running but Self.Online false → red. This is the exact
         signature of the clash fake-ip hijack of controlplane.tailscale.com
         (see atelier memory clash-tailscale-fakeip): tailscaled is up but
         can't reach the coordination server. Loud on purpose.
  down : backend Stopped / NeedsLogin / anything else → red, state in tooltip.

`tailscale status --json` prints a version-skew warning to STDERR; we read
stdout only so it never poisons the JSON. stdlib only. Always exits 0 and
prints exactly one JSON object so waybar stays happy.
"""
import json
import subprocess

ICON = "󰖂"  # nf-md-vpn


def emit(text: str, cls: str, tooltip: str) -> None:
    print(json.dumps({"text": text, "class": cls, "tooltip": tooltip}, ensure_ascii=False))


def main() -> None:
    try:
        out = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=8,
        ).stdout
        d = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        emit(f"{ICON} ?", "down", "tailscale 不可用")
        return

    state = d.get("BackendState", "?")
    self_node = d.get("Self") or {}
    online = bool(self_node.get("Online"))
    ips = self_node.get("TailscaleIPs") or []
    v4 = next((ip for ip in ips if ":" not in ip), ips[0] if ips else "?")
    peers = sum(1 for p in (d.get("Peer") or {}).values() if p.get("Online"))

    if state == "Running" and online:
        emit(ICON, "up", f"tailnet 在线 · {v4} · {peers} 台 peer 在线")
    elif state == "Running":
        emit(f"{ICON} off", "down",
             "tailnet 掉线:tailscaled 在跑但连不上协调服务器"
             "(疑似 clash fake-ip 劫持 controlplane)")
    else:
        emit(f"{ICON} off", "down", f"tailscaled: {state}")


if __name__ == "__main__":
    main()
