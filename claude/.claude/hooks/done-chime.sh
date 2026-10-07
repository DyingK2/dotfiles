#!/usr/bin/env bash
# Stop hook: Claude Code 一轮响应结束时响一声。
# setsid -f 脱离 hook 进程、立即返回,不拖慢收尾;没 pw-play 的机器静默跳过。
snd=/usr/share/sounds/freedesktop/stereo/complete.oga
command -v pw-play >/dev/null 2>&1 && [ -r "$snd" ] &&
  setsid -f pw-play "$snd" >/dev/null 2>&1 </dev/null
exit 0
