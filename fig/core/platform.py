"""Platform & Operating System Abstraction Layer for Fig.
Detects OS immediately at startup and provides native path resolution,
environment variable translation, and filesystem conventions.
"""

from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class OperatingSystem(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    BSD = "bsd"
    UNKNOWN = "unknown"


def detect_os() -> OperatingSystem:
    """Detect current operating system immediately."""
    plat = sys.platform.lower()
    if plat.startswith("win"):
        return OperatingSystem.WINDOWS
    elif plat.startswith("darwin"):
        return OperatingSystem.MACOS
    elif plat.startswith("linux"):
        return OperatingSystem.LINUX
    elif "bsd" in plat:
        return OperatingSystem.BSD
    return OperatingSystem.UNKNOWN


# Cached OS detection constant evaluated once at module load
CURRENT_OS: OperatingSystem = detect_os()


def get_os_aliases(os_type: Optional[OperatingSystem] = None) -> list[str]:
    """Return recognized aliases for the OS (e.g. macos -> ['macos', 'darwin', 'osx'])."""
    target = os_type or CURRENT_OS
    if target == OperatingSystem.WINDOWS:
        return ["windows", "win", "win32"]
    elif target == OperatingSystem.MACOS:
        return ["macos", "darwin", "osx", "mac"]
    elif target == OperatingSystem.LINUX:
        return ["linux", "gnu/linux"]
    elif target == OperatingSystem.BSD:
        return ["bsd", "freebsd", "openbsd", "netbsd"]
    return [str(target.value)]


def matches_current_os(os_identifier: str, target_os: Optional[OperatingSystem] = None) -> bool:
    """Check if given string identifier matches the target OS (defaults to current OS)."""
    clean = os_identifier.strip().lower()
    return clean in get_os_aliases(target_os)


def get_user_home() -> Path:
    """Return user's home directory across OSes natively."""
    return Path.home().resolve()


def get_user_documents() -> Path:
    """Return the user's Documents directory across OSes.
    On Windows: %USERPROFILE%/Documents
    On macOS: ~/Documents
    On Linux: XDG_DOCUMENTS_DIR or ~/Documents
    """
    home = get_user_home()
    if CURRENT_OS == OperatingSystem.WINDOWS:
        # Check registry or standard folder
        docs = home / "Documents"
        if docs.exists():
            return docs
    elif CURRENT_OS == OperatingSystem.LINUX:
        xdg_docs = os.environ.get("XDG_DOCUMENTS_DIR")
        if xdg_docs:
            return Path(xdg_docs).expanduser().resolve()
    return home / "Documents"


def get_config_home() -> Path:
    """Return default application configuration directory for current OS.
    POSIX: $XDG_CONFIG_HOME or ~/.config
    Windows: %APPDATA% (or ~/.config for cross-platform tools)
    macOS: ~/Library/Application Support or ~/.config
    """
    if CURRENT_OS == OperatingSystem.WINDOWS:
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata).resolve()
        return get_user_home() / "AppData" / "Roaming"
    
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser().resolve()
    return get_user_home() / ".config"


def resolve_native_path(path_expr: str) -> Path:
    """Fully resolve a path expression natively for the current OS.
    Handles ~, $ENV_VARS, %ENV_VARS%, and forward/backward slashes.
    """
    clean_expr = path_expr.strip()

    # Expand Windows %VAR% or POSIX $VAR
    expanded = os.path.expandvars(clean_expr)

    # Expand ~ and ~user
    expanded = os.path.expanduser(expanded)

    # Convert to Path object with native separators
    p = Path(expanded)
    return p
