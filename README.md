# Fig

> **A fast, auditable, and transparent user & system configuration / dotfile manager.**

`fig` maps source dotfile repositories to system destinations using declarative templates (`fig.toml`), cross-platform links (symlinks, junctions, hardlinks), zero-loss collision backups, and reversible profiles.

[![Tests](https://img.shields.io/badge/tests-27%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

---

## Key Highlights

- **Early OS Detection**: Identifies operating system immediately at startup (`windows`, `linux`, `macos`) and resolves native paths, environment variables (`$HOME`, `%USERPROFILE%`, `%APPDATA%`, `~/Documents`), and filesystem conventions.
- **Interactive Template Builder (`fig build`)**: Interactive REPL that scans any local repository or remote GitHub repo (`gh:user/dotfiles`), detects directory trees and nested configs (like `nvim`), reads `pathspec.txt` for non-standard applications, presents a clean table, and lets you toggle exclusions and edit targets before building `fig.toml`.
- **Non-Standard App Standardization (`pathspec.txt`)**: For any custom or non-standard application, simply place a `pathspec.txt` inside its folder (e.g. `dotfiles/myapp/pathspec.txt`). Fig reads it directly without guessing.
- **POSIX Unification (`[os.posix.mappings]`)**: Rules shared across Linux and macOS (like Bash or Zsh configs) can be declared under `[os.posix.mappings]`, eliminating duplicate rules.
- **Visual Template Viewer & Editor (`fig view` / `fig edit`)**: Inspect your active or catalog templates in a clean, colorized layout or open them directly in your preferred editor (`$EDITOR`, `nvim`, `vim`, `notepad`).
- **One-Command Bootstrap (`fig -bootstrap` or `fig bootstrap`)**: Run inside any cloned dotfiles repo. It backs up existing configs, deploys links, and registers the repo as the machine's active template at `$HOME`.
- **Selective Safety Vault**: Before replacing *any* existing file or link, `fig` selectively archives colliding files into a timestamped vault (`~/.fig/backups/`) with a JSON manifest.
- **100% Reversible Rollback (`fig undo` / `fig revert`)**: Every link operation is logged. Revert any deployment or temporary session back to its exact prior state with a single command.
- **Zero-Drift Idempotency (`fig` / `fig sync`)**: Running `fig` repeatedly synchronizes against the active template. If nothing changed, it is a safe no-op.
- **Temporary Overrides (`fig temp` / `fig revert`)**: Temporarily apply your dotfiles on a coworker's or shared computer and instantly revert everything back to their exact previous state when finished.
- **Zero Dependencies**: Written entirely in standard library Python (Python 3.11+).

---

## Quickstart

### 1. Build a Template for Your Dotfiles

If you already have a dotfiles directory or cloned repo, run the interactive builder:

```bash
fig build
```

Or build directly from GitHub:
```bash
fig build gh:yourusername/dotfiles
```

The builder will:
1. Scan your directory tree (detecting `.config/` mirrors, nested `nvim` setups, stow-style folders, and `pathspec.txt` files).
2. Present a clean, readable table of discovered applications.
3. Allow you to interactively toggle exclusions (`toggle 2`), edit paths (`edit 3`), or add custom apps.
4. Generate a clean `fig.toml` template.

### 2. Bootstrapping on a Fresh Machine

Clone your dotfiles repository and run `fig -bootstrap`:

```bash
git clone https://github.com/yourusername/dotfiles.git ~/dotfiles
cd ~/dotfiles
fig -bootstrap
```

What this does:
1. Detects `fig.toml` (or launches the builder if missing).
2. Computes collisions on your filesystem.
3. Archives conflicting files to `~/.fig/backups/<timestamp>_bootstrap/`.
4. Deploys symlinks/hardlinks natively to your system.
5. Registers this repository as the machine's active template at `~/.fig/`.

### 3. Routine Syncing

Once bootstrapped, run `fig` (or `fig sync`) from anywhere:

```bash
fig
```

This enforces your active template idempotently. If files are already linked, nothing is modified.

### 4. Viewing & Editing Templates

View the active template:
```bash
fig view
```

Edit the active template in `$EDITOR` (e.g. `nvim`, `vim`, or `notepad`):
```bash
fig edit
```

List all templates & profiles:
```bash
fig template list
```

### 5. Checking Status & Health

```bash
fig check
```

Example output:
```
Platform:        Windows
Active Template: C:\Users\user\dotfiles\fig.toml
Repository Root: C:\Users\user\dotfiles

Target Statuses:
  [OK]       C:\Users\user\.gitconfig -> C:\Users\user\dotfiles\.gitconfig
  [OK]       C:\Users\user\Documents\PowerShell\Microsoft.PowerShell_profile.ps1
  [OK]       C:\Users\user\AppData\Local\nvim -> C:\Users\user\dotfiles\nvim
  [MISSING]  C:\Users\user\.config\starship.toml
```

### 6. Undoing / Rolling Back Changes

View backup history:
```bash
fig history
```

Restore system back to prior state:
```bash
fig undo
```

### 7. Temporary Takeover on Coworker's Machine

```bash
# Temporarily apply your dotfiles (snapshots coworker's current state)
fig temp ~/my-dotfiles

# ... do your work ...

# Instantly restore coworker's original state and clean up links
fig revert
```

---

## Non-Standard Application Standardization (`pathspec.txt`)

For any application that doesn't follow standard `.config` or `$HOME` conventions, place a `pathspec.txt` inside its folder:

```
dotfiles/
├── my_weird_tool/
│   ├── config.json
│   └── pathspec.txt
```

In `pathspec.txt`, specify either a single target or platform-specific targets:

```ini
# Single universal target:
~/.local/share/my_weird_tool

# Or platform-specific targets:
windows = %APPDATA%/my_weird_tool
posix   = ~/.local/share/my_weird_tool
macos   = ~/Library/Application Support/my_weird_tool
```

`fig build` automatically recognizes `pathspec.txt` and routes the folder accordingly.

---

## Template Specification (`fig.toml`)

```toml
[meta]
name = "my-cross-platform-dotfiles"
version = "1.0.0"
description = "My daily driver dotfiles"

[settings]
link_mode = "auto"              # "auto" | "symlink" | "hardlink" | "junction" | "copy"
backup_on_collision = true      # Safeguard existing files
ignore = [".git", "README.md", "fig.toml", "private/*"]

# Universal mappings across all platforms
[mappings]
"git/.gitconfig"      = "~/.gitconfig"
"ssh/config"          = "~/.ssh/config"
"starship.toml"       = "~/.config/starship.toml"

# POSIX-unified mappings (applies to both Linux and macOS)
[os.posix.mappings]
"zsh/.zshrc"          = "~/.zshrc"
"nvim"                = "~/.config/nvim"
"wezterm"             = "~/.config/wezterm"

# Windows-specific mappings
[os.windows.mappings]
"nvim"                = "%LOCALAPPDATA%/nvim"
"powershell/profile.ps1" = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
"wezterm"             = "~/.config/wezterm"
```

---

## Command Reference

| Command | Aliases | Description |
| :--- | :--- | :--- |
| `fig` / `fig sync` | `apply` | Synchronize system files against active template. |
| `fig -bootstrap [DIR]` | `fig bootstrap` | Deploy dotfiles from `DIR`, back up collisions, and set as active. |
| `fig build [DIR\|URL]` | — | Interactive REPL scanner to build a new template from local dir or GitHub repo. |
| `fig view [TARGET]` | `template view` | View formatted inspection of active or specified template. |
| `fig edit [TARGET]` | `template edit` | Open template in visual editor (`$EDITOR`, `nvim`, `notepad`). |
| `fig check` | `status` | Check status of all managed target files (linked, drifted, collision, missing). |
| `fig preview` | `diff`, `-n` | Preview planned actions without modifying filesystem. |
| `fig undo [ID]` | `rollback`, `restore` | Restore replaced files and clean up newly added links. |
| `fig history` | `backups` | List all historical collision backup sessions in `~/.fig/backups/`. |
| `fig temp <DIR>` | `guest`, `borrow` | Temporarily deploy dotfiles for a work session. |
| `fig revert` | `unborrow` | Revert temporary session and restore original machine state. |
| `fig template list` | — | List all saved templates and active template. |
| `fig profile switch <name>` | — | Switch active configuration to a named profile and sync. |

---

## Running Tests

```bash
python -m unittest discover tests
```
