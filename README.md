# Fig

> **Fast, auditable, and transparent user & system configuration / dotfile manager.**

`fig` maps source dotfile repositories to system destinations using declarative templates (`fig.toml`), cross-platform links (symlinks, junctions, hardlinks), zero-loss collision backups, and reversible profiles.

[![Tests](https://img.shields.io/badge/tests-31%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-blue.svg)]()
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)

---

## Key Highlights

- **Temporary Userspace Overrides ("")**: Need to help somebody on their workstation and dont want to override their configs/binds? Run `fig temp <your-repo>` to temporarily transform their machine into your familiar environment with your editor, shell, and whatever else you have specced in your template. When you're done, run `fig revert` to instantly restore their machine back to its exact previous state! (If you overrode their nvim plugins and **installed** your own, be nice enough to revert it back through the plugin manager, fig wont do that! 😅)
- **Safety Guard, Mandatory System Specs & Redundancy Disaster Vault**: Modifying system files (`/etc/`, systemd units, Windows system files) is strictly isolated from user dotfiles. Every system entry requires an explicit pathspec, triggers a prominent breaking-changes warning banner requiring user confirmation (`-y` to bypass), prompts for elevated permissions (UAC on Windows / `sudo` on Linux), and archives redundant backups to an independent machine-wide vault (`%ProgramData%\fig\backups\` or `/var/backups/fig/`) ensuring disaster recoverability even if user files are wiped.
- **Full Audit Logging**: Every operation—from link deployments and collision backups to system rollbacks—is logged with ISO timestamps in `~/.fig/logs/fig.log` and the system redundancy audit log for complete accountability.
- **Interactive Terminal Suite (REPL Builder, Visual Viewer & In-Place Editor)**:
  - `fig build`: Interactive REPL scanner that discovers configs, shows a clean table, lets you toggle exclusions (`toggle <num>`), and builds templates.
  - `fig view`: Formatted, colorized inspection of active or catalog templates.
  - `fig edit`: In-place template editing via `$EDITOR` / `$VISUAL` (`nvim`, `vim`, `notepad`) with automated syntax validation upon exit.
- **Template & Profile Catalog with Instant Swapping**: Catalog multiple profiles/templates (`fig profile`, `fig template`) and swap between them instantly. Perfect for shared computers forced under a single user account (lab machines, shared workstations, family PCs), separating work vs personal profiles, or test-driving someone else's dotfile configuration without blowing away your own.
- **Rapid OS Bootstrapping & Universal App Compatibility**: Deploy your entire workstation in one command (`fig -bootstrap`). Zero external dependencies (pure Python 3.11+ standard library). Compatible with any first- or third-party application via standardized `pathspec.txt` files.

---

## Quickstart

Fig provides 4 primary operational workflows. Choose the one that matches your situation:

### Option 1: Bootstrapping an Existing Dotfiles Repo on a Fresh OS (`fig -bootstrap`)

> **Intended Use:** You've just installed a clean OS. You clone your dotfiles repository (where you have already configured a `fig.toml` or third-party `pathspec.txt` files) and want to deploy everything immediately in one shot.

```bash
git clone https://github.com/yourusername/dotfiles.git ~/dotfiles
cd ~/dotfiles
fig -bootstrap
```

*Note: While `fig -bootstrap` will auto-generate a template at runtime if none is found, the intended practice is to have your template already committed to your repo. `fig -bootstrap` backs up any conflicting system files, creates all links, and registers this repository as your machine's active template at `$HOME`.*

---

### Option 2: Interactive Setup & Building a New Template (`fig build`)

> **Intended Use:** You have a dotfiles directory (or want to clone one straight from GitHub) and want Fig to scan the directory tree, identify applications, and guide you through building a clean `fig.toml`.

```bash
# Build template from current directory
fig build

# Or build from a specific directory path
fig build /path/to/my-dotfiles

# Or clone straight from GitHub and launch the builder
fig build gh:yourusername/dotfiles
```

The interactive REPL will:
1. Scan your directory tree (detecting `.config/` mirrors, nested `nvim` setups, stow-style folders, and `pathspec.txt` files).
2. Present a clean, readable table of discovered applications.
3. Allow you to interactively toggle exclusions (`toggle 2`), edit destination paths (`edit 3`), or add custom apps.
4. Generate a clean, validated `fig.toml`.

---

### Option 3: Everyday Routine Synchronization (`fig` / `fig sync`)

> **Intended Use:** You've made changes to your dotfiles repo (or pulled upstream git commits) and want to enforce your active template idempotently.

```bash
fig
# or: fig sync
```

Fig inspects your active template registered at `~/.fig/config.toml`. If links are already established and healthy, running `fig` is a safe, zero-impact no-op.

---

### Option 4: Temporary Coworker / Guest Takeover (`fig temp` & `fig revert`)

> **Intended Use:** You are assisting a coworker or friend on their computer and want your familiar environment temporarily.

```bash
# 1. Temporarily deploy your dotfiles (snapshots coworker's current state)
fig temp ~/my-dotfiles

# 2. Do your work with your familiar shell, editor, and tools...

# 3. Cleanly revert coworker's machine back to its exact original state
fig revert
```

---

## Dotfile Repository Setup & Directory Tree Conventions

Dotfile repositories in the wild use varying structures. Fig natively understands and standardizes the most common conventions without requiring you to restructure your repository:

### 1. The Stow-Style Flat Convention
Folders named after tools containing standard configuration files:
```
dotfiles/
├── git/
│   └── .gitconfig          -> ~/.gitconfig
├── zsh/
│   └── .zshrc              -> ~/.zshrc
└── tmux/
    └── .tmux.conf          -> ~/.tmux.conf
```

### 2. The `.config` Mirror Convention
A directory named `.config` or `config` in your repo:
```
dotfiles/
└── .config/
    ├── alacritty/
    │   └── alacritty.toml  -> ~/.config/alacritty/alacritty.toml
    └── kitty/
        └── kitty.conf      -> ~/.config/kitty/kitty.conf
```

### 3. Nested Directory Configs (e.g. Neovim)
Complex tools like Neovim feature deep folder trees containing `init.lua`, `lua/`, and `plugins/`. Instead of creating dozens of individual file symlinks, Fig detects the folder and creates a **directory-level link**:
```
dotfiles/
└── nvim/                   -> ~/.config/nvim (or %LOCALAPPDATA%/nvim on Windows)
    ├── init.lua
    └── lua/
        └── config/
```

### 4. Root-Level Dotfiles
Standard dotfiles placed directly in the repository root:
```
dotfiles/
├── .gitconfig              -> ~/.gitconfig
├── .zshrc                  -> ~/.zshrc
└── starship.toml           -> ~/.config/starship.toml
```

---

## Pathspec Specification Guide (`pathspec.txt`)

For any custom, third-party, or non-standard application, simply drop a `pathspec.txt` (or `.fig.pathspec`) file inside the application's directory:

```
dotfiles/
└── my_custom_app/
    ├── config.json
    ├── themes/
    └── pathspec.txt
```

### Simple Universal Target
If the application uses the same destination on all platforms:
```ini
~/.local/share/my_custom_app
```

### Multi-Platform Targets, Link Modes & Tree Linking
For advanced applications, specify key-value pairs:
```ini
# Platform-specific destinations
windows = %APPDATA%/my_custom_app
posix   = ~/.local/share/my_custom_app
macos   = ~/Library/Application Support/my_custom_app

# Link strategy: symlink (default), hardlink, junction, or copy
link_mode = symlink

# Link type: 'dir' to link the entire directory tree, or 'file' for single files
type = dir

# Scope: 'user' (default) or 'system' (requires --system elevation)
scope = user
```

When `fig build` scans your repository, it reads `pathspec.txt` directly—eliminating guesswork and hardcoded heuristics.

---

## Template Specification (`fig.toml`)

Your `fig.toml` file declares all mappings, presets, and safety rules for your repository:

```toml
[meta]
name = "my-complete-config"
version = "1.0.0"
description = "Personal cross-platform dotfiles with optional system configuration"

[settings]
link_mode = "auto"              # "auto" | "symlink" | "hardlink" | "junction" | "copy"
backup_on_collision = true      # Always archive conflicting files before overwriting
ignore = [".git", "README.md", "fig.toml", "*.swp"]

# -------------------------------------------------------------
# USER CONFIGURATION SECTION (Default, Unprivileged)
# -------------------------------------------------------------
[presets]
include = ["git", "ssh", "starship"]

# Universal user mappings (applies to all OSes)
[mappings]
"git/.gitconfig"      = "~/.gitconfig"
"ssh/config"          = "~/.ssh/config"
"starship.toml"       = "~/.config/starship.toml"

# POSIX-unified mappings (applies to both Linux and macOS without duplication)
[os.posix.mappings]
"zsh/.zshrc"          = "~/.zshrc"
"nvim"                = "~/.config/nvim"
"wezterm"             = "~/.config/wezterm"

# Windows-specific mappings
[os.windows.mappings]
"nvim"                = "%LOCALAPPDATA%/nvim"
"powershell/profile.ps1" = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
"wezterm"             = "~/.config/wezterm"

# -------------------------------------------------------------
# SYSTEM CONFIGURATION SECTION (Strictly requires --system)
# Every entry MUST have an explicit destination pathspec.
# -------------------------------------------------------------
[system.mappings]
"system/hosts"        = "/etc/hosts" # or C:\Windows\System32\drivers\etc\hosts on Windows

[os.linux.system.mappings]
"system/sysctl.d/99-custom.conf" = "/etc/sysctl.d/99-custom.conf"

[os.windows.system.mappings]
"system/wsl.conf"     = "%ProgramData%/wsl/wsl.conf"
```

---

## User Guide & Command Reference

### Core Commands

| Command | Aliases | Description |
| :--- | :--- | :--- |
| `fig` / `fig sync` | `apply` | Synchronize user dotfiles against active template (idempotent). |
| `fig -bootstrap [DIR]` | `fig bootstrap` | Deploy dotfiles from `DIR`, back up collisions, and set as active. |
| `fig build [DIR\|URL]` | — | Interactive REPL scanner to review and build a `fig.toml` template. |
| `fig check` | `status` | Inspect link health, drift, collisions, and missing target files. |
| `fig preview` | `diff`, `-n` | Preview planned actions without modifying filesystem. |
| `fig undo [ID]` | `rollback`, `restore` | Restore previous files from backup vault and remove deployed links. |
| `fig history` | `backups` | List historical backup sessions in vault. |
| `fig temp <DIR>` | `guest`, `borrow` | Temporarily deploy dotfiles for a work session on a coworker's machine. |
| `fig revert` | `unborrow` | Revert temporary session and restore original machine state. |
| `fig view [TARGET]` | `template view` | View formatted inspection of template (including system section). |
| `fig edit [TARGET]` | `template edit` | Open template in visual editor (`$EDITOR`, `nvim`, `notepad`). |
| `fig template list` | — | List all saved templates and the current active template. |
| `fig profile switch <name>` | — | Switch active configuration to a named profile and sync. |

### Global Flags

- `--system` / `-system`: Operate in elevated SYSTEM mode (targets `/etc/`, systemd, or Windows system files).
- `-y` / `--yes`: Skip breaking-changes confirmation prompts in automated scripts.
- `--preview` / `-n`: Simulate actions without modifying the filesystem.
- `-v` / `--version`: Display Fig version and detected host platform.
- `-h` / `--help`: Display comprehensive help and syntax.

### Interactive REPL Builder Commands (`fig build`)

When running `fig build`, Fig enters an interactive REPL with the following commands:
- `toggle <#>`: Toggle include/exclude for mapping (e.g. `toggle 2`).
- `exclude <#>`: Exclude an application from being linked.
- `include <#>`: Re-include an application for linking.
- `edit <#>`: Interactively modify the target destination path.
- `add`: Add a manual mapping with an explicit source and destination.
- `list`: Reprint the clean summary table.
- `done`: Finalize review and save `fig.toml`.
- `quit`: Exit without saving changes.

---

## System Configuration Mode (`--system` / `-system`)

System-level files (`/etc/`, systemd units, Windows system configuration) are strictly isolated from user dotfiles:

1. **Explicit Mandate**: System files are **never** auto-discovered or linked unless `--system` is passed.
2. **Safety Guard**: Displays a breaking-changes warning banner detailing affected system paths and asks for confirmation (`y/N`). Use `-y` to bypass in scripts.
3. **Elevation Check**: Checks for administrative privileges **only after** the warning is confirmed. If unprivileged, Fig prompts to elevate via UAC on Windows or `sudo` on Linux/macOS.
4. **Disaster Recovery Vault**: System changes are redundantly saved to `%ProgramData%\fig\backups\` (Windows) or `/var/backups/fig/` (Linux/macOS) in addition to user backups.
5. **System Rollback**:
   ```bash
   fig undo --system
   ```

---

## State Storage & Audit Logs

Fig organizes persistent state into separated user and machine-wide tiers:

```
~/.fig/                                 # User State Directory
├── config.toml                         # Active template pointer & global settings
├── active_template.toml                # Mirrored active template
├── backups/                            # User collision backup vault
│   └── YYYYMMDD_HHMMSS_<reason>/
│       ├── manifest.json               # Audit trail & restore manifest
│       └── files/                      # Preserved original user files
├── logs/
│   └── fig.log                         # Timestamped audit log
├── profiles/                           # Saved named profiles
├── repos/                              # Cloned remote dotfile repositories
└── sessions/                           # Temporary override ("temp mode") session state

%ProgramData%\fig\ or /var/backups/fig/ # System Redundancy Disaster Vault
├── backups/
│   └── YYYYMMDD_HHMMSS_system/         # System disaster recovery archives
│       ├── manifest.json
│       └── files/                      # Preserved original system files
└── logs/
    └── system_fig.log                  # System-level audit log
```

---

## Standalone Execution Wrappers & Packaging Roadmap

### What are `fig.bat` and `fig_sh`?

- **`fig.bat`** (Windows Batch Script) and **`fig_sh`** (POSIX Shell Script) are zero-installation local wrappers located in the repository root.
- They allow developers or sysadmins to clone this repository and immediately run `.\fig.bat <command>` or `./fig_sh <command>` without installing Fig via `pip` or configuring their system `PATH`.
- Once you install Fig with `pip install -e .`, the `fig` executable registered in `pyproject.toml` is globally available anywhere in your terminal.

### Packaging & Binary Executable Roadmap

Because Fig is engineered with **zero external third-party dependencies** in standard Python 3.11+, it is an ideal candidate for standalone packaging:

1. **Standalone Binary Executable (PyInstaller / Nuitka / PyOxidizer)**:
   - Fig can be compiled into a single self-contained binary (`fig.exe` on Windows, `fig` on Linux/macOS) bundling a lightweight Python runtime.
   - End users will be able to run Fig on clean systems without needing Python installed.
2. **Built-in `zipapp` Executable**:
   - Python's standard `zipapp` module can package Fig into a single executable archive:
     ```bash
     python -m zipapp fig -m fig.cli:main -o fig
     ```
3. **One-Line Web Installers**:
   - POSIX: `curl -fsSL https://get.fig.sh | sh` (downloads binary to `~/.local/bin/fig`).
   - Windows: `irm https://get.fig.sh/install.ps1 | iex` (downloads `fig.exe` to `%LOCALAPPDATA%\Programs\fig\bin`).

---

## Running Tests

Fig includes an automated test suite verifying cross-platform linking, collision detection, template generation, builder REPL workflows, and system elevation:

```bash
python -m unittest discover tests
```
