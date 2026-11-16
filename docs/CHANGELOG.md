# Changelog

All notable changes to the **Fig** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.9] - 2026-11-16

### Added
- **Interactive Template Rebuilder (`fig rebuild`) & In-REPL Editing (`fig.builder`)**:
  - Added `fig rebuild` command to edit and update templates directly inside the Builder REPL without needing an explicit path argument.
  - Automatically resolves the original source of truth for the active template (or current directory `fig.toml` if present).
  - Pre-populates all existing custom destination expressions, link mode overrides (`junction`, `symlink`), OS target scopes (`windows`, `posix`), unpacked package hierarchies, and exclusions so configurations are never lost.
  - Discovers newly added repository packages/files and allows toggling them directly.
- **Machine State Registry (`~/.fig/state.toml`) & Zero-Duplication Live Links (`~/.fig/active_template.toml`)**:
  - Renamed Fig's internal machine-local state file from `config.toml` to `state.toml` (with backward-compatible fallback).
  - Replaced physical file copying of `active_template.toml` with a live filesystem link (symlink/hardlink) pointing directly to the source repository's `fig.toml`, eliminating stale duplicate templates.
- **Profile Generation & Directory Profiles (`fig.profiles`)**:
  - Added profile name prompt on build/rebuild, defaulting to `unnamed_<timestamp>` or template name.
  - Saved profiles into dedicated directories (`~/.fig/profiles/<profile_name>/fig.toml`) integrated with `fig temp` / `fig revert`.
- **Dynamic CWD Detection for `fig apply`**:
  - `fig apply` checks current working directory for `fig.toml`: applies and activates it if present, or refreshes links from the active template otherwise, with explicit `[INFO]` notifications.
  - Bare `fig` always refreshes the current active template without changing active registrations.

### Changed
- **Domain-Driven Package Refactor & `builder.py` Split**:
  - Reorganized `fig/` into clear feature domains: `config/`, `sync/`, `builder/`, `ui/`, `profiles/`, and `utils/` (removing `core/`, `modules/`, and `builtins/`).
  - Split the 84 KB `builder.py` monolith into focused modules under `fig/builder/` (`scanner.py`, `render.py`, `repl.py`, `assembler.py`, `wizard.py`).
  - Relocated `referencerepo/` out of the importable package into `tests/fixtures/referencerepo/`.
- **Concise Documentation & Clean Root**:
  - Consolidated documentation into 3 focused guides (`README.md`, `docs/README.md`, `docs/Template Spec.md`) alongside `docs/CHANGELOG.md`, retiring `PROJECT_MAP.md` and redundant docs.
  - Organized `scripts/` by purpose (`scripts/release/`, `scripts/maintenance/`, `scripts/qa/`) and removed OS-specific `.bat`/`.sh` wrappers.
  - Ignored `releases/` in `.gitignore` for clean GitHub Releases distribution.

---

## [0.5.8] - 2026-11-13

### Added
- **Modern CLI / TUI REPL UI Overhaul (`fig.builder`, `fig.ui.ansi`)**:
  - Anchored the scoped template list view at the top of the terminal using in-place ANSI screen clearing (`clear_screen()` + `redraw()`) gated by `sys.stdout.isatty()`.
  - Added transient status notification header (`status_msg`) displaying concise operation badges directly under the banner.
  - Replaced multi-line command legends with a 1-line horizontal shortcuts bar (`<#> Toggle · cd <#> Open · edit <#> Remap · mode <#> Mode · pack/unpack · : Menu · ? Help · done Save · quit Exit`).
  - Re-architected `help` / `?` and `tree` as temporary modal views inside a framed ANSI box (`format_box()`), returning cleanly to the template view on `[Enter]`.
  - Updated prompt to `fig builder (<scope>) > `.

---

## [0.5.7] - 2026-11-08

### Added
- **Git Remote Cloning & Non-Blocking Authentication (`fig.utils.git_clone`)**:
  - Integrated interactive clone destination popup (`./<repo>`, `~/repos/<repo>`, `~/.dotfiles`, `~/.fig/repos/<repo>`, `Custom Path...`).
  - Added `--dest <path>` CLI option to `fig build` and `fig bootstrap`.
  - Inherited direct TTY streams in interactive sessions for SSH passphrases, host key confirmations, and Git Credential Manager OAuth.
  - Configured `GIT_TERMINAL_PROMPT=0` in non-interactive sessions to fail fast with actionable diagnostics.
  - Added direct remote repository bootstrap support (`fig bootstrap <git_url>`).

---

## [0.5.6] - 2026-11-08

### Added
- **Zero-Dependency Terminal Popup & Submenu Engine (`fig.ui.menu`)**:
  - Implemented interactive floating selection popup using `msvcrt` on Windows and `termios`/`tty` on POSIX with `↑`/`↓` (`k`/`j`), `1-9` shortcuts, `Enter`, `Esc`/`q`, and non-interactive fallback.
- **Neovim-Style Command Palette (`:` or `menu`)**:
  - Pressing `:` or typing `menu` in the Builder REPL opens a floating command palette.
- **Interactive Preset Destination Selector (`edit <#>`), OS Scope (`os <#>`), and Per-Link Modes (`mode <#>`)**:
  - Added curated preset path picker popup in `edit <#>`.
  - Added `os <#|name> [target]` to assign `Universal`, `Windows`, `Linux`, `macOS`, or `POSIX` scopes.
  - Added inline table support in `fig.toml` (`"app" = { target = "...", mode = "junction" }`) and `ResolvedLink(tuple)` for backward-compatible 2-tuple unpacking.

