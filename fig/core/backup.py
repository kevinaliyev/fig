"""Selective Collision Backup and Restore Engine.
Backs up only files/directories that are about to be overwritten, stores them
with a manifest, and allows full rollback/restoration.
"""

from __future__ import annotations

import os
import json
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from fig.core.linker import get_link_target, is_symlink_or_junction, remove_link_or_entry


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


class BackupManifestEntry:
    def __init__(
        self,
        dest_path: Path,
        is_symlink: bool,
        symlink_target: Optional[str] = None,
        is_dir: bool = False,
        backup_rel_path: Optional[str] = None,
        file_hash: Optional[str] = None,
    ):
        self.dest_path = dest_path
        self.is_symlink = is_symlink
        self.symlink_target = symlink_target
        self.is_dir = is_dir
        self.backup_rel_path = backup_rel_path
        self.file_hash = file_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dest_path": str(self.dest_path),
            "is_symlink": self.is_symlink,
            "symlink_target": self.symlink_target,
            "is_dir": self.is_dir,
            "backup_rel_path": self.backup_rel_path,
            "file_hash": self.file_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BackupManifestEntry:
        return cls(
            dest_path=Path(data["dest_path"]),
            is_symlink=data.get("is_symlink", False),
            symlink_target=data.get("symlink_target"),
            is_dir=data.get("is_dir", False),
            backup_rel_path=data.get("backup_rel_path"),
            file_hash=data.get("file_hash"),
        )


class BackupSession:
    """Represents a timestamped backup session directory."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.manifest_file = session_dir / "manifest.json"
        self.files_dir = session_dir / "files"

    @classmethod
    def create(
        cls,
        backups_root: Path,
        reason: str = "backup",
        repo_root: Optional[Path] = None,
    ) -> BackupSession:
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"{now_str}_{reason}"
        session_dir = backups_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        session = cls(session_dir)
        session.files_dir.mkdir(parents=True, exist_ok=True)
        
        # Init manifest
        manifest_data = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "reason": reason,
            "repo_root": str(repo_root) if repo_root else None,
            "overridden_entries": [],
            "newly_created_destinations": [],
        }
        session.save_manifest(manifest_data)
        return session

    def load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_file.exists():
            return {}
        try:
            return json.loads(self.manifest_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_manifest(self, data: Dict[str, Any]) -> None:
        self.manifest_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def backup_collision(self, dest: Path) -> Optional[BackupManifestEntry]:
        """If dest exists or is a symlink, back it up and record entry."""
        dest_expanded = Path(os.path.expanduser(str(dest))).resolve()
        dest_raw = Path(os.path.expanduser(str(dest)))

        # Check existence or broken symlink
        if not dest_raw.exists() and not is_symlink_or_junction(dest_raw):
            return None

        is_sym = is_symlink_or_junction(dest_raw)
        sym_target = None
        if is_sym:
            tgt = get_link_target(dest_raw)
            sym_target = str(tgt) if tgt else None

        is_dir = dest_raw.is_dir() and not is_sym

        # Safe relative path encoding for storage inside files/
        # Strip Windows drive letters (C:) or root slashes
        clean_name = str(dest_expanded)
        if ":" in clean_name:
            clean_name = clean_name.split(":", 1)[1]
        clean_name = clean_name.lstrip("\\/")

        backup_dest = self.files_dir / clean_name
        backup_dest.parent.mkdir(parents=True, exist_ok=True)

        file_hash = None
        rel_backup_path = str(backup_dest.relative_to(self.session_dir))

        if not is_sym:
            if is_dir:
                if backup_dest.exists():
                    shutil.rmtree(backup_dest)
                shutil.copytree(dest_raw, backup_dest)
            else:
                shutil.copy2(dest_raw, backup_dest)
                file_hash = compute_file_hash(dest_raw)

        entry = BackupManifestEntry(
            dest_path=dest_raw,
            is_symlink=is_sym,
            symlink_target=sym_target,
            is_dir=is_dir,
            backup_rel_path=rel_backup_path if not is_sym else None,
            file_hash=file_hash,
        )

        # Update manifest
        manifest = self.load_manifest()
        manifest.setdefault("overridden_entries", []).append(entry.to_dict())
        self.save_manifest(manifest)
        return entry

    def record_new_destination(self, dest: Path) -> None:
        """Record that a new destination was deployed that had no collision."""
        manifest = self.load_manifest()
        manifest.setdefault("newly_created_destinations", []).append(str(dest))
        self.save_manifest(manifest)

    def restore(self) -> Tuple[List[str], List[str]]:
        """Restore all original files from this backup session.
        Returns (restored_paths, removed_new_paths).
        """
        manifest = self.load_manifest()
        restored: List[str] = []
        removed_new: List[str] = []

        # 1. Remove newly created files that did not previously exist
        new_dests = manifest.get("newly_created_destinations", [])
        for p_str in new_dests:
            p = Path(os.path.expanduser(p_str))
            if p.exists() or is_symlink_or_junction(p):
                remove_link_or_entry(p)
                removed_new.append(str(p))

        # 2. Restore overridden entries
        overridden = manifest.get("overridden_entries", [])
        for entry_dict in overridden:
            entry = BackupManifestEntry.from_dict(entry_dict)
            dest = entry.dest_path

            # Remove current deployed file/link at dest
            remove_link_or_entry(dest)

            dest.parent.mkdir(parents=True, exist_ok=True)

            if entry.is_symlink:
                if entry.symlink_target:
                    os.symlink(entry.symlink_target, dest)
                    restored.append(f"{dest} -> {entry.symlink_target} (symlink)")
            elif entry.backup_rel_path:
                stored_file = self.session_dir / entry.backup_rel_path
                if stored_file.exists():
                    if entry.is_dir:
                        shutil.copytree(stored_file, dest)
                    else:
                        shutil.copy2(stored_file, dest)
                    restored.append(str(dest))

        return restored, removed_new


def list_all_backups(backups_root: Path) -> List[Dict[str, Any]]:
    """Return summary list of all backup sessions in reverse chronological order."""
    if not backups_root.exists():
        return []

    sessions = []
    for d in sorted(backups_root.iterdir(), reverse=True):
        if d.is_dir() and (d / "manifest.json").exists():
            bs = BackupSession(d)
            m = bs.load_manifest()
            sessions.append({
                "id": m.get("id", d.name),
                "timestamp": m.get("created_at"),
                "reason": m.get("reason"),
                "overridden_count": len(m.get("overridden_entries", [])),
                "path": str(d),
            })
    return sessions
