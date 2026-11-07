# FIG: Configuration & Dotfile Manager
### Architectural Blueprint, Implementation Roadmap & Audit Guide

> **Status:** All Phases (1, 2, 3, 4) Complete (31 Automated Unit & Integration Tests Passing)  
> **Target Platforms:** POSIX (Linux, macOS) & Windows (10/11)  
> **Runtime:** Python 3.11+ (Standard Library first, zero-mandatory external dependencies)

---

## 1. Executive Summary & Core Principles

`fig` is a fast, transparent, and auditable configuration and dotfile manager. It bridges the gap between raw symlink tools (like GNU Stow) and heavy declarative configuration managers (like Chezmoi or Nix).

### Core Pillars
1. **Clear Scope Separation (User Dotfiles vs System Configurations)**:
   - User dotfiles (`~/.zshrc`, `~/.config/nvim`, etc.) are managed by default with zero elevation requirements.
   - System-level configurations (`/etc/`, systemd unit files, Windows system files) are **strictly isolated**. They are never auto-discovered or applied unless the user explicitly passes the `--system` / `-system` flag.
2. **Explicit Pathspec Mandate for System Configurations**:
   - Every system configuration MUST explicitly specify its exact destination path. No guesswork or auto-routing is permitted for system files.
3. **Safety & Breaking Changes Guard**:
   - Any operation involving system configurations displays a prominent warning detailing the risks to system stability and lists affected paths.
   - Requires explicit user confirmation (`y/N`), which can be bypassed in automation with `-y` / `--yes`.
4. **Elevation Protocol (UAC & sudo)**:
   - Elevation is checked **only after** breaking-change warnings are confirmed.
   - Windows: Re-launches in an elevated shell via UAC.
   - POSIX: Re-launches using `sudo`.
5. **System Redundancy Disaster-Recovery Vault**:
   - In addition to the user's `~/.fig/backups/` vault, system-level modifications are archived in an independent, machine-wide redundancy vault:
     - Windows: `%ProgramData%\fig\backups\` and `%ProgramData%\fig\logs\`
     - Linux/macOS: `/var/backups/fig/` and `/var/log/fig/`
   - Even if the user wipes their home directory or deletes Fig user files, system recovery remains fully intact.
6. **Audit Trail Logging**:
   - Every operation is recorded with ISO timestamps to `~/.fig/logs/fig.log` (and system operations to the redundancy system log).
7. **Interactive Builder with `-system` Mode (`fig build -system`)**:
   - The builder provides an overview, validates explicit pathspecs, displays warnings, and confirms system rules before writing them to `fig.toml`.
8. **100% Reversible Rollback (`fig undo` / `fig undo --system`)**:
   - Reverts modifications cleanly, restores original files, and deletes newly created links.
9. **Zero Dependencies**: Pure Python 3.11+ standard library.

---

## 2. Template Specification (`fig.toml`)

```toml
[meta]
name = "my-complete-config"
version = "1.0.0"
description = "Cross-platform dotfiles and optional system configurations"

[settings]
link_mode = "auto"              # "auto" | "symlink" | "hardlink" | "junction" | "copy"
backup_on_collision = true      # Safeguard existing files
ignore = [".git", "README.md", "fig.toml", "*.swp"]

# -------------------------------------------------------------
# USER CONFIGURATION SECTION (Default, Unprivileged)
# -------------------------------------------------------------
[presets]
include = ["git", "ssh", "starship"]

[mappings]
"git/.gitconfig"      = "~/.gitconfig"
"ssh/config"          = "~/.ssh/config"
"starship.toml"       = "~/.config/starship.toml"

[os.posix.mappings]
"zsh/.zshrc"          = "~/.zshrc"
"nvim"                = "~/.config/nvim"

[os.windows.mappings]
"nvim"                = "%LOCALAPPDATA%/nvim"
"powershell/profile.ps1" = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"

# -------------------------------------------------------------
# SYSTEM CONFIGURATION SECTION (Strictly requires --system)
# Every entry MUST have an explicit destination pathspec.
# -------------------------------------------------------------
[system.mappings]
"system/hosts"        = "/etc/hosts" # or C:\Windows\System32\drivers\etc\hosts on Windows

