#!/usr/bin/env python3
"""waybar custom/tasks reader — 今日主线 pill, live from TickTick Open API.

waybar runs this on an interval. Online: fetch projects, pick today's main
line, write it to the offline cache, emit a JSON pill. Offline / error / no
token: fall back to the last cached title so the bar degrades gracefully.

Selection rule: prefer undone tasks tagged 在读; else priority==5 undone;
take the one with the smallest sortOrder. None → empty (pill hidden via CSS).

Contract (see atelier efforts/2026-06-27-waybar-center/):
  ~/.config/atelier/ticktick-token : access token (from ticktick-auth.py)
  ~/.cache/atelier/task-now         : single-line cached title (offline fallback)

stdlib only. Always exits 0 and prints exactly one JSON object so waybar is happy.
"""
import json
import os
import urllib.error
import urllib.request

ICON = ""  # nf-fa-tasks
API = "https://api.ticktick.com/open/v1"
TOKEN_PATH = os.path.expanduser(
    os.path.join(os.environ.get("XDG_CONFIG_HOME", "~/.config"), "atelier", "ticktick-token")
)
CACHE_PATH = os.path.expanduser(
    os.path.join(os.environ.get("XDG_CACHE_HOME", "~/.cache"), "atelier", "task-now")
)


def emit(title: str) -> None:
    if title:
        print(json.dumps({"text": f"{ICON} {title}", "class": "has-task"}, ensure_ascii=False))
    else:
        print(json.dumps({"text": ""}, ensure_ascii=False))


def read_cache() -> str:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return f.readline().strip()
    except OSError:
        return ""


def write_cache(title: str) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(title + "\n")
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


def read_token() -> str:
    try:
        with open(TOKEN_PATH, encoding="utf-8") as f:
            return f.readline().strip()
    except OSError:
        return ""


def api_get(path: str, token: str):
    req = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pick_title(tasks: list) -> str:
    undone = [t for t in tasks if t.get("status", 0) == 0]
    reading = [t for t in undone if "在读" in (t.get("tags") or [])]
    pool = reading or [t for t in undone if t.get("priority", 0) == 5]
    if not pool:
        return ""
    pool.sort(key=lambda t: t.get("sortOrder", 0))
    return (pool[0].get("title") or "").strip()


def main() -> None:
    token = read_token()
    if not token:
        # not yet authed — degrade to whatever was cached (likely empty)
        emit(read_cache())
        return
    try:
        projects = api_get("/project", token)
        tasks = []
        for p in projects:
            pid = p.get("id")
            if not pid:
                continue
            data = api_get(f"/project/{pid}/data", token)
            tasks.extend(data.get("tasks") or [])
        title = pick_title(tasks)
        write_cache(title)  # keep offline fallback fresh (incl. clearing it)
        emit(title)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        # offline / token expired / API hiccup → show last known
        emit(read_cache())


if __name__ == "__main__":
    main()
