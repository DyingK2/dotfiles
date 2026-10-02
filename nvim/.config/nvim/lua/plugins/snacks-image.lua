-- markdown 里直接显示图片：走 kitty 图形协议（alacritty 下不显示）；
-- 非 png 格式靠 imagemagick 转换。在 tmux 里需要开 allow-passthrough
return {
  "folke/snacks.nvim",
  opts = {
    image = {
      enabled = true,
      doc = {
        inline = true, -- 图画在 ![](...) 下方，光标进该行时显示回源码
        float = true,
        max_width = 80,
        max_height = 40,
      },
    },
  },
}
