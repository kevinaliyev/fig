"""System Configuration Management Subsystem for Fig.
Handles elevated system configuration deployment, mandatory explicit pathspecs,
safety breaking-changes warnings with confirmation, elevation re-launching,
and system redundancy backup vaults (%ProgramData%/fig or /var/backups/fig).
"""

from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig.core.config import FigState, get_system_fig_root
from fig.core.platform import CURRENT_OS, OperatingSystem
from fig.core.elevation import is_elevated, display_breaking_changes_warning, request_elevation
from fig.core.logger import log_event
from fig.core.linker import deploy_link, LinkMode, LinkStatus, get_link_target
from fig.core.backup import BackupSession, list_all_backups
from fig.core.template import Template
from fig.core.engine import EngineResult


class SystemConfigManager:
    """Manages system-level configurations and safety enforcement."""

    def __init__(self, fig_state: Optional[FigState] = None):
        self.state = fig_state or FigState()

    def get_system_redundancy_dir(self) -> Path:
        """Return system-level redundancy backup directory."""
        return self.state.system_backups_dir

    def plan_system_deployment(
        self,
        template: Template,
        repo_root: Path,
    ) -> List[Tuple[Path, Path]]:
        """Validate and resolve system mappings with mandatory pathspec check."""
        if not template.has_system_mappings:
            raise ValueError(
                f"Template '{template.name}' contains no system-level specifications. "
                "System configs must be explicitly declared under [system.mappings] or [os.<name>.system.mappings]."
            )
        
        return template.resolve_plan(repo_root, is_system=True)

    def apply_system(
        self,
        template: Template,
        repo_root: Path,
        force_yes: bool = False,
        dry_run: bool = False,
    ) -> EngineResult:
        """Apply system-level configurations with full safety workflow."""
        repo_root = repo_root.resolve()
        plan = self.plan_system_deployment(template, repo_root)

        dest_paths_str = [str(dest) for _, dest in plan]

        # PHASE 1: Prominent Breaking-Changes Warning
        confirmed = display_breaking_changes_warning(
            dest_paths_str,
            force_yes=force_yes,
            interactive=True,
        )
        if not confirmed:
            res = EngineResult(
                action="system_apply",
                template_name=template.name,
                repo_root=repo_root,
                dry_run=dry_run,
            )
            res.failed.append((repo_root, repo_root, "Cancelled by user at breaking changes warning prompt."))
            return res

        # PHASE 2: Elevation Check & Re-launch (ONLY after warning confirmed)
        if not dry_run and not is_elevated():
            print("[ELEVATION REQUIRED] Modifying system files requires administrative/root privileges.")
            ret = request_elevation(interactive=not force_yes)
            res = EngineResult(
                action="system_apply",
                template_name=template.name,
                repo_root=repo_root,
                dry_run=dry_run,
            )
            if ret != 0:
                res.failed.append((repo_root, repo_root, f"Elevation process exited with status code {ret}"))
            return res

        # PHASE 3: System Redundancy Backup Vault Creation
        user_session: Optional[BackupSession] = None
        sys_session: Optional[BackupSession] = None

        if not dry_run and template.backup_on_collision:
            self.state.ensure_directories(include_system=True)
            # 1. User vault session
            user_session = BackupSession.create(
                backups_root=self.state.backups_dir,
                reason="system_apply",
                repo_root=repo_root,
            )
            # 2. Redundancy system vault session (disaster recovery)
            try:
                sys_vault_root = self.get_system_redundancy_dir()
                sys_vault_root.mkdir(parents=True, exist_ok=True)
                sys_session = BackupSession.create(
                    backups_root=sys_vault_root,
                    reason="system_redundancy_apply",
                    repo_root=repo_root,
                )
            except Exception as e:
                log_event(f"Notice: Could not write to system redundancy vault: {e}", is_system=True, level="WARN")

        result = EngineResult(
            action="system_apply",
            template_name=template.name,
            repo_root=repo_root,
            backup_id=user_session.load_manifest().get("id") if user_session else None,
            dry_run=dry_run,
        )

        mode_enum = LinkMode(template.link_mode) if template.link_mode in [m.value for m in LinkMode] else LinkMode.AUTO

        # PHASE 4: Execution
        log_event(f"Applying system template '{template.name}' ({len(plan)} targets)", is_system=True)

        for src, dest in plan:
            dest_raw = Path(os.path.expanduser(str(dest)))
            has_collision = dest_raw.exists() or dest_raw.is_symlink()

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

            # Backup in both user vault and system redundancy vault
            if not dry_run and has_collision and not already_synced:
                if user_session:
                    user_session.backup_collision(dest_raw)
                if sys_session:
                    sys_session.backup_collision(dest_raw)
                result.backed_up.append(dest_raw)

            # Deploy link
            status, msg = deploy_link(src, dest, mode=mode_enum, dry_run=dry_run)

            if status == LinkStatus.CREATED:
                result.created.append((src, dest_raw))
                if not dry_run and not has_collision:
                    if user_session:
                        user_session.record_new_destination(dest_raw)
                    if sys_session:
                        sys_session.record_new_destination(dest_raw)
            elif status == LinkStatus.ALREADY_LINKED:
                result.already_linked.append((src, dest_raw))
            elif status == LinkStatus.WOULD_CREATE:
                result.created.append((src, dest_raw))
            else:
                result.failed.append((src, dest_raw, msg))
                log_event(f"System link failure for {dest_raw}: {msg}", is_system=True, level="ERROR")

        return result

    def restore_system(
        self,
        backup_id: Optional[str] = None,
        force_yes: bool = False,
    ) -> Tuple[List[str], List[str]]:
        """Restore system configurations from redundancy vault or user vault."""
        # Find backup from system redundancy vault first, fallback to user vault
        backups = list_all_backups(self.get_system_redundancy_dir())
        if not backups:
            backups = list_all_backups(self.state.backups_dir)

        if not backups:
            raise RuntimeError("No system backups found in redundancy vault or user vault.")

        target_backup = None
        if backup_id:
            for b in backups:
                if b["id"] == backup_id:
                    target_backup = b
                    break
            if not target_backup:
                raise ValueError(f"System backup session '{backup_id}' not found.")
        else:
            target_backup = backups[0]

        manifest_path = Path(target_backup["path"]) / "manifest.json"
        session = BackupSession(Path(target_backup["path"]))
        manifest = session.load_manifest()

        overridden = [e["dest_path"] for e in manifest.get("overridden_entries", [])]
        confirmed = display_breaking_changes_warning(
            overridden,
            force_yes=force_yes,
            interactive=True,
        )
        if not confirmed:
            raise RuntimeError("System rollback cancelled by user.")

        if not is_elevated():
            print("[ELEVATION REQUIRED] Restoring system files requires administrative/root privileges.")
            ret = request_elevation(["undo", "--system"], interactive=not force_yes)
            if ret != 0:
                raise PermissionError("Elevation failed for system restore.")
            return [], []

        log_event(f"Restoring system backup session '{target_backup['id']}'", is_system=True)
        return session.restore()
