# FIG: Configuration & Dotfile Manager
### Architectural Blueprint, Implementation Roadmap & Audit Guide

> **Status:** Phases 1, 2, 3 Complete & Builder/Viewer Integrated (27 Automated Unit & Integration Tests Passing)  
> **Target Platforms:** POSIX (Linux, macOS) & Windows (10/11)  
> **Runtime:** Python 3.11+ (Standard Library first, zero-mandatory external dependencies)

---

## 1. Executive Summary & Core Principles

`fig` is a fast, transparent, and auditable configuration and dotfile manager. It bridges the gap between raw symlink tools (like GNU Stow) and heavy declarative configuration managers (like Chezmoi or Nix).

### Core Pillars
1. **Early OS Detection & Native Path Resolution**: Identifies the host operating system immediately at startup (`fig.core.platform`), translating environmental conventions (`$HOME`, `%USERPROFILE%`, `~/Documents`, `$XDG_CONFIG_HOME`, `%APPDATA%`) and native path semantics.
2. **Interactive Template Builder (`fig build`)**: Interactive REPL that scans local repositories or remote GitHub repositories (`gh:user/dotfiles`), identifies nested directories (like `nvim`), respects `.config/` mirrors, and parses `pathspec.txt` files for non-standard tools.
3. **Non-Standard App Standardization (`pathspec.txt`)**: Simple, standardized per-folder specification for arbitrary applications, removing guesswork and hardcoded heuristics.
4. **POSIX Unification (`[os.posix.mappings]`)**: Rules shared across Linux and macOS can be declared under `[os.posix.mappings]` so they never need to be defined twice.
5. **Template Viewer & Visual Editor (`fig view` / `fig edit`)**: Inspect colorized templates or edit them directly in `$EDITOR` (`nvim`, `vim`, `nano`, `notepad`) with automatic post-edit syntax validation.
6. **Safety & Non-Destructive Overwrites**: Before any file or symlink is replaced, `fig` selectively captures existing target files into a timestamped, manifest-backed backup vault (`~/.fig/backups/`).
7. **One-Command Bootstrap (`fig -bootstrap` / `fig bootstrap`)**: Run inside any cloned dotfiles repository to inspect the repo, back up collisions, deploy links, and register the repo as the machine's active template at `$HOME`.
8. **Zero-Drift Idempotency (`fig` / `fig sync`)**: Subsequent runs synchronize against the active template. If no changes occurred, running `fig` is a safe, zero-impact no-op.
9. **100% Reversible Rollback (`fig undo` / `fig revert`)**: Every deployment and temporary session is logged with a manifest. A user can cleanly revert any deployment back to its exact prior state.
10. **Temporary Overrides ("Temp Mode")**: Easily turn a coworker's workstation into your environment with `fig temp <repo>`, and revert it completely back to their original state with `fig revert`.
11. **Zero Dependencies**: 100% standard library Python 3.11+ so any machine can run it out of the box with zero setup hurdles.

---

## 2. Template Specification (`fig.toml`)

```toml
[meta]
name = "my-cross-platform-dotfiles"
version = "1.0.0"
description = "Personal cross-platform dotfiles"

[settings]
link_mode = "auto"              # "auto" | "symlink" | "hardlink" | "junction" | "copy"
backup_on_collision = true      # Always backup conflicting files before link creation
ignore = [".git", ".gitignore", "README.md", "fig.toml", "*.swp"]

# Universal mappings (applied on any OS)
[mappings]
"git/.gitconfig"      = "~/.gitconfig"
"ssh/config"          = "~/.ssh/config"
"starship.toml"       = "~/.config/starship.toml"

# POSIX-unified mappings (Linux & macOS)
[os.posix.mappings]
"zsh/.zshrc"          = "~/.zshrc"
"nvim"                = "~/.config/nvim"
"wezterm"             = "~/.config/wezterm"

# Windows-specific mappings & presets
[os.windows.mappings]
"wezterm"                       = "~/.config/wezterm"
"powershell/profile.ps1"        = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
"nvim"                          = "%LOCALAPPDATA%/nvim"
```

---

## 3. Directory Hierarchy

```
~/.fig/                              # User Fig State Directory ($FIG_HOME or ~/.fig)
├── config.toml                      # Global Fig state (active template pointer, settings)
├── active_template.toml             # Mirrored active template
├── backups/                         # Backup vault for collision recovery
│   └── 20261107_120000_bootstrap/  # Timestamped backup session
│       ├── manifest.json            # Deployment & backup manifest (source -> dest -> backup)
│       └── files/                   # Exact copy of overridden files preserving relative tree
├── profiles/                        # Named configuration profiles
├── repos/                           # Cloned remote dotfile repositories
└── sessions/                        # Temporary override / guest mode sessions
    └── active_borrow.json
```

