"""Fig Configuration and State Management.
Handles paths, state directories, and active template pointers in ~/.fig.
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    # Fallback if python < 3.11 (though 3.11+ is target)
    import tomli as tomllib  # type: ignore


def get_fig_home() -> Path:
    """Return the Fig state directory path.
    Priority: $FIG_HOME -> $XDG_CONFIG_HOME/fig -> ~/.fig
    """
    if "FIG_HOME" in os.environ:
        return Path(os.environ["FIG_HOME"]).expanduser().resolve()
    
    if "XDG_CONFIG_HOME" in os.environ:
        return (Path(os.environ["XDG_CONFIG_HOME"]) / "fig").expanduser().resolve()
    
    return (Path.home() / ".fig").resolve()


class FigState:
    """Encapsulates persistent state stored inside ~/.fig."""

    def __init__(self, fig_home: Optional[Path] = None):
        self.home = fig_home or get_fig_home()
        self.config_file = self.home / "config.toml"
        self.active_template_link = self.home / "active_template.toml"
        self.backups_dir = self.home / "backups"
        self.profiles_dir = self.home / "profiles"
        self.sessions_dir = self.home / "sessions"

    def ensure_directories(self) -> None:
        """Create necessary directories if they do not exist."""
        self.home.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """Load global Fig config from ~/.fig/config.toml."""
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "rb") as f:
                return tomllib.load(f)
        except Exception:
            return {}

    def save_config(self, data: Dict[str, Any]) -> None:
        """Save configuration dictionary to ~/.fig/config.toml."""
        self.ensure_directories()
        # Clean manual TOML serialization for standard library compatibility
        lines = []
        for key, val in data.items():
            if isinstance(val, dict):
                lines.append(f"[{key}]")
                for sub_k, sub_v in val.items():
                    lines.append(f"{sub_k} = {self._toml_value(sub_v)}")
                lines.append("")
            else:
                lines.append(f"{key} = {self._toml_value(val)}")
        
        self.config_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

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

    def get_active_template_path(self) -> Optional[Path]:
        """Return Path to currently active template file, or None if unset."""
        cfg = self.load_config()
        active = cfg.get("active", {}).get("template_path")
        if active:
            p = Path(active)
            if p.exists():
                return p
        if self.active_template_link.exists():
            return self.active_template_link.resolve()
        return None

    def set_active_template_path(self, template_path: Path, repo_root: Optional[Path] = None) -> None:
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

        self.save_config(cfg)
