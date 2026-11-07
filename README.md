# fig

> **A fast, auditable, and transparent user & system configuration / dotfile manager.**

`fig` maps source dotfile repositories to system destinations using declarative templates (`fig.toml`), cross-platform links (symlink, junction, hardlink), zero-loss collision backups, and reversible profiles.

[![Tests](https://img.shields.io/badge/tests-13%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

---

## Key Features

- **Repository-Centric Templates**: Keep a simple `fig.toml` in your dotfiles repository mapping source files to system paths.
- **Built-in Application Presets**: Out-of-the-box defaults for Git, Zsh, Bash, Tmux, Neovim, Alacritty, Kitty, Starship, Fish, SSH, Helix, and Wezterm.
- **Non-Destructive Collision Vault**: Before replacing *any* existing file or link, `fig` selectively archives colliding files into a timestamped vault (`~/.fig/backups/`) with a JSON manifest.
- **Instant Rollback (`fig restore`)**: Revert any deployment back to its exact prior state with a single command.
- **One-Command Bootstrap (`fig -bootstrap` or `fig bootstrap`)**: Run inside any cloned dotfiles repo. It backs up existing configs, deploys links, and registers the repo as the machine's active template at `$HOME`.
- **Zero-Drift Idempotency (`fig` / `fig apply`)**: Running `fig` repeatedly synchronizes against the active template. If nothing changed, it is a safe no-op.
- **Borrow Mode (`fig borrow` / `fig unborrow`)**: Temporarily apply your dotfiles on a coworker's or shared computer and instantly revert everything back to their exact previous state when finished.
- **Profile Switching (`fig profile`)**: Switch between multiple configuration profiles (e.g. personal, work, server) under a single account.
- **Zero-Dependency Core**: Written entirely in standard library Python (Python 3.11+). No external dependencies needed to bootstrap a fresh machine.
- **Cross-Platform Resilience**: Works seamlessly on Linux, macOS, BSD, and Windows (with automatic fallbacks for directory junctions and hardlinks when Windows Developer Mode is unprivileged).

---

## Quickstart

### 1. Bootstrapping on a Fresh Machine

Clone your dotfiles repository and run `fig --bootstrap`:

```bash
git clone https://github.com/yourusername/dotfiles.git ~/dotfiles
cd ~/dotfiles
fig -bootstrap
```

What this does:
1. Detects `fig.toml` (or generates one automatically if missing).
2. Checks for collisions on your filesystem.
3. Archives conflicting files to `~/.fig/backups/<timestamp>_bootstrap/`.
4. Deploys symlinks to your system.
5. Registers this repository as the machine's active template at `~/.fig/`.

### 2. Routine Syncing

Once bootstrapped, simply run `fig` from anywhere:

```bash
fig
```

This enforces your active template idempotently. If files are already linked, nothing is modified.

### 3. Checking Status

```bash
fig status
```

Example output:
```
Active Template: /home/user/dotfiles/fig.toml
Repository Root: /home/user/dotfiles

Target Statuses:
  [OK]       /home/user/.gitconfig -> /home/user/dotfiles/.gitconfig
  [OK]       /home/user/.zshrc -> /home/user/dotfiles/.zshrc
  [MISSING]  /home/user/.config/starship.toml
```

### 4. Undoing / Restoring Backups

View previous backups:
```bash
fig backups
```

Restore the system to the previous state (replaces links with original files):
```bash
fig restore
```

Or restore a specific session:
```bash
fig restore 20261107_051020_bootstrap
```

### 5. Borrowing a Coworker's Workstation

Help a coworker with your familiar tools, then leave without leaving a trace:

```bash
# Take over temporarily (snapshots their existing configs)
fig borrow ~/my-dotfiles

# ... do your work ...

# Instantly restore their original configs and delete your links
fig unborrow
```

---

## Template Specification (`fig.toml`)

Create a `fig.toml` in your repository root:

```toml
[meta]
name = "personal-dotfiles"
version = "1.0.0"
description = "My daily driver dotfiles"

[settings]
link_mode = "auto"              # "auto" | "symlink" | "hardlink" | "junction" | "copy"
backup_on_collision = true      # Safeguard existing files
ignore = [".git", "README.md", "fig.toml"]

# Automatically map popular tools present in your repo
[presets]
include = ["git", "zsh", "neovim", "tmux", "starship", "alacritty"]

# Explicit file/folder mappings (supports ~, $ENV, %APPDATA%)
[mappings]
"zsh/.zshrc"          = "~/.zshrc"
"git/.gitconfig"      = "~/.gitconfig"
"nvim"                = "~/.config/nvim"
"tmux/.tmux.conf"     = "~/.tmux.conf"
"scripts/status.sh"   = "~/.local/bin/status.sh"
```

---

## Command Reference

| Command | Description |
| :--- | :--- |
| `fig` / `fig apply` | Synchronize system files against active template at `$HOME`. |
| `fig -bootstrap [DIR]` | Bootstrap dotfiles from `DIR` (or current directory), back up collisions, and set as active. |
| `fig status` | Check status of all managed target files (linked, drifted, collision, missing). |
| `fig diff` / `-n` / `--dry-run` | Preview actions without modifying the filesystem. |
| `fig backups` | List all historical collision backup sessions in `~/.fig/backups/`. |
| `fig restore [ID]` | Restore replaced files and clean up newly added links. |
| `fig init [DIR]` | Generate a ready-to-use `fig.toml` based on files in `DIR`. |
| `fig borrow <DIR>` | Temporarily apply dotfiles for a work session. |
| `fig unborrow` / `fig revert` | Revert borrowed session and restore original configuration. |
| `fig profile list` | List available named profiles. |
| `fig profile switch <name>` | Switch active configuration to a named profile and apply. |

---

## State & Directory Structure

All persistent state is stored in `~/.fig` (or `$FIG_HOME`):

```
~/.fig/
├── config.toml               # Global settings & active template pointer
├── active_template.toml      # Mirrored active template
├── backups/                  # Timestamped collision vaults
│   └── 20261107_051020_bootstrap/
│       ├── manifest.json     # Audit trail and path restoration map
│       └── files/            # Preserved original files
├── profiles/                 # Saved named profiles
└── sessions/                 # Borrow mode temporary session state
```

---

## Architecture & Contributing

For full architecture details, design decisions, and future roadmap phases (such as elevated system-level configuration mode), see [PROJECT_MAP.md](PROJECT_MAP.md).

### Running Tests

```bash
python -m unittest discover tests
```
