# FIG: Configuration & Dotfile Manager
### Architectural Blueprint, Implementation Roadmap & Audit Guide

> **Status:** Phase 1, 2 & 3 Complete (17 Automated Unit & Integration Tests Passing)  
> **Target Platforms:** POSIX (Linux, macOS, BSD) & Windows (10/11)  
> **Runtime:** Python 3.11+ (Standard Library first, zero-mandatory external dependencies)

---

## 1. Executive Summary & Core Principles

`fig` is a fast, transparent, and auditable configuration and dotfile manager. It bridges the gap between raw symlink tools (like GNU Stow) and heavy declarative configuration managers (like Chezmoi or Nix).

### Core Pillars
1. **Early OS Detection & Native Path Resolution**: Identifies the host operating system immediately at startup (`fig.core.platform`), translating environmental conventions (`$HOME`, `%USERPROFILE%`, `~/Documents`, `$XDG_CONFIG_HOME`, `%APPDATA%`) and native path semantics.
2. **OS-Specific Declarations in Templates**: Single-repository dotfiles can cleanly declare both universal mappings and OS-specific mappings/presets (e.g., `[os.windows.mappings]` vs `[os.linux.mappings]`), allowing tools like Wezterm, PowerShell, or Neovim to route to different files and directories depending on the OS.
3. **Interactive Setup Wizard (REPL)**: If `fig` is run on a clean system with no active template and no bootstrap flag, it enters a guided REPL wizard asking about the user's shells, git, ssh, editor, and terminal, generating a clean starter `fig.toml` (which remains unactivated until explicitly deployed).
4. **Safety & Non-Destructive Overwrites**: Before any file or symlink is replaced, `fig` selectively captures existing target files into a timestamped, manifest-backed backup vault (`~/.fig/backups/`).
5. **One-Command Bootstrap (`fig -bootstrap` / `fig bootstrap`)**: Run inside any cloned dotfiles repository to inspect the repo, back up collisions, deploy links, and register the repo as the machine's active template at `$HOME`.
6. **Zero-Drift Idempotency (`fig` / `fig sync`)**: Subsequent runs synchronize against the active template. If no changes occurred, running `fig` is a safe, zero-impact no-op.
7. **Instant Reversibility (`fig undo`)**: Every deployment operation is logged with a manifest. A user or script can cleanly revert any deployment back to its exact prior state.
8. **Temporary Overrides ("Temp / Guest Mode")**: Easily turn a coworker's or shared workstation into your environment with `fig temp <repo>`, and revert it completely back to their original state with `fig revert`.
9. **Zero Dependencies**: 100% standard library Python 3.11+ so any machine can run it out of the box with zero setup hurdles.

---

## 2. Template Specification (`fig.toml`)

A `fig.toml` file lives in the root of the user's dotfiles repository:

```toml
[meta]
name = "my-cross-platform-dotfiles"
version = "1.0.0"
description = "Personal cross-platform dotfiles"

[settings]
link_mode = "auto"              # "auto" | "symlink" | "hardlink" | "junction" | "copy"
backup_on_collision = true      # Always backup conflicting files before link creation
ignore = [".git", ".gitignore", "README.md", "fig.toml", "*.swp"]

# Universal presets shared across all operating systems
[presets]
include = ["git", "ssh", "starship"]

# Universal mappings (applied on any OS)
[mappings]
"git/.gitconfig"      = "~/.gitconfig"
"ssh/config"          = "~/.ssh/config"
"starship.toml"       = "~/.config/starship.toml"

# Windows-specific mappings & presets
[os.windows.mappings]
"wezterm/wezterm_win.lua"       = "~/.config/wezterm/wezterm.lua"
"powershell/profile.ps1"        = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
"nvim"                          = "%LOCALAPPDATA%/nvim"

[os.windows.presets]
include = ["powershell", "windows-terminal"]

# Linux-specific mappings & presets
[os.linux.mappings]
"wezterm/wezterm_linux.lua"     = "~/.config/wezterm/wezterm.lua"
"zsh/.zshrc"                    = "~/.zshrc"
"nvim"                          = "~/.config/nvim"

[os.linux.presets]
include = ["zsh", "tmux"]

# macOS / Darwin-specific mappings
[os.macos.mappings]
"wezterm/wezterm_mac.lua"       = "~/.config/wezterm/wezterm.lua"
"zsh/.zshrc"                    = "~/.zshrc"
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
└── sessions/                        # Temporary override / guest mode sessions
    └── active_borrow.json
```

---

## 4. Component Breakdown

