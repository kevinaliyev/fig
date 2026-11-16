# fig Technical Guide & Internals

fig is a cross-platform dotfile and configuration manager written in pure Python (3.11+ standard library, zero external runtime dependencies).

**Related Docs:**
- [Template Spec](Template%20Spec.md) — `fig.toml` schema, pathspec shorthands, OS scopes, and `--system` mode
- [Changelog](CHANGELOG.md) — Release history

---

## 1. Architecture & Package Layout

```text
fig/
├── cli.py           # CLI parser & command dispatcher
├── config/          # FigState (~/.fig/state.toml), Template TOML parser, OS detection, presets
├── sync/            # FigEngine, cross-platform Linker, BackupSession vault, SystemConfigManager
├── builder/         # RepoScanner, scoped REPL, tree/table renderer, Template assembler, wizard
├── ui/              # ANSI styling primitives, interactive popup menus, fig view/edit
├── profiles/        # ProfileManager & BorrowSessionManager (temp/revert)
└── utils/           # Audit logger, UAC/sudo elevation, Git remote cloning, cleanup
```

### Linking Strategy (`LinkMode.AUTO`)
1. **POSIX (Linux / macOS)**: Creates native `os.symlink`.
2. **Windows**: Attempts `os.symlink`; if unprivileged Developer Mode is unavailable, falls back to **NTFS Directory Junctions** (`mklink /J`) for directories or **Hardlinks** (`os.link`) for files, and finally byte-copy if cross-volume.

### Collision Safety & Rollback
Before replacing any existing file or directory at a destination, `FigEngine` archives the original item into `~/.fig/backups/<session_id>/` with a `manifest.json`. Running `fig undo` restores the exact pre-deployment state.

---

## 2. Interactive Builder & Rebuilder (`fig build` / `fig rebuild`)

- **`fig build [DIR|URL]`**: Scans a local directory or clones a remote Git repo (supporting `gh:user/repo`, HTTPS, and SSH with live TTY auth) and launches the interactive REPL.
- **`fig rebuild [TARGET]`**: Resolves the active template's source of truth automatically (no path required) and opens the REPL pre-populated with your existing mappings, link modes, OS scopes, and exclusions.

### REPL Commands
- **Navigate**: `cd <#|name>` (open folder), `cd ..` / `back`, `cd /`, `tree`
- **Select**: `<#>` (toggle), `only <#> ...`, `exclude <#>`, `include <#>`, `all` / `none`
- **Configure**: `edit <#>` (preset picker), `mode <#> [type]`, `os <#> [scope]`, `pack` / `unpack`
- **Palette & Save**: `:` or `menu` (command palette), `?` / `help` (modal guide), `done` (save & prompt profile name), `quit`

---

## 3. Runtime Layout (`~/.fig/`)

Runtime state is stored in `$FIG_HOME` (defaults to `~/.fig/`, bridging `$XDG_CONFIG_HOME/fig` if set):

- `state.toml` — Machine-local registry tracking the active template path, repository root, active profile, and registered profiles.
- `active_template.toml` — Live symlink/hardlink pointing directly to the active repository's `fig.toml` (no duplicate copies).
- `profiles/<name>/fig.toml` — Named configuration profiles created on build/rebuild.
- `backups/` — Timestamped collision backup vaults with JSON manifests.
- `sessions/` — Active temporary session state (`active_borrow.json`) for `fig temp` / `fig revert`.
- `logs/fig.log` — Centralized audit log of all operations.

---

## 4. Global Flags

- `--system` / `-system`: Operate on system-level targets (`/etc/`, `systemd`, Windows system files) with UAC/sudo elevation and redundant backups in `%ProgramData%\fig\` or `/var/backups/fig/`.
- `--preview` / `-n`: Dry-run simulation without modifying the filesystem.
- `-y` / `--yes`: Skip confirmation prompts in automated scripts.
- `--dest <PATH>`: Custom clone destination when bootstrapping or building from a Git URL.

---

## 5. Development & Helper Scripts (`scripts/`)

```powershell
python -m unittest discover tests                   # Run all 76 unit tests
python scripts/release/bump_version.py check        # Verify version parity across manifests
python scripts/release/bump_version.py <ver>        # Bump version across package & manifests
python scripts/release/install.py                   # Build standalone binary & install to ~/.local/bin
python scripts/release/package_release.py           # Stage zip archive & update Scoop SHA256
python scripts/maintenance/clean.py                 # Purge build/cache artifacts
python scripts/qa/qa_fixture.py                     # Generate QA test dotfile fixtures
```
