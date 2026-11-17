# fig Template Specification (`fig.toml`)

A `fig.toml` file lives at the root of your dotfiles repository and defines what gets linked, where it goes, and which operating systems or link strategies apply.

---

## 1. Repository Conventions

When scanning a repository without a `fig.toml`, Fig applies two standard conventions:
- **Top-level files** (e.g. `.gitconfig`, `.zshrc`) default to `~/<filename>`.
- **Top-level directories** (e.g. `nvim/`, `wezterm/`) default to `~/.config/<dirname>` as whole-directory links.
- **Directory `pathspec.txt` / `.fig.pathspec`**: Placing a `pathspec.txt` (or `.fig.pathspec`) inside a directory overrides its default destination automatically when running `fig build`, so the path is pre-set before the REPL opens (see [Section 4](#4-directory-overrides-pathspectxt--figpathspec)).

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

---

## 4. Directory Overrides (`pathspec.txt` / `.fig.pathspec`)

To pre-configure the destination of a directory tree in your dotfiles repository—so `fig build` sets its target automatically instead of defaulting to `~/.config/<dirname>`—place a `pathspec.txt` or `.fig.pathspec` file inside that directory:

```text
dotfiles/
├── my_app/
│   ├── pathspec.txt
│   └── config.json
```

> **Scope Note:** `pathspec.txt` / `.fig.pathspec` files are discovered at any directory depth (both user-scoped and `--system` configs). If a package directory contains a top-level `.config/` subfolder alongside home-level files (e.g., `git/.gitconfig` + `git/.config/ignore`), Fig automatically rationalizes `.config/` to `~/.config/<pkg>/...` and unpacks the package into individual mappings.

### Format

Comments starting with `#` and blank lines are ignored. You can use either a **single-line destination** or **`key = value` pairs**:

**Single-line shorthand:**
```text
~/.local/share/my_app
```

**Key-value configuration:**
```ini
# Destination per platform (supports all Section 3 shorthands and env vars)
windows = @appdata/my_app
posix = ~/.config/my_app       # Matches Linux and macOS
# Also supported: linux = ..., macos = ...
# Or a universal fallback:
# destination = ~/.local/share/my_app

# Optional metadata
type = dir                     # dir | directory | tree | file (defaults to dir)
link_mode = symlink            # symlink | hardlink | junction | copy
scope = user                   # user | system

# Optional per-file or nested-directory overrides (relative to this pathspec.txt)
.gitconfig = ~/.gitconfig
.config = ~/.config/git
.config/ignore = ~/.config/git/global_ignore
```

### Supported Keys

- **Universal destination**: `destination`, `dest`, `target`, `default`, or `universal` (used when no OS-specific key matches).
- **OS-specific destination**: `windows`, `linux`, `macos`, `posix` (applies to Linux and macOS). On Windows, Fig checks `windows` then `universal`; on Linux/macOS, it checks `<os>` → `posix` → `universal`.
- **Relative file / directory overrides**: Any other `relative/path = <destination>` key maps a specific file, subdirectory, or nested file relative to the directory containing `pathspec.txt` (case-preserving).
- **`type` / `kind`**: `dir`, `directory`, or `tree` (links as a directory; default) or `file`.
- **`link_mode` / `mode`**: `symlink`, `hardlink`, `junction`, or `copy`.
- **`scope`**: `user` (default) or `system`. Any destination starting with `/etc/`, `/usr/`, `/var/`, `/opt/`, `C:/Windows`, `C:/Program Files`, `C:/ProgramData`, `%ProgramData%`, or `%SystemRoot%` is also treated as `system` automatically.
