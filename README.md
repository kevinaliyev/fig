# fig

## Warning! This program is still undergoing QA Testing and features may be incomplete and/or broken!

fig (`v0.5.9`) is a zero-dependency, auditable dotfile and configuration manager for Windows, Linux, and macOS.

Built with Python 3.11+ standard library only, Fig manages user dotfiles and elevated system configurations via declarative `fig.toml` templates—with automatic collision backups, rollback history, interactive REPL building, and temporary workstation takeovers.

---

## Core Commands

| Command | Aliases | Description |
| :--- | :--- | :--- |
| `fig` | — | Refresh links from your currently active template |
| `fig apply` | `sync` | Apply `./fig.toml` if in current directory; otherwise refresh active template |
| `fig build [DIR\|URL]` | — | Scan a repo (or clone Git URL) and build `fig.toml` via interactive REPL |
| `fig rebuild [TARGET]` | — | Edit/rebuild your active template inside the REPL without losing settings |
| `fig bootstrap [DIR\|URL]` | `-b` | Deploy dotfiles from a repo, back up collisions, and register as active |
| `fig check` | `status` | Inspect link health (`[OK]`, `[DRIFT]`, `[CONFLICT]`, `[MISSING]`) |
| `fig preview` | `diff`, `-n` | Dry-run simulation of planned links and backups |
| `fig undo [ID]` | `rollback`, `restore` | Restore backed-up files from vault and remove deployed links |
| `fig temp <DIR>` | `guest`, `borrow` | Temporarily deploy dotfiles for a session; restore cleanly with `fig revert` |
| `fig view` / `fig edit` | — | Inspect active template or open it in `$EDITOR` |
| `fig profile list\|switch` | — | List or switch between named configuration profiles |

---

## Quick Start & Installation

### Run or Install from Source (Python 3.11+)

```powershell
# Clone repository
git clone https://github.com/youruser/fig.git
cd fig

# Run unit tests
python -m unittest discover tests

# Build standalone binary and install to ~/.local/bin
python scripts/release/install.py
```

Simply run the command **fig** while your cwd is your dotfiles repo (you can also pass an explicit path). 

**Alternatively if you already have a fig template, run fig --bootstrap to skip the REPL Builder entirely.**


---

## Configuration Spec (`fig.toml`)

Fig templates live in your dotfile repository and support universal mappings, OS-specific overrides, per-link modes, and system files:

```toml
[meta]
name = "dotfiles"
version = "1.0.0"

[settings]
link_mode = "auto"            # auto, symlink, junction, hardlink, copy
backup_on_collision = true
ignore = [".git", ".gitignore", "README.md", "fig.toml"]

[mappings]
".gitconfig" = "~/.gitconfig"
"nvim" = { target = "~/.config/nvim", mode = "junction" }
"wezterm" = "~/.config/wezterm"

[os.windows.mappings]
"pwsh/profile.ps1" = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"

[os.posix.mappings]
"zsh/.zshrc" = "~/.zshrc"
```

---

## Documentation

- [Technical Guide & Internals](docs/README.md) — Architecture, CLI flags, runtime layout (`~/.fig/`), and helper scripts
- [Template Spec](docs/Template%20Spec.md) — `fig.toml` schema, pathspec shorthands, OS scopes, and `--system` mode
- [Changelog](docs/CHANGELOG.md) — Release history