[os.linux.system.mappings]
"system/sysctl.d/99-custom.conf" = "/etc/sysctl.d/99-custom.conf"
"system/systemd/myservice.service" = "/etc/systemd/system/myservice.service"

[os.windows.system.mappings]
"system/wsl.conf"     = "%ProgramData%/wsl/wsl.conf"
```

---

## 3. Architecture & Codebase Structure

The codebase is organized into clean functional tiers:

```
fig/
├── core/                            # Low-Level Engine Primitives & Security
│   ├── config.py                    # State directories (~/.fig, %ProgramData%/fig)
│   ├── platform.py                  # Early OS detection, POSIX unification, path translation
│   ├── elevation.py                 # UAC/sudo elevation management, breaking-changes guard
│   ├── logger.py                    # Audit logging (~/.fig/logs/fig.log, system logs)
│   ├── linker.py                    # Atomic symlinks, junctions, hardlinks, deletions
│   ├── backup.py                    # Selective collision backup vault & manifests
│   ├── template.py                  # TOML parser, user & system section isolation
│   └── engine.py                    # Deployment orchestrator & idempotency engine
│
├── modules/                         # High-Level Feature Subsystems
│   ├── system.py                    # System configuration manager & redundancy vault
│   ├── builder.py                   # Interactive REPL builder & scanner (-system supported)
│   ├── scanner.py                   # Layout analyzer, nested configs, pathspec parser
│   ├── viewer.py                    # Template visualizer & editor ($EDITOR / nvim)
│   ├── profiles.py                  # Profiles & temporary takeover ("temp mode")
│   ├── wizard.py                    # Starter questionnaire wizard
│   └── git_clone.py                 # Git remote repository cloner
│
├── builtins/                        # Built-in Catalog
│   └── catalog.py                   # Preset mappings for standard user tools
│
├── cli.py                           # CLI Interface & Command Dispatcher
├── __init__.py
└── __main__.py
```

### State & Storage Structure

```
~/.fig/                              # User Fig State Directory
├── config.toml                      # Active template pointer & global settings
├── active_template.toml             # Mirrored active template
├── backups/                         # User collision backup vault
│   └── YYYYMMDD_HHMMSS_<reason>/
│       ├── manifest.json
│       └── files/
├── logs/                            # User audit logs
│   └── fig.log
├── profiles/                        # Saved named profiles
├── repos/                           # Cloned remote dotfile repositories
└── sessions/                        # Temporary override sessions

%ProgramData%\fig\ or /var/backups/fig/ # System Redundancy Disaster Vault
├── backups/                         # Redundant system file backups
│   └── YYYYMMDD_HHMMSS_system/
│       ├── manifest.json
│       └── files/
└── logs/                            # System audit log
    └── system_fig.log
```

---

## 4. Phased Implementation Status

### Phase 1: Core Engine & Safety Foundation (COMPLETED)
- [x] Architectural specification & blueprint (`PROJECT_MAP.md`).
- [x] Early OS detection & Native Path Resolution (`fig.core.platform`).
- [x] POSIX unification (`[os.posix.mappings]`) shared across Linux and macOS.
- [x] Cross-platform linking mechanism (`fig.core.linker`).
- [x] Collision detection & Backup Engine (`fig.core.backup`).
- [x] Audit Logging Engine (`fig.core.logger`).
- [x] Template Engine with user/system isolation (`fig.core.template`).

### Phase 2: Builder, Pathspec & Refactored CLI (COMPLETED)
- [x] Repository Scanner & `pathspec.txt` parser (`fig.modules.scanner`).
- [x] Interactive Template Builder REPL with exclusion toggling (`fig.modules.builder`).
- [x] Git remote repo cloning (`fig.modules.git_clone`).
- [x] Template Viewer & Visual Editor integration (`fig.modules.viewer`).
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

### Phase 4: System Configuration & Elevation (COMPLETED)
- [x] System configuration module (`fig.modules.system`).
- [x] Explicit pathspec enforcement for all system mappings.
- [x] Breaking-changes warning banner & confirmation guard (`-y` / `--yes` flag).
- [x] Elevation check & re-launch: UAC prompt on Windows / sudo on Linux.
- [x] System redundancy disaster-recovery vault (`%ProgramData%\fig\backups\` / `/var/backups/fig/`).
- [x] System rollback: `fig undo --system` / `fig -system undo`.
- [x] System builder: `fig build --system`.
