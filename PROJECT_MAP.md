# FIG: Configuration & Dotfile Manager
### Architectural Blueprint, Implementation Roadmap & Audit Guide

> **Status:** Active Implementation (Phase 1 & Phase 2 In Progress)  
> **Initial Author:** Antigravity AI  
> **Target Platforms:** POSIX (Linux, macOS, BSD) & Windows (10/11)  
> **Runtime:** Python 3.11+ (Standard Library first, zero-mandatory external dependencies)

---

## 1. Executive Summary & Vision

`fig` is a modern, transparent, and auditable configuration and dotfile manager. It bridges the gap between raw symlink tools (like GNU Stow) and heavy declarative configuration managers (like Chezmoi or Nix).

### Core Pillars
1. **Repository-Centric Templates**: Dotfile repositories declare how their tree maps to the system filesystem using a clear, human-readable template (`fig.toml`).
2. **Safety & Non-Destructive Overwrites**: Before any file or symlink is replaced, `fig` selectively captures existing target files into a timestamped, manifest-backed backup vault (`~/.fig/backups/`).
3. **One-Command Bootstrap**: On a clean machine, running `fig bootstrap` inside a cloned dotfiles repository inspects the repo, auto-detects configs, backs up collisions, deploys symlinks, and registers the repo as the machine's active template at `$HOME`.
4. **Zero-Drift Idempotency**: Subsequent runs of `fig` (or `fig apply`) synchronize against the active template. If no changes occurred, running `fig` is a safe, zero-impact no-op.
5. **Instant Reversibility (`undo` / `restore`)**: Every deployment operation is logged with a manifest. A user or script can cleanly revert any deployment back to its exact prior state.
6. **Temporary Overrides ("Borrow Mode")**: Quickly turn a coworker's or shared workstation into your environment with a single command, and revert it completely back to their original state with zero residue.
7. **Multi-Profile Switching**: Easily maintain and toggle between personal, work, server, or shared-user profile templates under a single account.
8. **Auditable Codebase**: Written in clean, modular Python without obfuscated dependencies so users and system administrators can easily review every filesystem operation.

---

## 2. Architecture & Directory Hierarchy

### 2.1 File System Structure

```
~/.fig/                              # User Fig State Directory ($FIG_HOME or ~/.fig)
├── config.toml                      # Global Fig state (active template pointer, settings)
├── active_template.toml             # Active deployed template (or symlink to repo template)
├── backups/                         # Backup vault for collision recovery
│   └── 20261107_120000_bootstrap/  # Timestamped backup session
│       ├── manifest.json            # Deployment & backup manifest (source -> dest -> backup)
│       └── files/                   # Exact copy of overridden files preserving relative tree
└── sessions/                        # Temporary override / borrow mode sessions
    └── active_borrow.json
```

### 2.2 Template Specification (`fig.toml`)

A `fig.toml` file lives in the root of the user's dotfiles repository or inside `~/.fig/`:

```toml
[meta]
name = "my-dotfiles"
version = "1.0.0"
author = "User"
description = "Personal cross-platform dotfiles"

# Global settings for this template
[settings]
link_mode = "symlink"          # "symlink" | "hardlink" | "copy" | "auto"
backup_on_collision = true     # Always backup conflicting files before link creation
ignore = [".git", ".gitignore", "README.md", "fig.toml", "*.swp"]

# Explicit file/folder mapping rules
# source (relative to repo root) = destination (supports ~, $ENV, %APPDATA%)
[mappings]
"zsh/.zshrc"          = "~/.zshrc"
"git/.gitconfig"      = "~/.gitconfig"
"nvim"                = "~/.config/nvim"
"tmux/.tmux.conf"     = "~/.tmux.conf"
"starship.toml"       = "~/.config/starship.toml"

# Built-in presets enable automatic mapping for standard tools without manual paths
[presets]
include = ["git", "zsh", "tmux", "neovim", "alacritty", "kitty", "starship", "fish"]
```

---

## 3. Component Breakdown

