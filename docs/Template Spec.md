# fig Template Specification (`fig.toml`)

A `fig.toml` file lives at the root of your dotfiles repository and defines what gets linked, where it goes, and which operating systems or link strategies apply.

---

## 1. Repository Conventions

When scanning a repository without a `fig.toml`, Fig applies two standard conventions:
- **Top-level files** (e.g. `.gitconfig`, `.zshrc`) default to `~/<filename>`.
- **Top-level directories** (e.g. `nvim/`, `wezterm/`) default to `~/.config/<dirname>` as whole-directory links.
- **Nested `pathspec.txt`**: Placing a `pathspec.txt` inside any subdirectory overrides its target destination automatically.

---

## 2. Schema Sections

### `[meta]` & `[settings]`
```toml
[meta]
name = "dotfiles"
version = "1.0.0"
description = "Cross-platform dotfiles"

[settings]
link_mode = "auto"            # auto | symlink | junction | hardlink | copy
backup_on_collision = true
ignore = [".git", ".gitignore", "README.md", "fig.toml", ".fig.toml"]
```

### `[mappings]` (Universal)
Applied on every operating system:
```toml
[mappings]
".gitconfig" = "~/.gitconfig"
"nvim" = { target = "~/.config/nvim", mode = "junction" }
```

### `[os.<platform>.mappings]` (Platform-Specific)
Supported platform keys: `windows`, `linux`, `macos`, `posix` (matches Linux and macOS).
```toml
[os.windows.mappings]
"pwsh/profile.ps1" = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"

[os.posix.mappings]
"zsh/.zshrc" = "~/.zshrc"
```

### `[system_mappings]` & `[os.<platform>.system_mappings]`
Used only when `--system` is passed (requires Administrator / `sudo` privileges):
```toml
[os.linux.system_mappings]
"system/etc/hosts" = "/etc/hosts"
```

---

## 3. Pathspec Shorthands

Usable in `fig.toml`, `pathspec.txt`, and the Builder REPL (`edit <#>`):

| Shorthand | Expands To |
| :--- | :--- |
| `~` or `@home/...` | User home directory (`$HOME` / `%USERPROFILE%`) |
| `.config/...` or `config/...` | `~/.config/...` |
| `@docs/...` or `Documents/...` | `~/Documents/...` |
| `@appdata/...` | `%APPDATA%/...` (Windows) |
| `@localappdata/...` | `%LOCALAPPDATA%/...` (Windows) |
