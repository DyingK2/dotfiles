# bin —— 自用脚本(stow 包)

自用实用脚本的**真相**住这里,`stow bin` 把它们符号链接进 `~/.local/bin/`
(已在 PATH)。进 git、双机经 Tailscale 同步。

## 用法

- 加脚本:丢进 `bin/.local/bin/`,`chmod +x`,`cd ~/dotfiles && stow bin`。
- 双机同步:matebook `cd ~/dotfiles && git pull && stow bin`。

判据:当命令敲、想版本化 + 双机同步 → 这里;一次性 / 速朽实验 → `~/workspace/scratch/`。

> `.local/bin/.gitignore`(空)只为让 git 保留空目录;stow 默认忽略它,不会外链进 `~/.local/bin`。