---

## [0.5.5] - 2026-11-08

### Changed
- **Visual & Semantic Overhaul of `fig view` (`fig.ui.viewer`)**:
  - Added ANSI color banners, headers, and aligned tables with columnar link mode badges (`[auto]`, `[junction]`, `[symlink]`).
  - Upgraded OS platform matching via `matches_current_os()` to highlight active platform configurations above inactive targets.
  - Removed redundant catalog preset dumping in generated templates and viewer output.

---

## [0.5.4] - 2026-11-08

### Added
- **Packaging Control (`pack` vs `unpack`) with Child Exclusion Preservation**:
  - Preserved explicit `pack` whole-directory linking even when child files are excluded, recording excluded children into `ignore_patterns`.

### Fixed
- **Repository Root Scanning & Package Origin Preservation**:
  - Eliminated arbitrary nested directory hijacking in `RepoScanner` when `.config/<app>` existed inside a package.
  - Preserved top-level package `source_rel` and stopped discarding dotfiles (e.g. `.luacheckrc`, `.stylua.toml`, `.editorconfig`) inside `_scan_children`.

---

## [0.5.3] - 2026-11-08

### Fixed
- **Explicit Mappings vs Ignore Patterns & Stale Ignore Purging**:
  - Ensured explicit mappings in `[mappings]` / `[os.<os>.mappings]` are never dropped by `ignore_patterns`, and purged stale ignores for newly active packages.
- **Redundant Collision Backups on In-Sync Copied Files**:
  - Added byte-level comparison before collision backups so already synchronized copied files bypass the backup vault.
- **CLI Output & Completion Confirmation**:
  - Added definitive completion status banners (`[OK]`, `[SUCCESS]`, `[FAILED]`) after synchronization.

---

## [0.5.2] - 2026-11-08

### Added
- **Selective Leaf Linking & Granular Package Unpacking in Builder REPL**:
  - Added `unpack` (`files`, `split`, `ungroup`), `pack` (`dir`, `group`), and `only <#...>` commands.
  - Subdirectories (depth >= 1) default to unpacked containers so only active leaf files are linked and excluded leaves go to `ignore_patterns`.

### Fixed
- **Directory Junction & Symlink Idempotency**:
  - Fixed false-positive `"Source and destination cannot be identical"` errors on active junctions/symlinks.
  - Upgraded status checks to detect Windows directory junctions via `is_symlink_or_junction` and handle broken reparse point removal.

---

## [0.5.1] - 2026-11-07

### Added
- **Workstation Cleanup & Uninstallation (`fig clean`, `fig uninstall`)**:
  - Added `CleanupManager`, `fig clean` (`--releases`, `--all`, `--preview`), `fig uninstall` (`-y`, `--preserve-backups`, `--system`, `--preview`), and `scripts/uninstall.bat` / `scripts/uninstall.sh`.
- **Automated Version Synchronization (`scripts/bump_version.py`)**:
  - Added unified version propagation and consistency checking (`bump_version.py check`).

### Changed
- **Repository Hygiene**:
  - Reorganized packaging and scripts into `packaging/`, `scripts/`, and `tests/`.

---

## [0.5.0] - 2026-11-07

### Added
- **Scoped Directory Takeover in Builder REPL**:
  - Replaced inline tree expansions with scoped navigation (`cd <#|name>`, `cd ..`, `cd /`), `tree` ASCII inspection, and a segregated Excluded Items table.
- **Pathspec Macro Shorthands**:
  - Added `.config/...`, `~` / `@home/...`, `@docs/...`, `@appdata/...`, and `@localappdata/...`.
- **Standalone Binary Packaging & Scoop Support**:
  - Added PyInstaller spec (`packaging/fig.spec`), `scripts/install.py`, and Scoop manifest (`packaging/scoop/fig.json`).

### Changed
- **Lazy Backup Allocation & Linker Fallback Chain**:
  - Initialized backup sessions only when collisions or new links occur; added Windows fallback from symlink -> NTFS junction -> hardlink -> copy.

---

## [0.4.0] - 2026-11-07

### Added
- **Administrative System Mode (`--system` / `-system`)**:
  - Isolated system configuration handling (`/etc/`, systemd, Windows system files) requiring explicit destination pathspecs.
  - Added breaking-changes safety banner (`-y` to bypass), post-confirmation UAC/`sudo` elevation, and machine-wide redundancy vaults (`%ProgramData%\fig\`, `/var/backups/fig/`).

---

## [0.3.0] - 2026-11-07

### Added
- **Temporary Session Takeover (`fig temp` and `fig revert`)**:
  - Deploy personal dotfiles temporarily on a host machine and restore the exact prior state with `fig revert`.
- **Profile Management (`fig profile`)**:
  - Added named profile storage and `fig profile switch <name>`.

---

## [0.2.0] - 2026-11-07

### Added
- **Interactive Template Builder REPL (`fig build`)** and **`pathspec.txt`** localized routing.
- **Template Operations & Inspection**:
  - Added `fig view`, `fig edit`, `fig bootstrap`, `fig check`, `fig preview`, `fig undo`, and `fig history`.

---

## [0.1.0] - 2026-11-07

### Added
- **Core Engine, Platform Detection, Cross-Platform Linker, Collision Backup Vault, Audit Logging, and Declarative TOML Template Engine** implemented in pure Python 3.11+ standard library.
