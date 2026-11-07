"""Repository Layout Analyzer and Pathspec Engine for Fig.
Inspects dotfile repositories, interprets pathspec.txt files, detects nested
configurations (e.g. nvim, wezterm), handles .config mirrors and $HOME stand-ins,
and produces structured candidate mappings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from fig.core.platform import CURRENT_OS, OperatingSystem, resolve_native_path
from fig.builtins.catalog import get_platform_catalog, COMMON_PRESETS, WINDOWS_PRESETS, POSIX_PRESETS


IGNORE_DIR_NAMES = {
    ".git", ".github", ".vscode", ".idea", "__pycache__", ".fig", "node_modules"
}
IGNORE_FILE_NAMES = {
    ".gitignore", "README.md", "readme.md", "README", "LICENSE", "LICENSE.md",
    "fig.toml", ".fig.toml", "fig.template.toml", ".DS_Store"
}

# Known applications whose entire directory should be linked to config directory
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
}


@dataclass
class DiscoveredConfig:
    app_name: str
    source_rel: str
    dest_expr: str
    is_directory: bool
    is_excluded: bool = False
    detection_source: str = "auto"
    os_target: Optional[str] = None  # None = universal, "windows", "posix", "linux", "macos"

    @property
    def display_type(self) -> str:
        return "[dir]" if self.is_directory else "[file]"


def parse_pathspec_file(pathspec_file: Path) -> Dict[str, str]:
    """Parse a pathspec.txt file.
    Supports either:
      - Simple single line: ~/.local/share/app
      - Key/value pairs:
          destination = ~/.local/share/app
          windows = %APPDATA%/app
          posix = ~/.config/app
          linux = ~/.config/app
          macos = ~/Library/Application Support/app
    """
    results: Dict[str, str] = {}
    if not pathspec_file.is_file():
        return results

    try:
        lines = pathspec_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return results

    cleaned_lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    if not cleaned_lines:
        return results

    # If first line has no '=', treat whole first line as default destination
    if "=" not in cleaned_lines[0]:
        results["universal"] = cleaned_lines[0]
        return results

    for line in cleaned_lines:
        if "=" in line:
            key, val = line.split("=", 1)
            k = key.strip().lower()
            v = val.strip().strip('"').strip("'")
            if k in ("destination", "dest", "target", "default", "universal"):
                results["universal"] = v
            else:
                results[k] = v

    return results


class RepoScanner:
    """Scans dotfile repositories and discovers applications and configuration paths."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def scan(self) -> List[DiscoveredConfig]:
        """Scan repository directory tree and identify all application configs."""
        discovered: List[DiscoveredConfig] = []
        seen_sources: set[str] = set()

        if not self.repo_root.is_dir():
            return discovered

        # 1. Search for explicit pathspec.txt / .pathspec files
        for p in self.repo_root.rglob("pathspec.txt"):
            parent_dir = p.parent
            if any(part in IGNORE_DIR_NAMES for part in parent_dir.parts):
                continue
            rel_dir = parent_dir.relative_to(self.repo_root)
            specs = parse_pathspec_file(p)
            for os_key, dest in specs.items():
                target_os = None if os_key == "universal" else os_key
                discovered.append(DiscoveredConfig(
                    app_name=parent_dir.name,
                    source_rel=str(rel_dir).replace("\\", "/"),
                    dest_expr=dest,
                    is_directory=True,
                    detection_source="pathspec.txt",
                    os_target=target_os,
                ))
            seen_sources.add(str(rel_dir).replace("\\", "/"))

        # Also check .fig.pathspec
        for p in self.repo_root.rglob(".fig.pathspec"):
            parent_dir = p.parent
            if any(part in IGNORE_DIR_NAMES for part in parent_dir.parts):
                continue
            rel_dir = parent_dir.relative_to(self.repo_root)
            specs = parse_pathspec_file(p)
            for os_key, dest in specs.items():
                target_os = None if os_key == "universal" else os_key
                discovered.append(DiscoveredConfig(
                    app_name=parent_dir.name,
                    source_rel=str(rel_dir).replace("\\", "/"),
                    dest_expr=dest,
                    is_directory=True,
                    detection_source="pathspec.txt",
                    os_target=target_os,
                ))
            seen_sources.add(str(rel_dir).replace("\\", "/"))

        # 2. Check for .config / config directory mirror
        for config_cand in [self.repo_root / ".config", self.repo_root / "config"]:
            if config_cand.is_dir():
                for item in config_cand.iterdir():
                    if item.name in IGNORE_DIR_NAMES or item.name in IGNORE_FILE_NAMES:
                        continue
                    rel_path = str(item.relative_to(self.repo_root)).replace("\\", "/")
                    if rel_path in seen_sources:
                        continue

                    # If item is a directory (e.g. .config/nvim), link whole directory
                    # On Windows, link to %APPDATA%/app or ~/.config/app
                    app_name = item.name
                    win_dest = f"%APPDATA%/{app_name}" if item.is_dir() else f"~/.config/{app_name}"
                    posix_dest = f"~/.config/{app_name}"

                    if item.name in KNOWN_CONFIG_DIRS:
                        win_dest = KNOWN_CONFIG_DIRS[item.name].get("windows", win_dest)
                        posix_dest = KNOWN_CONFIG_DIRS[item.name].get("posix", posix_dest)

                    if win_dest == posix_dest:
                        discovered.append(DiscoveredConfig(
                            app_name=app_name,
                            source_rel=rel_path,
                            dest_expr=posix_dest,
                            is_directory=item.is_dir(),
                            detection_source=".config directory",
                        ))
                    else:
                        discovered.append(DiscoveredConfig(
                            app_name=app_name,
                            source_rel=rel_path,
                            dest_expr=win_dest,
                            is_directory=item.is_dir(),
                            detection_source=".config directory",
                            os_target="windows",
                        ))
                        discovered.append(DiscoveredConfig(
                            app_name=app_name,
                            source_rel=rel_path,
                            dest_expr=posix_dest,
                            is_directory=item.is_dir(),
                            detection_source=".config directory",
                            os_target="posix",
                        ))
                    seen_sources.add(rel_path)

        # 3. Check for top-level directories named after known applications (nvim, alacritty, kitty, etc.)
        for item in self.repo_root.iterdir():
            if not item.is_dir() or item.name.startswith(".") or item.name in IGNORE_DIR_NAMES:
                continue
            rel_path = str(item.relative_to(self.repo_root)).replace("\\", "/")
            if rel_path in seen_sources:
                continue

            name_lower = item.name.lower()
            if name_lower in KNOWN_CONFIG_DIRS:
                paths = KNOWN_CONFIG_DIRS[name_lower]
                win_dest = paths.get("windows", f"~/.config/{name_lower}")
                posix_dest = paths.get("posix", f"~/.config/{name_lower}")

                if win_dest == posix_dest:
                    discovered.append(DiscoveredConfig(
                        app_name=item.name,
                        source_rel=rel_path,
                        dest_expr=posix_dest,
                        is_directory=True,
                        detection_source="known config dir",
                    ))
                else:
                    discovered.append(DiscoveredConfig(
                        app_name=item.name,
                        source_rel=rel_path,
                        dest_expr=win_dest,
                        is_directory=True,
                        detection_source="known config dir",
                        os_target="windows",
                    ))
                    discovered.append(DiscoveredConfig(
                        app_name=item.name,
                        source_rel=rel_path,
                        dest_expr=posix_dest,
                        is_directory=True,
                        detection_source="known config dir",
                        os_target="posix",
                    ))
                seen_sources.add(rel_path)

            # Check for stow-style folders (e.g. git/.gitconfig, zsh/.zshrc, tmux/.tmux.conf)
            elif (item / ".gitconfig").exists():
                discovered.append(DiscoveredConfig(
                    app_name="git",
                    source_rel=f"{rel_path}/.gitconfig",
                    dest_expr="~/.gitconfig",
                    is_directory=False,
                    detection_source="stow style",
                ))
                seen_sources.add(rel_path)
            elif (item / ".zshrc").exists():
                discovered.append(DiscoveredConfig(
                    app_name="zsh",
                    source_rel=f"{rel_path}/.zshrc",
                    dest_expr="~/.zshrc",
                    is_directory=False,
                    detection_source="stow style",
                    os_target="posix",
                ))
                seen_sources.add(rel_path)
            elif (item / ".tmux.conf").exists() or (item / "tmux.conf").exists():
                tmux_file = ".tmux.conf" if (item / ".tmux.conf").exists() else "tmux.conf"
                discovered.append(DiscoveredConfig(
                    app_name="tmux",
                    source_rel=f"{rel_path}/{tmux_file}",
                    dest_expr="~/.tmux.conf",
                    is_directory=False,
                    detection_source="stow style",
                ))
                seen_sources.add(rel_path)
            elif (item / "profile.ps1").exists() or (item / "Microsoft.PowerShell_profile.ps1").exists():
                ps_file = "profile.ps1" if (item / "profile.ps1").exists() else "Microsoft.PowerShell_profile.ps1"
                discovered.append(DiscoveredConfig(
                    app_name="powershell",
                    source_rel=f"{rel_path}/{ps_file}",
                    dest_expr="~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1",
                    is_directory=False,
                    detection_source="powershell profile",
                    os_target="windows",
                ))
                discovered.append(DiscoveredConfig(
                    app_name="powershell",
                    source_rel=f"{rel_path}/{ps_file}",
                    dest_expr="~/.config/powershell/Microsoft.PowerShell_profile.ps1",
                    is_directory=False,
                    detection_source="powershell profile",
                    os_target="posix",
                ))
                seen_sources.add(rel_path)
            elif (item / "init.lua").exists() or (item / "init.vim").exists():
                # Generic neovim / vim directory
                discovered.append(DiscoveredConfig(
                    app_name=item.name,
                    source_rel=rel_path,
                    dest_expr="%LOCALAPPDATA%/nvim",
                    is_directory=True,
                    detection_source="nvim init file",
                    os_target="windows",
                ))
                discovered.append(DiscoveredConfig(
                    app_name=item.name,
                    source_rel=rel_path,
                    dest_expr="~/.config/nvim",
                    is_directory=True,
                    detection_source="nvim init file",
                    os_target="posix",
                ))
                seen_sources.add(rel_path)
            else:
                # Any other directory in repo defaults to ~/.config/<name>
                discovered.append(DiscoveredConfig(
                    app_name=item.name,
                    source_rel=rel_path,
                    dest_expr=f"~/.config/{item.name}",
                    is_directory=True,
                    detection_source="directory convention",
                ))
                seen_sources.add(rel_path)

        # 4. Check for top-level individual dotfiles and config files
        for item in self.repo_root.iterdir():
            if item.is_dir() or item.name in IGNORE_FILE_NAMES:
                continue
            rel_path = item.name
            if rel_path in seen_sources:
                continue

            name = item.name
            if name == ".gitconfig" or name == "gitconfig":
                discovered.append(DiscoveredConfig(
                    app_name="git",
                    source_rel=rel_path,
                    dest_expr="~/.gitconfig",
                    is_directory=False,
                    detection_source="home dotfile",
                ))
            elif name in (".zshrc", "zshrc"):
                discovered.append(DiscoveredConfig(
                    app_name="zsh",
                    source_rel=rel_path,
                    dest_expr="~/.zshrc",
                    is_directory=False,
                    detection_source="home dotfile",
                    os_target="posix",
                ))
            elif name in (".bashrc", "bashrc"):
                discovered.append(DiscoveredConfig(
                    app_name="bash",
                    source_rel=rel_path,
                    dest_expr="~/.bashrc",
                    is_directory=False,
                    detection_source="home dotfile",
                    os_target="posix",
                ))
            elif name in (".tmux.conf", "tmux.conf"):
                discovered.append(DiscoveredConfig(
                    app_name="tmux",
                    source_rel=rel_path,
                    dest_expr="~/.tmux.conf",
                    is_directory=False,
                    detection_source="home dotfile",
                ))
            elif name in (".vimrc", "vimrc"):
                discovered.append(DiscoveredConfig(
                    app_name="vim",
                    source_rel=rel_path,
                    dest_expr="~/.vimrc",
                    is_directory=False,
                    detection_source="home dotfile",
                ))
            elif name == "starship.toml":
                discovered.append(DiscoveredConfig(
                    app_name="starship",
                    source_rel=rel_path,
                    dest_expr="~/.config/starship.toml",
                    is_directory=False,
                    detection_source="starship config",
                ))
            elif name in ("wezterm.lua", ".wezterm.lua"):
                discovered.append(DiscoveredConfig(
                    app_name="wezterm",
                    source_rel=rel_path,
                    dest_expr="~/.config/wezterm/wezterm.lua",
                    is_directory=False,
                    detection_source="wezterm config",
                ))
            elif name.startswith("."):
                # Generic home dotfile (e.g. .inputrc, .editorconfig)
                discovered.append(DiscoveredConfig(
                    app_name=name.lstrip("."),
                    source_rel=rel_path,
                    dest_expr=f"~/{name}",
                    is_directory=False,
                    detection_source="home dotfile",
                ))
            else:
                # Top-level non-hidden file
                discovered.append(DiscoveredConfig(
                    app_name=Path(name).stem,
                    source_rel=rel_path,
                    dest_expr=f"~/{name}",
                    is_directory=False,
                    detection_source="unspecified",
                ))

        return discovered
