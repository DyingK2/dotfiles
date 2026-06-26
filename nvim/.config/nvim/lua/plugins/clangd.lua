return {
  "neovim/nvim-lspconfig",
  opts = {
    servers = {
      clangd = {
        cmd = {
          "clangd",
          "--header-insertion=never",
          "--background-index",
          "--clang-tidy",
          "--completion-style=detailed",
          "--function-arg-placeholders",
          "--fallback-style=llvm",
          "--pch-storage=memory",
          "--query-driver=/usr/bin/*gcc*",
        },
      },
    },
  },
}