| Component | Module | Responsibility |
| :--- | :--- | :--- |
| **CLI Dispatcher** | `fig.cli` | Argument parsing, command routing (`bootstrap`, `apply`, `status`, `diff`, `restore`, `profile`, `borrow`, `init`). |
| **Config / State** | `fig.core.config` | Manages `~/.fig`, reads/writes global configuration, tracks active template pointer. |
| **Template Engine** | `fig.core.template` | Parses `fig.toml`, expands environment variables/home directory, resolves built-in presets, auto-discovers configs when template is absent. |
| **Link Engine** | `fig.core.linker` | Atomic creation of symlinks/junctions/hardlinks, path resolution, loop detection, permission error recovery (e.g. Windows Dev Mode vs Junctions). |
| **Backup Vault** | `fig.core.backup` | Selective collision backup (only backs up files being replaced), generates `manifest.json`, executes full rollback/restoration. |
| **Orchestrator** | `fig.core.engine` | High-level operations: `bootstrap()`, `apply()`, `revert()`, `plan()` (dry run), `status()`. |
| **Profile Manager** | `fig.core.profiles` | Switching between named templates/profiles, managing temporary "borrow" sessions. |
| **Built-in Presets** | `fig.builtins` | Catalog of default paths for popular Unix/Windows tools (zsh, bash, git, tmux, vim, nvim, starship, alacritty, kitty, etc.). |

---

## 4. Phased Implementation Roadmap

### Phase 1: Core Engine & Safety Foundation (COMPLETED)
- [x] Architectural specification & blueprint (`PROJECT_MAP.md`).
- [x] Cross-platform linking mechanism (`fig.core.linker`):
  - POSIX symlinks (`os.symlink`)
  - Windows auto-handling (symlink if permitted, directory junction for folders, hardlink for files as fallback).
- [x] Collision detection & Backup Engine (`fig.core.backup`):
  - Selective backup only for colliding paths.
  - Timestamped backup sessions with `manifest.json`.
  - Atomic rollback/restore capability.
- [x] Template Engine (`fig.core.template`):
  - TOML parser with path variable expansion (`~`, `$HOME`, `$XDG_CONFIG_HOME`, `%APPDATA%`).
  - Auto-generation of templates when bootstrap runs in a bare directory.
- [x] Built-in App Presets (`fig.builtins`):
  - Path dictionaries for Bash, Zsh, Git, Tmux, Neovim, Starship, Alacritty, Kitty, Fish, etc.

### Phase 2: CLI Interface & Core Commands (COMPLETED)
- [x] `fig bootstrap`:
  - Find `fig.toml` in current directory (or auto-generate if missing).
  - Perform collision backup.
  - Deploy links destructively over existing files.
  - Register as machine's active template in `~/.fig/config.toml`.
- [x] `fig` / `fig apply`:
  - Read active template from `~/.fig/config.toml`.
  - Check drift and enforce symlink state idempotently.
- [x] `fig status`:
  - Show status of active template: linked, broken, modified, or missing targets.
- [x] `fig diff` / `--dry-run`:
  - Preview operations before touching the filesystem.
- [x] `fig backup list` & `fig restore [id]`:
  - Inspect backup vault and restore system to previous state.

### Phase 3: Advanced Profiles & Temporary Overrides ("Borrow Mode") (COMPLETED)
- [x] Profile management: `fig profile create`, `fig profile list`, `fig profile switch <name>`.
- [x] Temporary override / Borrow mode:
  - `fig borrow <repo-or-template>`: Snapshot coworker's current state, apply temporary dotfiles.
  - `fig revert` / `fig unborrow`: Instantly wipe borrowed links and restore coworker's exact state.

### Phase 4: System Configuration & Elevation (Future / Post-Prototype)
- [ ] Elevated system configuration mode (`fig --system` / `fig system`):
  - Target system directories (`/etc/`, systemd unit files, Windows system configuration).
  - Explicit sudo/UAC checks, elevated backup namespace (`/var/backups/fig/` or `~/.fig/system_backups/`).

---

## 5. Audit & Handoff Reference for Future Agents & Engineers

If an agent or engineer is resuming work on this repository:
1. **Read this file (`PROJECT_MAP.md`)** to inspect the architecture and checked/unchecked tasks.
2. **Inspect the test suite (`python -m unittest discover tests`)** to verify what currently passes.
3. **Check the core module directories (`fig/core/`)** to understand existing implementations before making modifications.
4. **Maintain zero-mandatory external dependencies** to keep `fig` universally bootable with stock Python 3.11+.
5. **Update the checkboxes** in Section 4 as new features and tests are implemented.
