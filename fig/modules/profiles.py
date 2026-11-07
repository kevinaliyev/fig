"""Profile and Temporary Override ("Temp Mode") Engine.
Enables multi-profile switching and temporary dotfile application with instant reversibility.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig.core.config import FigState
from fig.core.linker import remove_link_or_entry
from fig.core.backup import BackupSession
from fig.core.template import Template, discover_template


class ProfileManager:
    def __init__(self, fig_state: Optional[FigState] = None):
        self.state = fig_state or FigState()

    def list_profiles(self) -> List[Dict[str, Any]]:
        """List registered profiles stored in ~/.fig/profiles/."""
        self.state.ensure_directories()
        cfg = self.state.load_config()
        active_prof = cfg.get("active", {}).get("profile_name", "default")

        profiles = []
        for p in self.state.profiles_dir.glob("*.toml"):
            profiles.append({
                "name": p.stem,
                "path": str(p),
                "is_active": p.stem == active_prof,
            })
        return profiles

    def save_profile(self, name: str, template_path: Path, repo_root: Optional[Path] = None) -> Path:
        """Save a template as a named profile."""
        self.state.ensure_directories()
        target = self.state.profiles_dir / f"{name}.toml"
        shutil.copy2(template_path, target)

        cfg = self.state.load_config()
        cfg.setdefault("profiles", {})[name] = {
            "template_path": str(target.resolve()),
            "repo_root": str(repo_root.resolve()) if repo_root else str(template_path.parent.resolve()),
        }
        self.state.save_config(cfg)
        return target

    def switch_profile(self, name: str) -> Path:
        """Switch active template to named profile."""
        self.state.ensure_directories()
        target = self.state.profiles_dir / f"{name}.toml"
        if not target.exists():
            raise ValueError(f"Profile '{name}' does not exist in {self.state.profiles_dir}")

        cfg = self.state.load_config()
        repo_root = cfg.get("profiles", {}).get(name, {}).get("repo_root", str(target.parent))

        cfg.setdefault("active", {})["profile_name"] = name
        cfg["active"]["template_path"] = str(target.resolve())
        cfg["active"]["repo_root"] = str(repo_root)
        self.state.save_config(cfg)

        shutil.copy2(target, self.state.active_template_link)
        return target


class BorrowSessionManager:
    """Manages temporary workstation takeover and instant revert."""

    def __init__(self, fig_state: Optional[FigState] = None):
        self.state = fig_state or FigState()
        self.session_file = self.state.sessions_dir / "active_borrow.json"

    def has_active_borrow(self) -> bool:
        return self.session_file.exists()

    def get_borrow_info(self) -> Optional[Dict[str, Any]]:
        if not self.has_active_borrow():
            return None
        try:
            return json.loads(self.session_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def record_borrow(self, backup_id: str, prev_active_template: Optional[str]) -> None:
        self.state.ensure_directories()
        data = {
            "backup_id": backup_id,
            "prev_active_template": prev_active_template,
        }
        self.session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear_borrow(self) -> None:
        if self.session_file.exists():
            self.session_file.unlink()
