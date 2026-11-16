"""Fig Cleanup & Uninstallation Subsystem.
Provides programmatic and CLI routines for:
  1. Purging active template links (restoring original backups).
  2. Cleaning user-level state (~/.fig, ~/.config/fig: logs, backups, profiles).
  3. Purging elevated system redundancy vaults (%ProgramData%/fig or /var/backups/fig).
  4. Uninstalling the Fig binary from %USERPROFILE%/.local/bin and cleaning PATH.
  5. Pruning repository build artifacts (build/, dist/, __pycache__) and obsolete releases.
"""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig import __version__
from fig.config.platform import CURRENT_OS, OperatingSystem
from fig.config.state import FigState, get_fig_home, get_system_fig_root
from fig.utils.elevation import is_elevated
from fig.sync.engine import FigEngine
from fig.sync.linker import remove_link_or_entry, is_symlink_or_junction
from fig.ui.ansi import (
    render_banner,
    badge_ok,
    badge_conflict,
    c_bold,
    c_cyan,
    c_yellow,
    c_red,
    c_dim,
    c_green,
)


class CleanupManager:
    """Orchestrates system uninstallation, state purging, and repository maintenance."""

    def __init__(self, fig_state: Optional[FigState] = None):
        self.state = fig_state or FigState()

    # =========================================================================
    # 1. Repository Artifacts & Release Pruning
    # =========================================================================

    def clean_repo_artifacts(
        self,
        repo_root: Optional[Path] = None,
        clean_releases: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, List[str]]:
        """Clean temporary build directories, python caches, and obsolete releases in repo."""
        root = repo_root or Path.cwd().resolve()
        results: Dict[str, List[str]] = {
            "clutter": [],
            "build": [],
            "caches": [],
            "releases": [],
        }

        # 1. Root clutter / test artifacts
        root_clutter = [
            root / "fig.toml",
            root / ".fig.toml",
            root / "fig.spec",      # should be in packaging/
            root / "CHANGELOG.md",  # should be in docs/
        ]
        for f in root_clutter:
            if f.exists():
                results["clutter"].append(str(f.name))
                if not dry_run:
                    self._safe_remove(f)

        # 2. Build directories
        build_dirs = [
            root / "build",
            root / "dist",
            root / ".pytest_cache",
        ]
        for d in build_dirs:
            if d.exists():
                results["build"].append(str(d.name))
                if not dry_run:
                    self._safe_remove(d)

        for egg in root.glob("*.egg-info"):
            results["build"].append(str(egg.name))
            if not dry_run:
                self._safe_remove(egg)

        # 3. Python bytecode caches
        for dirpath, dirnames, filenames in os.walk(root):
            if ".git" in dirpath:
                continue
            for d in dirnames:
                if d == "__pycache__":
                    p = Path(dirpath) / d
                    results["caches"].append(str(p.relative_to(root)))
                    if not dry_run:
                        self._safe_remove(p)
            for f in filenames:
                if f.endswith((".pyc", ".pyo")):
                    p = Path(dirpath) / f
                    results["caches"].append(str(p.relative_to(root)))
                    if not dry_run:
                        self._safe_remove(p)

        # 4. Obsolete version releases in releases/
        if clean_releases:
            releases_dir = root / "releases"
            current_prefix = f"fig-v{__version__}"
            if releases_dir.exists():
                for item in releases_dir.iterdir():
                    if item.name.startswith(current_prefix):
                        continue
                    if item.name.startswith("fig-v") or item.name.startswith("fig-0."):
                        results["releases"].append(str(item.name))
                        if not dry_run:
                            self._safe_remove(item)

        return results

    # =========================================================================
    # 2. Deployed Symlink / Junction Purging
    # =========================================================================

    def purge_active_links(self, dry_run: bool = False) -> Tuple[List[str], List[str]]:
        """Revert and purge all active deployed links created by Fig, restoring originals."""
        engine = FigEngine(self.state)
        try:
            return engine.restore_backup()
        except Exception:
            return [], []

    # =========================================================================
    # 3. User State Purging (~/.fig and ~/.config/fig)
    # =========================================================================

    def purge_user_state(
        self,
        preserve_backups: bool = False,
        dry_run: bool = False,
    ) -> List[str]:
        """Purge ~/.fig and ~/.config/fig state directories."""
        purged: List[str] = []
        fig_home = get_fig_home()
        dot_fig = (Path.home() / ".fig").resolve()

        targets = set()
        if fig_home.exists():
            targets.add(fig_home)
        if dot_fig.exists():
            targets.add(dot_fig)

        for target in targets:
            if preserve_backups:
                # Remove everything inside target except backups/
                for item in target.iterdir():
                    if item.name == "backups":
                        continue
                    purged.append(str(item))
                    if not dry_run:
                        self._safe_remove(item)
            else:
                purged.append(str(target))
                if not dry_run:
                    self._safe_remove(target)

        return purged

    # =========================================================================
    # 4. System Redundancy Vault Purging (Elevated)
    # =========================================================================

    def purge_system_state(self, dry_run: bool = False) -> List[str]:
        """Purge system-level disaster redundancy vaults if elevated."""
        purged: List[str] = []
        system_root = get_system_fig_root()
        if system_root.exists():
            purged.append(str(system_root))
            if not dry_run:
                self._safe_remove(system_root)
        return purged

    # =========================================================================
    # 5. Binary & PATH Uninstallation
    # =========================================================================

    def uninstall_binary(self, dry_run: bool = False) -> Tuple[bool, str]:
        """Delete fig binary from user PATH directory and clean environment."""
        local_bin_dir = Path.home() / ".local" / "bin"
        binary_names = ["fig.exe", "fig"]

        removed_any = False
        msgs: List[str] = []

        for name in binary_names:
            target_bin = local_bin_dir / name
            if target_bin.exists():
                if dry_run:
                    msgs.append(f"[WOULD REMOVE] {target_bin}")
                else:
                    try:
                        target_bin.unlink(missing_ok=True)
                        removed_any = True
                        msgs.append(f"Removed binary at {target_bin}")
                    except Exception as e:
                        msgs.append(f"Failed to remove {target_bin}: {e}")

        # Clean Windows PATH if on Windows
        if CURRENT_OS == OperatingSystem.WINDOWS and not dry_run:
            try:
                cmd = (
                    f"$bin = [System.IO.Path]::Combine($env:USERPROFILE, '.local', 'bin'); "
                    f"$userPath = [Environment]::GetEnvironmentVariable('Path', 'User'); "
                    f"if ($userPath -like ('*' + $bin + '*')) {{ "
                    f"    $newPath = ($userPath.Split(';') | Where-Object {{ $_ -ne $bin }}) -join ';'; "
                    f"    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); "
                    f"}}"
                )
                subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=10)
                msgs.append("Cleaned user PATH environment variable.")
            except Exception:
                pass

        return removed_any, "\n".join(msgs)

    # =========================================================================
    # 6. Complete Uninstallation Orchestrator
    # =========================================================================

    def full_uninstall(
        self,
        preserve_backups: bool = False,
        clean_system: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Perform a complete, structured uninstallation of Fig from the workstation."""
        summary: Dict[str, Any] = {}

        # 1. Rollback deployed links
        restored, removed_links = self.purge_active_links(dry_run=dry_run)
        summary["restored_files"] = restored
        summary["removed_links"] = removed_links

        # 2. Purge user state
        purged_user = self.purge_user_state(preserve_backups=preserve_backups, dry_run=dry_run)
        summary["purged_user_state"] = purged_user

        # 3. Purge system state (if requested and elevated)
        purged_sys: List[str] = []
        if clean_system and is_elevated():
            purged_sys = self.purge_system_state(dry_run=dry_run)
        summary["purged_system_state"] = purged_sys

        # 4. Uninstall binary
        uninstalled, bin_msg = self.uninstall_binary(dry_run=dry_run)
        summary["binary_removed"] = uninstalled
        summary["binary_log"] = bin_msg

        return summary

    # =========================================================================
    # Helpers
    # =========================================================================

    def _safe_remove(self, path: Path) -> bool:
        try:
            if is_symlink_or_junction(path):
                remove_link_or_entry(path)
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            return True
        except Exception:
            return False
