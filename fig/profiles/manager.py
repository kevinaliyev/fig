"""Profile and Temporary Override ("Temp Mode") Engine.
Enables multi-profile switching and temporary dotfile application with instant reversibility.
"""

from __future__ import annotations

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig.config.state import FigState
from fig.sync.linker import remove_link_or_entry
from fig.sync.backup import BackupSession
from fig.config.template import Template, discover_template


class ProfileManager:
    def __init__(self, fig_state: Optional[FigState] = None):
        self.state = fig_state or FigState()

    def list_profiles(self) -> List[Dict[str, Any]]:
        """List registered profiles stored in ~/.fig/profiles/."""
        self.state.ensure_directories()
        cfg = self.state.load_config()
        active_prof = cfg.get("active", {}).get("profile_name", "default")

        profiles = []
        seen = set()
        # 1. Directory profiles: ~/.fig/profiles/<name>/fig.toml
        if self.state.profiles_dir.exists():
            for p_dir in self.state.profiles_dir.iterdir():
                if p_dir.is_dir() and (p_dir / "fig.toml").exists():
                    name = p_dir.name
                    seen.add(name)
                    profiles.append({
                        "name": name,
                        "path": str(p_dir / "fig.toml"),
                        "is_active": name == active_prof,
                    })

            # 2. File profiles: ~/.fig/profiles/<name>.toml
            for p in self.state.profiles_dir.glob("*.toml"):
                if p.stem not in seen:
                    profiles.append({
                        "name": p.stem,
                        "path": str(p),
                        "is_active": p.stem == active_prof,
                    })

        return sorted(profiles, key=lambda x: x["name"])

    def save_profile(self, name: str, template_path: Path, repo_root: Optional[Path] = None) -> Path:
        """Save a template as a named profile directory in ~/.fig/profiles/<name>/fig.toml."""
        self.state.ensure_directories()
        clean_name = name.strip() or "default"
        prof_dir = self.state.profiles_dir / clean_name
        prof_dir.mkdir(parents=True, exist_ok=True)
        target = prof_dir / "fig.toml"

        abs_tpl = template_path.resolve()
        # Live link if possible, fallback to copy
        try:
            if target.exists() or target.is_symlink():
                target.unlink(missing_ok=True)
            target.symlink_to(abs_tpl)
        except Exception:
            try:
                os.link(abs_tpl, target)
            except Exception:
                shutil.copy2(abs_tpl, target)

        cfg = self.state.load_config()
        resolved_repo = str(repo_root.resolve()) if repo_root else str(template_path.parent.resolve())
        cfg.setdefault("profiles", {})[clean_name] = {
            "template_path": str(abs_tpl),
            "profile_template": str(target.resolve()),
            "repo_root": resolved_repo,
        }
        self.state.save_config(cfg)
        return target

    def switch_profile(self, name: str) -> Path:
        """Switch active template to named profile."""
        self.state.ensure_directories()
        cfg = self.state.load_config()
        prof_info = cfg.get("profiles", {}).get(name, {})

        target = None
        if prof_info.get("template_path") and Path(prof_info["template_path"]).exists():
            target = Path(prof_info["template_path"])
        elif (self.state.profiles_dir / name / "fig.toml").exists():
            target = self.state.profiles_dir / name / "fig.toml"
        elif (self.state.profiles_dir / f"{name}.toml").exists():
            target = self.state.profiles_dir / f"{name}.toml"

        if not target:
            raise ValueError(f"Profile '{name}' does not exist in {self.state.profiles_dir}")

        repo_root_str = prof_info.get("repo_root", str(target.parent))
        repo_root = Path(repo_root_str)

        self.state.set_active_template_path(target, repo_root=repo_root, profile_name=name)
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

    def record_borrow(
        self,
        backup_id: str,
        prev_active_template: Optional[str],
        prev_profile: Optional[str] = None,
    ) -> None:
        self.state.ensure_directories()
        data = {
            "backup_id": backup_id,
            "prev_active_template": prev_active_template,
            "prev_profile": prev_profile,
        }
        self.session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear_borrow(self) -> None:
        if self.session_file.exists():
            self.session_file.unlink()
