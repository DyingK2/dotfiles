#!/bin/sh
# custom/wall 的 on-click 诊断:对两个被墙金丝雀,分别测「直连(系统当前路由)」
# 与「显式走 clash mixed 端口 7897」,一眼分清是 clash/TUN 挂了还是代理节点挂了。
#   - 直连 通、走7897 通  → 一切正常
#   - 直连 挂、走7897 通  → TUN/系统路由问题(clash 没接管)
#   - 直连 挂、走7897 挂  → 代理节点挂 / 上游断网
PROXY=http://127.0.0.1:7897
probe() {
    curl -sS -o /dev/null -w "%{http_code} · %{time_total}s\n" --max-time 8 "$@" 2>/dev/null \
        || echo "失败/超时"
}
echo "== 墙外连通诊断 =="
for url in https://www.google.com/generate_204 https://www.youtube.com/generate_204; do
    echo "$url"
    printf '  直连  : '; probe --noproxy '*' "$url"
    printf '  走7897: '; probe -x "$PROXY" "$url"
done
echo
read -p "[enter] 关闭" _
