-- Options are automatically loaded before lazy.nvim startup
-- Default options that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/options.lua
-- Add any additional options here

-- 拼写检查跳过中日韩字符，只检查英文（"cjk" 是 spelllang 的特殊标志，不是词典）
vim.opt.spelllang = { "en", "cjk" }

vim.opt.expandtab = true
vim.opt.shiftwidth = 4
vim.opt.tabstop = 4
vim.opt.softtabstop = 4
vim.opt.smartindent = true

-- 跨机剪贴板：在 tmux 里钉死走 OSC52 copy provider。
-- 判据用 $TMUX 而非 SSH_CONNECTION：boat 跑常驻 tmux server,其环境固定在启动时刻、
-- 且 session env 里 SSH_CONNECTION 被标记删除(-SSH_CONNECTION)、WAYLAND_DISPLAY=wayland-1 常驻,
-- 故 ssh attach 进来的 nvim 拿不到 SSH_CONNECTION 却拿得到 boat 的 wl-copy → 会错落 boat。
-- 改判 $TMUX：只要在 tmux 里就发 OSC52,由 tmux(set-clipboard on)转发给“当前 attach 的客户端终端”——
-- 本地是 boat 的 kitty、远程是 matebook 的 kitty,tmux 自动路由到“你此刻坐的那台”,本地/远程都对。
-- paste 故意读本地寄存器而非 OSC52 query,避免终端反复弹 read 授权框;
-- 要把外部剪贴板灌进远程 nvim,用终端 bracketed paste(Ctrl+Shift+V)即可。
local in_tmux = vim.env.TMUX and vim.env.TMUX ~= ""
local in_ssh = (vim.env.SSH_CONNECTION and vim.env.SSH_CONNECTION ~= "")
  or (vim.env.SSH_TTY and vim.env.SSH_TTY ~= "")
if in_tmux or in_ssh then
  local osc52 = require("vim.ui.clipboard.osc52")
  local function reg_paste(reg)
    return function()
      return { vim.fn.getreg(reg, 1, true), vim.fn.getregtype(reg) }
    end
  end
  vim.g.clipboard = {
    name = "osc52",
    copy = {
      ["+"] = osc52.copy("+"),
      ["*"] = osc52.copy("*"),
    },
    paste = {
      ["+"] = reg_paste('"'),
      ["*"] = reg_paste('"'),
    },
  }
  vim.opt.clipboard = "unnamedplus" -- 让裸 yy 也走 +，无需手敲 "+yy
end