---

## 4. Component Breakdown

| Component | Module | Responsibility |
| :--- | :--- | :--- |
| **Platform Abstraction** | `fig.core.platform` | Immediate OS detection (`windows`, `linux`, `macos`), POSIX unification, native path resolution (`~`, `$ENV`, `%ENV%`, Documents, AppData). |
| **Repository Scanner & Pathspec** | `fig.core.scanner` | Analyzes repo layout, interprets `pathspec.txt`, detects nested directory configs (`nvim`, `wezterm`), mirrors `.config/`. |
| **Template Builder** | `fig.core.builder` | Interactive REPL scanner, clean tabular preview, item exclusion toggling, custom path addition, and template assembly. |
| **Git Remote Cloner** | `fig.core.git_clone` | Clones remote dotfile repos (`gh:user/dotfiles` or Git URLs) into `~/.fig/repos/`. |
| **Template Viewer & Editor** | `fig.core.viewer` | Formats and colorizes templates for inspection; launches `$EDITOR` (`nvim`, `vim`, `notepad`) with validation. |
| **CLI Dispatcher** | `fig.cli` | Argument parsing, command routing (`bootstrap`, `build`, `sync`, `check`, `preview`, `undo`, `history`, `temp`, `revert`, `view`, `edit`, `profile`). |
| **Config / State** | `fig.core.config` | Manages `~/.fig`, reads/writes global configuration, tracks active template pointer. |
| **Link Engine** | `fig.core.linker` | Atomic creation of symlinks/junctions/hardlinks, path resolution, permission error recovery (Windows Dev Mode vs Junctions/Hardlinks). |
| **Backup Vault** | `fig.core.backup` | Selective collision backup (only backs up files being replaced), generates `manifest.json`, executes full rollback/restoration. |
| **Orchestrator** | `fig.core.engine` | High-level operations: `bootstrap()`, `apply()`, `revert()`, `plan()` (dry run), `status()`. |
| **Profile Manager** | `fig.core.profiles` | Switching between named templates/profiles, managing temporary "temp / guest" sessions. |

---

## 5. Phased Implementation Status

### Phase 1: Core Engine & Safety Foundation (COMPLETED)
- [x] Architectural specification & blueprint (`PROJECT_MAP.md`).
- [x] Early OS detection & Native Path Resolution (`fig.core.platform`).
- [x] POSIX unification (`[os.posix.mappings]`) shared across Linux and macOS.
- [x] Cross-platform linking mechanism (`fig.core.linker`).
- [x] Collision detection & Backup Engine (`fig.core.backup`).
- [x] Template Engine with OS-Specific Declarations (`fig.core.template`).

### Phase 2: Builder, Pathspec & Refactored CLI (COMPLETED)
- [x] Repository Scanner & `pathspec.txt` parser (`fig.core.scanner`).
- [x] Interactive Template Builder REPL with exclusion toggling (`fig.core.builder`).
- [x] Git remote repo cloning (`fig.core.git_clone`).
- [x] Template Viewer & Visual Editor integration (`fig.core.viewer`).
- [x] `fig bootstrap` & `fig -bootstrap`.
- [x] `fig` / `fig sync`: Routine synchronization against active template.
- [x] `fig check`: Health, drift, collisions, and missing files inspection.
- [x] `fig preview`: Dry-run previewing without touching filesystem.
- [x] `fig undo`: Restores replaced files and cleanly purges newly created links.
- [x] `fig history`: List backup vault history.

### Phase 3: Temporary Overrides ("Temp Mode") & Profiles (COMPLETED)
- [x] Profile management: `fig profile list`, `fig profile switch <name>`.
- [x] `fig temp <repo>`: Snapshot coworker's current state, deploy temporary dotfiles.
- [x] `fig revert`: Instantly wipe temporary links and restore coworker's exact state.

### Phase 4: System Configuration & Elevation (Planned Next Step)
- [ ] Elevated system configuration mode (`fig --system` / `fig system`):
  - Target system directories (`/etc/`, systemd unit files, Windows system configuration).
  - Explicit sudo/UAC elevation checks.
  - Elevated backup namespace (`/var/backups/fig/` or `~/.fig/system_backups/`).
