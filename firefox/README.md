# firefox —— 日用 profile 的共享配置(stow 包)

`stow firefox` 把 `~/.mozilla/shared/` 链到这里,内含:

- `user.js` —— Betterfox 146 + 个人 override(每次启动覆盖 about:config)。
- `chrome/userChrome.css` —— 隐藏原生标签栏(配合 Sidebery 树状标签)、去 sidebar 标题。

profile 目录名是随机 hash,stow 够不着,所以每台机**一次性**手链(已在 boat/matebook 做过):

    ln -s "firefox/<hash>.default-release" ~/.mozilla/main      # 稳定别名
    ln -sf ../../shared/user.js ~/.mozilla/main/user.js
    rm -rf ~/.mozilla/main/chrome && ln -s ../../shared/chrome ~/.mozilla/main/chrome

`~/.mozilla/claude-pick` 同理是 claude.ai 专用 profile 的别名(见 `bin/claude-web`)。

注意:userChrome 隐藏了标签栏,**没装 Sidebery 的 profile 别链这份 chrome**。
Sidebery 设置不在文件里(IndexedDB,绑 profile 内部 UUID),跨机走 Sidebery 设置页的 Export/Import。

claude-pick **故意不在** Main 的 Profile Group 里(prefs.js 无 `toolkit.profiles.storeID`,组库无行):
组内 profile 一启动就把自己写成安装默认,会让裸 `firefox` 开错;独立 profile 经 `--profile 路径` 起不碰 profiles.ini。
代价是 about:profiles 里看不到它,只能经 `claude-web` 起——这正是想要的。
