"""Fig Orchestrator Engine.
Coordinates template discovery, collision backups, linking, idempotency checks,
and state management for bootstrap and apply.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig.core.config import FigState
from fig.core.linker import deploy_link, LinkMode, LinkStatus, get_link_target
from fig.core.backup import BackupSession, list_all_backups
from fig.core.template import Template, discover_template, generate_default_template


@dataclass
class EngineResult:
    action: str
    template_name: str
    repo_root: Path
    created: List[Tuple[Path, Path]] = field(default_factory=list)
    already_linked: List[Tuple[Path, Path]] = field(default_factory=list)
    backed_up: List[Path] = field(default_factory=list)
    failed: List[Tuple[Path, Path, str]] = field(default_factory=list)
    backup_id: Optional[str] = None
    dry_run: bool = False

    @property
    def is_success(self) -> bool:
        return len(self.failed) == 0


class FigEngine:
    def __init__(self, fig_state: Optional[FigState] = None):
        self.state = fig_state or FigState()

    def bootstrap(
        self,
        repo_dir: Path,
        dry_run: bool = False,
    ) -> EngineResult:
        """Bootstrap dotfiles from a given directory."""
        repo_dir = repo_dir.resolve()
        if not repo_dir.is_dir():
            raise ValueError(f"Repository directory does not exist: {repo_dir}")

        tpl_path = discover_template(repo_dir)
        if not tpl_path:
            # Auto-generate default template
            tpl = generate_default_template(repo_dir)
            tpl_path = repo_dir / "fig.toml"
            if not dry_run:
                tpl.save(tpl_path)
        else:
            tpl = Template.load(tpl_path)

        result = self._execute_deployment(
            action="bootstrap",
            template=tpl,
            repo_root=repo_dir,
            dry_run=dry_run,
        )

        if not dry_run and result.is_success:
            self.state.set_active_template_path(tpl_path, repo_dir)
            # Also mirror active template to ~/.fig/active_template.toml
            if tpl_path.exists():
                shutil.copy2(tpl_path, self.state.active_template_link)

        return result

    def apply(self, dry_run: bool = False) -> EngineResult:
        """Apply the currently active template registered in ~/.fig."""
        active_path = self.state.get_active_template_path()
        if not active_path or not active_path.exists():
            raise RuntimeError(
                "No active template found. Run 'fig bootstrap <path>' in a dotfile repository first."
            )

        cfg = self.state.load_config()
        repo_root_str = cfg.get("active", {}).get("repo_root")
        if repo_root_str and Path(repo_root_str).is_dir():
            repo_root = Path(repo_root_str).resolve()
        else:
            repo_root = active_path.parent.resolve()

        tpl = Template.load(active_path)

        return self._execute_deployment(
            action="apply",
            template=tpl,
            repo_root=repo_root,
            dry_run=dry_run,
        )

    def _execute_deployment(
        self,
        action: str,
        template: Template,
        repo_root: Path,
        dry_run: bool = False,
    ) -> EngineResult:
        """Internal worker to plan, backup collisions, and deploy links."""
        plan = template.resolve_plan(repo_root)
        result = EngineResult(
            action=action,
            template_name=template.name,
            repo_root=repo_root,
            dry_run=dry_run,
        )

        mode_enum = LinkMode(template.link_mode) if template.link_mode in [m.value for m in LinkMode] else LinkMode.AUTO

        # Phase 1: Determine collisions & initialize backup session
        session: Optional[BackupSession] = None
        if not dry_run and template.backup_on_collision:
            self.state.ensure_directories()
            session = BackupSession.create(
                backups_root=self.state.backups_dir,
                reason=action,
                repo_root=repo_root,
            )
            result.backup_id = session.load_manifest().get("id")

        # Phase 2: Execute links
        for src, dest in plan:
            dest_raw = Path(os.path.expanduser(str(dest)))
            
            # Check collision
            has_collision = dest_raw.exists() or dest_raw.is_symlink()

            # If dest is already linked to src, no collision backup is needed
            already_synced = False
            try:
                if dest_raw.exists() and os.path.samefile(src, dest_raw):
                    already_synced = True
            except (OSError, ValueError):
                pass
            if not already_synced and dest_raw.is_symlink():
                tgt = get_link_target(dest_raw)
                if tgt and tgt.resolve() == src.resolve():
                    already_synced = True

            if not dry_run and session and has_collision and not already_synced:
                backup_entry = session.backup_collision(dest_raw)
                if backup_entry:
                    result.backed_up.append(dest_raw)

            # Deploy
            status, msg = deploy_link(src, dest, mode=mode_enum, dry_run=dry_run)

            if status == LinkStatus.CREATED:
                result.created.append((src, dest_raw))
                if not dry_run and session and not has_collision:
                    session.record_new_destination(dest_raw)
            elif status == LinkStatus.ALREADY_LINKED:
                result.already_linked.append((src, dest_raw))
            elif status == LinkStatus.WOULD_CREATE:
                result.created.append((src, dest_raw))
            else:
                result.failed.append((src, dest_raw, msg))

        return result

    def status(self) -> Dict[str, Any]:
        """Inspect active template status and filesystem state."""
        active_path = self.state.get_active_template_path()
        if not active_path or not active_path.exists():
            return {
                "active_template": None,
                "mappings": [],
                "error": "No active template registered. Run 'fig bootstrap' first.",
            }

        cfg = self.state.load_config()
        repo_root_str = cfg.get("active", {}).get("repo_root")
        repo_root = Path(repo_root_str).resolve() if repo_root_str else active_path.parent.resolve()

        tpl = Template.load(active_path)
        plan = tpl.resolve_plan(repo_root)

        entries = []
        for src, dest in plan:
            dest_raw = Path(os.path.expanduser(str(dest)))
            item_status = "missing"
            target_info = None

            try:
                if dest_raw.exists() and os.path.samefile(src, dest_raw):
                    item_status = "linked"
                    target_info = str(src)
            except (OSError, ValueError):
                pass

            if item_status != "linked":
                if dest_raw.is_symlink():
                    target = get_link_target(dest_raw)
                    target_info = str(target)
                    if target and target.resolve() == src.resolve():
                        item_status = "linked"
                    else:
                        item_status = "drifted"
                elif dest_raw.exists():
                    item_status = "collision"
                else:
                    item_status = "missing"

            entries.append({
                "source": str(src),
                "destination": str(dest_raw),
                "status": item_status,
                "current_target": target_info,
            })

        return {
            "active_template": str(active_path),
            "template_name": tpl.name,
            "repo_root": str(repo_root),
            "mappings": entries,
        }

    def restore_backup(self, backup_id: Optional[str] = None) -> Tuple[List[str], List[str]]:
        """Restore previous state from backup vault."""
        backups = list_all_backups(self.state.backups_dir)
        if not backups:
            raise RuntimeError("No backups found in vault.")

        target_backup = None
        if backup_id:
            for b in backups:
                if b["id"] == backup_id:
                    target_backup = b
                    break
            if not target_backup:
                raise ValueError(f"Backup with ID '{backup_id}' not found.")
        else:
            # Default to most recent
            target_backup = backups[0]

        session = BackupSession(Path(target_backup["path"]))
        return session.restore()
