# fig

> **A fast, auditable, and transparent user & system configuration / dotfile manager.**

`fig` maps source dotfile repositories to system destinations using declarative templates (`fig.toml`), cross-platform links (symlink, junction, hardlink), zero-loss collision backups, and reversible profiles.

[![Tests](https://img.shields.io/badge/tests-17%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

---

## Key Highlights

- **Early OS Detection**: Identifies operating system immediately at startup (`windows`, `linux`, `macos`, `bsd`) and resolves native paths, environment variables (`$HOME`, `%USERPROFILE%`, `%APPDATA%`, `~/Documents`), and filesystem conventions.
- **OS-Specific Declarations in Templates**: Single dotfile repo can route different configurations based on OS (e.g. `[os.windows.mappings]` for PowerShell/WezTerm Windows vs `[os.linux.mappings]` for Bash/WezTerm Linux).
- **Interactive Setup Wizard (REPL)**: If you run `fig` on a clean system without an active template, Fig launches a guided REPL asking about your shells, editor, git, and terminal to generate a clean starter template.
- **One-Command Bootstrap (`fig -bootstrap` or `fig bootstrap`)**: Run inside any cloned dotfiles repo. It backs up existing configs, deploys links, and registers the repo as the machine's active template at `$HOME`.
- **Selective Safety Vault**: Before replacing *any* existing file or link, `fig` selectively archives colliding files into a timestamped vault (`~/.fig/backups/`) with a JSON manifest.
- **Instant Rollback (`fig undo`)**: Revert any deployment back to its exact prior state with a single command.
- **Zero-Drift Idempotency (`fig` / `fig sync`)**: Running `fig` repeatedly synchronizes against the active template. If nothing changed, it is a safe no-op.
- **Temporary Overrides (`fig temp` / `fig revert`)**: Temporarily apply your dotfiles on a coworker's or shared computer and instantly revert everything back to their exact previous state when finished.
- **Profile Switching (`fig profile`)**: Switch between multiple configuration profiles (e.g. personal, work, server) under a single account.
- **Zero-Dependency Core**: Written entirely in standard library Python (Python 3.11+).

---

## Quickstart

### 1. First Run & Setup Wizard

If you don't have a template yet, simply run `fig`:

```bash
fig
```

Fig will detect your OS and guide you through an interactive REPL setup to generate a starter `fig.toml` in your directory.

### 2. Bootstrapping a Dotfiles Repository

Clone your dotfiles repository and run `fig -bootstrap`:

```bash
git clone https://github.com/yourusername/dotfiles.git ~/dotfiles
cd ~/dotfiles
fig -bootstrap
```

What this does:
1. Detects `fig.toml` (or generates one automatically if missing).
2. Checks for collisions on your filesystem.
3. Archives conflicting files to `~/.fig/backups/<timestamp>_bootstrap/`.
4. Deploys symlinks/hardlinks natively to your system.
5. Registers this repository as the machine's active template at `~/.fig/`.

### 3. Routine Syncing

Once bootstrapped, run `fig` (or `fig sync`) from anywhere:

```bash
fig
```

This enforces your active template idempotently. If files are already linked, nothing is modified.

### 4. Checking Status & Health

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
  [MISSING]  C:\Users\user\.config\starship.toml
```

### 5. Previewing Changes

```bash
fig preview
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

# Instantly restore coworker's original state
fig revert
```

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
ignore = [".git", "README.md", "fig.toml"]

# Shared across all platforms
[presets]
include = ["git", "ssh", "starship"]

[mappings]
"git/.gitconfig"      = "~/.gitconfig"
"ssh/config"          = "~/.ssh/config"
"starship.toml"       = "~/.config/starship.toml"

# Windows-specific mappings
[os.windows.mappings]
"wezterm/wezterm_win.lua"     = "~/.config/wezterm/wezterm.lua"
"powershell/profile.ps1"      = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
"nvim"                        = "%LOCALAPPDATA%/nvim"

# Linux-specific mappings
[os.linux.mappings]
"wezterm/wezterm_linux.lua"   = "~/.config/wezterm/wezterm.lua"
"zsh/.zshrc"                  = "~/.zshrc"
"nvim"                        = "~/.config/nvim"

# macOS-specific mappings
[os.macos.mappings]
"wezterm/wezterm_mac.lua"     = "~/.config/wezterm/wezterm.lua"
"zsh/.zshrc"                  = "~/.zshrc"
```

---

## Command Reference

| Command | Aliases | Description |
| :--- | :--- | :--- |
| `fig` / `fig sync` | `apply` | Synchronize system files against active template. |
| `fig -bootstrap [DIR]` | `fig bootstrap` | Bootstrap dotfiles from `DIR`, back up collisions, and set as active. |
| `fig check` | `status` | Check status of all managed target files (linked, drifted, collision, missing). |
| `fig preview` | `diff`, `-n` | Preview planned actions without modifying filesystem. |
| `fig undo [ID]` | `rollback`, `restore` | Restore replaced files and clean up newly added links. |
| `fig history` | `backups` | List all historical collision backup sessions in `~/.fig/backups/`. |
| `fig temp <DIR>` | `guest`, `borrow` | Temporarily apply dotfiles for a work session. |
| `fig revert` | `unborrow` | Revert temporary session and restore original machine state. |
| `fig setup [DIR]` | — | Run interactive setup wizard (REPL) to generate starter `fig.toml`. |
| `fig profile list` | — | List available named configuration profiles. |
| `fig profile switch <name>` | — | Switch active configuration to a named profile and sync. |

---

## Architecture & Contributing

For full architecture details, see [PROJECT_MAP.md](PROJECT_MAP.md).

### Running Tests

```bash
python -m unittest discover tests
```
