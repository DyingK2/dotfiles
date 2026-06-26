return {
  -- 表格渲染时用虚拟文本补齐被 conceal 掉的宽度，使各列对齐；
  -- 表格外的加粗/代码等照常按 conceal 渲染
  {
    "MeanderingProgrammer/render-markdown.nvim",
    ft = { "markdown" },
    dependencies = { "nvim-treesitter/nvim-treesitter" },
    opts = {},
  },

  -- marksman 没有关闭 lint 的配置项，只能在客户端过滤掉
  -- "Link to non-existent document/heading" 这类断链诊断
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        marksman = {
          handlers = {
            ["textDocument/publishDiagnostics"] = function(err, result, ctx)
              if result and result.diagnostics then
                result.diagnostics = vim.tbl_filter(function(d)
                  return not d.message:find("non-existent", 1, true)
                end, result.diagnostics)
              end
              vim.lsp.diagnostic.on_publish_diagnostics(err, result, ctx)
            end,
          },
        },
      },
    },
  },
}
