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

-- 跨机剪贴板：SSH 会话里钉死走 OSC52 copy provider。
-- 理由：boat 等被连机存在 wl-copy，naive unnamedplus 会把 yank 错落到“远端自己”的剪贴板；
-- 且 tmux 吞掉 SSH_TTY 致 nvim 内建 OSC52 自动探测失效。故显式设定。
-- paste 故意读本地寄存器而非 OSC52 query，避免终端反复弹出 read 授权框；
-- 要把外部剪贴板灌进远程 nvim，用终端 bracketed paste(Ctrl+Shift+V) 即可。
if vim.env.SSH_CONNECTION and vim.env.SSH_CONNECTION ~= "" then
  local osc52 = require("vim.ui.clipboard.osc52")
  local function reg_paste(reg)
    return function()
      return { vim.fn.getreg(reg, 1, true), vim.fn.getregtype(reg) }
    end
  end
  vim.g.clipboard = {
    name = "osc52-ssh",
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
