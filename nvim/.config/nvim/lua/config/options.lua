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
