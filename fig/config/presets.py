"""Built-in Presets Catalog for Common Tools and Applications.
Provides standard default destination paths separated by operating system,
allowing dotfiles to automatically route to the right destination on Windows, Linux, and macOS.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional
from fig.config.platform import CURRENT_OS, OperatingSystem


# Common presets shared across all platforms
COMMON_PRESETS: Dict[str, Dict[str, str]] = {
    "git": {
        ".gitconfig": "~/.gitconfig",
        "gitconfig": "~/.gitconfig",
        "git/config": "~/.config/git/config",
        "git/ignore": "~/.config/git/ignore",
    },
    "ssh": {
        "ssh/config": "~/.ssh/config",
        "ssh_config": "~/.ssh/config",
        ".ssh/config": "~/.ssh/config",
    },
    "starship": {
        "starship.toml": "~/.config/starship.toml",
        ".config/starship.toml": "~/.config/starship.toml",
    },
    "tmux": {
        ".tmux.conf": "~/.tmux.conf",
        "tmux.conf": "~/.tmux.conf",
        "tmux/tmux.conf": "~/.config/tmux/tmux.conf",
    },
    "vim": {
        ".vimrc": "~/.vimrc",
        "vimrc": "~/.vimrc",
        ".vim": "~/.vim",
    },
    "helix": {
        "helix": "~/.config/helix",
        "helix/config.toml": "~/.config/helix/config.toml",
    },
}

# Windows-specific presets
WINDOWS_PRESETS: Dict[str, Dict[str, str]] = {
    "powershell": {
        "powershell/profile.ps1": "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1",
        "profile.ps1": "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1",
        "Microsoft.PowerShell_profile.ps1": "~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1",
    },
    "neovim": {
        "nvim": "%LOCALAPPDATA%/nvim",
        "neovim": "%LOCALAPPDATA%/nvim",
    },
    "alacritty": {
        "alacritty.toml": "%APPDATA%/alacritty/alacritty.toml",
        "alacritty": "%APPDATA%/alacritty",
    },
    "wezterm": {
        "wezterm.lua": "~/.config/wezterm/wezterm.lua",
        ".wezterm.lua": "~/.wezterm.lua",
        "wezterm_win.lua": "~/.config/wezterm/wezterm.lua",
    },
    "windows-terminal": {
        "wt/settings.json": "%LOCALAPPDATA%/Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json",
        "settings.json": "%LOCALAPPDATA%/Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json",
    },
}

# POSIX (Linux and macOS) presets
POSIX_PRESETS: Dict[str, Dict[str, str]] = {
    "bash": {
        ".bashrc": "~/.bashrc",
        "bashrc": "~/.bashrc",
        ".bash_profile": "~/.bash_profile",
    },
    "zsh": {
        ".zshrc": "~/.zshrc",
        "zshrc": "~/.zshrc",
        ".zshenv": "~/.zshenv",
        ".zprofile": "~/.zprofile",
    },
    "fish": {
        "fish": "~/.config/fish",
        "config.fish": "~/.config/fish/config.fish",
    },
    "powershell": {
        "powershell/profile.ps1": "~/.config/powershell/Microsoft.PowerShell_profile.ps1",
        "profile.ps1": "~/.config/powershell/Microsoft.PowerShell_profile.ps1",
    },
    "neovim": {
        "nvim": "~/.config/nvim",
        ".config/nvim": "~/.config/nvim",
    },
    "alacritty": {
        "alacritty.toml": "~/.config/alacritty/alacritty.toml",
        "alacritty": "~/.config/alacritty",
    },
    "kitty": {
        "kitty": "~/.config/kitty",
        "kitty.conf": "~/.config/kitty/kitty.conf",
    },
    "wezterm": {
        "wezterm.lua": "~/.config/wezterm/wezterm.lua",
        ".wezterm.lua": "~/.wezterm.lua",
        "wezterm_linux.lua": "~/.config/wezterm/wezterm.lua",
    },
    "ghostty": {
        "ghostty": "~/.config/ghostty",
    },
}


def get_platform_catalog(os_type: Optional[OperatingSystem] = None) -> Dict[str, Dict[str, str]]:
    """Return merged preset catalog for requested or current OS."""
    target_os = os_type or CURRENT_OS
    catalog = {k: v.copy() for k, v in COMMON_PRESETS.items()}

    if target_os == OperatingSystem.WINDOWS:
        for app, entries in WINDOWS_PRESETS.items():
            if app in catalog:
                catalog[app].update(entries)
            else:
                catalog[app] = entries.copy()
    else:
        for app, entries in POSIX_PRESETS.items():
            if app in catalog:
                catalog[app].update(entries)
            else:
                catalog[app] = entries.copy()

    return catalog


# Default export pointing to active OS catalog
PRESET_CATALOG = get_platform_catalog()


def get_available_presets(os_type: Optional[OperatingSystem] = None) -> List[str]:
    """Return sorted list of supported preset names for the OS."""
    return sorted(get_platform_catalog(os_type).keys())


def resolve_preset_mappings(
    preset_names: List[str],
    os_type: Optional[OperatingSystem] = None,
) -> Dict[str, str]:
    """Return dictionary of relative-source to destination for requested presets on target OS."""
    catalog = get_platform_catalog(os_type)
    mappings: Dict[str, str] = {}
    for name in preset_names:
        key = name.lower()
        if key in catalog:
            mappings.update(catalog[key])
    return mappings