| Component | Module | Responsibility |
| :--- | :--- | :--- |
| **Platform Abstraction** | `fig.core.platform` | Immediate OS detection (`windows`, `linux`, `macos`, `bsd`), native path resolution (`~`, `$ENV`, `%ENV%`, Documents, AppData). |
| **CLI Dispatcher** | `fig.cli` | Argument parsing, command routing (`bootstrap`, `sync`, `check`, `preview`, `undo`, `history`, `temp`, `revert`, `setup`, `profile`). |
| **Interactive Wizard (REPL)** | `fig.core.wizard` | Guided questionnaire generating starter `fig.toml` when invoked in unconfigured environments. |
| **Config / State** | `fig.core.config` | Manages `~/.fig`, reads/writes global configuration, tracks active template pointer. |
| **Template Engine** | `fig.core.template` | Parses `fig.toml`, filters OS-specific mapping blocks (`[os.<name>.mappings]`), resolves presets and native target paths. |
| **Link Engine** | `fig.core.linker` | Atomic creation of symlinks/junctions/hardlinks, path resolution, permission error recovery (Windows Dev Mode vs Junctions/Hardlinks). |
| **Backup Vault** | `fig.core.backup` | Selective collision backup (only backs up files being replaced), generates `manifest.json`, executes full rollback/restoration. |
| **Orchestrator** | `fig.core.engine` | High-level operations: `bootstrap()`, `apply()`, `revert()`, `plan()` (dry run), `status()`. |
| **Profile Manager** | `fig.core.profiles` | Switching between named templates/profiles, managing temporary "temp / guest" sessions. |
| **Built-in Presets** | `fig.builtins` | OS-differentiated catalog of default paths for standard tools. |

---

## 5. Phased Implementation Status

### Phase 1: Core Engine & Safety Foundation (COMPLETED)
- [x] Architectural specification & blueprint (`PROJECT_MAP.md`).
- [x] Early OS detection & Native Path Resolution (`fig.core.platform`).
- [x] Cross-platform linking mechanism (`fig.core.linker`):
  - POSIX symlinks (`os.symlink`)
  - Windows auto-handling (symlink if permitted, directory junction for folders, hardlink for files as fallback, `os.path.samefile` drift verification).
- [x] Collision detection & Backup Engine (`fig.core.backup`):
  - Selective backup only for colliding paths.
  - Timestamped backup sessions with `manifest.json`.
  - Atomic rollback/restore capability.
- [x] Template Engine with OS-Specific Declarations (`fig.core.template`):
  - TOML parser with path variable expansion (`~`, `$HOME`, `$XDG_CONFIG_HOME`, `%APPDATA%`, Documents).
  - Explicit OS sections: `[os.windows.mappings]`, `[os.linux.mappings]`, `[os.macos.mappings]`.
  - Conditional plan resolution matching host OS.
- [x] Built-in App Presets (`fig.builtins`):
  - Platform-aware path dictionaries for Bash, Zsh, PowerShell, Git, SSH, Tmux, Neovim, Starship, Alacritty, Kitty, Fish, Windows Terminal, Helix, Wezterm.

### Phase 2: Refactored CLI Interface & Core Commands (COMPLETED)
- [x] `fig bootstrap` & `fig -bootstrap`:
  - Find `fig.toml` in directory (or auto-generate if missing).
  - Perform collision backup.
  - Deploy links destructively over existing files.
  - Register as machine's active template in `~/.fig/config.toml`.
- [x] `fig` / `fig sync`:
  - Routine synchronization against active template.
  - Zero-drift idempotency check.
- [x] `fig check`:
  - Replaces confusing `status` command (with `status` kept as alias).
  - Inspect health, drift, collisions, and missing files.
- [x] `fig preview`:
  - Replaces confusing `diff` command (with `diff` kept as alias).
  - Previews operations without touching filesystem.
- [x] `fig undo`:
  - Replaces confusing `restore` command (with `restore` kept as alias).
  - Restores replaced files and cleanly purges newly created links.
- [x] `fig history`:
  - Replaces `backups` command (with `backups` kept as alias).
- [x] `fig setup` (Interactive REPL Wizard):
  - Invoked automatically if running `fig` without an active template.
  - Guides user through questions and outputs starter `fig.toml` (unactivated).

### Phase 3: Temporary Overrides ("Temp Mode") & Profiles (COMPLETED)
- [x] Profile management: `fig profile list`, `fig profile switch <name>`.
- [x] `fig temp <repo>` (replaces `borrow`):
  - Snapshot coworker's current state, deploy temporary dotfiles.
- [x] `fig revert` (replaces `unborrow`):
  - Instantly wipe temporary links and restore coworker's exact state.

### Phase 4: System Configuration & Elevation (Planned Next Step)
- [ ] Elevated system configuration mode (`fig --system` / `fig system`):
  - Target system directories (`/etc/`, systemd unit files, Windows system configuration).
  - Explicit sudo/UAC elevation checks.
  - Elevated backup namespace (`/var/backups/fig/` or `~/.fig/system_backups/`).
