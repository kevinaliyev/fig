# Fig

> **A fast, auditable, and transparent user & system configuration / dotfile manager.**

`fig` maps source dotfile repositories to system destinations using declarative templates (`fig.toml`), cross-platform links (symlinks, junctions, hardlinks), zero-loss collision backups, and reversible profiles.

[![Tests](https://img.shields.io/badge/tests-31%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

---

## Key Highlights

- **Scope Separation**: Clear separation between everyday user dotfiles (unprivileged) and system-level configuration files (`/etc/`, systemd, Windows system files). System files are **never** touched unless you explicitly pass `--system`.
- **Breaking Changes Safety Guard**: Modifying system files triggers an explicit breaking changes warning detailing affected paths and risks to system stability. Confirmation (`y/N`) is mandatory (skippable with `-y` in automation).
- **Elevation Protocol**: If you aren't in an elevated shell when applying system configs, Fig prompts for UAC elevation on Windows or `sudo` on Linux/macOS (only *after* you have confirmed the breaking-change warning).
- **System Redundancy Disaster Vault**: System changes are saved to an independent system-level redundancy vault (`%ProgramData%\fig\backups\` on Windows or `/var/backups/fig/` on Linux/macOS) in addition to user backups, ensuring disaster recoverability even if user files are deleted.
- **Mandatory System Pathspecs**: Every system configuration entry must explicitly define its destination path. No auto-guessing for system files.
- **Audit Logging**: Every operation is logged with ISO timestamps in `~/.fig/logs/fig.log` and system redundancy logs.
- **Interactive Template Builder (`fig build`)**: Interactive REPL that scans local repositories or remote GitHub repos (`gh:user/dotfiles`), detects directory trees, reads `pathspec.txt`, and lets you toggle exclusions before generating `fig.toml`.
- **POSIX Unification (`[os.posix.mappings]`)**: Rules shared across Linux and macOS can be declared under `[os.posix.mappings]`, eliminating duplicate rules.
- **100% Reversible Rollback (`fig undo` / `fig undo --system`)**: Revert any deployment or temporary session back to its exact prior state with a single command.
- **Zero Dependencies**: Written entirely in standard library Python (Python 3.11+).

---

## Quickstart

### 1. User Dotfiles (Default Mode)

```bash
# Build template interactively
fig build

# Or clone from GitHub & build
fig build gh:yourusername/dotfiles

# Bootstrap dotfiles (backs up collisions & activates template)
fig -bootstrap

# Routine idempotent synchronization
fig
```

### 2. System Configuration Mode (`--system` / `-system`)

System configurations must be explicitly declared in `fig.toml` under `[system.mappings]` or `[os.<name>.system.mappings]`:

```toml
[system.mappings]
"system/hosts" = "/etc/hosts" # or C:\Windows\System32\drivers\etc\hosts on Windows

[os.linux.system.mappings]
"system/sysctl.d/99-custom.conf" = "/etc/sysctl.d/99-custom.conf"
```

To apply system configurations:

```bash
fig -system
# or: fig apply --system
```

What happens:
1. Fig checks for system configurations and displays a prominent **BREAKING CHANGES WARNING** with the list of affected system paths.
2. Prompts for confirmation: `Are you sure you want to proceed with system modifications? [y/N]`.
3. Checks elevation: If not in an elevated shell, prompts to elevate (UAC on Windows / `sudo` on Linux).
4. Saves a disaster-recovery backup in the system redundancy vault (`%ProgramData%\fig\backups\` or `/var/backups/fig/`).
5. Atomically deploys the links.

To skip the warning prompt in automation or scripts, pass `-y`:
```bash
fig -system -y
```

### 3. Reviewing System Specs in Builder

```bash
fig build --system
```

Scans for folders with `pathspec.txt` containing system scopes or allows manual entry of explicit system pathspecs, provides an overview, and saves to `fig.toml`.

### 4. Undoing / Rolling Back System Changes

```bash
fig undo --system
```

Restores system files from the system redundancy disaster recovery vault.

---

## Template Specification (`fig.toml`)

```toml
[meta]
name = "my-complete-config"
version = "1.0.0"

[settings]
link_mode = "auto"              # "auto" | "symlink" | "hardlink" | "junction" | "copy"
backup_on_collision = true

# User Dotfiles Section
[mappings]
"git/.gitconfig"      = "~/.gitconfig"
"ssh/config"          = "~/.ssh/config"

[os.posix.mappings]
"zsh/.zshrc"          = "~/.zshrc"
"nvim"                = "~/.config/nvim"

[os.windows.mappings]
"nvim"                = "%LOCALAPPDATA%/nvim"
"powershell/profile.ps1" = "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"

# System Configuration Section (Strictly requires --system)
[system.mappings]
"system/hosts"        = "/etc/hosts"

[os.linux.system.mappings]
"system/sysctl.conf"  = "/etc/sysctl.d/99-custom.conf"

[os.windows.system.mappings]
"system/wsl.conf"     = "%ProgramData%/wsl/wsl.conf"
```

---

## Command Reference

| Command | Aliases | Description |
| :--- | :--- | :--- |
| `fig` / `fig sync` | `apply` | Synchronize user dotfiles against active template. |
| `fig -system` | `fig sync --system` | Apply system configurations (triggers warning & elevation check). |
| `fig -bootstrap [DIR]` | `fig bootstrap` | Deploy dotfiles from `DIR`, back up collisions, and set as active. |
| `fig build [DIR\|URL]` | — | Interactive REPL scanner to build user dotfile templates. |
| `fig build --system` | — | Review and assemble system configuration specifications. |
| `fig check` | `status` | Check health and link status of managed target files. |
| `fig preview` | `diff`, `-n` | Preview planned actions without modifying filesystem. |
| `fig undo [ID]` | `rollback`, `restore` | Restore replaced user files and remove newly added links. |
| `fig undo --system` | — | Restore system configuration from redundancy vault. |
| `fig history` | `backups` | List historical user backup sessions. |
| `fig history --system` | — | List historical system redundancy backups. |
| `fig temp <DIR>` | `guest`, `borrow` | Temporarily deploy dotfiles for a work session. |
| `fig revert` | `unborrow` | Revert temporary session and restore original machine state. |
| `fig view [TARGET]` | `template view` | View formatted inspection of template (including system section). |
| `fig edit [TARGET]` | `template edit` | Open template in visual editor (`$EDITOR`, `nvim`, `notepad`). |
| `fig profile switch <name>` | — | Switch active configuration to a named profile and sync. |

---

## Running Tests

```bash
python -m unittest discover tests
```
