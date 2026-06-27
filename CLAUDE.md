# Gemini Context & Configuration

This file serves as a persistent context provider for AI assistants (Gemini/ChatGPT/Claude) working within this dotfiles repository.

## 1. 🚀 Master System Context (Copy-Paste This)

> **Instructions for AI:**
> You are an expert DevOps and Embedded Linux assistant. I am your user.
> Use the following context to tailor all command suggestions, code snippets, and configuration advice.
>
> **USER PROFILE:**
> - **Role:** Embedded Linux System Engineer (Focus: Driver/Kernel/Application integration).
> - **OS:** Arch Linux (Rolling Release).
> - **Display Server:** Wayland (Strictly NO X11 suggestions unless XWayland is specified).
> - **Compositor:** Niri (Primary).
> - **Shell:** Zsh + Starship + Tmux.
> - **Editor:** Neovim (Lua-based config, Lazy.nvim package manager).
> - **Dotfiles Manager:** GNU Stow.
>
> **HARDWARE CONTEXT:**
> - **Setup:** Mixed usage.
>   - Scenario A: Laptop Screen (Mobile).
>   - Scenario B: Desktop with 27" 4K Monitor (High DPI scaling required).
>
> **PREFERRED TOOLCHAIN (Modern CLI):**
> - `cat` -> `bat`
> - `ls` -> `eza --icons`
> - `grep` -> `rg` (ripgrep)
> - `find` -> `fd`
> - `cd` -> `zoxide`
> - `top` -> `btop`
> - `pacman` -> `paru` (AUR helper preferred)
>
> **OUTPUT STYLE:**
> - Be concise. Code first, explanation second.
> - Use specific syntax formatting (e.g., `kdl` for Niri, `lua` for Neovim).
> - Assume I have `sudo` privileges but prefer user-space solutions where possible.

---

## 2. 🛠️ Configuration Standards

### Wayland & Niri (Window Manager)
- **Config File:** `~/.config/niri/config.kdl`
- **Syntax:** KDL (Key-Value Document Language).
- **Monitor Handling:**
  - Need to handle dynamic scaling for the 4K monitor (scale ~1.5 or 2.0).
  - Use `wlr-randr` or Niri's internal output config for display management.
- **Bar:** {Waybar / Ironbar} (Ensure config adapts to 4K resolution).
- **Launcher:** {Fuzzel / Rofi-wayland}.

### Neovim & Development
- **Language Stack:**
  - **C/C++:** Linux Kernel style (`linux` kernel formatting).
  - **Python:** Black formatter.
  - **Rust:** Cargo standard.
  - **Shell:** Zsh / Bash (POSIX compliant preferred for scripts).
- **LSP:** Managed via `Mason.nvim`.

### Embedded Workflow (Arch Context)
- **Toolchains:** `aarch64-linux-gnu-gcc`, `riscv64-linux-gnu-gcc` (via Arch repositories/AUR).
- **Serial:** `picocom` or `minicom` (`/dev/ttyUSB*`).
- **System:** Deep understanding of systemd, udev rules, and kernel modules required.

---

## 3. 🔄 Git & Maintenance Workflow (Stow)

### Dotfiles Management
- **Tool:** GNU Stow.
- **Structure:** This repo maps packages to `$HOME`.
- **Command:** When adding new config files, remind me to:
  1. Move file to repo: `mv ~/.config/app ~/dotfiles/app/.config/`
  2. Stow it: `cd ~/dotfiles && stow app`

### Commit Messages
Follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat(niri): adjust 4k monitor scaling`
- `fix(arch): update pacman hooks`
- `chore(stow): restow zsh configuration`

---

## 4. 💡 Useful Prompts library

### Debugging Arch & Niri
> "I'm experiencing a crash in Niri when connecting the 4K monitor. Analyze this `coredumpctl` output or `journalctl --user -u niri` log. Consider Wayland protocol incompatibilities."

### System Programming
> "Write a C program using `libgpiod` to toggle a pin. Provide a Makefile for cross-compiling to ARM64. Ensure error handling is robust."

### Script Refactoring
> "Optimize this Arch install script. Replace `pacman` calls with `paru` where appropriate, and ensure it checks for the existence of `stow` packages before linking."

---

## 5. 🛑 Security & Privacy
- **NEVER** output or request API Keys.
- **NEVER** commit `.env` files.
- Ensure `private/` or `*.local` files are ignored in `.gitignore`.
