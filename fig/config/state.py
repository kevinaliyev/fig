"""Fig Configuration and State Management.
Handles paths, state directories, active template pointers in ~/.fig,
and system-level redundancy vault paths in %ProgramData%/fig or /var/backups/fig.
"""

from __future__ import annotations

import os
import sys
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore


def get_fig_home() -> Path:
    """Return the user Fig state directory path.
    Priority: $FIG_HOME -> $XDG_CONFIG_HOME/fig -> ~/.fig
    Creates a junction/symlink at ~/.fig if XDG_CONFIG_HOME is used so that
    ~/.fig/logs/fig.log and ~/.fig/ active templates are universally accessible.
    """
    if "FIG_HOME" in os.environ:
        return Path(os.environ["FIG_HOME"]).expanduser().resolve()
    
    if "XDG_CONFIG_HOME" in os.environ:
        xdg_fig = (Path(os.environ["XDG_CONFIG_HOME"]) / "fig").expanduser().resolve()
        dot_fig = (Path.home() / ".fig").resolve()
        # Bridge ~/.fig -> ~/.config/fig if not already pointing there
        if not dot_fig.exists() and dot_fig != xdg_fig:
            try:
                xdg_fig.mkdir(parents=True, exist_ok=True)
                if sys.platform.startswith("win"):
                    import _winapi
                    _winapi.CreateJunction(str(xdg_fig), str(dot_fig))
                else:
                    dot_fig.symlink_to(xdg_fig, target_is_directory=True)
            except Exception:
                pass
        return xdg_fig
    
    return (Path.home() / ".fig").resolve()


def get_system_fig_root() -> Path:
    """Return the system-level redundancy directory path.
    Priority: $FIG_SYSTEM_ROOT -> %ProgramData%/fig (Windows) -> /var/backups/fig (POSIX)
    """
    if "FIG_SYSTEM_ROOT" in os.environ:
        return Path(os.environ["FIG_SYSTEM_ROOT"]).expanduser().resolve()

    if sys.platform.startswith("win"):
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")
        return Path(program_data) / "fig"
    else:
        return Path("/var/backups/fig")


class FigState:
    """Encapsulates persistent state stored inside ~/.fig and system redundancy vaults."""

    def __init__(self, fig_home: Optional[Path] = None, system_root: Optional[Path] = None):
        self.home = fig_home or get_fig_home()
        self.system_root = system_root or get_system_fig_root()

        # User state files & directories
        self.state_file = self.home / "state.toml"
        # Backward-compatibility alias for legacy scripts
        self.config_file = self.home / "config.toml"
        self.active_template_link = self.home / "active_template.toml"
        self.backups_dir = self.home / "backups"
        self.logs_dir = self.home / "logs"
        self.profiles_dir = self.home / "profiles"
        self.sessions_dir = self.home / "sessions"
        self.repos_dir = self.home / "repos"

        # System redundancy directories
        self.system_backups_dir = self.system_root / "backups"
        self.system_logs_dir = self.system_root / "logs"

    def ensure_directories(self, include_system: bool = False) -> None:
        """Create necessary user directories (and system directories if elevated)."""
        self.home.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.repos_dir.mkdir(parents=True, exist_ok=True)

        if include_system:
            try:
                self.system_root.mkdir(parents=True, exist_ok=True)
                self.system_backups_dir.mkdir(parents=True, exist_ok=True)
                self.system_logs_dir.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                pass

    def load_config(self) -> Dict[str, Any]:
        """Load Fig state registry from ~/.fig/state.toml (falling back to legacy config.toml)."""
        target_file = self.state_file if self.state_file.exists() else self.config_file
        if not target_file.exists():
            return {}
        try:
            with open(target_file, "rb") as f:
                return tomllib.load(f)
        except Exception:
            return {}

    def save_config(self, data: Dict[str, Any]) -> None:
        """Save state registry dictionary to ~/.fig/state.toml (and mirror to config.toml)."""
        self.ensure_directories()
        lines = []
        for key, val in data.items():
            if isinstance(val, dict):
                lines.append(f"[{key}]")
                for sub_k, sub_v in val.items():
                    lines.append(f"{sub_k} = {self._toml_value(sub_v)}")
                lines.append("")
            else:
                lines.append(f"{key} = {self._toml_value(val)}")
        
        content = "\n".join(lines).strip() + "\n"
        self.state_file.write_text(content, encoding="utf-8")
        # Keep config.toml synced as compatibility mirror
        try:
            self.config_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _toml_value(val: Any) -> str:
        if isinstance(val, bool):
            return "true" if val else "false"
        elif isinstance(val, (int, float)):
            return str(val)
        elif isinstance(val, list):
            items = ", ".join(FigState._toml_value(x) for x in val)
            return f"[{items}]"
        else:
            escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'

    def link_active_template(self, template_path: Path) -> None:
        """Create a live link at ~/.fig/active_template.toml pointing directly to template_path."""
        self.ensure_directories()
        abs_target = template_path.resolve()
        dest = self.active_template_link

        if dest.exists() or dest.is_symlink():
            try:
                if dest.is_dir():
                    shutil.rmtree(dest, ignore_errors=True)
                else:
                    dest.unlink(missing_ok=True)
            except Exception:
                pass

        # 1. Try symlink first (cross-platform standard)
        try:
            dest.symlink_to(abs_target)
            return
        except (OSError, PermissionError, NotImplementedError):
            pass

        # 2. Try hardlink (unprivileged on Windows NTFS for files on same volume)
        try:
            os.link(abs_target, dest)
            return
        except (OSError, PermissionError, NotImplementedError):
            pass

        # 3. Fallback to file copy if across volumes or filesystem doesn't support links
        try:
            shutil.copy2(abs_target, dest)
        except Exception:
            pass

    def get_active_template_path(self) -> Optional[Path]:
        """Return Path to currently active template file, or None if unset."""
        cfg = self.load_config()
        active = cfg.get("active", {}).get("template_path")
        if active:
            p = Path(active)
            if p.exists():
                return p
        if self.active_template_link.exists():
            try:
                resolved = self.active_template_link.resolve()
                if resolved.exists():
                    return resolved
            except Exception:
                pass
            return self.active_template_link
        return None

    def get_active_repo_root(self) -> Optional[Path]:
        """Return Path to repository root of active template, or None."""
        cfg = self.load_config()
        repo = cfg.get("active", {}).get("repo_root")
        if repo:
            p = Path(repo)
            if p.is_dir():
                return p
        active_tpl = self.get_active_template_path()
        if active_tpl and active_tpl.parent.is_dir():
            return active_tpl.parent
        return None

    def set_active_template_path(
        self,
        template_path: Path,
        repo_root: Optional[Path] = None,
        profile_name: Optional[str] = None,
    ) -> None:
        """Register the given template file as the active template."""
        self.ensure_directories()
        cfg = self.load_config()
        if "active" not in cfg:
            cfg["active"] = {}
        
        abs_tpl = template_path.resolve()
        cfg["active"]["template_path"] = str(abs_tpl)
        if repo_root:
            cfg["active"]["repo_root"] = str(repo_root.resolve())
        elif abs_tpl.parent.is_dir():
            cfg["active"]["repo_root"] = str(abs_tpl.parent)

        if profile_name:
            cfg["active"]["profile_name"] = profile_name

        self.save_config(cfg)
        self.link_active_template(abs_tpl)
