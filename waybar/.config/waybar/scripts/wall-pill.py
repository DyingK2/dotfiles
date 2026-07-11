#!/usr/bin/env python3
"""waybar custom/wall reader — 墙外连通哨兵 pill.

waybar runs this on an interval. GET a deterministically-blocked canary
(Google's generate_204) over whatever routing is currently in effect, and
boil "can I reach 墙外 right now" down to up / down as one JSON pill:

  up   : HTTP 204 → the whole out-of-country chain (local net + clash TUN +
         proxy node) is healthy. Quiet, normal color. Latency in tooltip.
  down : timeout / connect failure / non-204 → red. clash stopped, dead proxy
         node, or upstream link down all land here. Loud on purpose.

On this box clash-verge runs in TUN mode: the Meta interface transparently
captures even a plain request to google (fake-ip + policy route table 2022),
so an unproxied GET here == what the browser actually gets. No proxy env, no
`-x` — we probe the effective path on purpose (真实出国体感).

stdlib only. Always exits 0 and prints exactly one JSON object so waybar stays
happy. Mirrors tailscale-pill.py.
"""
import json
import time
import urllib.error
import urllib.request

ICON = "󰇧"  # nf-md-earth
URL = "https://www.google.com/generate_204"
TIMEOUT = 6


def emit(text: str, cls: str, tooltip: str) -> None:
    print(json.dumps({"text": text, "class": cls, "tooltip": tooltip}, ensure_ascii=False))


def main() -> None:
    req = urllib.request.Request(URL, method="GET", headers={"User-Agent": "waybar-wall/1"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            code = resp.status
        ms = round((time.monotonic() - start) * 1000)
    except urllib.error.HTTPError as e:
        # got an HTTP response but not 204 — likely captive portal / block page
        emit(f"{ICON} off", "down", f"墙外异常:HTTP {e.code}(疑似劫持/门户页)")
        return
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            emit(f"{ICON} off", "down", f"墙外不可达:探测超时 {TIMEOUT}s(查 clash / 节点)")
        else:
            emit(f"{ICON} off", "down", f"墙外不可达:连接失败 · {reason}")
        return

    if code == 204:
        emit(ICON, "up", f"墙外可达 · google 204 · {ms}ms")
    else:
        emit(f"{ICON} off", "down", f"墙外异常:HTTP {code}(期望 204)")


if __name__ == "__main__":
    main()
