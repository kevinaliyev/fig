"""Repository Layout Analyzer and Pathspec Engine for Fig.
Inspects dotfile repositories, interprets pathspec.txt files, detects nested
configurations (e.g. nvim, wezterm), handles .config mirrors and $HOME stand-ins,
and produces structured candidate mappings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig.config.platform import CURRENT_OS, OperatingSystem, resolve_native_path
from fig.sync.linker import is_symlink_or_junction


IGNORE_DIR_NAMES = {
    ".git", ".github", ".vscode", ".idea", "__pycache__", ".fig", "node_modules"
}
IGNORE_FILE_NAMES = {
    ".gitignore", "README.md", "readme.md", "README", "LICENSE", "LICENSE.md",
    "fig.toml", ".fig.toml", "fig.template.toml", ".DS_Store"
}

KNOWN_CONFIG_DIRS = {
    "nvim": {"posix": "~/.config/nvim", "windows": "%LOCALAPPDATA%/nvim"},
    "neovim": {"posix": "~/.config/nvim", "windows": "%LOCALAPPDATA%/nvim"},
    "alacritty": {"posix": "~/.config/alacritty", "windows": "%APPDATA%/alacritty"},
    "kitty": {"posix": "~/.config/kitty", "windows": "%APPDATA%/kitty"},
    "wezterm": {"posix": "~/.config/wezterm", "windows": "~/.config/wezterm"},
    "fish": {"posix": "~/.config/fish", "windows": "~/.config/fish"},
    "helix": {"posix": "~/.config/helix", "windows": "%APPDATA%/helix"},
    "ghostty": {"posix": "~/.config/ghostty", "windows": "%APPDATA%/ghostty"},
    "tmux": {"posix": "~/.config/tmux", "windows": "~/.config/tmux"},
    "starship": {"posix": "~/.config", "windows": "~/.config"},
    "powershell": {
        "windows": "~/Documents/PowerShell",
        "posix": "~/.config/powershell",
    },
    "pwsh": {
        "windows": "~/Documents/PowerShell",
        "posix": "~/.config/powershell",
    },
    "karabiner": {"posix": "~/.config/karabiner", "windows": "~/.config/karabiner"},
    "qbittorrent": {"posix": "~/.config/qbittorrent", "windows": "%APPDATA%/qBittorrent"},
    "zsh": {"posix": "~/.config/zsh", "windows": "~/.config/zsh"},
}


@dataclass
class DiscoveredConfig:
    app_name: str
    source_rel: str                     # e.g. "wezterm", "pwsh/CurrentUserAllHosts/profile.ps1", ".gitconfig"
    dest_expr: str                      # e.g. "~/.config/wezterm", "~/Documents/PowerShell/profile.ps1", "~/.gitconfig"
    is_directory: bool
    is_excluded: bool = False
    is_system: bool = False
    detection_source: str = "auto"
    os_target: Optional[str] = None     # None = universal, "windows", "posix", etc.
    link_mode: Optional[str] = None     # None = inherit default, "symlink", "junction", "hardlink", "copy", "auto"

    # Hierarchy & Tree Properties
    child_count: int = 0                # Total files in subtree
    is_expandable: bool = False         # True if directory has children
    is_expanded: bool = False           # True if expanded in builder review table
    depth: int = 0                      # 0 = top-level package or root file, 1 = direct child, 2 = grandchild...
    parent_source_rel: Optional[str] = None
    children: List[DiscoveredConfig] = field(default_factory=list)
    customized: bool = False            # True if destination edited or child toggled
    link_as_dir: bool = True            # True = link whole directory atomically. False = container folder, link leaf files individually.

    @property
    def display_type(self) -> str:
        if self.is_directory:
            if self.is_expanded:
                return "[dir-]"
            if self.is_expandable:
                return "[dir+]"
            return "[dir] "
        return "[file]"


def is_system_path(dest_expr: str) -> bool:
    """Check if destination expression targets root/system directories."""
    clean = dest_expr.strip().replace("\\", "/").lower()
    if clean.startswith(("/etc/", "/usr/", "/var/", "/opt/")):
        return True
    if clean.startswith(("c:/windows", "c:/program files", "c:/programdata", "%programdata%", "%systemroot%")):
        return True
    return False


def parse_pathspec_file(pathspec_file: Path) -> Tuple[Dict[str, str], bool, Dict[str, Any]]:
    """Parse a pathspec.txt file.
    Supports:
      destination = ~/.local/share/app
      windows = %APPDATA%/app
      posix = ~/.local/share/app
      link_mode = symlink | hardlink | junction | copy
      type = dir | file
      scope = system | user
    Returns (targets_dict, is_system_scope, metadata_dict).
    """
    results: Dict[str, str] = {}
    metadata: Dict[str, Any] = {}
    is_system = False
    if not pathspec_file.is_file():
        return results, is_system, metadata

    try:
        lines = pathspec_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return results, is_system, metadata

    cleaned_lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    if not cleaned_lines:
        return results, is_system, metadata

    for line in cleaned_lines:
        if "=" in line:
            key, val = line.split("=", 1)
            k = key.strip().lower()
            v = val.strip().strip('"').strip("'")
            if k == "scope":
                if v.lower() == "system":
                    is_system = True
                metadata["scope"] = v.lower()
            elif k in ("link_mode", "mode"):
                metadata["link_mode"] = v.lower()
            elif k in ("type", "kind"):
                metadata["type"] = v.lower()
                metadata["is_directory"] = v.lower() in ("dir", "directory", "tree")
            elif k in ("destination", "dest", "target", "default", "universal"):
                results["universal"] = v
                if is_system_path(v):
                    is_system = True
            else:
                results[k] = v
                if is_system_path(v):
                    is_system = True
        else:
            # First line without '='
            results["universal"] = line
            if is_system_path(line):
                is_system = True

    return results, is_system, metadata


class RepoScanner:
    """Scans dotfile repositories and discovers applications and configuration paths."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def scan(self, scan_system: bool = False) -> List[DiscoveredConfig]:
        """Scan repository directory tree.
        If scan_system is False (default): ONLY returns user configs. System configs are skipped!
        If scan_system is True: returns ONLY system-scoped configs with explicit pathspecs.

        Core Philosophy:
          - If a file is alone in /dotfiles/ (or root): defaults to ~/ or $HOME.
          - If a directory is in /dotfiles/: defaults to ~/.config/<dirname> (recursive package link).
          - Each item inside directories is scanned as children and can be expanded in the builder.
        """
        discovered: List[DiscoveredConfig] = []
        if not self.repo_root.is_dir():
            return discovered

        # 1. Search for explicit pathspec.txt / .fig.pathspec files
        explicit_pathspecs: Dict[str, Tuple[str, bool, bool]] = {} # rel_dir -> (dest_expr, is_system, is_dir)
        for root, dirs, files in os.walk(self.repo_root, followlinks=False):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIR_NAMES and not is_symlink_or_junction(Path(root) / d)]
            for p_name in ("pathspec.txt", ".fig.pathspec"):
                if p_name in files:
                    p = Path(root) / p_name
                    parent_dir = p.parent
                    rel_dir = str(parent_dir.relative_to(self.repo_root)).replace("\\", "/")
                    specs, item_is_sys, meta = parse_pathspec_file(p)

                    host_dest = None
                    if CURRENT_OS == OperatingSystem.WINDOWS:
                        host_dest = specs.get("windows") or specs.get("universal")
                    elif CURRENT_OS in (OperatingSystem.LINUX, OperatingSystem.MACOS):
                        host_dest = (
                            specs.get(CURRENT_OS.value)
                            or specs.get("posix")
                            or specs.get("universal")
                        )
                    if not host_dest and "universal" in specs:
                        host_dest = specs["universal"]

                    if host_dest:
                        is_dir = meta.get("is_directory", True)
                        explicit_pathspecs[rel_dir] = (host_dest, item_is_sys, is_dir)

        # Handle system scan mode
        if scan_system:
            for rel_dir, (dest_expr, item_is_sys, is_dir) in explicit_pathspecs.items():
                if item_is_sys:
                    parent_name = Path(rel_dir).name
                    discovered.append(DiscoveredConfig(
                        app_name=parent_name,
                        source_rel=rel_dir,
                        dest_expr=dest_expr,
                        is_directory=is_dir,
                        is_system=True,
                        detection_source="pathspec.txt",
                    ))
            return discovered

        # 2. Standalone files in repo_root (alone in /dotfiles/) -> default to ~/ ($HOME)
        for f in sorted(self.repo_root.iterdir()):
            if not f.is_file():
                continue
            if f.name in IGNORE_FILE_NAMES or f.name in IGNORE_DIR_NAMES:
                continue
            if f.name in (".git", ".DS_Store"):
                continue

            app = f.stem.lstrip(".") or f.name.lstrip(".")
            discovered.append(DiscoveredConfig(
                app_name=app,
                source_rel=f.name,
                dest_expr=f"~/{f.name}",
                is_directory=False,
                detection_source="root file ($HOME)",
            ))

        # 3. Top-level directories in repo_root
        seen_dirs: set[str] = set()
        for app_dir in sorted(self.repo_root.iterdir()):
            if not app_dir.is_dir() or app_dir.name in IGNORE_DIR_NAMES:
                continue
            if app_dir.name.startswith(".") and app_dir.name not in (".config", "config"):
                continue

            app_name = app_dir.name
            rel_dir = str(app_dir.relative_to(self.repo_root)).replace("\\", "/")
            if rel_dir in seen_dirs:
                continue

            # Special case: standalone .config / config directory mirror
            if app_name in (".config", "config"):
                for sub in sorted(app_dir.iterdir()):
                    if sub.name in IGNORE_DIR_NAMES or sub.name in IGNORE_FILE_NAMES:
                        continue
                    sub_rel = str(sub.relative_to(self.repo_root)).replace("\\", "/")
                    sub_dest = f"~/.config/{sub.name}"
                    if sub.is_file():
                        discovered.append(DiscoveredConfig(
                            app_name=sub.stem.lstrip(".") or sub.name,
                            source_rel=sub_rel,
                            dest_expr=sub_dest,
                            is_directory=False,
                            detection_source=".config mirror file",
                        ))
                    elif sub.is_dir():
                        sub_children, sub_file_count = self._scan_children(sub, parent_dest=sub_dest, depth=1)
                        discovered.append(DiscoveredConfig(
                            app_name=sub.name,
                            source_rel=sub_rel,
                            dest_expr=sub_dest,
                            is_directory=True,
                            child_count=sub_file_count,
                            is_expandable=sub_file_count > 0,
                            is_expanded=False,
                            depth=0,
                            children=sub_children,
                            detection_source=".config mirror directory",
                        ))
                seen_dirs.add(rel_dir)
                continue

            # Check if this app has an explicit pathspec
            pathspec_entry = explicit_pathspecs.get(rel_dir)
            if pathspec_entry and not pathspec_entry[1]:  # User-scoped pathspec
                dest_expr = pathspec_entry[0]
                is_dir = pathspec_entry[2]
                scan_target = app_dir
                source_rel = rel_dir
                detection_src = "pathspec.txt"
            else:
                source_rel = rel_dir
                scan_target = app_dir
                dest_expr = f"~/.config/{app_name}"
                detection_src = "directory package"
                is_dir = True

            # Recursively scan children of scan_target
            children, total_files = self._scan_children(scan_target, parent_dest=dest_expr, depth=1)

            discovered.append(DiscoveredConfig(
                app_name=app_name,
                source_rel=source_rel,
                dest_expr=dest_expr,
                is_directory=is_dir,
                child_count=total_files,
                is_expandable=total_files > 0,
                is_expanded=False,
                depth=0,
                children=children,
                detection_source=detection_src,
            ))
            seen_dirs.add(rel_dir)

        return discovered

    def _scan_children(
        self,
        current_dir: Path,
        parent_dest: str,
        depth: int,
    ) -> Tuple[List[DiscoveredConfig], int]:
        """Recursively scan child files and subdirectories."""
        children: List[DiscoveredConfig] = []
        total_files = 0
        try:
            entries = sorted(current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return children, 0

        for entry in entries:
            if entry.name in IGNORE_DIR_NAMES or entry.name in IGNORE_FILE_NAMES:
                continue

            rel_path = str(entry.relative_to(self.repo_root)).replace("\\", "/")
            app_name = entry.stem.lstrip(".") or entry.name

            if entry.is_file():
                total_files += 1
                child_dest = self._get_default_child_dest(entry, parent_dest)
                children.append(DiscoveredConfig(
                    app_name=app_name,
                    source_rel=rel_path,
                    dest_expr=child_dest,
                    is_directory=False,
                    depth=depth,
                    parent_source_rel=str(current_dir.relative_to(self.repo_root)).replace("\\", "/"),
                ))
            elif entry.is_dir():
                sub_children, sub_file_count = self._scan_children(
                    entry, parent_dest=f"{parent_dest}/{entry.name}", depth=depth + 1
                )
                total_files += sub_file_count
                children.append(DiscoveredConfig(
                    app_name=app_name,
                    source_rel=rel_path,
                    dest_expr=f"{parent_dest}/{entry.name}",
                    is_directory=True,
                    child_count=sub_file_count,
                    is_expandable=sub_file_count > 0,
                    is_expanded=False,
                    depth=depth,
                    parent_source_rel=str(current_dir.relative_to(self.repo_root)).replace("\\", "/"),
                    children=sub_children,
                    link_as_dir=False,  # Subdirectories default to folder containers, not whole directory links
                ))

        return children, total_files

    def _get_default_child_dest(self, entry: Path, parent_dest: str) -> str:
        """Provide natural default destination for common configuration files."""
        name_lower = entry.name.lower()
        parent_lower = parent_dest.lower()
        entry_str_lower = str(entry).replace("\\", "/").lower()

        # PowerShell profile and script handling
        if "powershell" in parent_lower or "pwsh" in parent_lower or "powershell" in entry_str_lower:
            base_ps = "~/Documents/PowerShell" if CURRENT_OS == OperatingSystem.WINDOWS else "~/.config/powershell"
            if name_lower in ("profile.ps1", "microsoft.powershell_profile.ps1"):
                if "currenthost" in entry_str_lower or name_lower.startswith("microsoft."):
                    return f"{base_ps}/Microsoft.PowerShell_profile.ps1"
                return f"{base_ps}/profile.ps1"

            # Profile scope folders (e.g. CurrentUserAllHosts) should not nest inside destination
            parts = Path(str(entry)).parts
            if any(p.lower() in ("currentuserallhosts", "currentusercurrenthost", "allusersallhosts", "alluserscurrenthost") for p in parts):
                return f"{base_ps}/{entry.name}"

        if CURRENT_OS == OperatingSystem.WINDOWS:
            if name_lower in ("profile.ps1", "microsoft.powershell_profile.ps1"):
                return "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
        if name_lower in (".gitconfig", "gitconfig"):
            return "~/.gitconfig"
        if name_lower in (".tmux.conf", "tmux.conf"):
            return "~/.tmux.conf"
        return f"{parent_dest}/{entry.name}"
