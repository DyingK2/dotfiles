#!/usr/bin/env -S uv run --no-project python3
"""One-time TickTick OAuth helper for the waybar 今日主线 pill.

Registers nothing — you create the app at https://developer.ticktick.com/manage
first (Redirect URI must be exactly http://127.0.0.1:8080/callback), then run:

    ticktick-auth.py --client-id <ID> --client-secret <SECRET>

It opens the authorize page in your browser, catches the redirect locally,
exchanges the code for an access token, and saves it (chmod 600) to
  ~/.config/atelier/ticktick-token

No external deps — stdlib only. See atelier efforts/2026-06-27-waybar-center/.
"""
import argparse
import base64
import http.server
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

REDIRECT_URI = "http://127.0.0.1:8080/callback"
PORT = 8080
SCOPE = "tasks:read tasks:write"
AUTHORIZE_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://ticktick.com/oauth/token"
TOKEN_PATH = os.path.expanduser(
    os.path.join(os.environ.get("XDG_CONFIG_HOME", "~/.config"), "atelier", "ticktick-token")
)

_code_holder = {}
_done = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        _code_holder["code"] = qs.get("code", [None])[0]
        _code_holder["error"] = qs.get("error", [None])[0]
        _done.set()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = "授权失败，可关闭本页重试" if _code_holder.get("error") else "授权成功，可关闭本页回到终端"
        self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode("utf-8"))

    def log_message(self, *args):  # silence
        pass


def get_code(client_id: str) -> str:
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "scope": SCOPE,
            "state": "waybar",
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
        }
    )
    url = f"{AUTHORIZE_URL}?{params}"
    server = http.server.HTTPServer(("127.0.0.1", PORT), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"打开浏览器授权（若没自动弹出，手动访问）：\n{url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    _done.wait(timeout=300)
    server.shutdown()
    if _code_holder.get("error"):
        sys.exit(f"授权被拒绝: {_code_holder['error']}")
    code = _code_holder.get("code")
    if not code:
        sys.exit("未拿到 code")
    return code


def exchange(client_id: str, client_secret: str, code: str) -> dict:
    body = urllib.parse.urlencode(
        {
            "code": code,
            "grant_type": "authorization_code",
            "scope": SCOPE,
            "redirect_uri": REDIRECT_URI,
        }
    ).encode("utf-8")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    args = ap.parse_args()

    code = get_code(args.client_id)
    tok = exchange(args.client_id, args.client_secret, code)
    access = tok.get("access_token")
    if not access:
        sys.exit(f"token 响应异常: {tok}")

    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(access + "\n")
    os.chmod(TOKEN_PATH, 0o600)
    exp = tok.get("expires_in")
    print(f"\n✓ token 已保存到 {TOKEN_PATH} (chmod 600)")
    if exp:
        print(f"  有效期约 {int(exp)//86400} 天，过期后重跑本脚本即可。")


if __name__ == "__main__":
    main()
