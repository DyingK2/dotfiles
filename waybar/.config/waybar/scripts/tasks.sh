#!/usr/bin/env bash
# waybar custom/tasks reader —— 渲染「今日主线」缓存为 JSON pill。
# Contract (see atelier efforts/2026-06-27-waybar-center/DESIGN.md):
#   ~/.cache/atelier/task-now : 单行标题；空 = 无主线。
set -euo pipefail

cache="${XDG_CACHE_HOME:-$HOME/.cache}/atelier/task-now"
title="$(head -n1 "$cache" 2>/dev/null || true)"

if [ -z "$title" ]; then
  printf '{"text":""}\n'
  exit 0
fi

# JSON-escape backslash 与 double-quote
esc="${title//\\/\\\\}"
esc="${esc//\"/\\\"}"
printf '{"text":" %s","class":"has-task"}\n' "$esc"
