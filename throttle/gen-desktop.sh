#!/usr/bin/env bash
# 从系统 .desktop 生成同名覆盖:只留英文主字段,把每条 Exec 前缀成「在 throttle.slice 里启动」。
# 浏览器包更新改了 .desktop 时重跑一次:  ~/dotfiles/throttle/gen-desktop.sh
set -euo pipefail
out="$(dirname "$(readlink -f "$0")")/.local/share/applications"
mkdir -p "$out"
for f in firefox chromium google-chrome com.google.Chrome; do
    src=/usr/share/applications/$f.desktop
    [ -f "$src" ] || continue
    awk '
        /^\[/ { print (NR > 1 ? "\n" : "") $0; next }
        /^(Type|Name|GenericName|Icon|Terminal|Categories|MimeType|StartupNotify|StartupWMClass|Actions|Keywords)=/ { print; next }
        /^Exec=/ { sub(/^Exec=/, "Exec=systemd-run --user --scope --quiet --slice=throttle.slice "); print }
    ' "$src" >"$out/$f.desktop"
    echo "生成 $out/$f.desktop"
done
