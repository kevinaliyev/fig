"""Built-in Presets Catalog for Common Tools and Applications.
Provides standard default destination paths so users can configure dotfiles
with minimal boilerplate.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional


def is_windows() -> bool:
    return sys.platform.startswith("win")


# Preset definitions: mapping from preset name to relative source candidate patterns
# and their target path expression.
PRESET_CATALOG: Dict[str, Dict[str, str]] = {
    "git": {
        ".gitconfig": "~/.gitconfig",
        "gitconfig": "~/.gitconfig",
        "git/config": "~/.config/git/config",
        "git/ignore": "~/.config/git/ignore",
    },
    "zsh": {
        ".zshrc": "~/.zshrc",
        "zshrc": "~/.zshrc",
        ".zshenv": "~/.zshenv",
        ".zprofile": "~/.zprofile",
    },
    "bash": {
        ".bashrc": "~/.bashrc",
        "bashrc": "~/.bashrc",
        ".bash_profile": "~/.bash_profile",
    },
    "tmux": {
        ".tmux.conf": "~/.tmux.conf",
        "tmux.conf": "~/.tmux.conf",
        "tmux/tmux.conf": "~/.config/tmux/tmux.conf",
    },
    "neovim": {
        "nvim": "~/.config/nvim" if not is_windows() else "%LOCALAPPDATA%/nvim",
        ".config/nvim": "~/.config/nvim" if not is_windows() else "%LOCALAPPDATA%/nvim",
    },
    "vim": {
        ".vimrc": "~/.vimrc",
        "vimrc": "~/.vimrc",
        ".vim": "~/.vim",
    },
    "alacritty": {
        "alacritty.toml": "~/.config/alacritty/alacritty.toml" if not is_windows() else "%APPDATA%/alacritty/alacritty.toml",
        "alacritty.yml": "~/.config/alacritty/alacritty.yml" if not is_windows() else "%APPDATA%/alacritty/alacritty.yml",
        "alacritty": "~/.config/alacritty" if not is_windows() else "%APPDATA%/alacritty",
    },
    "kitty": {
        "kitty": "~/.config/kitty",
        "kitty.conf": "~/.config/kitty/kitty.conf",
    },
    "starship": {
        "starship.toml": "~/.config/starship.toml",
        ".config/starship.toml": "~/.config/starship.toml",
    },
    "fish": {
        "fish": "~/.config/fish",
        "config.fish": "~/.config/fish/config.fish",
    },
    "ssh": {
        "ssh/config": "~/.ssh/config",
        "ssh_config": "~/.ssh/config",
    },
    "wezterm": {
        "wezterm.lua": "~/.config/wezterm/wezterm.lua",
        ".wezterm.lua": "~/.wezterm.lua",
    },
    "helix": {
        "helix": "~/.config/helix",
    },
    "ghostty": {
        "ghostty": "~/.config/ghostty",
    },
}


def get_available_presets() -> List[str]:
    """Return sorted list of supported preset names."""
    return sorted(PRESET_CATALOG.keys())


def resolve_preset_mappings(preset_names: List[str]) -> Dict[str, str]:
    """Return dictionary of relative-source to destination for requested presets."""
    mappings: Dict[str, str] = {}
    for name in preset_names:
        key = name.lower()
        if key in PRESET_CATALOG:
            mappings.update(PRESET_CATALOG[key])
    return mappings
